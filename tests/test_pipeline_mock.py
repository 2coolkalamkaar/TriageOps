"""
Pipeline integration tests with mocked LLM calls.

All tests use unittest.mock to patch _call_model, so no API key is needed.
These tests verify:
  - Scope gate correctly declines out-of-scope input
  - Secret redaction happens before any LLM call
  - Code overrides model risk labels for risky commands
  - Declined path returns correct Report shape
  - Full pipeline returns well-formed Report for in-scope input
"""

import json
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Fixtures: mock LLM responses
# ---------------------------------------------------------------------------

def _make_classification_json(
    type_="Kubernetes",
    severity="P2",
    in_scope=True,
    key_error_lines=None,
    reason="Pod is crash-looping.",
) -> str:
    return json.dumps({
        "type": type_,
        "severity": severity,
        "in_scope": in_scope,
        "key_error_lines": key_error_lines or ["CrashLoopBackOff"],
        "reason": reason,
    })


def _make_analysis_json(
    root_cause="Missing environment variable MY_DB_URL",
    commands=None,
    confidence_level="High",
) -> str:
    commands = commands or ["kubectl describe pod web-7d9"]
    return json.dumps({
        "summary": "Pod is crash-looping due to missing env var.",
        "root_cause": root_cause,
        "evidence": ["CrashLoopBackOff", "Exit Code: 1"],
        "other_causes": [],
        "fix_steps": [
            {
                "step": "Set the missing environment variable",
                "command": cmd,
                "why": "The app needs this variable to start.",
                "risk": "low",
            }
            for cmd in commands
        ],
        "verification": ["kubectl get pod web-7d9"],
        "prevention": ["Always validate env vars in CI before deployment."],
        "confidence": {
            "level": confidence_level,
            "reason": "Error directly matches the evidence.",
            "would_raise": [],
        },
        "clarifying_questions": [],
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPipelineMocked:

    def test_scope_gate_declines_out_of_scope(self):
        """Out-of-scope input (in_scope=False) should return a declined Report."""
        oos_classification = _make_classification_json(
            type_="Unknown", in_scope=False, reason="Not an infrastructure problem."
        )

        with patch("triageops.llm._call_model", return_value=oos_classification):
            from triageops.pipeline import run_triage
            report = run_triage("Please write me a poem about pandas.")

        assert report.declined is True
        assert report.analysis is None
        assert report.decline_message is not None
        assert "TriageOps" in report.decline_message

    def test_secret_redaction_before_llm(self):
        """Secrets in input must be redacted before the LLM is called."""
        classification_json = _make_classification_json()
        analysis_json = _make_analysis_json()

        call_args_seen = []
        _call_count = [0]

        def capturing_call_model(system_prompt, user_message):
            call_args_seen.append(user_message)
            _call_count[0] += 1
            # First call = classifier, second call = analyst
            if _call_count[0] == 1:
                return classification_json
            return analysis_json

        with patch("triageops.llm._call_model", side_effect=capturing_call_model):
            from triageops.pipeline import run_triage
            report = run_triage(
                "Error: DB_PASSWORD=SuperSecret123 not working\n"
                "Pod in CrashLoopBackOff\nExit Code: 1"
            )

        # The raw secret must never appear in any LLM call
        for call in call_args_seen:
            assert "SuperSecret123" not in call, "Secret leaked to LLM!"

        # The report should note secrets were found
        assert len(report.secrets_found) > 0

    def test_risky_command_override(self):
        """Code must override model's 'low' risk label when a risky command is present."""
        classification_json = _make_classification_json()
        # LLM returns a risky command with low risk (bad model behaviour)
        analysis_json = _make_analysis_json(
            commands=["rm -rf /var/log/old"],
        )
        # Manually set risk to low in the JSON (the model wrongly labels it low)
        analysis_data = json.loads(analysis_json)
        analysis_data["fix_steps"][0]["risk"] = "low"
        analysis_json = json.dumps(analysis_data)

        with patch("triageops.llm._call_model", side_effect=[classification_json, analysis_json]):
            from triageops.pipeline import run_triage
            report = run_triage("Pod CrashLoopBackOff Exit Code 1")

        # Code must have overridden the model's 'low' to 'high'
        risky_steps = [s for s in report.analysis.fix_steps if s.command == "rm -rf /var/log/old"]
        assert len(risky_steps) == 1
        assert risky_steps[0].risk == "high", "Code should override model's low risk label"

        # Command warnings should be populated
        assert len(report.command_warnings) >= 1
        assert any("rm -rf" in w.command for w in report.command_warnings)

    def test_empty_input_declined(self):
        """Empty input should be declined without calling the LLM at all."""
        with patch("triageops.llm._call_model") as mock_llm:
            from triageops.pipeline import run_triage
            report = run_triage("")

        mock_llm.assert_not_called()
        assert report.declined is True
        assert report.classification.type == "Unknown"

    def test_full_pipeline_happy_path(self):
        """Full pipeline with in-scope input returns a well-formed Report."""
        classification_json = _make_classification_json()
        analysis_json = _make_analysis_json()

        with patch("triageops.llm._call_model", side_effect=[classification_json, analysis_json]):
            from triageops.pipeline import run_triage
            report = run_triage("kubectl describe pod web-7d9\nStatus: CrashLoopBackOff\nExit Code: 1")

        assert report.declined is False
        assert report.classification.type == "Kubernetes"
        assert report.analysis is not None
        assert report.analysis.root_cause != ""
        assert len(report.analysis.fix_steps) >= 1
        assert report.latency_ms is not None

    def test_pipeline_report_is_serializable(self):
        """Report must serialise to JSON without errors."""
        classification_json = _make_classification_json()
        analysis_json = _make_analysis_json()

        with patch("triageops.llm._call_model", side_effect=[classification_json, analysis_json]):
            from triageops.pipeline import run_triage
            report = run_triage("CrashLoopBackOff Exit Code 1")

        json_str = report.model_dump_json()
        assert len(json_str) > 10
        parsed = json.loads(json_str)
        assert "classification" in parsed
