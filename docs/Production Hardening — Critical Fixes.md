# TriageOps: Production Hardening (Critical Fixes)

This document explains the five critical issues found while reviewing TriageOps for production use: what each problem was, why it mattered, what we changed, and how to check the fix yourself.

**TL;DR**

| # | Problem | Risk | Fix |
|---|---|---|---|
| 1 | LLM failures silently returned made-up "High confidence" diagnoses | Engineers act on fake evidence during an incident | Fail closed (HTTP 503); offline answers are marked **degraded**, capped at Low confidence, with no invented evidence |
| 2 | A real GCP project ID was hardcoded as the default | Leaks the project; every install tried to use it | Removed; the provider comes only from environment variables |
| 3 | `/triage` blocked the server's event loop | One slow LLM call froze the server for all users | Endpoint now runs in a threadpool |
| 4 | API was open: no auth, no rate limit, wildcard CORS, leaked error text | Anyone could spend your LLM quota; internal details exposed | API keys, per-client rate limiting, explicit CORS, request IDs, safe errors |
| 5 | Offline engine suggested `truncate -s 0 <log>` marked "low risk" | Destroys log data during an incident | New safety rule flags file truncation; suggests `logrotate -f` instead |

---

## 1. Silent fallback to fabricated diagnoses

### The problem
When the Gemini / Vertex AI call failed (timeout, quota, bad credentials), `llm.py` caught the error and quietly switched to the **offline heuristic engine**. That engine returned hardcoded reports, for example:

- "process **24601** was OOM-killed", "**/dev/sda1** is full, **/var/log/application.log** is **44G**"
- a fix command containing `postgres://user:pass@db:5432/app`
- all marked **High confidence**

The keyword matching was crude: any input containing `137` got the OOM answer, and any input containing `pod` got the "missing env var" answer. **Nothing in the report said it came from the heuristic.**

### Why it matters
In an incident, a confident report with specific-looking evidence is something people act on. If that evidence was invented, the tool is worse than useless: it sends on-call engineers in the wrong direction.

### What we changed
- **Fail closed by default.** If the configured LLM fails, the pipeline raises `LLMUnavailableError` and the API returns **`503 Service Unavailable`** with a `Retry-After: 30` header. No canned answer is substituted.
- **Opt-in fallback only.** Set `TRIAGEOPS_ALLOW_OFFLINE_FALLBACK=1` if you *want* the offline heuristic when the LLM is down (useful for demos).
- **Every report records its engine.** Two new fields on `Report`:
  - `engine`: `gemini_api`, `vertex_ai`, `offline`, or `none` (no LLM call, e.g. empty input)
  - `degraded`: `true` whenever any step used the offline heuristic
- **Degraded reports can't pose as real diagnoses:**
  - confidence is forced to **Low**
  - evidence is limited to lines copied **verbatim from your input**
  - the summary is prefixed with `[DEGRADED — offline heuristic, not an LLM diagnosis]`
  - a warning banner appears in the Markdown report, the web UI (toast), and the Streamlit UI
- **Fabricated specifics removed** from the offline answers. Real-looking values were replaced with placeholders (`<container>`, `<deployment>`, `<namespace>`, `<value-from-secret>`), and a special case tuned to one golden-test input was removed.
- The same rule now applies when the model returns invalid JSON after retries: it raises an error unless fallback is explicitly allowed.

**Files:** `src/triageops/llm.py`, `src/triageops/pipeline.py`, `src/triageops/schemas.py`, `src/triageops/render.py`, `src/triageops/web/app.js`, `src/triageops/ui/app.py`

---

## 2. Hardcoded GCP project ID

### The problem
`llm.py` had a real project ID as the fallback value:

```python
or "project-036ddc82-f451-4fae-9e3"
```

Because that string was always truthy, the provider check *always* chose Vertex AI, even when nothing was configured. Anyone running the code would try to call that project.

### What we changed
- The default is removed. The provider is chosen only from the environment:
  1. `TRIAGEOPS_FORCE_OFFLINE=1` → offline (demo mode)
  2. `GEMINI_API_KEY` → Gemini API
  3. `VERTEX_PROJECT` or `GOOGLE_CLOUD_PROJECT` → Vertex AI
  4. nothing set → offline, **with a startup warning**, and every report marked `degraded`
- `/health` now reports `llm_provider`, so you can see at a glance which engine the server will use.

> ⚠️ **Action required:** the old ID is still in git history. It is not a credential, but you may want to review that project's IAM bindings, or scrub history with `git filter-repo`.

---

## 3. `/triage` blocked the whole server

### The problem
The endpoint was declared `async def` but called `run_triage()`, which makes **two blocking LLM calls** (several seconds each). In FastAPI, blocking code inside an `async def` freezes the event loop, so while one user's triage was running, **every other request waited**, including `/health`. Under load this looks like a full outage, and health checks may kill the container.

### What we changed
`/triage` is now a plain `def`. FastAPI runs plain functions in a worker threadpool, so slow LLM calls no longer block other requests.

**File:** `src/triageops/api.py`

---

## 4. Open API: no auth, no rate limit, wildcard CORS, leaked errors

### The problem
- **No authentication.** Anyone who could reach the server could call `/triage`, which makes it a free proxy to your Gemini bill.
- **No rate limiting.** A single client could send unlimited requests.
- **CORS** was `allow_origins=["*"]` together with `allow_credentials=True`, a combination browsers reject and security reviewers flag immediately.
- **Error responses** returned `str(exc)`, which can expose internal paths, config, or upstream error text.

### What we changed

**API keys**
- Set `TRIAGEOPS_API_KEYS` to one or more comma-separated keys.
- `/triage`, `/runbooks`, and `/runbooks/{name}` then require either header:
  - `X-API-Key: <key>`
  - `Authorization: Bearer <key>`
- Keys are compared in constant time (`hmac.compare_digest`).
- `/health`, `/`, and static files stay public so load balancers and the UI page still work.
- The web UI asks for the key on the first `401`, stores it in the browser, and retries.
- If no keys are set, the API still works but logs a loud warning at startup.

**Rate limiting**
- `TRIAGEOPS_RATE_LIMIT_PER_MIN` (default **20**) limits `/triage` per client.
- A client is identified by its API key if one is sent, otherwise by IP address.
- Over the limit returns **`429 Too Many Requests`** with a `Retry-After` header.
- It's an in-memory sliding window, **counted per worker process**: with 4 workers the effective limit is 4×. For multi-instance deployments, move the limit to your gateway or Redis (a planned follow-up).

**CORS**
- Disabled by default. The bundled UI is served from the same origin and doesn't need it.
- Set `TRIAGEOPS_CORS_ORIGINS=https://a.example,https://b.example` to allow specific origins. Credentials are never allowed.

**Request IDs and safe errors**
- Every response includes an `X-Request-ID` header (taken from the incoming request if present, otherwise generated).
- The ID appears in server logs for that request.
- Errors return a generic message plus the request ID, e.g. `Internal error while triaging (request_id=3f2a…)`. Full details stay in the server logs only.
- The validation-error (422) handler was registered incorrectly and probably never ran. It's now attached to `RequestValidationError`.

**Streamlit UI** (in `docker-compose.yml`)
- The Streamlit app runs the pipeline in-process and has no auth of its own.
- It's now bound to `127.0.0.1:8501`, so it's reachable only from the server itself. Put it behind an authenticating proxy before exposing it.

**Files:** `src/triageops/api.py`, `src/triageops/web/app.js`, `docker-compose.yml`

---

## 5. Unsafe `truncate` suggestion

### The problem
For disk-full incidents, the offline engine recommended:

```bash
truncate -s 0 /var/log/application.log    # labelled: low risk
```

That permanently deletes the log, often the very evidence you need for the incident. No safety rule caught it.

### What we changed
- **New safety rule** in `safety.py` flags `truncate -s 0`, `truncate --size=0`, and `: > /path` as risky. The suggested alternative is `logrotate -f`, or archiving before clearing.
- The offline engine now suggests `logrotate -f /etc/logrotate.d/<app>`, which keeps a compressed copy.
- Offline steps that change state (`docker update`, `kubectl set env`, `logrotate -f`) are now labelled **medium** risk instead of low.

**Files:** `src/triageops/safety.py`, `src/triageops/llm.py`

---

## New configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | – | Use the Gemini API directly |
| `GOOGLE_CLOUD_PROJECT` / `VERTEX_PROJECT` | – | Use Vertex AI (no hardcoded default any more) |
| `TRIAGEOPS_API_KEYS` | empty (open) | Comma-separated API keys for protected endpoints |
| `TRIAGEOPS_RATE_LIMIT_PER_MIN` | `20` | `/triage` requests per client per minute, per worker; `0` disables |
| `TRIAGEOPS_CORS_ORIGINS` | empty (CORS off) | Allowed browser origins |
| `TRIAGEOPS_ALLOW_OFFLINE_FALLBACK` | `0` | `1` = use offline heuristic when the LLM fails (instead of 503) |
| `TRIAGEOPS_FORCE_OFFLINE` | `0` | `1` = never call the LLM (demo mode) |

Generate an API key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## API behaviour changes

| Situation | Before | After |
|---|---|---|
| LLM down / quota exceeded | `200` with fabricated High-confidence report | `503` + `Retry-After: 30` (or a `degraded` report if fallback is enabled) |
| Missing / wrong API key (keys configured) | `200` | `401` + `WWW-Authenticate: Bearer` |
| Too many requests | unlimited | `429` + `Retry-After` |
| Unexpected server error | `500` with raw exception text | `500` with generic message + `request_id` |
| Every response | – | `X-Request-ID` header |
| `/health` | `status`, `version`, `runbooks_loaded` | adds `llm_provider`, `auth_enabled` |
| `/triage` response | – | adds `engine`, `degraded` (also inside `data`) |

---

## How to verify on your server

```bash
# 1. Install and run the tests
pip install -e ".[dev]"
pytest -v

# 2. Configure and start
export GOOGLE_CLOUD_PROJECT=<your-project>        # or GEMINI_API_KEY=...
export TRIAGEOPS_API_KEYS=<generated-key>
uvicorn triageops.api:app --host 0.0.0.0 --port 8000
# Behind nginx / a load balancer, add:
#   --proxy-headers --forwarded-allow-ips=<proxy-ip>

# 3. Health shows provider + auth
curl -s localhost:8000/health
# -> {"status":"ok", ..., "llm_provider":"vertex_ai", "auth_enabled":true}

# 4. Auth is enforced
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/triage \
  -H 'Content-Type: application/json' -d '{"text":"pod CrashLoopBackOff"}'
# -> 401

# 5. Authorised request works, and reports its engine
curl -s -X POST localhost:8000/triage -H "X-API-Key: <generated-key>" \
  -H 'Content-Type: application/json' -d '{"text":"pod CrashLoopBackOff exit code 1"}' \
  | python -c "import sys,json; r=json.load(sys.stdin); print(r['engine'], r['degraded'])"
# -> vertex_ai False

# 6. Rate limit (default 20/min): the 21st request in a minute returns 429
for i in $(seq 1 21); do curl -s -o /dev/null -w "%{http_code} " -X POST localhost:8000/triage \
  -H "X-API-Key: <generated-key>" -H 'Content-Type: application/json' -d '{"text":"disk full"}'; done; echo
```

**What the tests cover:** `tests/test_api_and_fallback.py` (new) checks that failures fail closed, that degraded reports are labelled correctly, that the engine is recorded, auth (header and bearer), rate limiting, the 503 and 500 responses (no leaked details), and that there's no wildcard CORS. `tests/test_safety.py` adds the truncation rules. CI now runs the new test file.

## Things to know

- **You must configure a provider.** Without `GOOGLE_CLOUD_PROJECT` or `GEMINI_API_KEY`, the server runs in degraded offline mode (the old code quietly fell back to the hardcoded project).
- **Golden suite scores may drop with a live model.** LLM errors now fail the test case instead of being covered by canned answers. The new number reflects what the LLM actually does.
- **Rate limits are per process.** Use a gateway or Redis-backed limiter for multi-replica deployments.

## What's next

The next improvements, in priority order:

1. **Allowlist-based command safety:** classify commands as read-only or mutating, default unknown commands to medium risk, and add blast-radius labels (pod / namespace / cluster / data).
2. **Better secret redaction:** stop redacting image digests and git SHAs; add Slack, Stripe, Google API key, and JWT patterns.
3. **Smarter truncation:** keep the head, the tail, and lines matching error signatures, instead of only the last 400 lines.
4. **Docker / CI hardening:** multi-stage image, lockfile, no dev dependencies, real `/health` check in CI, Trivy scan, SBOM, blocking mypy, golden suite as a scheduled regression gate.
5. **Observability:** Prometheus metrics (per-stage latency, tokens, cost, fallback rate), OpenTelemetry tracing, JSON logs in production.
6. **Integrations:** Alertmanager / PagerDuty webhooks in, Slack reports out.
