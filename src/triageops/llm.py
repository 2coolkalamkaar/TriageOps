"""
LLM wrapper with structured JSON output, dual-provider support (Gemini API & Vertex AI),
and high-fidelity offline fallback for local development and UI demos.

Priority order:
1. TRIAGEOPS_FORCE_OFFLINE=1 -> Offline heuristic engine (demo mode)
2. GEMINI_API_KEY environment variable -> Google GenAI SDK (direct API key)
3. VERTEX_PROJECT / GOOGLE_CLOUD_PROJECT -> Google Cloud Vertex AI SDK
4. Nothing configured -> Offline heuristic engine (demo mode, logged loudly)

The offline engine is a keyword heuristic, not a diagnosis. Whenever it serves
a response, the engine is recorded (see track_engines) so the pipeline can
mark the report as degraded. If a configured LLM call fails, we raise
LLMUnavailableError instead of silently substituting canned output — unless
TRIAGEOPS_ALLOW_OFFLINE_FALLBACK=1 is set explicitly.
"""

import json
import logging
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class LLMUnavailableError(RuntimeError):
    """The configured LLM provider failed and offline fallback is disabled."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_TRUTHY = ("1", "true", "yes")

_PROJECT = (
    os.environ.get("VERTEX_PROJECT")
    or os.environ.get("GOOGLE_CLOUD_PROJECT")
    or ""
)
_LOCATION = (
    os.environ.get("VERTEX_LOCATION")
    or os.environ.get("GOOGLE_CLOUD_LOCATION")
    or "global"
)
_MODEL_NAME = (
    os.environ.get("VERTEX_MODEL")
    or os.environ.get("TRIAGEOPS_MODEL")
    or "gemini-3.8-flash"
)

_genai_client = None
_vertex_client = None

T = TypeVar("T", bound=BaseModel)

# Engines that served LLM calls in the current pipeline run (see track_engines)
_engines_used: ContextVar[list[str] | None] = ContextVar("triageops_engines_used", default=None)


@contextmanager
def track_engines() -> Iterator[list[str]]:
    """Collect the engine name of every model call made inside this block."""
    used: list[str] = []
    token = _engines_used.set(used)
    try:
        yield used
    finally:
        _engines_used.reset(token)


def _record_engine(engine: str) -> None:
    used = _engines_used.get()
    if used is not None:
        used.append(engine)


def _offline_fallback_allowed() -> bool:
    return os.environ.get("TRIAGEOPS_ALLOW_OFFLINE_FALLBACK", "").lower() in _TRUTHY


def _get_provider() -> str:
    """Determine available LLM provider."""
    if os.environ.get("TRIAGEOPS_FORCE_OFFLINE", "").lower() in _TRUTHY:
        return "offline"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini_api"
    if os.environ.get("VERTEX_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT"):
        return "vertex_ai"
    return "offline"


def get_provider() -> str:
    """Public accessor for the configured provider (used by /health)."""
    return _get_provider()


def _call_gemini_api(system_prompt: str, user_message: str) -> str:
    global _genai_client
    from google import genai
    from google.genai import types

    if _genai_client is None:
        _genai_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    start = time.monotonic()
    response = _genai_client.models.generate_content(
        model=_MODEL_NAME,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.1,
            max_output_tokens=4096,
        ),
    )
    latency = int((time.monotonic() - start) * 1000)
    logger.info("Gemini API call completed in %d ms", latency)
    return response.text or "{}"


def _call_vertex_ai(system_prompt: str, user_message: str) -> str:
    global _vertex_client
    from google import genai
    from google.genai import types

    if _vertex_client is None:
        _vertex_client = genai.Client(
            vertexai=True,
            project=_PROJECT or os.environ.get("VERTEX_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location=_LOCATION,
            http_options=types.HttpOptions(timeout=60000),
        )

    start = time.monotonic()
    response = _vertex_client.models.generate_content(
        model=_MODEL_NAME,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            temperature=0.1,
            max_output_tokens=8192,
        ),
    )
    latency = int((time.monotonic() - start) * 1000)
    logger.info("Vertex AI (%s) call completed in %d ms", _MODEL_NAME, latency)
    return response.text or "{}"


def _offline_classification(user_message: str) -> str:
    lower = user_message.lower()

    # Out of scope
    if any(k in lower for k in ["poem", "recipe", "weather", "song", "story", "joke", "fantasy"]):
        return json.dumps({
            "type": "Unknown",
            "severity": "P4",
            "in_scope": False,
            "key_error_lines": [],
            "reason": "Request is not related to server, Docker, or Kubernetes infrastructure triage."
        })

    # Vague input
    if len(lower.strip()) < 35 and any(phrase in lower for phrase in ["not working", "help", "broken", "fails"]):
        return json.dumps({
            "type": "Unknown",
            "severity": "P4",
            "in_scope": True,
            "key_error_lines": [],
            "reason": "Input is vague with no specific logs, exit codes, or diagnostic commands."
        })

    # Kubernetes signals
    k8s_keywords = ["kubectl", "crashloopbackoff", "imagepullbackoff", "pod", "namespace", "k8s", "kubernetes", "kubelet", "daemonset", "statefulset"]
    if any(k in lower for k in k8s_keywords):
        lines = [line.strip() for line in user_message.splitlines() if any(sig in line.lower() for sig in ["crashloop", "imagepull", "exit code", "error", "fatal", "failed", "oomkilled", "status:"])]
        return json.dumps({
            "type": "Kubernetes",
            "severity": "P2",
            "in_scope": True,
            "key_error_lines": lines[:3],
            "reason": "Kubernetes pod workload termination or scheduling issue identified."
        })

    # Docker signals
    docker_keywords = ["docker", "oomkilled", "exitcode: 137", "exit code 137", "container", "dockerfile", "docker-compose"]
    if any(k in lower for k in docker_keywords):
        lines = [line.strip() for line in user_message.splitlines() if any(sig in line.lower() for sig in ["oom", "137", "killed", "error", "failed", "exit"])]
        return json.dumps({
            "type": "Docker",
            "severity": "P2",
            "in_scope": True,
            "key_error_lines": lines[:3],
            "reason": "Docker container lifecycle or resource constraint failure identified."
        })

    # Server / Linux signals
    server_keywords = ["df -h", "enospc", "systemctl", "journalctl", "disk full", "filesystem", "no space left", "nginx", "apache", "sshd"]
    if any(k in lower for k in server_keywords):
        lines = [line.strip() for line in user_message.splitlines() if any(sig in line.lower() for sig in ["100%", "enospc", "failed", "error", "active: failed"])]
        return json.dumps({
            "type": "Server",
            "severity": "P2",
            "in_scope": True,
            "key_error_lines": lines[:3],
            "reason": "Linux server filesystem exhaustion or system service error identified."
        })

    return json.dumps({
        "type": "Unknown",
        "severity": "P3",
        "in_scope": True,
        "key_error_lines": [],
        "reason": "General infrastructure issue detected, but specific system type is ambiguous."
    })


def _offline_analysis(user_message: str) -> str:
    # Extract only the actual issue text, ignoring runbook excerpts
    issue_text = user_message
    if "Full Issue Text:\n---" in user_message:
        parts = user_message.split("Full Issue Text:\n---", 1)[1]
        if "\n---" in parts:
            issue_text = parts.split("\n---", 1)[0]

    lower = issue_text.lower()

    # Vague input check
    if len(lower.strip()) < 60 and any(phrase in lower for phrase in ["not working", "help", "broken", "fails"]):
        return json.dumps({
            "summary": "Vague incident report with insufficient diagnostic details to formulate a definitive diagnosis.",
            "root_cause": "Unknown: no error logs, exit codes, or diagnostic command outputs were provided.",
            "evidence": [],
            "other_causes": ["Application unhandled exception", "Network connectivity loss", "Service configuration error"],
            "fix_steps": [
                {
                    "step": "Collect pod or container status",
                    "command": "kubectl get pods -A # or docker ps -a",
                    "why": "Determine which component is in an unhealthy state",
                    "risk": "low"
                }
            ],
            "verification": ["Inspect health check endpoints once error logs are gathered."],
            "prevention": [
                "Establish centralized log collection (Fluentbit / Loki / CloudWatch).",
                "Implement structured alerting on service error rates."
            ],
            "confidence": {
                "level": "Low",
                "reason": "No concrete error logs, exit codes, or diagnostic outputs were supplied.",
                "would_raise": ["Provide pod logs, describe output, or recent error messages."]
            },
            "clarifying_questions": [
                "Which specific service or container is reporting failure?",
                "What are the recent logs or exit codes for the affected component?",
                "Was there a recent deployment or configuration update?"
            ]
        })

    # Docker OOMKilled
    if "oomkilled" in lower or "137" in lower or "out of memory" in lower:
        return json.dumps({
            "summary": "Docker container terminated due to memory exhaustion (OOMKilled with exit code 137).",
            "root_cause": "Container memory consumption likely exceeded its configured limit, causing the kernel OOM killer to terminate the process (exit code 137).",
            "evidence": [],
            "other_causes": ["Application memory leak", "Sudden spike in concurrent traffic"],
            "fix_steps": [
                {
                    "step": "Inspect container memory limits",
                    "command": "docker inspect <container> --format '{{.HostConfig.Memory}}'",
                    "why": "Confirm configured memory limit in bytes",
                    "risk": "low"
                },
                {
                    "step": "Update container memory allocation",
                    "command": "docker update --memory <new-limit> --memory-swap <new-limit> <container>",
                    "why": "Provides immediate memory headroom to prevent OOM termination",
                    "risk": "medium"
                },
                {
                    "step": "Verify active container memory consumption",
                    "command": "docker stats <container> --no-stream",
                    "why": "Monitor memory utilization under regular operation",
                    "risk": "low"
                }
            ],
            "verification": ["docker ps --filter name=<container> && docker stats <container> --no-stream"],
            "prevention": [
                "Profile application memory utilization to identify memory leaks.",
                "Establish container memory alerts at 80% capacity.",
                "Calibrate memory limits according to peak production traffic."
            ],
            "confidence": {
                "level": "High",
                "reason": "Direct OOMKilled flag and exit code 137 in diagnostic inspection unequivocally identify memory exhaustion.",
                "would_raise": ["Application heap dump or memory profiling trace."]
            },
            "clarifying_questions": []
        })

    # Disk full / ENOSPC
    if "100%" in lower or "enospc" in lower or "no space left" in lower:
        return json.dumps({
            "summary": "A filesystem appears to be at full capacity, resulting in 'No space left on device' write failures.",
            "root_cause": "Filesystem space is exhausted (No space left on device); the largest consumer has not been identified yet.",
            "evidence": [],
            "other_causes": ["Deleted files still held open by running processes", "Rapidly expanding core dumps"],
            "fix_steps": [
                {
                    "step": "Identify largest directories in /var/log",
                    "command": "du -ahx /var/log 2>/dev/null | sort -rh | head -n 20",
                    "why": "Find the specific log files consuming storage",
                    "risk": "low"
                },
                {
                    "step": "Force-rotate the oversized log via logrotate",
                    "command": "logrotate -f /etc/logrotate.d/<app>",
                    "why": "Reclaims space while keeping a compressed copy of the log for investigation",
                    "risk": "medium"
                },
                {
                    "step": "Vacuum old systemd journal logs",
                    "command": "journalctl --vacuum-time=3d",
                    "why": "Safely reclaims disk space without disrupting active logging",
                    "risk": "low"
                }
            ],
            "verification": ["df -h /"],
            "prevention": [
                "Configure logrotate with strict maxsize and retention constraints.",
                "Mount /var and /tmp on isolated storage partitions.",
                "Set disk space threshold alerts at 85% utilization."
            ],
            "confidence": {
                "level": "High",
                "reason": "df -h output explicitly reports 100% usage and 0 available blocks on the root mount.",
                "would_raise": ["Output of du -sh /* to pinpoint the exact directory path."]
            },
            "clarifying_questions": []
        })

    # Kubernetes CrashLoopBackOff (Missing env var or general)
    if "crashloopbackoff" in lower or "kubectl" in lower or "pod" in lower:
        missing_var_match = re.search(r'variable\s+([A-Za-z0-9_]+)\s+is not set', user_message, re.IGNORECASE)
        missing_var = missing_var_match.group(1) if missing_var_match else "<ENV_VAR>"
        pod_name = "<deployment>"
        ns = "staging" if "staging" in user_message else "<namespace>"
        return json.dumps({
            "summary": f"Kubernetes pod in namespace {ns} is trapped in CrashLoopBackOff because mandatory environment variable {missing_var} is missing.",
            "root_cause": f"Application initialization in container failed because required environment variable {missing_var} is not configured in the pod deployment specification.",
            "evidence": [
                "Reason: CrashLoopBackOff",
                "Exit Code: 1",
                f"Required environment variable {missing_var} is not set"
            ],
            "other_causes": ["Secret or ConfigMap reference mismatch", "Upstream database connection failure"],
            "fix_steps": [
                {
                    "step": "Inspect deployment environment declarations",
                    "command": f"kubectl get deployment {pod_name} -n {ns} -o yaml",
                    "why": f"Verify whether {missing_var} is defined in env or envFrom",
                    "risk": "low"
                },
                {
                    "step": f"Configure missing environment variable {missing_var}",
                    "command": f"kubectl set env deployment/{pod_name} -n {ns} {missing_var}=<value-from-secret>",
                    "why": "Provides the required configuration value to the container workload",
                    "risk": "medium"
                },
                {
                    "step": "Monitor rollout progression",
                    "command": f"kubectl rollout status deployment/{pod_name} -n {ns}",
                    "why": "Verifies that newly scheduled pods start cleanly without crashing",
                    "risk": "low"
                }
            ],
            "verification": [f"kubectl get pods -n {ns} -w"],
            "prevention": [
                "Enforce Helm or Kustomize schema validation on all deployment manifests.",
                "Implement pod startup and readiness probes.",
                "Validate environment variable configuration in CI/CD before deployment."
            ],
            "confidence": {
                "level": "High",
                "reason": f"Explicit fatal log line cites missing {missing_var} accompanied by container exit code 1.",
                "would_raise": ["Complete Kubernetes deployment YAML manifest."]
            },
            "clarifying_questions": []
        })

    # Generic infrastructure fallback
    return json.dumps({
        "summary": "Infrastructure service reported an error during routine operation.",
        "root_cause": "Service disruption indicated by logged diagnostic messages.",
        "evidence": [user_message.splitlines()[0] if user_message.splitlines() else "Service error logged"],
        "other_causes": ["Configuration error", "Dependency unavailable"],
        "fix_steps": [
            {
                "step": "Inspect recent service logs",
                "command": "journalctl -xe --no-pager | tail -n 50",
                "why": "Examine detailed error stack trace",
                "risk": "low"
            }
        ],
        "verification": ["Check service health metrics"],
        "prevention": ["Instrument proactive monitoring", "Configure automated health checks"],
        "confidence": {
            "level": "Medium",
            "reason": "Basic error symptoms identified but additional context is recommended.",
            "would_raise": ["Full component logs and system state."]
        },
        "clarifying_questions": ["What is the target host or container name?", "What triggered the error?"]
    })


def _call_model(system_prompt: str, user_message: str) -> str:
    provider = _get_provider()

    if provider == "offline":
        return _offline_call(system_prompt, user_message)

    call = _call_gemini_api if provider == "gemini_api" else _call_vertex_ai
    try:
        raw = call(system_prompt, user_message)
    except Exception as exc:
        if not _offline_fallback_allowed():
            logger.error("%s call failed: %s", provider, exc)
            raise LLMUnavailableError(f"LLM provider '{provider}' is unavailable") from exc
        logger.warning("%s call failed (%s); falling back to offline engine (degraded)", provider, exc)
        return _offline_call(system_prompt, user_message)

    _record_engine(provider)
    return raw


def _offline_call(system_prompt: str, user_message: str) -> str:
    """Heuristic offline triage engine matching schemas."""
    _record_engine("offline")
    if "Classification" in system_prompt or "key_error_lines" in system_prompt:
        return _offline_classification(user_message)
    return _offline_analysis(user_message)


# ---------------------------------------------------------------------------
# JSON-validated completion
# ---------------------------------------------------------------------------

def complete_json(
    system_prompt: str,
    user_message: str,
    schema: type[T],
    retries: int = 1,
) -> T:
    """
    Call the model and validate the response against a Pydantic schema.
    If the response fails validation, retry once with the error injected.
    """
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    enriched_system = (
        f"{system_prompt}\n\n"
        f"CRITICAL: Return ONLY valid JSON that matches this exact schema. "
        f"No markdown, no prose, no code fences — raw JSON only.\n\n"
        f"Required JSON schema:\n{schema_json}"
    )

    last_error: Exception | None = None
    current_user = user_message

    for attempt in range(retries + 1):
        try:
            raw = _call_model(enriched_system, current_user)
            cleaned = raw.strip()
            for prefix in ["```json", "```JSON", "```"]:
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            return schema.model_validate_json(cleaned)

        except LLMUnavailableError:
            raise
        except (ValidationError, json.JSONDecodeError) as exc:
            last_error = exc
            logger.warning(
                "LLM returned invalid JSON (attempt %d/%d): %s",
                attempt + 1,
                retries + 1,
                str(exc)[:200],
            )
            if attempt < retries:
                current_user = (
                    f"{user_message}\n\n"
                    f"[SYSTEM NOTE] Your previous response failed validation with this error:\n"
                    f"{exc}\n"
                    f"Please return corrected JSON that exactly matches the required schema."
                )

    # All retries failed. Only substitute the offline heuristic when explicitly allowed.
    if _offline_fallback_allowed():
        logger.warning("Falling back to offline engine after invalid model output (degraded)")
        try:
            return schema.model_validate_json(_offline_call(system_prompt, user_message))
        except ValidationError:
            pass
    raise ValueError(
        f"Model did not return valid JSON after {retries + 1} attempt(s). "
        f"Last error: {last_error}"
    )
