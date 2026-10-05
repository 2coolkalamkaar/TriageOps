# TriageOps

**DevOps Incident Triage Agent** — paste a server, Docker, or Kubernetes error and get a classified, evidence-backed, safety-checked incident report.

## Features

- **7-step pipeline**: secret redaction → LLM classifier → scope gate → runbook retrieval → root cause analysis → command safety review → report
- **Structured JSON outputs**: all LLM steps return validated Pydantic models
- **Safety-first**: risky commands (`rm -rf`, `kubectl delete`, `kill -9`) detected by code (not LLM) and flagged with safer alternatives
- **Secret detection**: secrets redacted before any external API call
- **10 runbooks**: K8s CrashLoopBackOff, ImagePullBackOff, OOMKilled, Docker exit-137, port conflicts, build failures, disk full, SSH refused, memory exhaustion, service crashes
- **CLI + REST API + Streamlit UI**

## Quick Start

```bash
# Install
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Configure
export GOOGLE_CLOUD_PROJECT=your-project
export GOOGLE_CLOUD_LOCATION=us-central1
export TRIAGEOPS_MODEL=gemini-2.0-flash

# CLI
kubectl describe pod web-7d9 | triageops
triageops error.log
cat build.log | triageops --json

# API
uvicorn triageops.api:app --reload
# POST http://localhost:8000/triage

# UI
streamlit run src/triageops/ui/app.py

# Tests (no API key needed)
pytest tests/test_safety.py tests/test_schemas.py tests/test_pipeline_mock.py -v

# Golden tests (needs API key)
python tests/run_golden.py
```

## Architecture

```
Raw Input
  → [1] Safety Pre-scan      (code: regex redacts secrets)
  → [2] Classifier           (LLM: type, severity, in_scope, key lines)
  → [3] Scope Gate           (code: decline if not infrastructure)
  → [4] Runbook Retrieval    (code: BM25 search over 10 runbooks)
  → [5] Analyst              (LLM: root cause, fix steps, confidence)
  → [6] Command Review       (code: flag risky patterns, override risk labels)
  → [7] Report Assembly      (code: structured markdown + JSON)
```

**Three kinds of steps (by design):**
- **Code**: secret redaction, scope gating, risky command detection, report rendering
- **LLM**: root cause reasoning, fix step generation, confidence rating
- Never the LLM for facts that code can check deterministically

## Project Structure

```
triageops/
  src/triageops/
    schemas.py       # Pydantic models for all pipeline stages
    safety.py        # Secret redaction + risky command detection
    llm.py           # Vertex AI wrapper with JSON retry
    prompts.py       # Classifier + analyst system prompts
    retrieval.py     # BM25 runbook search
    pipeline.py      # 7-step orchestrator
    render.py        # Markdown report renderer
    cli.py           # triageops CLI (Typer + Rich)
    api.py           # FastAPI REST API
    ui/app.py        # Streamlit UI
  runbooks/          # 10 markdown runbooks
  tests/
    test_safety.py
    test_schemas.py
    test_pipeline_mock.py
    golden/          # 5 JSON golden test cases
    run_golden.py    # Golden test harness
```

## Important Limitations

- Secret detection uses regex heuristics — catches common patterns, not everything
- Risky command detection uses regex — cannot catch all possible destructive patterns
- The agent **never executes commands** — it only suggests. A human must apply fixes.
- Confidence ratings are rubric-based judgements, not calibrated statistics

## License

MIT
