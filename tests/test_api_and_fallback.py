"""
Tests for production hardening:
  - LLM failures fail closed (no silent canned diagnosis) unless fallback is opted into
  - Offline-engine reports are marked degraded with Low confidence
  - API key auth, rate limiting, and safe error responses on the REST API
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from triageops import api, llm
from triageops.pipeline import run_triage

K8S_INPUT = "kubectl describe pod web-7d9\nReason: CrashLoopBackOff\nExit Code: 1"


def _classification() -> str:
    return json.dumps({
        "type": "Kubernetes",
        "severity": "P2",
        "in_scope": True,
        "key_error_lines": ["Reason: CrashLoopBackOff"],
        "reason": "Pod is crash-looping.",
    })


def _analysis() -> str:
    return json.dumps({
        "summary": "Pod crash-looping.",
        "root_cause": "Missing env var.",
        "evidence": ["Exit Code: 1"],
        "fix_steps": [{"step": "Inspect", "command": "kubectl describe pod web-7d9", "why": "Look", "risk": "low"}],
        "confidence": {"level": "High", "reason": "Direct evidence.", "would_raise": []},
    })


# ---------------------------------------------------------------------------
# LLM fallback behaviour
# ---------------------------------------------------------------------------

class TestFallback:

    def test_provider_failure_fails_closed(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.delenv("TRIAGEOPS_FORCE_OFFLINE", raising=False)
        monkeypatch.delenv("TRIAGEOPS_ALLOW_OFFLINE_FALLBACK", raising=False)
        with patch("triageops.llm._call_gemini_api", side_effect=RuntimeError("boom")):
            with pytest.raises(llm.LLMUnavailableError):
                run_triage(K8S_INPUT)

    def test_provider_failure_with_opt_in_fallback_is_degraded(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("TRIAGEOPS_ALLOW_OFFLINE_FALLBACK", "1")
        monkeypatch.delenv("TRIAGEOPS_FORCE_OFFLINE", raising=False)
        with patch("triageops.llm._call_gemini_api", side_effect=RuntimeError("boom")):
            report = run_triage(K8S_INPUT)
        assert report.degraded is True
        assert report.engine == "offline"
        assert report.analysis is not None
        assert report.analysis.confidence.level == "Low"
        # Evidence must only contain lines copied verbatim from the input
        for ev in report.analysis.evidence:
            assert ev in K8S_INPUT

    def test_forced_offline_is_degraded(self, monkeypatch):
        monkeypatch.setenv("TRIAGEOPS_FORCE_OFFLINE", "1")
        report = run_triage(K8S_INPUT)
        assert report.degraded is True
        assert report.engine == "offline"

    def test_no_provider_configured_does_not_use_vertex(self, monkeypatch):
        for var in ("TRIAGEOPS_FORCE_OFFLINE", "GEMINI_API_KEY", "VERTEX_PROJECT", "GOOGLE_CLOUD_PROJECT"):
            monkeypatch.delenv(var, raising=False)
        assert llm.get_provider() == "offline"

    def test_llm_engine_recorded(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.delenv("TRIAGEOPS_FORCE_OFFLINE", raising=False)
        with patch("triageops.llm._call_gemini_api", side_effect=[_classification(), _analysis()]):
            report = run_triage(K8S_INPUT)
        assert report.engine == "gemini_api"
        assert report.degraded is False
        assert report.analysis.confidence.level == "High"


# ---------------------------------------------------------------------------
# REST API hardening
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api, "API_KEYS", ["secret-key"])
    monkeypatch.setattr(api, "_limiter", api._RateLimiter(limit=2))
    monkeypatch.setenv("TRIAGEOPS_FORCE_OFFLINE", "1")
    return TestClient(api.app)


class TestApi:

    def test_health_is_public(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["auth_enabled"] is True
        assert "X-Request-ID" in res.headers

    def test_triage_requires_key(self, client):
        assert client.post("/triage", json={"text": K8S_INPUT}).status_code == 401

    def test_triage_rejects_wrong_key(self, client):
        res = client.post("/triage", json={"text": K8S_INPUT}, headers={"X-API-Key": "nope"})
        assert res.status_code == 401

    def test_triage_accepts_bearer_and_header_key(self, client):
        ok1 = client.post("/triage", json={"text": K8S_INPUT}, headers={"Authorization": "Bearer secret-key"})
        ok2 = client.post("/triage", json={"text": K8S_INPUT}, headers={"X-API-Key": "secret-key"})
        assert ok1.status_code == 200 and ok2.status_code == 200
        assert ok1.json()["degraded"] is True

    def test_rate_limit(self, client):
        headers = {"X-API-Key": "secret-key"}
        for _ in range(2):
            assert client.post("/triage", json={"text": K8S_INPUT}, headers=headers).status_code == 200
        res = client.post("/triage", json={"text": K8S_INPUT}, headers=headers)
        assert res.status_code == 429
        assert "Retry-After" in res.headers

    def test_runbooks_require_key(self, client):
        assert client.get("/runbooks").status_code == 401
        assert client.get("/runbooks", headers={"X-API-Key": "secret-key"}).status_code == 200

    def test_internal_error_does_not_leak_details(self, client):
        with patch("triageops.api.run_triage", side_effect=RuntimeError("db password is hunter2")):
            res = client.post("/triage", json={"text": K8S_INPUT}, headers={"X-API-Key": "secret-key"})
        assert res.status_code == 500
        assert "hunter2" not in res.text
        assert "request_id=" in res.json()["detail"]

    def test_llm_unavailable_returns_503(self, client):
        with patch("triageops.api.run_triage", side_effect=llm.LLMUnavailableError("down")):
            res = client.post("/triage", json={"text": K8S_INPUT}, headers={"X-API-Key": "secret-key"})
        assert res.status_code == 503
        assert "Retry-After" in res.headers

    def test_no_wildcard_cors(self, client):
        res = client.get("/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in {k.lower() for k in res.headers}
