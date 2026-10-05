"""Tests for Pydantic schemas — no LLM required."""

import pytest
from pydantic import ValidationError

from triageops.schemas import (
    Analysis,
    Classification,
    Confidence,
    FixStep,
    Report,
)

# ---------------------------------------------------------------------------
# Classification schema
# ---------------------------------------------------------------------------

class TestClassification:

    def test_valid_classification(self):
        cls = Classification(
            type="Kubernetes",
            severity="P2",
            in_scope=True,
            key_error_lines=["CrashLoopBackOff", "Exit Code: 1"],
            reason="Pod is crash-looping with exit code 1.",
        )
        assert cls.type == "Kubernetes"
        assert cls.severity == "P2"
        assert cls.in_scope is True

    def test_invalid_type_rejected(self):
        with pytest.raises(ValidationError):
            Classification(
                type="AWS",  # invalid
                severity="P1",
                in_scope=True,
                key_error_lines=[],
                reason="test",
            )

    def test_invalid_severity_rejected(self):
        with pytest.raises(ValidationError):
            Classification(
                type="Docker",
                severity="P5",  # invalid
                in_scope=True,
                key_error_lines=[],
                reason="test",
            )

    def test_defaults_applied(self):
        cls = Classification(
            type="Server",
            severity="P3",
            in_scope=False,
            reason="Not infrastructure.",
        )
        assert cls.key_error_lines == []

    def test_all_valid_types(self):
        for t in ("Server", "Docker", "Kubernetes", "Mixed", "Unknown"):
            cls = Classification(type=t, severity="P4", in_scope=True, reason="ok")
            assert cls.type == t

    def test_all_valid_severities(self):
        for s in ("P1", "P2", "P3", "P4"):
            cls = Classification(type="Server", severity=s, in_scope=True, reason="ok")
            assert cls.severity == s


# ---------------------------------------------------------------------------
# FixStep schema
# ---------------------------------------------------------------------------

class TestFixStep:

    def test_valid_fix_step(self):
        step = FixStep(
            step="Restart the nginx service",
            command="sudo systemctl restart nginx",
            why="Reloads the configuration after changes.",
            risk="low",
        )
        assert step.command == "sudo systemctl restart nginx"
        assert step.risk == "low"

    def test_command_is_optional(self):
        step = FixStep(step="Review logs", why="Understand the cause.")
        assert step.command is None

    def test_invalid_risk_rejected(self):
        with pytest.raises(ValidationError):
            FixStep(step="test", why="test", risk="critical")  # invalid

    def test_default_risk_is_low(self):
        step = FixStep(step="safe step", why="safe")
        assert step.risk == "low"


# ---------------------------------------------------------------------------
# Confidence schema
# ---------------------------------------------------------------------------

class TestConfidence:

    def test_valid_confidence(self):
        conf = Confidence(
            level="High",
            reason="Error line directly cited in evidence.",
            would_raise=[],
        )
        assert conf.level == "High"

    def test_invalid_level_rejected(self):
        with pytest.raises(ValidationError):
            Confidence(level="Very High", reason="test")

    def test_would_raise_defaults_empty(self):
        conf = Confidence(level="Low", reason="Vague input.")
        assert conf.would_raise == []


# ---------------------------------------------------------------------------
# Report schema
# ---------------------------------------------------------------------------

class TestReport:

    def test_minimal_report(self):
        cls = Classification(type="Unknown", severity="P4", in_scope=False, reason="OOS")
        report = Report(classification=cls, declined=True, decline_message="Out of scope.")
        assert report.declined is True
        assert report.analysis is None
        assert report.secrets_found == []
        assert report.command_warnings == []

    def test_report_serializes_to_json(self):
        cls = Classification(type="Server", severity="P3", in_scope=True, reason="test")
        report = Report(classification=cls)
        json_str = report.model_dump_json()
        assert "classification" in json_str
        assert "Server" in json_str

    def test_report_with_analysis(self):
        cls = Classification(type="Docker", severity="P2", in_scope=True, reason="OOM")
        conf = Confidence(level="High", reason="OOMKilled in logs.", would_raise=[])
        analysis = Analysis(
            summary="Container OOMKilled.",
            root_cause="Memory limit too low.",
            evidence=["OOMKilled", "Exit Code 137"],
            fix_steps=[FixStep(step="Increase memory", command="docker run --memory=1g ...", why="Fix OOM")],
            confidence=conf,
        )
        report = Report(classification=cls, analysis=analysis)
        assert report.analysis.root_cause == "Memory limit too low."
        assert len(report.analysis.fix_steps) == 1
