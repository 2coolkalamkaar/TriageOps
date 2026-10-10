/**
 * TriageOps — Incident Command Center Application Logic
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const rawLogInput = document.getElementById("rawLogInput");
  const runTriageBtn = document.getElementById("runTriageBtn");
  const btnSpinner = document.getElementById("btnSpinner");
  const btnIcon = document.getElementById("btnIcon");
  const btnText = document.getElementById("btnText");
  const clearBtn = document.getElementById("clearBtn");
  const pasteBtn = document.getElementById("pasteBtn");
  const logFileUpload = document.getElementById("logFileUpload");
  const charCountLabel = document.getElementById("charCountLabel");
  const lineCountLabel = document.getElementById("lineCountLabel");
  const liveSecretWarning = document.getElementById("liveSecretWarning");

  // Output Containers
  const emptyStatePlaceholder = document.getElementById("emptyStatePlaceholder");
  const loadingState = document.getElementById("loadingState");
  const loadingStatusText = document.getElementById("loadingStatusText");
  const activeReportView = document.getElementById("activeReportView");
  const markdownView = document.getElementById("markdownView");
  const jsonView = document.getElementById("jsonView");
  const rawMarkdownContent = document.getElementById("rawMarkdownContent");
  const rawJsonContent = document.getElementById("rawJsonContent");

  // Stepper Elements
  const step1 = document.getElementById("step1");
  const step2 = document.getElementById("step2");
  const step3 = document.getElementById("step3");
  const step4 = document.getElementById("step4");
  const pipelineTimingLabel = document.getElementById("pipelineTimingLabel");

  // Report Elements
  const severityBadge = document.getElementById("severityBadge");
  const severityLabel = document.getElementById("severityLabel");
  const componentBadge = document.getElementById("componentBadge");
  const componentIcon = document.getElementById("componentIcon");
  const componentLabel = document.getElementById("componentLabel");
  const latencyBadge = document.getElementById("latencyBadge");
  const latencyVal = document.getElementById("latencyVal");

  const confidenceLevelText = document.getElementById("confidenceLevelText");
  const confidenceFill = document.getElementById("confidenceFill");
  const confidenceReasonText = document.getElementById("confidenceReasonText");
  const confidenceRaiseBlock = document.getElementById("confidenceRaiseBlock");
  const confidenceRaiseText = document.getElementById("confidenceRaiseText");

  const securityAlertCard = document.getElementById("securityAlertCard");
  const secretsBadgeContainer = document.getElementById("secretsBadgeContainer");
  const declineCard = document.getElementById("declineCard");
  const declineMessageText = document.getElementById("declineMessageText");

  const summaryCard = document.getElementById("summaryCard");
  const incidentSummaryText = document.getElementById("incidentSummaryText");
  const clarifyingBlock = document.getElementById("clarifyingBlock");
  const clarifyingList = document.getElementById("clarifyingList");

  const rootCauseCard = document.getElementById("rootCauseCard");
  const rootCauseText = document.getElementById("rootCauseText");
  const evidenceList = document.getElementById("evidenceList");
  const otherCausesBlock = document.getElementById("otherCausesBlock");
  const otherCausesList = document.getElementById("otherCausesList");

  const commandWarningsCard = document.getElementById("commandWarningsCard");
  const warningListContainer = document.getElementById("warningListContainer");

  const fixPlaybookCard = document.getElementById("fixPlaybookCard");
  const fixStepsContainer = document.getElementById("fixStepsContainer");

  const verificationContainer = document.getElementById("verificationContainer");
  const preventionContainer = document.getElementById("preventionContainer");
  const matchedRunbooksList = document.getElementById("matchedRunbooksList");
  const runbookCountBadge = document.getElementById("runbookCountBadge");

  // Drawers
  const runbookDrawer = document.getElementById("runbookDrawer");
  const closeDrawerBtn = document.getElementById("closeDrawerBtn");
  const drawerRunbookTitle = document.getElementById("drawerRunbookTitle");
  const drawerContent = document.getElementById("drawerContent");
  const runbookLibraryBtn = document.getElementById("runbookLibraryBtn");

  const historyDrawer = document.getElementById("historyDrawer");
  const closeHistoryBtn = document.getElementById("closeHistoryBtn");
  const historyToggleBtn = document.getElementById("historyToggleBtn");
  const historyList = document.getElementById("historyList");

  // Tabs
  const tabDashboard = document.getElementById("tabDashboard");
  const tabMarkdown = document.getElementById("tabMarkdown");
  const tabJson = document.getElementById("tabJson");

  // Export buttons
  const copyMdBtn = document.getElementById("copyMdBtn");
  const copyJsonBtn = document.getElementById("copyJsonBtn");
  const downloadBtn = document.getElementById("downloadBtn");
  const copyRawMdBtn = document.getElementById("copyRawMdBtn");
  const copyRawJsonBtn = document.getElementById("copyRawJsonBtn");

  // State
  let currentReportData = null;
  let currentMarkdownText = "";
  let triageHistory = [];

  // --------------------------------------------------------------------------
  // Presets Data
  // --------------------------------------------------------------------------
  const PRESETS = {
    k8s_real_cluster: `Name:                 payment-gateway-5cc8b7bb78-dwpd9
Namespace:            production
Priority Class Name:  production-critical
Controlled By:        ReplicaSet/payment-gateway-5cc8b7bb78
Node:                 sre-agent-cluster-worker/172.18.0.3

Containers:
  payment-gateway:
    Image:         python:3.11-alpine
    Command:
      python3 -c
      import time, sys
      print("[INFO] Payment Gateway starting up...")
      print("[INFO] Allocating memory buffer for payment processing batch...")
      buf = bytearray(128 * 1024 * 1024)  # 128 MB allocation
      time.sleep(3600)
    State:          Waiting
      Reason:       CrashLoopBackOff
    Last State:     Terminated
      Reason:       OOMKilled
      Exit Code:    137
      Started:      Mon, 05 Oct 2026 06:46:05 +0000
      Finished:     Mon, 05 Oct 2026 06:46:12 +0000
    Restart Count:  101
    Limits:
      cpu:     100m
      memory:  32Mi
    Requests:
      cpu:     50m
      memory:  16Mi

Events:
  Warning  BackOff     45s (x127 over 30m)  kubelet   Back-off restarting failed container payment-gateway in pod payment-gateway-5cc8b7bb78-dwpd9_production
  Normal   Logging     10s                  kopf      [handler] production/payment-gateway-5cc8b7bb78-dwpd9 -> error_state=OOMKilled deployment=payment-gateway
  Warning  OOMKilling  10s                  kernel    Memory cgroup out of memory: Killed process 4192 (python3) total-vm:189440kB, anon-rss:32768kB, file-rss:128kB`,

    k8s_live_imagepull: `Name:         payment-service-78bb68978d-2ghhh
Namespace:    production
Node:         sre-agent-cluster-worker/172.18.0.3
Controlled By: ReplicaSet/payment-service-78bb68978d

Containers:
  payment-app:
    Image:   nginx:this-tag-does-not-exist-123
    State:   Waiting
      Reason: ImagePullBackOff
    Ready:   False

Events:
  Normal   Scheduled  15m                    default-scheduler  Successfully assigned production/payment-service-78bb68978d-2ghhh to sre-agent-cluster-worker
  Normal   Pulling    13m (x4 over 15m)      kubelet            Pulling image "nginx:this-tag-does-not-exist-123"
  Warning  Failed     13m (x4 over 15m)      kubelet            Failed to pull image "nginx:this-tag-does-not-exist-123": rpc error: code = NotFound desc = failed to pull and unpack image: not found
  Warning  Failed     13m (x4 over 15m)      kubelet            Error: ErrImagePull
  Normal   BackOff    2m41s (x125 over 27m)  kubelet            Back-off pulling image "nginx:this-tag-does-not-exist-123"
  Warning  Failed     2m41s (x125 over 27m)  kubelet            Error: ImagePullBackOff`,

    k8s_crashloop: `Name:         web-api-7d9f8b4-xkpqr
Namespace:    production
Status:       Running

Conditions:
  Ready           False

Containers:
  web-api:
    Image:         myregistry/web-api:v2.3.1
    State:         Waiting
      Reason:      CrashLoopBackOff
    Last State:    Terminated
      Reason:      Error
      Exit Code:   1
      Started:     Mon, 04 Oct 2026 22:10:05 +0000
      Finished:    Mon, 04 Oct 2026 22:10:06 +0000
    Ready:         False
    Restart Count: 8
    Limits:
      memory: 256Mi
    Requests:
      memory: 128Mi
    Environment:
      NODE_ENV:  production

Events:
  Warning  BackOff  2m   kubelet  Back-off restarting failed container

--- Pod logs (--previous) ---
time="2026-10-04T22:10:05Z" level=info msg="Starting web-api server"
time="2026-10-04T22:10:05Z" level=fatal msg="Required environment variable MY_DB_URL is not set" error="env: MY_DB_URL not found"`,

    docker_oom: `$ docker inspect api-container | python3 -c "import sys,json; s=json.load(sys.stdin)[0]['State']; print(s)"
{'Status': 'exited', 'Running': False, 'Paused': False, 'Restarting': False, 'OOMKilled': True, 'ExitCode': 137, 'Error': '', 'StartedAt': '2026-10-04T20:00:01Z', 'FinishedAt': '2026-10-04T20:14:33Z'}

$ docker stats --no-stream api-container
CONTAINER ID   NAME            CPU %     MEM USAGE / LIMIT     MEM %     NET I/O
deadbeef1234   api-container   0.00%     512MiB / 512MiB       100.00%   1.5GB / 800MB

$ dmesg | grep -i oom | tail -5
[1234567.890] Out of memory: Kill process 24601 (python3) score 900 or sacrifice child
[1234568.001] Killed process 24601 (python3) total-vm:1048576kB, anon-rss:524288kB`,

    server_disk: `$ df -h
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       100G  100G     0 100% /
tmpfs           7.8G     0  7.8G   0% /dev/shm
/dev/sdb1       500G  120G  380G  24% /data

$ journalctl -u nginx -n 20 --no-pager
Oct 04 23:01:15 web-01 nginx[1234]: write() to "/var/log/nginx/access.log" failed (28: No space left on device)
Oct 04 23:01:15 web-01 nginx[1234]: *12345 open() "/var/cache/nginx/proxy_temp/1" failed (28: No space left on device)
Oct 04 23:01:16 web-01 nginx[1234]: nginx: [alert] worker process 5678 exited on signal 6

$ du -sh /var/* 2>/dev/null | sort -rh | head -5
45G    /var/log
18G    /var/lib
1.2G   /var/cache
800M   /var/tmp
120M   /var/run

$ du -sh /var/log/* 2>/dev/null | sort -rh | head -5
44G    /var/log/application.log
500M   /var/log/syslog
200M   /var/log/auth.log`,

    leaked_secret: `I'm having issues with my Kubernetes cluster. Here's what I see:

kubectl get pods -n staging
NAME                    READY   STATUS             RESTARTS   AGE
worker-6f7d8-xkpqr      0/1     CrashLoopBackOff   12         1h

Here is the relevant config snippet:
DATABASE_URL=postgres://admin:SuperSecretPassword999@db.internal:5432/mydb
API_KEY=ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890ab

Should I just run 'kubectl delete namespace staging --force' and start fresh?
Or maybe 'rm -rf /etc/kubernetes' to reset everything?`,

    k8s_imagepull: `Name:         frontend-74b88-m9xzt
Namespace:    production
Status:       Pending

Containers:
  frontend:
    Image:          private.ecr.aws/myorg/frontend:v3.4.1
    State:          Waiting
      Reason:       ImagePullBackOff
    Ready:          False

Events:
  Normal   Scheduled   45s   default-scheduler   Successfully assigned production/frontend-74b88-m9xzt to worker-node-2
  Normal   Pulling     44s   kubelet             Pulling image "private.ecr.aws/myorg/frontend:v3.4.1"
  Warning  Failed      22s   kubelet             Failed to pull image "private.ecr.aws/myorg/frontend:v3.4.1": rpc error: code = Unknown desc = failed to pull and unpack image: failed to resolve reference "private.ecr.aws/myorg/frontend:v3.4.1": unexpected status code [manifests v3.4.1]: 401 Unauthorized
  Warning  Failed      22s   kubelet             Error: ImagePullBackOff
  Normal   BackOff     9s    kubelet             Back-off pulling image "private.ecr.aws/myorg/frontend:v3.4.1"`,

    vague: `my app is not working please help`
  };

  // --------------------------------------------------------------------------
  // Initialize Defaults
  // --------------------------------------------------------------------------
  loadHistoryFromStorage();
  fetchRunbooksMeta();

  // Load first preset by default
  rawLogInput.value = PRESETS.k8s_real_cluster;
  updateEditorStats();
  checkClientSideSecrets();

  // --------------------------------------------------------------------------
  // Editor Event Listeners
  // --------------------------------------------------------------------------
  rawLogInput.addEventListener("input", () => {
    updateEditorStats();
    checkClientSideSecrets();
  });

  rawLogInput.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      executeTriage();
    }
  });

  clearBtn.addEventListener("click", () => {
    rawLogInput.value = "";
    updateEditorStats();
    checkClientSideSecrets();
    rawLogInput.focus();
  });

  pasteBtn.addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        rawLogInput.value = text;
        updateEditorStats();
        checkClientSideSecrets();
        showToast("Pasted from clipboard", "success");
      }
    } catch {
      rawLogInput.focus();
      document.execCommand("paste");
    }
  });

  logFileUpload.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      rawLogInput.value = event.target.result;
      updateEditorStats();
      checkClientSideSecrets();
      showToast(`Loaded file: ${file.name}`, "success");
    };
    reader.readAsText(file);
  });

  // Preset Chips Clicking
  document.querySelectorAll(".preset-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".preset-chip").forEach(c => c.classList.remove("active-preset"));
      chip.classList.add("active-preset");
      const key = chip.getAttribute("data-preset");
      if (PRESETS[key]) {
        rawLogInput.value = PRESETS[key];
        updateEditorStats();
        checkClientSideSecrets();
        executeTriage();
      }
    });
  });

  // Run Triage Button
  runTriageBtn.addEventListener("click", () => {
    executeTriage();
  });

  // --------------------------------------------------------------------------
  // Tabs Navigation
  // --------------------------------------------------------------------------
  const tabs = [
    { btn: tabDashboard, view: "dashboard" },
    { btn: tabMarkdown, view: "markdown" },
    { btn: tabJson, view: "json" },
  ];

  tabs.forEach(t => {
    t.btn.addEventListener("click", () => {
      tabs.forEach(item => item.btn.classList.remove("active"));
      t.btn.classList.add("active");
      switchView(t.view);
    });
  });

  function switchView(viewName) {
    if (viewName === "dashboard") {
      activeReportView.classList.remove("hidden");
      markdownView.classList.add("hidden");
      jsonView.classList.add("hidden");
    } else if (viewName === "markdown") {
      activeReportView.classList.add("hidden");
      markdownView.classList.remove("hidden");
      jsonView.classList.add("hidden");
    } else if (viewName === "json") {
      activeReportView.classList.add("hidden");
      markdownView.classList.add("hidden");
      jsonView.classList.remove("hidden");
    }
  }

  // --------------------------------------------------------------------------
  // Real-time Client Secret Scanner
  // --------------------------------------------------------------------------
  function checkClientSideSecrets() {
    const text = rawLogInput.value;
    const patterns = [
      /gh[pousr]_[A-Za-z0-9]{36,}/,
      /AKIA[0-9A-Z]{16}/,
      /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
      /(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*['"]?[^\s'"]{6,}['"]?/i
    ];

    const hasSecret = patterns.some(p => p.test(text));
    if (hasSecret) {
      liveSecretWarning.classList.remove("hidden");
    } else {
      liveSecretWarning.classList.add("hidden");
    }
  }

  function updateEditorStats() {
    const text = rawLogInput.value;
    charCountLabel.textContent = `${text.length} chars`;
    const lines = text ? text.split("\n").length : 0;
    lineCountLabel.textContent = `${lines} lines`;
  }

  // --------------------------------------------------------------------------
  // Core Triage Pipeline Execution
  // --------------------------------------------------------------------------
  async function executeTriage() {
    const text = rawLogInput.value.trim();
    if (!text) {
      showToast("Please enter an error message or log first.", "error");
      rawLogInput.focus();
      return;
    }

    // UI Loading state
    runTriageBtn.disabled = true;
    btnSpinner.classList.remove("hidden");
    btnIcon.classList.add("hidden");
    btnText.textContent = "Triaging...";

    emptyStatePlaceholder.classList.add("hidden");
    activeReportView.classList.add("hidden");
    markdownView.classList.add("hidden");
    jsonView.classList.add("hidden");
    loadingState.classList.remove("hidden");

    // Stepper Animation: Step 1
    resetStepper();
    step1.classList.add("active");
    loadingStatusText.textContent = "Scanning for Secrets & Masking...";

    const startTime = performance.now();

    try {
      // Step 2 simulation transition
      setTimeout(() => {
        step1.classList.remove("active");
        step1.classList.add("completed");
        step2.classList.add("active");
        loadingStatusText.textContent = "Classifying Infrastructure Component...";
      }, 150);

      // Step 3 simulation transition
      setTimeout(() => {
        step2.classList.remove("active");
        step2.classList.add("completed");
        step3.classList.add("active");
        loadingStatusText.textContent = "Retrieving Grounded Runbooks (BM25)...";
      }, 300);

      // Call API
      const jsonRes = await apiFetch("/triage", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, format: "json" })
      });

      if (!jsonRes.ok) {
        const err = await jsonRes.json().catch(() => ({}));
        const detail = typeof err.detail === "string" ? err.detail : null;
        if (jsonRes.status === 429) throw new Error("Rate limit exceeded — wait a minute and retry");
        throw new Error(detail || `Triage failed (HTTP ${jsonRes.status})`);
      }

      const jsonData = await jsonRes.json();
      const report = jsonData.data;
      const mdString = jsonData.markdown || "";

      // Step 4 complete
      step3.classList.remove("active");
      step3.classList.add("completed");
      step4.classList.add("active");
      loadingStatusText.textContent = "Enforcing Safety Guardrails & RCA...";

      setTimeout(() => {
        step4.classList.remove("active");
        step4.classList.add("completed");

        const elapsed = Math.round(performance.now() - startTime);
        pipelineTimingLabel.textContent = `${report.latency_ms || elapsed}ms`;

        // Render report
        renderIncidentReport(report, mdString);

        // Record history
        saveToHistory(report);

        loadingState.classList.add("hidden");
        switchView("dashboard");
        tabDashboard.classList.add("active");
        tabMarkdown.classList.remove("active");
        tabJson.classList.remove("active");

        if (report.degraded) {
          showToast("DEGRADED MODE: offline heuristic, not an LLM diagnosis", "error");
        } else {
          showToast("Triage dossier generated successfully", "success");
        }
      }, 200);

    } catch (err) {
      console.error(err);
      loadingState.classList.add("hidden");
      emptyStatePlaceholder.classList.remove("hidden");
      showToast(`Triage Error: ${err.message}`, "error");
      resetStepper();
    } finally {
      runTriageBtn.disabled = false;
      btnSpinner.classList.add("hidden");
      btnIcon.classList.remove("hidden");
      btnText.textContent = "Run Triage Analysis";
    }
  }

  function resetStepper() {
    [step1, step2, step3, step4].forEach(s => {
      s.classList.remove("active", "completed");
    });
    pipelineTimingLabel.textContent = "Ready";
  }

  // --------------------------------------------------------------------------
  // Render Incident Report
  // --------------------------------------------------------------------------
  function renderIncidentReport(report, markdownText) {
    currentReportData = report;
    currentMarkdownText = markdownText;

    // Raw views
    rawMarkdownContent.textContent = markdownText;
    rawJsonContent.textContent = JSON.stringify(report, null, 2);

    const cls = report.classification || {};
    const analysis = report.analysis || {};

    // 1. Severity Badge
    const sev = (cls.severity || "P3").toUpperCase();
    severityLabel.textContent = `${sev} ${getSeverityDesc(sev)}`;
    severityBadge.className = `incident-badge severity-badge ${sev.toLowerCase()}-badge`;

    // 2. Component Badge
    const comp = cls.type || "Unknown";
    componentLabel.textContent = comp;
    componentIcon.textContent = getComponentIcon(comp);

    // 3. Latency
    latencyVal.textContent = report.latency_ms || 4;

    // 4. Confidence Meter
    const conf = analysis.confidence || { level: "Low", reason: "Sparse details" };
    const level = (conf.level || "Low").toLowerCase();
    confidenceLevelText.textContent = conf.level;
    confidenceLevelText.className = `confidence-val ${level}`;
    confidenceFill.className = `confidence-fill ${level}`;
    confidenceFill.style.width = level === "high" ? "95%" : level === "medium" ? "65%" : "30%";
    confidenceReasonText.textContent = conf.reason || "Confidence based on supplied diagnostic logs.";

    if (conf.would_raise && conf.would_raise.length > 0) {
      confidenceRaiseBlock.classList.remove("hidden");
      confidenceRaiseText.textContent = Array.isArray(conf.would_raise) ? conf.would_raise.join(", ") : conf.would_raise;
    } else {
      confidenceRaiseBlock.classList.add("hidden");
    }

    // 5. Security Card
    if (report.secrets_found && report.secrets_found.length > 0) {
      securityAlertCard.classList.remove("hidden");
      secretsBadgeContainer.innerHTML = "";
      report.secrets_found.forEach(s => {
        const tag = document.createElement("span");
        tag.className = "secret-tag";
        tag.textContent = s;
        secretsBadgeContainer.appendChild(tag);
      });
    } else {
      securityAlertCard.classList.add("hidden");
    }

    // 6. Declined check
    if (report.declined) {
      declineCard.classList.remove("hidden");
      declineMessageText.textContent = report.decline_message || "This request was declined because it is out of infrastructure scope.";
      summaryCard.classList.add("hidden");
      rootCauseCard.classList.add("hidden");
      fixPlaybookCard.classList.add("hidden");
      document.querySelector(".dual-columns").classList.add("hidden");
      return;
    } else {
      declineCard.classList.add("hidden");
      summaryCard.classList.remove("hidden");
      rootCauseCard.classList.remove("hidden");
      fixPlaybookCard.classList.remove("hidden");
      document.querySelector(".dual-columns").classList.remove("hidden");
    }

    // 7. Executive Summary
    incidentSummaryText.textContent = analysis.summary || "Infrastructure incident triage completed.";

    // Clarifying Questions
    if (analysis.clarifying_questions && analysis.clarifying_questions.length > 0) {
      clarifyingBlock.classList.remove("hidden");
      clarifyingList.innerHTML = "";
      analysis.clarifying_questions.forEach(q => {
        const li = document.createElement("li");
        li.textContent = q;
        clarifyingList.appendChild(li);
      });
    } else {
      clarifyingBlock.classList.add("hidden");
    }

    // 8. Root Cause & Evidence
    rootCauseText.textContent = analysis.root_cause || "Root cause is under investigation.";

    evidenceList.innerHTML = "";
    if (analysis.evidence && analysis.evidence.length > 0) {
      analysis.evidence.forEach(ev => {
        const div = document.createElement("div");
        div.className = "evidence-line";
        div.textContent = ev;
        evidenceList.appendChild(div);
      });
    } else {
      const div = document.createElement("div");
      div.className = "evidence-line";
      div.textContent = "No verbatim line citations available.";
      evidenceList.appendChild(div);
    }

    // Differential causes
    if (analysis.other_causes && analysis.other_causes.length > 0) {
      otherCausesBlock.classList.remove("hidden");
      otherCausesList.innerHTML = "";
      analysis.other_causes.forEach(cause => {
        const chip = document.createElement("span");
        chip.className = "diff-chip";
        chip.textContent = cause;
        otherCausesList.appendChild(chip);
      });
    } else {
      otherCausesBlock.classList.add("hidden");
    }

    // 9. Command Warnings (Safety Guardrail)
    if (report.command_warnings && report.command_warnings.length > 0) {
      commandWarningsCard.classList.remove("hidden");
      warningListContainer.innerHTML = "";

      report.command_warnings.forEach(warn => {
        const item = document.createElement("div");
        item.className = "warning-item";

        const topRow = document.createElement("div");
        topRow.className = "warn-command-row";
        topRow.innerHTML = `<span class="warn-badge">Destructive</span> <code class="warn-cmd-text">${escapeHtml(warn.command)}</code>`;

        const reason = document.createElement("div");
        reason.className = "warn-reason";
        reason.textContent = `⚠️ ${warn.reason}`;

        item.appendChild(topRow);
        item.appendChild(reason);

        if (warn.safer_alternative) {
          const saferBox = document.createElement("div");
          saferBox.className = "warn-safer-box";
          saferBox.innerHTML = `
            <div>
              <span class="safer-label">Recommended Safer Alternative:</span>
              <code class="safer-cmd">${escapeHtml(warn.safer_alternative)}</code>
            </div>
            <button class="copy-icon-btn" title="Copy safe alternative" onclick="copyToClipboard('${escapeAttr(warn.safer_alternative)}')">📋</button>
          `;
          item.appendChild(saferBox);
        }

        warningListContainer.appendChild(item);
      });
    } else {
      commandWarningsCard.classList.add("hidden");
    }

    // 10. Fix Playbook Steps
    fixStepsContainer.innerHTML = "";
    if (analysis.fix_steps && analysis.fix_steps.length > 0) {
      analysis.fix_steps.forEach((step, idx) => {
        const card = document.createElement("div");
        card.className = "fix-step-card";

        const num = document.createElement("div");
        num.className = "step-badge-num";
        num.textContent = idx + 1;

        const content = document.createElement("div");
        content.className = "step-content";

        const lead = document.createElement("div");
        lead.className = "step-lead";
        lead.textContent = step.step;

        const why = document.createElement("div");
        why.className = "step-why";
        why.textContent = step.why;

        content.appendChild(lead);
        content.appendChild(why);

        if (step.command) {
          const codeRow = document.createElement("div");
          codeRow.className = "code-block-row";
          codeRow.innerHTML = `
            <code>${escapeHtml(step.command)}</code>
            <button class="copy-icon-btn" title="Copy command" onclick="copyToClipboard('${escapeAttr(step.command)}')">
              📋
            </button>
          `;
          content.appendChild(codeRow);
        }

        card.appendChild(num);
        card.appendChild(content);
        fixStepsContainer.appendChild(card);
      });
    }

    // 11. Verification
    verificationContainer.innerHTML = "";
    const verList = Array.isArray(analysis.verification) ? analysis.verification : [analysis.verification];
    verList.filter(Boolean).forEach(v => {
      const item = document.createElement("div");
      item.className = "check-item";
      item.innerHTML = `<span class="check-bullet">✓</span> <span>${escapeHtml(v)}</span>`;
      verificationContainer.appendChild(item);
    });

    // 12. Prevention
    preventionContainer.innerHTML = "";
    const prevList = Array.isArray(analysis.prevention) ? analysis.prevention : [analysis.prevention];
    prevList.filter(Boolean).forEach(p => {
      const item = document.createElement("div");
      item.className = "check-item";
      item.innerHTML = `<span class="prevention-bullet">•</span> <span>${escapeHtml(p)}</span>`;
      preventionContainer.appendChild(item);
    });

    // 13. Matched Runbooks Grounding
    matchedRunbooksList.innerHTML = "";
    const runbooks = report.runbooks_used || [];
    if (runbooks.length > 0) {
      runbooks.forEach(rb => {
        const chip = document.createElement("div");
        chip.className = "runbook-chip";
        chip.innerHTML = `<span>📖</span> <span>${escapeHtml(rb)}</span>`;
        chip.addEventListener("click", () => openRunbookDrawer(rb));
        matchedRunbooksList.appendChild(chip);
      });
    } else {
      matchedRunbooksList.innerHTML = `<span class="empty-state" style="padding:0">No specific runbooks triggered.</span>`;
    }
  }

  // --------------------------------------------------------------------------
  // Runbook Drawer
  // --------------------------------------------------------------------------
  async function openRunbookDrawer(runbookName) {
    drawerRunbookTitle.textContent = runbookName || "Runbook";
    drawerContent.innerHTML = `
      <div class="skeleton-loader">
        <div class="skeleton-line" style="width: 70%"></div>
        <div class="skeleton-line" style="width: 90%"></div>
        <div class="skeleton-line" style="width: 80%"></div>
      </div>
    `;
    runbookDrawer.classList.add("open");

    try {
      const res = await apiFetch(`/runbooks/${encodeURIComponent(runbookName)}`);
      if (!res.ok) throw new Error("Runbook not found");
      const data = await res.json();
      drawerContent.innerHTML = renderSimpleMarkdown(data.content);
    } catch {
      drawerContent.innerHTML = `<p class="empty-state">Could not load runbook details.</p>`;
    }
  }

  closeDrawerBtn.addEventListener("click", () => {
    runbookDrawer.classList.remove("open");
  });

  runbookLibraryBtn.addEventListener("click", async () => {
    drawerRunbookTitle.textContent = "Operational Runbook Index";
    runbookDrawer.classList.add("open");
    drawerContent.innerHTML = `<p>Loading available runbooks...</p>`;

    try {
      const res = await apiFetch("/runbooks");
      const data = await res.json();
      let html = `<h3>Loaded Runbooks (${data.count})</h3><ul>`;
      data.runbooks.forEach(rb => {
        html += `<li><a href="#" onclick="window.loadRunbookByName('${rb}'); return false;" style="color:var(--cyan); font-family:JetBrains Mono">${rb}</a></li>`;
      });
      html += `</ul>`;
      drawerContent.innerHTML = html;
    } catch {
      drawerContent.innerHTML = `<p class="empty-state">Failed to fetch runbooks list.</p>`;
    }
  });

  window.loadRunbookByName = (name) => {
    openRunbookDrawer(name);
  };

  // --------------------------------------------------------------------------
  // History Drawer
  // --------------------------------------------------------------------------
  historyToggleBtn.addEventListener("click", () => {
    renderHistoryItems();
    historyDrawer.classList.add("open");
  });

  closeHistoryBtn.addEventListener("click", () => {
    historyDrawer.classList.remove("open");
  });

  function saveToHistory(report) {
    const entry = {
      id: Date.now(),
      time: new Date().toLocaleTimeString(),
      severity: report.classification?.severity || "P3",
      type: report.classification?.type || "Unknown",
      summary: report.analysis?.summary || report.decline_message || "Triage incident",
      report: report
    };
    triageHistory.unshift(entry);
    if (triageHistory.length > 20) triageHistory.pop();
    try {
      localStorage.setItem("triageops_history", JSON.stringify(triageHistory));
    } catch {
      // storage full or disabled
    }
  }

  function loadHistoryFromStorage() {
    try {
      const saved = localStorage.getItem("triageops_history");
      if (saved) triageHistory = JSON.parse(saved);
    } catch {
      triageHistory = [];
    }
  }

  function renderHistoryItems() {
    historyList.innerHTML = "";
    if (triageHistory.length === 0) {
      historyList.innerHTML = `<p class="empty-state">No incidents triaged yet in this session.</p>`;
      return;
    }

    triageHistory.forEach(item => {
      const div = document.createElement("div");
      div.className = "history-item";
      div.innerHTML = `
        <div class="history-item-top">
          <span class="incident-badge severity-badge ${item.severity.toLowerCase()}-badge" style="padding:2px 8px;font-size:10px">${item.severity}</span>
          <span class="history-time">${item.time}</span>
        </div>
        <div style="font-size:12px;font-weight:600;color:#fff;margin-bottom:2px">${item.type}</div>
        <div class="history-summary">${escapeHtml(item.summary.slice(0, 90))}...</div>
      `;
      div.addEventListener("click", () => {
        renderIncidentReport(item.report, JSON.stringify(item.report, null, 2));
        historyDrawer.classList.remove("open");
        showToast("Restored incident from history", "success");
      });
      historyList.appendChild(div);
    });
  }

  async function fetchRunbooksMeta() {
    try {
      const res = await apiFetch("/runbooks");
      if (res.ok) {
        const data = await res.json();
        runbookCountBadge.textContent = `${data.count} Runbooks`;
      }
    } catch {
      // ignore
    }
  }

  // --------------------------------------------------------------------------
  // Clipboard and Exports
  // --------------------------------------------------------------------------
  copyMdBtn.addEventListener("click", () => copyToClipboard(currentMarkdownText));
  copyRawMdBtn.addEventListener("click", () => copyToClipboard(currentMarkdownText));
  copyJsonBtn.addEventListener("click", () => copyToClipboard(JSON.stringify(currentReportData, null, 2)));
  copyRawJsonBtn.addEventListener("click", () => copyToClipboard(JSON.stringify(currentReportData, null, 2)));

  downloadBtn.addEventListener("click", () => {
    if (!currentMarkdownText) return;
    const blob = new Blob([currentMarkdownText], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `incident_report_${Date.now()}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast("Downloaded incident_report.md", "success");
  });

  window.copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      showToast("Copied to clipboard", "success");
    } catch {
      showToast("Copy failed", "error");
    }
  };

  // Toast Notification
  function showToast(msg, type = "success") {
    const container = document.getElementById("toastContainer");
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${type === "success" ? "✓" : "⚠️"}</span> <span>${escapeHtml(msg)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transition = "opacity 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 2800);
  }

  // --------------------------------------------------------------------------
  // Utility Formatters
  // --------------------------------------------------------------------------
  function getSeverityDesc(sev) {
    switch (sev) {
      case "P1": return "CRITICAL";
      case "P2": return "HIGH";
      case "P3": return "MEDIUM";
      case "P4": return "LOW";
      default: return "";
    }
  }

  function getComponentIcon(comp) {
    switch (comp.toLowerCase()) {
      case "kubernetes": return "☸️";
      case "docker": return "🐳";
      case "server": return "💾";
      default: return "🖥️";
    }
  }

  // Authenticated fetch: sends the stored API key; on 401 asks for one and retries once.
  const API_KEY_STORAGE = "triageops_api_key";

  function getStoredApiKey() {
    try { return localStorage.getItem(API_KEY_STORAGE) || ""; } catch { return ""; }
  }

  function setStoredApiKey(key) {
    try {
      if (key) localStorage.setItem(API_KEY_STORAGE, key);
      else localStorage.removeItem(API_KEY_STORAGE);
    } catch { /* storage unavailable — key lives for this request only */ }
  }

  async function apiFetch(url, opts = {}, retried = false, keyOverride = null) {
    const key = keyOverride ?? getStoredApiKey();
    const headers = { ...(opts.headers || {}) };
    if (key) headers["X-API-Key"] = key;
    const res = await fetch(url, { ...opts, headers });
    if (res.status === 401 && !retried) {
      const entered = window.prompt("This TriageOps server requires an API key:");
      if (entered) {
        setStoredApiKey(entered.trim());
        return apiFetch(url, opts, true, entered.trim());
      }
    }
    if (res.status === 401) setStoredApiKey("");
    return res;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function escapeAttr(str) {
    if (!str) return "";
    return String(str).replace(/'/g, "\\'").replace(/"/g, "&quot;");
  }

  function renderSimpleMarkdown(md) {
    if (!md) return "";
    return md
      .replace(/^### (.*$)/gim, '<h3>$1</h3>')
      .replace(/^## (.*$)/gim, '<h2>$1</h2>')
      .replace(/^# (.*$)/gim, '<h1>$1</h1>')
      .replace(/```([a-z]*)\n([\s\S]*?)```/gim, '<pre><code>$2</code></pre>')
      .replace(/`([^`]+)`/gim, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/gim, '<strong>$1</strong>')
      .replace(/^\* (.*$)/gim, '<li>$1</li>')
      .replace(/^- (.*$)/gim, '<li>$1</li>')
      .replace(/\n\n/gim, '<br><br>');
  }
});
