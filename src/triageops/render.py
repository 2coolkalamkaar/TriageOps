"""
Markdown and plain-text report renderer.

Takes a fully assembled Report model and renders it as a clean,
human-readable incident report. No LLM — purely deterministic formatting.
"""

from datetime import UTC, datetime

from .schemas import Report

# ---------------------------------------------------------------------------
# Risk badge helpers
# ---------------------------------------------------------------------------

RISK_BADGE = {
    "high": "🔴 HIGH RISK",
    "medium": "🟡 MEDIUM RISK",
    "low": "🟢 LOW RISK",
}

SEVERITY_BADGE = {
    "P1": "🚨 P1 — Production Down",
    "P2": "⚠️  P2 — Major Degradation",
    "P3": "🔶 P3 — Partial Impact",
    "P4": "🔵 P4 — Minor",
}

CONFIDENCE_BADGE = {
    "High": "✅ High",
    "Medium": "🟡 Medium",
    "Low": "🔴 Low",
}

TYPE_BADGE = {
    "Kubernetes": "☸️  Kubernetes",
    "Docker": "🐳 Docker",
    "Server": "🖥️  Server",
    "Mixed": "🔀 Mixed",
    "Unknown": "❓ Unknown",
}


def to_markdown(report: Report) -> str:
    """
    Render a Report as a structured markdown incident report.
    """
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = []

    # -----------------------------------------------------------------------
    # Header
    # -----------------------------------------------------------------------
    cls = report.classification
    type_label = TYPE_BADGE.get(cls.type, cls.type)
    sev_label = SEVERITY_BADGE.get(cls.severity, cls.severity)

    lines += [
        "# TriageOps — Incident Report",
        f"_Generated: {now}_",
        "",
        "---",
        "",
    ]

    # -----------------------------------------------------------------------
    # Classification & Severity
    # -----------------------------------------------------------------------
    lines += [
        "## 📋 Classification",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| **Type** | {type_label} |",
        f"| **Severity** | {sev_label} |",
        f"| **Reason** | {cls.reason} |",
        "",
    ]

    if cls.key_error_lines:
        lines += ["**Key Error Lines:**", "```"]
        lines += cls.key_error_lines
        lines += ["```", ""]

    if report.degraded:
        lines += [
            "> ⚠️ **DEGRADED MODE** — this report was produced by the offline keyword heuristic, "
            "not the LLM. It is a generic checklist, not a diagnosis of your system.",
            "",
        ]

    # -----------------------------------------------------------------------
    # Declined path
    # -----------------------------------------------------------------------
    if report.declined:
        lines += [
            "## 🚫 Out of Scope",
            "",
            f"> {report.decline_message}",
            "",
        ]
        if report.secrets_found:
            lines += _render_security_notes(report)
        if report.latency_ms is not None:
            lines += [f"_Pipeline completed in {report.latency_ms}ms_"]
        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # Analysis
    # -----------------------------------------------------------------------
    analysis = report.analysis
    if not analysis:
        lines += ["_No analysis available._"]
        return "\n".join(lines)

    # Summary
    lines += [
        "## 📝 Summary",
        "",
        analysis.summary,
        "",
    ]

    # Root cause
    lines += [
        "## 🔍 Root Cause",
        "",
        analysis.root_cause,
        "",
    ]

    if analysis.evidence:
        lines += ["**Evidence from input:**"]
        for ev in analysis.evidence:
            lines.append(f"- `{ev}`")
        lines.append("")

    if analysis.other_causes:
        lines += ["**Other possible causes:**"]
        for cause in analysis.other_causes:
            lines.append(f"- {cause}")
        lines.append("")

    # Fix steps
    if analysis.fix_steps:
        lines += [
            "## 🔧 Recommended Fix",
            "",
        ]
        for i, step in enumerate(analysis.fix_steps, 1):
            risk_badge = RISK_BADGE.get(step.risk, "")
            lines.append(f"### Step {i}: {step.step}")
            lines.append(f"_{step.why}_")
            if step.command:
                lines.append(f"```bash\n{step.command}\n```")
            if step.risk == "high":
                lines.append(f"> ⚠️  **{risk_badge}** — See safety notes below.")
            elif step.risk == "medium":
                lines.append(f"> {risk_badge} — Proceed with caution.")
            lines.append("")

    # Command warnings
    if report.command_warnings:
        lines += [
            "### ⚠️ Safety Warnings",
            "",
        ]
        for w in report.command_warnings:
            lines.append(f"**Command:** `{w.command}`")
            lines.append(f"**Risk:** {w.reason}")
            if w.safer_alternative:
                lines.append(f"**Safer alternative:** {w.safer_alternative}")
            lines.append("")

    # Clarifying questions (vague input path)
    if analysis.clarifying_questions:
        lines += [
            "## ❓ Clarifying Questions",
            "",
            "_Input was too vague for a confident diagnosis. Please answer:_",
            "",
        ]
        for q in analysis.clarifying_questions:
            lines.append(f"1. {q}")
        lines.append("")

    # Verification
    if analysis.verification:
        lines += [
            "## ✅ Verification",
            "",
            "_Run these to confirm the fix worked:_",
            "",
        ]
        for v in analysis.verification:
            lines.append(f"```bash\n{v}\n```")
        lines.append("")

    # Prevention
    if analysis.prevention:
        lines += [
            "## 🛡️ Prevention",
            "",
        ]
        for p in analysis.prevention:
            lines.append(f"- {p}")
        lines.append("")

    # Confidence
    conf = analysis.confidence
    lines += [
        "## 📊 Confidence",
        "",
        f"**Level:** {CONFIDENCE_BADGE.get(conf.level, conf.level)}",
        f"**Reason:** {conf.reason}",
        "",
    ]
    if conf.would_raise:
        lines += ["**Would raise confidence:**"]
        for item in conf.would_raise:
            lines.append(f"- {item}")
        lines.append("")

    # Security notes
    if report.secrets_found:
        lines += _render_security_notes(report)

    # Runbooks used
    if report.runbooks_used:
        lines += [
            "## 📚 Runbooks Referenced",
            "",
        ]
        for rb in report.runbooks_used:
            lines.append(f"- `{rb}`")
        lines.append("")

    # Footer
    if report.latency_ms is not None:
        lines += [
            "---",
            f"_TriageOps | Engine: {report.engine} | Pipeline completed in {report.latency_ms}ms_",
        ]

    return "\n".join(lines)


def _render_security_notes(report: Report) -> list[str]:
    """Render the Security Notes section."""
    lines = [
        "## 🔐 Security Notes",
        "",
        "> ⚠️ **Sensitive information was detected and redacted from your input.**",
        "",
        "The following types of secrets were found:",
        "",
    ]
    for s in report.secrets_found:
        lines.append(f"- {s}")
    lines += [
        "",
        "**Actions required:**",
        "1. Remove the secrets from your logs and error messages before sharing.",
        "2. **Rotate all affected credentials immediately** — treat them as compromised.",
        "3. Review your logging configuration to prevent secrets from appearing in logs.",
        "4. Consider using a secrets manager (e.g. HashiCorp Vault, GCP Secret Manager, AWS Secrets Manager).",
        "",
    ]
    return lines


def to_json(report: Report) -> str:
    """Render a Report as formatted JSON."""
    return report.model_dump_json(indent=2)
