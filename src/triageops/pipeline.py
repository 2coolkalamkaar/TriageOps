"""
TriageOps pipeline — orchestrates all 7 steps.

Step 1: Safety pre-scan       (code: redact secrets)
Step 2: Classifier             (LLM: type, severity, in_scope, key lines)
Step 3: Scope gate             (code: decline if not in scope)
Step 4: Runbook retrieval      (code: BM25 search)
Step 5: Analyst                (LLM: root cause, fix steps, confidence)
Step 6: Command review         (code: flag risky commands, override risk labels)
Step 7: Report assembly        (code: build Report model)

Key design principle: Code wins over the model.
  - Secrets are redacted before any LLM call.
  - Risky command detection by regex overrides the model's risk labels.
  - Scope gating is a deterministic code check.
"""

import logging
import os
import re
import time
from pathlib import Path

from .llm import complete_json, track_engines
from .prompts import (
    ANALYST_SYSTEM,
    CLASSIFIER_SYSTEM,
    build_analyst_user,
    build_classifier_user,
)
from .retrieval import Runbooks
from .safety import redact_secrets, review_commands
from .schemas import Analysis, Classification, Report

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Runbooks singleton — loaded once at module level
# ---------------------------------------------------------------------------

def _get_runbooks_dir() -> Path:
    """Resolve runbooks directory: env var > package-relative default."""
    env_dir = os.environ.get("TRIAGEOPS_RUNBOOKS_DIR")
    if env_dir:
        return Path(env_dir)
    # Default: look for runbooks/ relative to the project root
    # (two levels up from src/triageops/)
    module_dir = Path(__file__).parent
    candidates = [
        module_dir.parent.parent / "runbooks",   # src/triageops/../../runbooks
        Path("runbooks"),                          # CWD/runbooks
    ]
    for c in candidates:
        if c.exists():
            return c
    return Path("runbooks")  # fallback even if it doesn't exist yet


_runbooks = Runbooks(_get_runbooks_dir())


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def run_triage(raw_input: str) -> Report:
    """
    Run the full 7-step TriageOps pipeline on raw input text.

    Args:
        raw_input: Raw log, error message, command output, or problem description.

    Returns:
        A fully populated Report instance, stamped with the engine that produced it.

    Raises:
        LLMUnavailableError: the configured LLM failed and offline fallback is disabled.
    """
    with track_engines() as engines:
        report = _run_pipeline(raw_input)

    if "offline" in engines:
        report.engine = "offline"
        report.degraded = True
        _mark_degraded(report)
    elif engines:
        report.engine = engines[-1]
    return report


def _mark_degraded(report: Report) -> None:
    """
    The offline engine is a keyword heuristic. Never let it present itself as a
    confident diagnosis: cap confidence at Low and only show evidence that was
    copied verbatim from the input.
    """
    analysis = report.analysis
    if analysis is None:
        return
    analysis.evidence = list(report.classification.key_error_lines)
    analysis.confidence.level = "Low"
    analysis.confidence.reason = (
        "DEGRADED MODE: produced by the offline keyword heuristic, not the LLM. "
        "Treat this as a generic checklist and verify every step against your system."
    )
    analysis.summary = f"[DEGRADED — offline heuristic, not an LLM diagnosis] {analysis.summary}"


def _run_pipeline(raw_input: str) -> Report:
    pipeline_start = time.monotonic()

    # ------------------------------------------------------------------
    # Step 1: Safety pre-scan — redact secrets BEFORE any external call
    # ------------------------------------------------------------------
    logger.info("Step 1: Safety pre-scan")
    clean_input, secrets_found = redact_secrets(raw_input)

    if secrets_found:
        logger.warning("Secrets detected and redacted: %s", secrets_found)

    # Handle empty input
    if not clean_input.strip():
        logger.info("Empty input received — declining")
        from .schemas import Classification as Cls
        empty_cls = Cls(
            type="Unknown",
            severity="P4",
            in_scope=False,
            key_error_lines=[],
            reason="Input was empty or contained only whitespace.",
        )
        return Report(
            classification=empty_cls,
            secrets_found=secrets_found,
            declined=True,
            decline_message=(
                "No input received. Please paste your error message, log output, "
                "or a description of the problem."
            ),
            latency_ms=int((time.monotonic() - pipeline_start) * 1000),
        )

    # Trim very long inputs to avoid context limits (keep last 400 lines)
    lines = clean_input.splitlines()
    if len(lines) > 400:
        logger.info("Input truncated from %d to 400 lines", len(lines))
        clean_input = "\n".join(lines[-400:])
        clean_input = f"[NOTE: Input was truncated to the last 400 lines]\n\n{clean_input}"

    # ------------------------------------------------------------------
    # Step 2: Classifier
    # ------------------------------------------------------------------
    logger.info("Step 2: Classifier LLM call")
    classification: Classification = complete_json(
        system_prompt=CLASSIFIER_SYSTEM,
        user_message=build_classifier_user(clean_input),
        schema=Classification,
    )
    logger.info(
        "Classification: type=%s severity=%s in_scope=%s",
        classification.type,
        classification.severity,
        classification.in_scope,
    )

    # ------------------------------------------------------------------
    # Step 3: Scope gate
    # ------------------------------------------------------------------
    logger.info("Step 3: Scope gate")
    if not classification.in_scope:
        logger.info("Input out of scope — declining")
        return Report(
            classification=classification,
            secrets_found=secrets_found,
            declined=True,
            decline_message=(
                "TriageOps handles server (Linux), Docker, and Kubernetes issues only. "
                "Your input appears to be outside this scope. "
                "If you believe this is an infrastructure problem, please include "
                "the relevant error messages, logs, or command output."
            ),
            latency_ms=int((time.monotonic() - pipeline_start) * 1000),
        )

    # ------------------------------------------------------------------
    # Step 4: Runbook retrieval
    # ------------------------------------------------------------------
    logger.info("Step 4: Runbook retrieval")
    search_query = " ".join(classification.key_error_lines) or clean_input[:500]
    search_query = f"{classification.type} {search_query}"
    runbook_hits = _runbooks.search(search_query, k=2)
    runbooks_used = [name for name, _ in runbook_hits]
    runbook_context = "\n\n".join(
        f"[Runbook: {name}]\n{text}" for name, text in runbook_hits
    )
    logger.info("Runbooks retrieved: %s", runbooks_used)

    # ------------------------------------------------------------------
    # Step 5: Analyst
    # ------------------------------------------------------------------
    logger.info("Step 5: Analyst LLM call")
    analyst_user = build_analyst_user(
        clean_input=clean_input,
        issue_type=classification.type,
        severity=classification.severity,
        key_error_lines=classification.key_error_lines,
        runbook_context=runbook_context,
    )
    analysis: Analysis = complete_json(
        system_prompt=ANALYST_SYSTEM,
        user_message=analyst_user,
        schema=Analysis,
    )
    logger.info(
        "Analysis: confidence=%s root_cause_chars=%d fix_steps=%d",
        analysis.confidence.level,
        len(analysis.root_cause),
        len(analysis.fix_steps),
    )

    # ------------------------------------------------------------------
    # Step 6: Command review — code overrides model's risk labels
    # ------------------------------------------------------------------
    logger.info("Step 6: Command review")
    fix_commands = [step.command for step in analysis.fix_steps if step.command]
    user_cmds = re.findall(r"['`]([^'`\n]{4,})['`]", clean_input)
    candidate_commands = list(dict.fromkeys(fix_commands + user_cmds))
    command_warnings = review_commands(candidate_commands, text_to_scan=clean_input)
    risky_commands = {w.command for w in command_warnings}

    for step in analysis.fix_steps:
        if step.command and step.command in risky_commands:
            if step.risk != "high":
                logger.debug("Overriding risk label to 'high' for command: %s", step.command)
            step.risk = "high"

    # ------------------------------------------------------------------
    # Step 7: Assemble report
    # ------------------------------------------------------------------
    logger.info("Step 7: Assembling report")
    latency_ms = int((time.monotonic() - pipeline_start) * 1000)
    logger.info("Pipeline complete in %dms", latency_ms)

    return Report(
        classification=classification,
        analysis=analysis,
        secrets_found=secrets_found,
        command_warnings=command_warnings,
        declined=False,
        runbooks_used=runbooks_used,
        latency_ms=latency_ms,
    )
