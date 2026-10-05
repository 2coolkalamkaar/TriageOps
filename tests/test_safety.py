"""Tests for the safety module — no LLM required."""

from triageops.safety import is_risky_command, redact_secrets, review_commands
from triageops.schemas import CommandWarning

# ---------------------------------------------------------------------------
# Secret redaction tests
# ---------------------------------------------------------------------------

class TestRedactSecrets:

    def test_clean_text_unchanged(self):
        """Safe text should pass through untouched."""
        text = "kubectl get pods -n production\ndocker ps -a"
        cleaned, found = redact_secrets(text)
        assert cleaned == text
        assert found == []

    def test_aws_access_key_redacted(self):
        text = "export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        cleaned, found = redact_secrets(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in cleaned
        assert "[REDACTED]" in cleaned
        assert any("AWS" in f for f in found)

    def test_github_token_redacted(self):
        text = "GITHUB_TOKEN=ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890ab"
        cleaned, found = redact_secrets(text)
        assert "ghp_" not in cleaned
        assert "[REDACTED]" in cleaned
        assert any("GitHub" in f for f in found)

    def test_password_assignment_redacted(self):
        text = "DATABASE_PASSWORD=SuperSecretPass123!"
        cleaned, found = redact_secrets(text)
        assert "SuperSecretPass123" not in cleaned
        assert len(found) > 0

    def test_url_with_credentials_redacted(self):
        text = "mongodb://admin:password123@db.example.com:27017/mydb"
        cleaned, found = redact_secrets(text)
        assert "password123" not in cleaned
        assert len(found) > 0

    def test_private_key_block_redacted(self):
        text = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xHn/ygWep4\n"
            "-----END RSA PRIVATE KEY-----"
        )
        cleaned, found = redact_secrets(text)
        assert "BEGIN RSA PRIVATE KEY" not in cleaned
        assert len(found) > 0

    def test_multiple_secrets_all_redacted(self):
        text = (
            "export AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n"
            "GITHUB_TOKEN=ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890ab\n"
            "password=mysecretpassword123"
        )
        cleaned, found = redact_secrets(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in cleaned
        assert "ghp_" not in cleaned
        assert len(found) >= 2

    def test_empty_text(self):
        cleaned, found = redact_secrets("")
        assert cleaned == ""
        assert found == []

    def test_returns_tuple(self):
        result = redact_secrets("hello world")
        assert isinstance(result, tuple)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Command review tests
# ---------------------------------------------------------------------------

class TestReviewCommands:

    def test_safe_commands_not_flagged(self):
        safe_commands = [
            "kubectl get pods -n production",
            "docker ps -a",
            "df -h",
            "journalctl -u nginx -n 50",
            "kubectl describe pod web-7d9",
            "systemctl status nginx",
        ]
        warnings = review_commands(safe_commands)
        assert warnings == []

    def test_rm_rf_flagged(self):
        warnings = review_commands(["rm -rf /var/log/old"])
        assert len(warnings) == 1
        assert warnings[0].command == "rm -rf /var/log/old"
        assert "delete" in warnings[0].reason.lower() or "recursive" in warnings[0].reason.lower()
        assert warnings[0].safer_alternative is not None

    def test_docker_system_prune_flagged(self):
        warnings = review_commands(["docker system prune"])
        assert len(warnings) == 1
        assert "prune" in warnings[0].reason.lower() or "removes" in warnings[0].reason.lower()

    def test_kill_9_flagged(self):
        warnings = review_commands(["kill -9 1234"])
        assert len(warnings) == 1
        assert "SIGKILL" in warnings[0].reason or "kill" in warnings[0].reason.lower()
        assert warnings[0].safer_alternative is not None

    def test_kubectl_delete_namespace_flagged(self):
        warnings = review_commands(["kubectl delete namespace production"])
        assert len(warnings) == 1
        assert "namespace" in warnings[0].reason.lower()

    def test_chmod_777_flagged(self):
        warnings = review_commands(["chmod -R 777 /var/www"])
        assert len(warnings) == 1
        assert "permission" in warnings[0].reason.lower() or "security" in warnings[0].reason.lower()

    def test_force_flag_flagged(self):
        warnings = review_commands(["kubectl delete pod web --force"])
        assert len(warnings) >= 1

    def test_returns_command_warning_objects(self):
        warnings = review_commands(["rm -rf /tmp/test"])
        assert all(isinstance(w, CommandWarning) for w in warnings)

    def test_empty_list(self):
        warnings = review_commands([])
        assert warnings == []

    def test_none_commands_skipped(self):
        """None values in the command list should not cause errors."""
        warnings = review_commands([None, "docker ps"])  # type: ignore
        assert warnings == []

    def test_multiple_risky_commands(self):
        commands = ["rm -rf /", "kill -9 999", "chmod -R 777 /etc"]
        warnings = review_commands(commands)
        assert len(warnings) >= 3

    def test_case_insensitive_matching(self):
        warnings = review_commands(["DOCKER SYSTEM PRUNE"])
        assert len(warnings) >= 1


# ---------------------------------------------------------------------------
# is_risky_command tests
# ---------------------------------------------------------------------------

class TestIsRiskyCommand:

    def test_risky_returns_true(self):
        assert is_risky_command("rm -rf /var/log") is True
        assert is_risky_command("kill -9 1234") is True

    def test_safe_returns_false(self):
        assert is_risky_command("kubectl get pods") is False
        assert is_risky_command("docker ps") is False

    def test_empty_string(self):
        assert is_risky_command("") is False
