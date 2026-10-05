"""
Deterministic safety module — no LLM involved.

Two responsibilities:
  1. Secret redaction: scan input text for sensitive patterns and replace
     matches with [REDACTED] before sending to any external API.
  2. Command review: check proposed fix commands against risky patterns
     and return annotated warnings with safer alternatives.

These checks are heuristics. They catch common patterns, not everything.
Always document this limitation clearly.
"""

import re

from .schemas import CommandWarning

# ---------------------------------------------------------------------------
# Secret patterns
# ---------------------------------------------------------------------------

SECRET_PATTERNS: dict[str, str] = {
    "AWS access key": r"AKIA[0-9A-Z]{16}",
    "AWS secret key": r"(?i)aws[_\-\s]?secret[_\-\s]?access[_\-\s]?key\s*[=:]\s*\S+",
    "Private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{36,}",
    "GCP service account key": r'"type"\s*:\s*"service_account"',
    "Bearer token": r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*",
    "Credentials in URL": r"[a-z]+://[^\s:@/]+:[^\s@/]+@",
    "Generic secret assignment": r"(?i)(password|passwd|secret|token|api[_\-]?key|auth[_\-]?key|access[_\-]?key)\s*[=:]\s*['\"]?\S{6,}['\"]?",
    "Hex secret (32+ chars)": r"\b[0-9a-fA-F]{32,}\b",
    "Base64 secret (40+ chars)": r"[A-Za-z0-9+/]{40,}={0,2}",
}

# Patterns too noisy for automatic redaction — just warn
WARN_ONLY_PATTERNS: dict[str, str] = {
    "Possible connection string": r"(?i)(mongodb|postgres|mysql|redis|amqp)://",
}


# ---------------------------------------------------------------------------
# Risky command patterns
# ---------------------------------------------------------------------------

RISKY_COMMANDS: list[tuple[str, str, str]] = [
    # (regex, reason, safer_alternative)
    (
        r"rm\s+-[a-z]*r[a-z]*f?\s+\S+",
        "Recursive force delete — irreversible",
        "Use `rm -ri` for interactive confirmation, or move to trash first",
    ),
    (
        r"kubectl\s+delete\s+(ns|namespace)\b",
        "Deletes an entire Kubernetes namespace and all its resources",
        "Use `kubectl get all -n <ns>` to inspect first; consider `kubectl cordon` if evicting pods",
    ),
    (
        r"kubectl\s+delete\s+(pv|pvc)\b",
        "Deletes persistent volumes — may cause permanent data loss",
        "Run `kubectl describe pv/pvc <name>` first; consider `kubectl patch` reclaim policy",
    ),
    (
        r"kubectl\s+delete\s+node\b",
        "Removes a node from the cluster",
        "Use `kubectl cordon <node>` then `kubectl drain <node> --ignore-daemonsets` first",
    ),
    (
        r"docker\s+system\s+prune",
        "Removes all unused containers, images, networks and volumes",
        "Use `docker system prune --filter 'until=24h'` or prune specific resources",
    ),
    (
        r"docker\s+(rm|rmi)\s+.*(-f|--force)",
        "Force-removes running containers or images in use",
        "Stop the container first with `docker stop <name>`, then remove",
    ),
    (
        r"--force\b",
        "Force flag skips safety checks — use with caution",
        "Prefer dry-run or describe commands to understand state before forcing",
    ),
    (
        r"kill\s+-9\b",
        "SIGKILL — hard kill with no graceful shutdown, may corrupt state",
        "Try `kill -15` (SIGTERM) first; use `kill -9` only if process ignores SIGTERM",
    ),
    (
        r"chmod\s+-R\s+777",
        "Opens permissions to everyone — major security risk",
        "Grant minimum required permissions; use `chmod -R 755` for directories",
    ),
    (
        r"\bmkfs\b",
        "Formats a filesystem — permanently destroys all data on the device",
        "Verify the target device with `lsblk` before proceeding; take a backup first",
    ),
    (
        r"\bdd\s+if=",
        "Low-level disk copy/write — can overwrite data irreversibly",
        "Double-check `of=` target; use `dd` with `status=progress` and verify first",
    ),
    (
        r"(?i)drop\s+(table|database|schema)\b",
        "Destroys database objects permanently",
        "Use a transaction with a `ROLLBACK` test first; take a backup beforehand",
    ),
    (
        r"kubectl\s+exec\s+.*--\s*(sh|bash|/bin/sh|/bin/bash)",
        "Opens an interactive shell in a production container",
        "Use `kubectl debug` with a copy of the pod rather than exec into production",
    ),
    (
        r"systemctl\s+(stop|disable)\s+(nginx|apache|sshd|docker|kubelet)",
        "Stops a critical system service",
        "Use `systemctl status <service>` and investigate logs before stopping",
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def redact_secrets(text: str) -> tuple[str, list[str]]:
    """
    Scan text for secret patterns and replace matches with [REDACTED].

    Returns:
        (redacted_text, list_of_secret_type_names_found)

    Important: this runs BEFORE any call to an external API.
    """
    found: list[str] = []
    out = text

    for name, pattern in SECRET_PATTERNS.items():
        if re.search(pattern, out, re.IGNORECASE | re.MULTILINE):
            found.append(name)
            out = re.sub(
                pattern,
                "[REDACTED]",
                out,
                flags=re.IGNORECASE | re.MULTILINE,
            )

    # Warn-only patterns (don't redact, just note)
    for name, pattern in WARN_ONLY_PATTERNS.items():
        if re.search(pattern, out, re.IGNORECASE):
            if name not in found:
                found.append(name)

    return out, found


def review_commands(commands: list[str]) -> list[CommandWarning]:
    """
    Check a list of commands against risky patterns.

    Returns a list of CommandWarning objects for any matches found.
    This runs AFTER the LLM produces fix steps — code overrides model risk labels.
    """
    warnings: list[CommandWarning] = []
    seen: set[str] = set()

    for cmd in commands:
        if not cmd:
            continue
        for pattern, reason, safer in RISKY_COMMANDS:
            key = f"{cmd}::{pattern}"
            if key not in seen and re.search(pattern, cmd, re.IGNORECASE):
                warnings.append(
                    CommandWarning(command=cmd, reason=reason, safer_alternative=safer)
                )
                seen.add(key)

    return warnings


def is_risky_command(command: str) -> bool:
    """Quick boolean check — used by the pipeline to set risk='high' on fix steps."""
    return bool(review_commands([command]))
