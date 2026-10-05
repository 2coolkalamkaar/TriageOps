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
# Custom CSS — clean, professional
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    /* Import font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    /* Base */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Header */
    .main-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 24px 32px;
        margin-bottom: 24px;
    }

    .main-header h1 {
        color: #e2e8f0;
        font-size: 28px;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.5px;
    }

    .main-header p {
        color: #94a3b8;
        font-size: 14px;
        margin: 4px 0 0 0;
    }

    .badge {
        display: inline-block;
        background: #1e40af;
        color: #bfdbfe;
        font-size: 11px;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 100px;
        letter-spacing: 0.5px;
        margin-left: 8px;
    }

    /* Metric cards */
    .metric-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 16px 20px;
        text-align: center;
    }

    .metric-label {
        color: #64748b;
        font-size: 12px;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 4px;
    }

    .metric-value {
        color: #e2e8f0;
        font-size: 22px;
        font-weight: 700;
    }

    /* Severity badges */
    .sev-p1 { color: #ef4444; font-weight: 700; }
    .sev-p2 { color: #f97316; font-weight: 700; }
    .sev-p3 { color: #eab308; font-weight: 700; }
    .sev-p4 { color: #22c55e; font-weight: 700; }

    /* Report area */
    .report-container {
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 10px;
        padding: 24px;
        font-family: 'Inter', sans-serif;
    }

    /* Input area */
    .stTextArea textarea {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 13px !important;
        background: #0f172a !important;
        border: 1px solid #334155 !important;
        color: #e2e8f0 !important;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #0f172a;
        border-right: 1px solid #1e293b;
    }

    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #2563eb, #1d4ed8);
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        font-size: 15px;
        padding: 12px 32px;
        width: 100%;
        transition: all 0.2s;
    }

    .stButton > button:hover {
        background: linear-gradient(135deg, #1d4ed8, #1e40af);
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4);
    }

    /* Warning box */
    .warning-box {
        background: #431407;
        border: 1px solid #9a3412;
        border-left: 4px solid #f97316;
        border-radius: 8px;
        padding: 12px 16px;
        margin: 8px 0;
    }

    /* Security box */
    .security-box {
        background: #1c1917;
        border: 1px solid #44403c;
        border-left: 4px solid #ef4444;
        border-radius: 8px;
        padding: 12px 16px;
        margin: 8px 0;
    }

    /* Hide streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar — settings & examples
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### ⚙️ Settings")

    output_format = st.radio(
        "Output Format",
        ["Markdown", "JSON"],
        index=0,
        horizontal=True,
    )

    st.divider()

    st.markdown("### 📋 Example Inputs")

    EXAMPLES = {
        "K8s CrashLoopBackOff": (
            "Name: web-api-7d9f8b4-xkpqr\nNamespace: production\n"
            "Status: Running\n\nContainers:\n  web-api:\n"
            "    State: Waiting\n      Reason: CrashLoopBackOff\n"
            "    Last State: Terminated\n      Reason: Error\n"
            "      Exit Code: 1\n    Restart Count: 8\n\n"
            "Pod logs (--previous):\n"
            "level=fatal msg=\"Required environment variable MY_DB_URL is not set\""
        ),
        "Docker OOMKilled": (
            "docker inspect api-container\n"
            "OOMKilled: true\nExitCode: 137\n\n"
            "docker stats --no-stream:\n"
            "MEM USAGE / LIMIT: 512MiB / 512MiB  MEM%: 100.00%\n\n"
            "dmesg: Out of memory: Kill process 24601 (python3) score 900"
        ),
        "Disk Full": (
            "df -h\n/dev/sda1  100G  100G  0  100%  /\n\n"
            "journalctl -u nginx:\n"
            "write() to \"/var/log/nginx/access.log\" failed (28: No space left on device)\n\n"
            "du -sh /var/log/*:\n44G  /var/log/application.log"
        ),
        "Vague Input": "my app is not working please help",
        "With Secret (test)": (
            "kubectl get pods -n staging\nNAME: worker-6f7d8  STATUS: CrashLoopBackOff\n\n"
            "Config snippet:\nAPI_KEY=ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890ab\n"
            "Should I run 'kubectl delete namespace staging --force' to fix it?"
        ),
    }

    for label, example_text in EXAMPLES.items():
        if st.button(f"📄 {label}", key=f"ex_{label}", use_container_width=True):
            st.session_state["input_text"] = example_text

    st.divider()
    st.markdown("### ℹ️ About")
    st.markdown("""
    **TriageOps** classifies and diagnoses infrastructure failures using a 7-step pipeline:
    - 🔒 Secret redaction
    - 🏷️ LLM classifier
    - 🔍 Runbook retrieval
    - 🧠 Root cause analysis
    - ⚠️ Safety command review
    - 📋 Incident report
    """)


# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------

# Header
st.markdown("""
<div class="main-header">
    <h1>🔧 TriageOps <span class="badge">v0.1</span></h1>
    <p>DevOps Incident Triage Agent — paste logs or errors to get a classified, safety-checked incident report</p>
</div>
""", unsafe_allow_html=True)

# Input
input_text = st.text_area(
    "Paste your error message, log output, or problem description",
    value=st.session_state.get("input_text", ""),
    height=220,
    placeholder="kubectl describe pod web-7d9\nStatus: CrashLoopBackOff\nExit Code: 1\n...",
    key="input_area",
    label_visibility="visible",
)

col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    run_btn = st.button("🚀 Run Triage", type="primary", use_container_width=True)
with col2:
    if st.button("🗑️ Clear", use_container_width=True):
        st.session_state["input_text"] = ""
        st.rerun()
with col3:
    char_count = len(input_text) if input_text else 0
    st.metric("Characters", f"{char_count:,}", label_visibility="visible")

# ---------------------------------------------------------------------------
# Run pipeline
# ---------------------------------------------------------------------------

if run_btn and input_text.strip():
    with st.spinner("Running triage pipeline..."):
        start_ts = time.time()
        try:
            report = run_triage(input_text)
            elapsed = int((time.time() - start_ts) * 1000)
        except Exception as e:
            st.error(f"Pipeline error: {e}")
            st.stop()

    st.divider()

    # ------------------------------------------------------------------
    # Metrics row
    # ------------------------------------------------------------------
    cls = report.classification
    analysis = report.analysis

    sev_colors = {"P1": "🔴", "P2": "🟠", "P3": "🟡", "P4": "🟢"}
    type_icons = {"Kubernetes": "☸️", "Docker": "🐳", "Server": "🖥️", "Mixed": "🔀", "Unknown": "❓"}
    conf_colors = {"High": "✅", "Medium": "🟡", "Low": "🔴"}

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Issue Type", f"{type_icons.get(cls.type, '')} {cls.type}")
    with m2:
        st.metric("Severity", f"{sev_colors.get(cls.severity, '')} {cls.severity}")
    with m3:
        conf_level = analysis.confidence.level if analysis else "N/A"
        st.metric("Confidence", f"{conf_colors.get(conf_level, '')} {conf_level}")
    with m4:
        st.metric("Secrets Found", len(report.secrets_found))
    with m5:
        st.metric("Pipeline Time", f"{elapsed}ms")

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------
    if report.declined:
        st.warning(f"⛔ **Out of Scope:** {report.decline_message}")

    if report.secrets_found:
        with st.expander("🔐 Security Alert — Secrets Detected", expanded=True):
            st.error(
                "Sensitive information was detected and **redacted** from your input. "
                "Rotate these credentials immediately."
            )
            for s in report.secrets_found:
                st.markdown(f"- `{s}`")

    if report.command_warnings:
        with st.expander(f"⚠️ Command Safety Warnings ({len(report.command_warnings)})", expanded=True):
            for w in report.command_warnings:
                st.markdown(f"**Command:** `{w.command}`")
                st.markdown(f"**Risk:** {w.reason}")
                if w.safer_alternative:
                    st.markdown(f"**Safer:** {w.safer_alternative}")
                st.divider()

    # ------------------------------------------------------------------
    # Report output
    # ------------------------------------------------------------------
    st.subheader("📋 Incident Report")

    if output_format == "JSON":
        st.json(json.loads(to_json(report)))
    else:
        md_output = to_markdown(report)
        st.markdown(md_output)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            "⬇️ Download Markdown",
            data=to_markdown(report),
            file_name="triageops-report.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with col_dl2:
        st.download_button(
            "⬇️ Download JSON",
            data=to_json(report),
            file_name="triageops-report.json",
            mime="application/json",
            use_container_width=True,
        )

elif run_btn and not input_text.strip():
    st.warning("Please paste some input to triage.")

# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------
else:
    st.markdown("""
    <div style="text-align: center; padding: 48px 24px; color: #64748b;">
        <div style="font-size: 48px; margin-bottom: 16px;">🔍</div>
        <div style="font-size: 18px; font-weight: 600; color: #94a3b8; margin-bottom: 8px;">
            Ready to Triage
        </div>
        <div style="font-size: 14px;">
            Paste your error logs, kubectl output, docker logs, or systemctl status
            and click <strong>Run Triage</strong>
        </div>
        <div style="font-size: 13px; margin-top: 16px;">
            Or pick an example from the sidebar ←
        </div>
    </div>
    """, unsafe_allow_html=True)
