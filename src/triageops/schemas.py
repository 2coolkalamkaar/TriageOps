"""
Pydantic schemas for all TriageOps data models.

All LLM responses are validated against these models.
Code steps never parse free-text — they always receive typed objects.
"""

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Primitive types
# ---------------------------------------------------------------------------

IssueType = Literal["Server", "Docker", "Kubernetes", "Mixed", "Unknown"]
SeverityLevel = Literal["P1", "P2", "P3", "P4"]
ConfidenceLevel = Literal["High", "Medium", "Low"]
RiskLevel = Literal["low", "medium", "high"]


# ---------------------------------------------------------------------------
# Step 2: Classifier output
# ---------------------------------------------------------------------------

class Classification(BaseModel):
    """Output of the LLM classifier step."""

    type: IssueType = Field(
        description="Issue category: Server, Docker, Kubernetes, Mixed, or Unknown"
    )
    severity: SeverityLevel = Field(
        description="P1=production down/data at risk, P2=major degradation, P3=partial, P4=minor"
    )
    in_scope: bool = Field(
        description="True if about servers, Docker, or Kubernetes (including vague infra problems)"
    )
    key_error_lines: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Up to 5 exact lines copied verbatim from the input that are the clearest error signals",
    )
    reason: str = Field(
        description="One sentence explaining the classification decision"
    )


# ---------------------------------------------------------------------------
# Step 5: Analyst output
# ---------------------------------------------------------------------------

class FixStep(BaseModel):
    """A single recommended fix action."""

    step: str = Field(description="Short description of this action")
    command: str | None = Field(
        default=None,
        description="The exact runnable command, or null if no command is needed",
    )
    why: str = Field(description="One-line explanation of why this step helps")
    risk: RiskLevel = Field(
        default="low",
        description="Risk level of this command. Code will override this if a risky pattern is detected.",
    )


class Confidence(BaseModel):
    """Confidence rating for the analysis."""

    level: ConfidenceLevel = Field(
        description="High=cause directly shown by evidence, Medium=strongly suggested, Low=limited evidence"
    )
    reason: str = Field(description="Why this confidence level was assigned")
    would_raise: list[str] = Field(
        default_factory=list,
        description="What additional information would raise confidence to High",
    )


class Analysis(BaseModel):
    """Output of the LLM analyst step."""

    summary: str = Field(description="2-3 sentence plain-language description of what is happening")
    root_cause: str = Field(description="Most likely root cause")
    evidence: list[str] = Field(
        default_factory=list,
        description="Specific lines or signals from the input that support the root cause",
    )
    other_causes: list[str] = Field(
        default_factory=list,
        description="Other possible causes, if any",
    )
    fix_steps: list[FixStep] = Field(
        default_factory=list,
        description="Ordered list of recommended fix actions",
    )
    verification: list[str] = Field(
        default_factory=list,
        description="Commands or signals to confirm the fix worked",
    )
    prevention: list[str] = Field(
        default_factory=list,
        description="2-4 practical recommendations to prevent recurrence",
    )
    confidence: Confidence
    clarifying_questions: list[str] = Field(
        default_factory=list,
        description="Questions to ask when input is too vague (Low confidence path)",
    )


# ---------------------------------------------------------------------------
# Step 6: Command review output
# ---------------------------------------------------------------------------

class CommandWarning(BaseModel):
    """A risky command flagged by the safety module."""

    command: str
    reason: str
    safer_alternative: str | None = None


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------

class Report(BaseModel):
    """The complete triage report assembled by the pipeline."""

    classification: Classification
    analysis: Analysis | None = None
    secrets_found: list[str] = Field(
        default_factory=list,
        description="Names of secret types detected and redacted from the input",
    )
    command_warnings: list[CommandWarning] = Field(
        default_factory=list,
        description="Risky commands flagged by the deterministic safety checker",
    )
    declined: bool = Field(
        default=False,
        description="True if the input was out of scope and the pipeline declined to analyse it",
    )
    decline_message: str | None = Field(
        default=None,
        description="Polite decline message shown to the user when declined=True",
    )
    runbooks_used: list[str] = Field(
        default_factory=list,
        description="Names of runbooks retrieved and passed to the analyst",
    )
    latency_ms: int | None = Field(
        default=None,
        description="Total pipeline latency in milliseconds",
    )
