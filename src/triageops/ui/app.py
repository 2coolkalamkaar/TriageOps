"""
TriageOps Streamlit UI

A functional, clean interface for the TriageOps backend.
Focus is on the backend — this UI is intentionally straightforward
and will be upgraded to a production-grade frontend later.

Run with:
    streamlit run src/triageops/ui/app.py
"""

import json
import sys
import time
from pathlib import Path

import streamlit as st

# Add src to path so we can import triageops directly
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from triageops.pipeline import run_triage
from triageops.render import to_json, to_markdown

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="TriageOps — DevOps Incident Triage",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS — clean, professional dark theme
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .main-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 24px 32px;
        margin-bottom: 24px;
    }
    .main-header h1 { color: #e2e8f0; font-size: 28px; font-weight: 700; margin: 0; letter-spacing: -0.5px; }
    .main-header p { color: #94a3b8; font-size: 14px; margin: 4px 0 0 0; }
    .badge {
        display: inline-block;
        background: #1e40af; color: #bfdbfe;
        font-size: 11px; font-weight: 600;
        padding: 2px 8px; border-radius: 100px;
        letter-spacing: 0.5px; margin-left: 8px;
    }

    .stTextArea textarea {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 13px !important;
    }

    .stButton > button {
        font-weight: 600; font-size: 15px;
        border-radius: 8px; width: 100%;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### ⚙️ Settings")
    output_format = st.radio("Output Format", ["Markdown", "JSON"], index=0, horizontal=True)

    st.divider()
    st.markdown("### 📋 Example Inputs")

    EXAMPLES = {
        "K8s CrashLoopBackOff": (
            "Name: web-api-7d9f8b4-xkpqr\nNamespace: production\n"
            "Containers:\n  web-api:\n    State: Waiting\n      Reason: CrashLoopBackOff\n"
            "    Last State: Terminated\n      Exit Code: 1\n    Restart Count: 8\n\n"
            "Pod logs:\nlevel=fatal msg=\"Required environment variable MY_DB_URL is not set\""
        ),
        "Docker OOMKilled": (
            "docker inspect api-container\nOOMKilled: true\nExitCode: 137\n\n"
            "docker stats: MEM USAGE / LIMIT: 512MiB / 512MiB  MEM%: 100.00%\n\n"
            "dmesg: Out of memory: Kill process 24601 (python3) score 900"
        ),
        "Disk Full": (
            "df -h\n/dev/sda1  100G  100G  0  100%  /\n\n"
            "journalctl -u nginx:\n"
            "write() to \"/var/log/nginx/access.log\" failed (28: No space left on device)\n\n"
            "du -sh /var/log/*:\n44G  /var/log/application.log"
        ),
        "Vague Input": "my app is not working please help",
        "Secret + Destructive": (
            "kubectl get pods -n staging\nNAME: worker-6f7d8  STATUS: CrashLoopBackOff\n\n"
            "Config:\nAPI_KEY=ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890ab\n"
            "Should I run 'kubectl delete namespace staging --force' to fix it?"
        ),
    }

    for label, example_text in EXAMPLES.items():
        if st.button(f"📄 {label}", key=f"ex_{label}", use_container_width=True):
            st.session_state["input_text"] = example_text
            st.rerun()

    st.divider()
    st.markdown("### ℹ️ About")
    st.markdown(
        "**TriageOps** is a 7-step DevOps triage pipeline:\n\n"
        "1. 🔒 Secret redaction\n"
        "2. 🏷️ LLM classifier\n"
        "3. 🚦 Scope gate\n"
        "4. 📚 Runbook retrieval\n"
        "5. 🧠 Root cause analysis\n"
        "6. ⚠️ Command safety review\n"
        "7. 📋 Report assembly"
    )

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------

st.markdown("""
<div class="main-header">
    <h1>🔧 TriageOps <span class="badge">v0.1</span></h1>
    <p>DevOps Incident Triage Agent — paste logs or error messages to get a classified, safety-checked incident report</p>
</div>
""", unsafe_allow_html=True)

input_text = st.text_area(
    "Paste your error message, log output, or problem description",
    value=st.session_state.get("input_text", ""),
    height=220,
    placeholder=(
        "kubectl describe pod web-7d9\n"
        "Status: CrashLoopBackOff\n"
        "Exit Code: 1\n"
        "...\n\n"
        "Tip: Use the sidebar examples to try pre-built test cases"
    ),
    key="input_area",
)

col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    run_btn = st.button("🚀 Run Triage", type="primary", use_container_width=True)
with col2:
    if st.button("🗑️ Clear", use_container_width=True):
        st.session_state["input_text"] = ""
        st.rerun()
with col3:
    st.metric("Chars", f"{len(input_text or ''):,}")

# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------

if run_btn and input_text and input_text.strip():
    with st.spinner("🔍 Running triage pipeline..."):
        t0 = time.time()
        try:
            report = run_triage(input_text)
            elapsed_ms = int((time.time() - t0) * 1000)
        except Exception as e:
            st.error(f"❌ Pipeline error: {e}")
            st.stop()

    st.divider()

    # Metrics
    cls = report.classification
    analysis = report.analysis
    type_icons = {"Kubernetes": "☸️", "Docker": "🐳", "Server": "🖥️", "Mixed": "🔀", "Unknown": "❓"}
    sev_icons = {"P1": "🔴", "P2": "🟠", "P3": "🟡", "P4": "🟢"}
    conf_icons = {"High": "✅", "Medium": "🟡", "Low": "🔴"}
    conf_level = analysis.confidence.level if analysis else "N/A"

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Type", f"{type_icons.get(cls.type, '')} {cls.type}")
    m2.metric("Severity", f"{sev_icons.get(cls.severity, '')} {cls.severity}")
    m3.metric("Confidence", f"{conf_icons.get(conf_level, '')} {conf_level}")
    m4.metric("Secrets", len(report.secrets_found))
    m5.metric("Time", f"{elapsed_ms}ms")

    if report.degraded:
        st.warning(
            "⚠️ **DEGRADED MODE** — produced by the offline keyword heuristic, not the LLM. "
            "Treat it as a generic checklist, not a diagnosis of your system."
        )

    # Declined
    if report.declined:
        st.warning(f"⛔ **Out of Scope**\n\n{report.decline_message}")

    # Security alert
    if report.secrets_found:
        with st.expander("🔐 Security Alert — Secrets Detected & Redacted", expanded=True):
            st.error(
                "⚠️ Sensitive credentials were found and redacted before sending to the LLM.\n"
                "**Rotate these immediately — treat them as compromised.**"
            )
            for s in report.secrets_found:
                st.markdown(f"- `{s}`")

    # Command warnings
    if report.command_warnings:
        with st.expander(f"⚠️ Safety Warnings — {len(report.command_warnings)} Risky Command(s)", expanded=True):
            for w in report.command_warnings:
                st.markdown(f"**Command:** `{w.command}`")
                st.error(f"**Risk:** {w.reason}")
                if w.safer_alternative:
                    st.info(f"**Safer alternative:** {w.safer_alternative}")
                st.divider()

    # Report
    st.subheader("📋 Incident Report")
    tab_md, tab_json = st.tabs(["📄 Markdown", "🔢 JSON"])

    with tab_md:
        st.markdown(to_markdown(report))

    with tab_json:
        st.json(json.loads(to_json(report)))

    # Downloads
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.download_button(
            "⬇️ Download Markdown",
            data=to_markdown(report),
            file_name="triageops-report.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with col_d2:
        st.download_button(
            "⬇️ Download JSON",
            data=to_json(report),
            file_name="triageops-report.json",
            mime="application/json",
            use_container_width=True,
        )

elif run_btn:
    st.warning("Please paste some input to triage.")

else:
    st.info(
        "👆 Paste an error message, log, or `kubectl`/`docker`/`journalctl` output above "
        "and click **Run Triage**.\n\n"
        "Or pick one of the **example inputs** from the sidebar →"
    )
