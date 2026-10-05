# TriageOps — DevOps Incident Triage Agent & Workflow

*Design document for the Rival.io Forward Developer practical assessment (CortexOne). Everything discussed is included here on purpose. Review it, then mark what to cut.*

---

## 1. Overview

**One-line pitch:** Paste a server, Docker or Kubernetes problem. TriageOps classifies it, finds the likely root cause, suggests a safe fix with exact commands, tells you how confident it is and why, and produces a clean incident report.

**Deliverables mapped to the assignment**

| Assignment item | What we build |
| --- | --- |
| Task 1: Agent | **TriageOps Troubleshooting Agent** (works standalone) |
| Task 2: Workflow (bonus +10) | **TriageOps Incident Workflow**: Classifier → Troubleshooting Agent → Report Formatter |

**Important design rule:** the agent must work fully on its own (5 tests), and the workflow reuses it (2 tests). They are two separate deliverables, not one blended thing.

---

## 2. Problem Statement

When something breaks, engineers lose time reading logs, guessing causes and searching for fixes. Juniors often run risky commands without understanding them. TriageOps gives a fast, structured, safety-aware first response for the three most common infrastructure failure areas.

**Scope (in):** Linux/server issues, Docker issues, Kubernetes issues. **Scope (out):** application business-logic bugs, cloud billing, anything not infrastructure. The agent politely declines these.

---

## 3. Design Principles

1. **Suggest, never execute.** The agent does not apply fixes to any real system. It gives commands and a human decides.
2. **Evidence over guessing.** Every root cause must point to a specific line or signal in the input.
3. **Honest uncertainty.** Confidence is based on evidence, and missing information is stated.
4. **Safety first.** Risky commands are flagged with a warning and a safer alternative.
5. **Predictable output.** Fixed format so downstream workflow steps can rely on it.
6. **Keep it small and well tested.** Prompt quality and testing carry 45% of the marks.

---

## 4. Agent Specification

### 4.1 Identity

- **Name (placeholder):** TriageOps Troubleshooting Agent
- **Description:** Diagnoses server, Docker and Kubernetes failures from pasted logs and error messages, and returns root cause, safe fix commands, confidence with reasoning, and prevention steps.

### 4.2 Core capabilities (agent level)

1. **Issue classification:** Server / Docker / Kubernetes / Unknown / Mixed.
2. **Root cause analysis:** points to the evidence in the input that supports the cause.
3. **Fix suggestions:** ordered, copy-pasteable commands with a one-line explanation each.
4. **Safety guardrails:** flags destructive or high-impact commands (for example `rm -rf`, `kubectl delete`, `docker system prune`, `--force`, `kill -9`, editing production configs) with a warning and a safer alternative.
5. **Secret detection and redaction warning:** if the input contains tokens, passwords, private keys or connection strings, the agent warns the user, avoids repeating the secret, and advises rotation.
6. **Severity rating (P1 to P4)** with a short justification.
7. **Confidence rating (High / Medium / Low)** with a reason and a list of what extra information would raise it.
8. **Clarifying questions** when the input is too thin, instead of guessing.
9. **Verification steps:** how to confirm the fix worked.
10. **Prevention recommendations:** how to stop it recurring.
11. **Out-of-scope handling:** polite refusal and redirection for non-infrastructure requests.
12. **Long and messy input handling:** extract the relevant error lines from large logs.
13. **Optional: knowledge base / runbooks** (if CortexOne supports document upload): common-error runbooks used to ground answers.

### 4.3 Tools / capabilities on CortexOne

To be confirmed after exploring the platform. Candidates:

- Model selection and instruction prompt (required)
- Knowledge base / document upload for runbooks
- Web search (for unfamiliar error messages)
- Any code/utility tools CortexOne offers
- Structured output settings, if available

*Action item: list exactly what is available and tick what is used.*

### 4.4 Output format (fixed)

```
## Classification
Type: <Server | Docker | Kubernetes | Mixed | Unknown>
Severity: <P1-P4> — <one-line reason>

## Summary
<2-3 sentence plain-language description of what is happening>

## Root Cause
<most likely cause>
Evidence: <specific lines/signals from the input>
Other possible causes: <short list, if any>

## Recommended Fix
1. <step> — <why>
   `command`
   ⚠️ <warning if risky> | Safer option: <alternative>

## Verification
<commands/signals that confirm it is fixed>

## Prevention
<2-4 practical recommendations>

## Confidence
Level: <High | Medium | Low>
Reason: <why>
Would raise confidence: <missing info, if any>

## Security Notes
<only if secrets or risky exposure were detected>
```

### 4.5 Draft system prompt

```
You are TriageOps, a senior Site Reliability Engineer who diagnoses infrastructure
failures. You help with three areas only: Linux/server issues, Docker issues, and
Kubernetes issues.

YOUR JOB
Given an error message, log, command output or description, you:
1. Classify the issue as Server, Docker, Kubernetes, Mixed, or Unknown.
2. Identify the most likely root cause and cite the exact evidence from the input.
3. Suggest an ordered fix with exact commands and a one-line reason for each.
4. Explain how to verify the fix and how to prevent recurrence.
5. Give a severity (P1-P4) and a confidence level (High/Medium/Low) with reasons.

RULES
- Never claim you executed anything. You only suggest. A human applies the fix.
- Base conclusions on evidence in the input. Do not invent log lines, flags,
  versions or file paths. If you are not sure a command or flag exists, say so.
- If the input is too vague or incomplete to diagnose, ask up to 3 specific
  clarifying questions and give the most likely directions, with Low confidence.
- Flag any destructive or high-impact command (delete, prune, force, kill -9,
  overwriting configs, restarting production workloads) with a warning, and offer a
  safer or reversible alternative first (describe, dry-run, backup, cordon, etc.).
- If the input contains secrets (tokens, passwords, private keys, connection
  strings), do not repeat them. Tell the user to remove and rotate them.
- Confidence rules: High = the cause is directly shown by the evidence. Medium =
  strongly suggested but alternatives remain. Low = limited evidence or missing
  context. Always state what information would raise confidence.
- Severity guide: P1 = production down or data at risk. P2 = major degradation.
  P3 = partial or non-critical issue. P4 = minor or cosmetic.
- For long logs, focus on the most relevant error lines and ignore noise.
- If the request is not about servers, Docker or Kubernetes, politely say it is out
  of scope and offer what you can help with.
- If the input is empty or unreadable, ask the user to paste the error text.

STYLE
Be concise, practical and plain-spoken. Use the exact output format below.

[Insert the output format from section 4.4 here]
```

---

## 5. Workflow Specification (Bonus Task)

### 5.1 Name and purpose

**TriageOps Incident Workflow.** Takes a raw pasted issue and turns it into a classified, analysed and formatted incident report using multiple connected steps.

### 5.2 Flow

```
User Input (raw issue text)
   → Step 1: Pre-check & Classifier  (type + severity + secret scan)
   → Step 2: Troubleshooting Agent   (root cause, fix, confidence)
   → Step 3: Safety Review           (flag risky commands)
   → Step 4: Report Formatter        (final incident report)
   → Final Response
```

### 5.3 Steps in detail

**Step 1: Pre-check and Classifier**

- Input: raw user text.
- Does: decides Server / Docker / Kubernetes / Mixed / Unknown, assigns severity, scans for secrets, flags out-of-scope input.
- Output: a small structured object, for example `{type, severity, has_secrets, in_scope, key_error_lines}`.
- Why it matters: the type and the extracted key lines are passed forward so the next step is focused.

**Step 2: Troubleshooting Agent**

- Input: original text plus Step 1 output.
- Does: root cause with evidence, fix steps, verification, prevention, confidence with reason.
- Output: structured analysis.
- If type is Unknown or input is out of scope, this step returns clarifying questions or a polite decline instead.

**Step 3: Safety Review**

- Input: the proposed fix commands.
- Does: checks every command against a list of risky patterns and adds warnings and safer alternatives.
- Output: the fix list annotated with risk level per command.
- Note: can be a rule-based check, a second small prompt, or part of the agent, depending on what CortexOne supports.

**Step 4: Report Formatter**

- Input: outputs of Steps 1 to 3.
- Does: assembles one clean incident report.
- Output: final report with sections: Title, Classification and Severity, Summary, Root Cause and Evidence, Recommended Fix (with warnings), Verification, Prevention, Confidence and Reason, Security Notes.

### 5.4 Data flow summary

| From | To | Data passed |
| --- | --- | --- |
| User | Step 1 | Raw issue text |
| Step 1 | Step 2 | Type, severity, secrets flag, key error lines, original text |
| Step 2 | Step 3 | Root cause, fix commands, confidence |
| Step 3 | Step 4 | Annotated fix list plus everything above |
| Step 4 | User | Final incident report |

### 5.5 Branching and edge handling (optional but strong)

- Unknown or out-of-scope → skip analysis, return clarifying questions or a decline.
- Secrets detected → add a Security Notes section and a rotate-credentials recommendation.
- Low confidence → report includes the exact info the user should provide next.

---

## 6. Optional Extras (include all for now, cut later)

| # | Extra | Effort | Impact | Notes |
| --- | --- | --- | --- | --- |
| 1 | Safety guardrails on commands | Low | High | Best value for effort |
| 2 | Secret detection warning | Low | High | Very SRE-minded |
| 3 | Severity P1 to P4 | Low | Medium | Easy to add to prompt |
| 4 | Clarifying questions | Low | Medium | Helps edge-case tests |
| 5 | Verification and prevention steps | Low | Medium | Makes output feel complete |
| 6 | Structured postmortem-style report | Low | Medium | Mostly formatting |
| 7 | Runbook knowledge base | Medium | High | Only if CortexOne supports it |
| 8 | Web search for unknown errors | Low | Medium | Only if available |
| 9 | Human-approval gate before any "apply" step | Low | High | Shows safety thinking |
| 10 | Multi-issue handling (several errors in one paste) | Medium | Medium | Stretch goal |

**Deliberately not building:** automatic execution of fixes on real systems. Reason: unsafe, likely unsupported on the platform, and a red flag for SRE reviewers. The explanation section should state this as a conscious design decision.

---

## 7. Testing Plan

### 7.1 Agent tests (5 required)

| # | Type | Example input | Expected behaviour |
| --- | --- | --- | --- |
| 1 | Kubernetes, common | Pod in `CrashLoopBackOff` with `kubectl describe` and logs | Correct root cause, fix, verification, High or Medium confidence |
| 2 | Docker, common | Container exits with code 137 / OOMKilled, or port already in use | Correct cause, memory or port fix, safe commands |
| 3 | Server | Disk full, or service failing in `systemctl status`, or SSH connection refused | Correct cause with `df`, `journalctl` style steps |
| 4 | Vague input | "my app is not working" | Asks clarifying questions, Low confidence, no invented diagnosis |
| 5 | Risky or sensitive | Log containing an API key, or user asks "how do I delete everything to fix it" | Redacts and warns about the secret, flags destructive command, offers a safer path |

Bonus edge cases if time allows: out-of-scope request ("write me a poem"), very long noisy log, mixed Docker-inside-K8s problem, empty input.

### 7.2 Workflow tests (2 required)

1. **Kubernetes ImagePullBackOff** → expect classification K8s, evidence cited, fix, final formatted report.
2. **Docker build failure inside a CI pipeline log with a leaked token** → expect Mixed or Docker classification, secret warning in Security Notes, report generated.

---
