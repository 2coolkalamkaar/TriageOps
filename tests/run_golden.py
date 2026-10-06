#!/usr/bin/env python3
"""
Golden test harness — runs the full pipeline against all test cases in tests/golden/
and scores each rule.

Requires a live Vertex AI setup (GOOGLE_CLOUD_PROJECT env var).

Usage:
    python tests/run_golden.py
    python tests/run_golden.py --case k8s_crashloop_env_var
    python tests/run_golden.py --verbose
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from triageops.pipeline import run_triage
from triageops.render import to_markdown

# ---------------------------------------------------------------------------
# Rule evaluators
# ---------------------------------------------------------------------------

def evaluate(report, test_case: dict) -> list[tuple[str, bool, str]]:
    """
    Evaluate a report against a test case's expect rules.
    Returns list of (rule_name, passed, detail).
    """
    results = []
    expect = test_case.get("expect", {})
    cls = report.classification
    analysis = report.analysis

    # classification.type
    if "classification.type" in expect:
        expected = expect["classification.type"]
        if isinstance(expected, list):
            passed = cls.type in expected
            detail = f"got={cls.type}, expected one of {expected}"
        else:
            passed = cls.type == expected
            detail = f"got={cls.type}, expected={expected}"
        results.append(("classification.type", passed, detail))

    # classification.in_scope
    if "classification.in_scope" in expect:
        passed = cls.in_scope == expect["classification.in_scope"]
        results.append((
            "classification.in_scope",
            passed,
            f"got={cls.in_scope}, expected={expect['classification.in_scope']}",
        ))

    # classification.severity
    if "classification.severity" in expect:
        expected = expect["classification.severity"]
        if isinstance(expected, list):
            passed = cls.severity in expected
            detail = f"got={cls.severity}, expected one of {expected}"
        else:
            passed = cls.severity == expected
            detail = f"got={cls.severity}, expected={expected}"
        results.append(("classification.severity", passed, detail))

    # declined
    if "declined" in expect:
        passed = report.declined == expect["declined"]
        results.append(("declined", passed, f"got={report.declined}, expected={expect['declined']}"))

    # secrets_found_min
    if "secrets_found_min" in expect:
        n = len(report.secrets_found)
        passed = n >= expect["secrets_found_min"]
        results.append((
            "secrets_found_min",
            passed,
            f"found={n}, required>={expect['secrets_found_min']}",
        ))

    # command_warnings_min
    if "command_warnings_min" in expect:
        n = len(report.command_warnings)
        passed = n >= expect["command_warnings_min"]
        results.append((
            "command_warnings_min",
            passed,
            f"warnings={n}, required>={expect['command_warnings_min']}",
        ))

    # command_warnings_max
    if "command_warnings_max" in expect:
        n = len(report.command_warnings)
        passed = n <= expect["command_warnings_max"]
        results.append((
            "command_warnings_max",
            passed,
            f"warnings={n}, max_allowed={expect['command_warnings_max']}",
        ))

    if analysis is None:
        if not report.declined:
            results.append(("analysis_present", False, "Analysis is None but report is not declined"))
        return results

    # analysis.confidence.level
    if "analysis.confidence.level" in expect:
        expected = expect["analysis.confidence.level"]
        level = analysis.confidence.level
        if isinstance(expected, list):
            passed = level in expected
            detail = f"got={level}, expected one of {expected}"
        else:
            passed = level == expected
            detail = f"got={level}, expected={expected}"
        results.append(("confidence.level", passed, detail))

    # must_mention — check in full markdown render
    if "must_mention" in expect:
        md = to_markdown(report).lower()
        for phrase in expect["must_mention"]:
            passed = phrase.lower() in md
            results.append((
                f"must_mention[{phrase!r}]",
                passed,
                "found" if passed else "NOT found in report",
            ))

    # must_not_mention — check in full markdown render (excluding Safety Warnings section where dangerous commands are legitimately warned against)
    if "must_not_mention" in expect:
        md_text = to_markdown(report)
        if "### ⚠️ Safety Warnings" in md_text:
            parts = md_text.split("### ⚠️ Safety Warnings")
            post = parts[1]
            rest = ""
            for heading in ["## ❓ Clarifying Questions", "## ✅ Verification", "## 🛡️ Prevention"]:
                if heading in post:
                    rest = post[post.index(heading):]
                    break
            md_text = parts[0] + rest
        md = md_text.lower()
        for phrase in expect["must_not_mention"]:
            passed = phrase.lower() not in md
            results.append((
                f"must_not_mention[{phrase!r}]",
                passed,
                "not found (good)" if passed else "FOUND in report (bad)",
            ))

    # must_not_mention_in_root_cause
    if "must_not_mention_in_root_cause" in expect:
        rc = analysis.root_cause.lower()
        for phrase in expect["must_not_mention_in_root_cause"]:
            passed = phrase.lower() not in rc
            results.append((
                f"root_cause_not_mention[{phrase!r}]",
                passed,
                "not found (good)" if passed else "FOUND in root_cause (bad)",
            ))

    # must_not_suggest — verify dangerous commands are not in recommended fix steps
    if "must_not_suggest" in expect:
        fix_cmds = " ".join((step.command or "").lower() for step in analysis.fix_steps)
        for phrase in expect["must_not_suggest"]:
            passed = phrase.lower() not in fix_cmds
            results.append((
                f"must_not_suggest[{phrase!r}]",
                passed,
                "not suggested in fix steps (good)" if passed else "SUGGESTED in fix steps (bad)",
            ))

    # must_mention_security — check in security notes section
    if "must_mention_security" in expect:
        md = to_markdown(report).lower()
        for phrase in expect["must_mention_security"]:
            passed = phrase.lower() in md
            results.append((
                f"security_mention[{phrase!r}]",
                passed,
                "found" if passed else "NOT found in report",
            ))

    # must_warn_commands
    if "must_warn_commands" in expect:
        warned_cmds = " ".join(w.command.lower() for w in report.command_warnings)
        warned_cmds += " " + to_markdown(report).lower()
        for cmd_pattern in expect["must_warn_commands"]:
            passed = cmd_pattern.lower() in warned_cmds
            results.append((
                f"must_warn[{cmd_pattern!r}]",
                passed,
                "found in warnings" if passed else "NOT found in warnings",
            ))

    # clarifying_questions_min
    if "clarifying_questions_min" in expect:
        n = len(analysis.clarifying_questions)
        passed = n >= expect["clarifying_questions_min"]
        results.append((
            "clarifying_questions_min",
            passed,
            f"questions={n}, required>={expect['clarifying_questions_min']}",
        ))

    return results


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_golden_tests(golden_dir: Path, case_filter: str | None, verbose: bool, delay: int = 5) -> int:
    """Run all golden tests and return exit code (0=all pass, 1=failures)."""
    cases = sorted(golden_dir.glob("*.json"))
    if not cases:
        print("No golden test cases found.")
        return 1

    if case_filter:
        cases = [c for c in cases if case_filter in c.stem]
        if not cases:
            print(f"No cases matching filter: {case_filter!r}")
            return 1

    total_rules = 0
    passed_rules = 0
    failed_cases = []

    print(f"\n{'='*60}")
    print("  TriageOps Golden Test Suite")
    print(f"  Running {len(cases)} case(s)  [inter-case delay: {delay}s]")
    print(f"{'='*60}\n")

    for case_path in cases:
        test_case = json.loads(case_path.read_text())
        name = test_case.get("name", case_path.stem)
        desc = test_case.get("description", "")
        input_text = test_case["input"]

        print(f"▶ {name}")
        if verbose and desc:
            print(f"  {desc}")

        start = time.monotonic()
        try:
            report = run_triage(input_text)
            latency = int((time.monotonic() - start) * 1000)
        except Exception as exc:
            print(f"  ❌ PIPELINE ERROR: {exc}\n")
            failed_cases.append(name)
            continue

        rule_results = evaluate(report, test_case)
        case_pass = all(p for _, p, _ in rule_results)

        for rule, passed, detail in rule_results:
            icon = "✅" if passed else "❌"
            print(f"  {icon} {rule}: {detail}")
            total_rules += 1
            if passed:
                passed_rules += 1

        status = "PASS" if case_pass else "FAIL"
        print(f"  → {status} ({latency}ms)\n")

        if not case_pass:
            failed_cases.append(name)

        if verbose:
            print("  --- Markdown Report ---")
            for line in to_markdown(report).split("\n")[:20]:
                print(f"  {line}")
            print("  ...\n")

        if delay > 0:
            print(f"  ⏱  Waiting {delay}s before next case...\n")
            time.sleep(delay)

    # Summary
    print(f"{'='*60}")
    print(f"  Results: {passed_rules}/{total_rules} rules passed")
    if failed_cases:
        print(f"  Failed cases: {', '.join(failed_cases)}")
    else:
        print("  All cases passed! 🎉")
    print(f"{'='*60}\n")

    return 0 if not failed_cases else 1


def main():
    parser = argparse.ArgumentParser(description="Run TriageOps golden test suite")
    parser.add_argument("--case", help="Filter by case name substring")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show report excerpts")
    parser.add_argument("--delay", type=int, default=5, help="Seconds to wait between cases (default: 5)")
    args = parser.parse_args()

    golden_dir = Path(__file__).parent / "golden"
    sys.exit(run_golden_tests(golden_dir, args.case, args.verbose, delay=args.delay))


if __name__ == "__main__":
    main()
