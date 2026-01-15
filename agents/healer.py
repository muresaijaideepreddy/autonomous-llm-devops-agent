import json
import os

COVERAGE_THRESHOLD = 98

def healing_hook(planner_output: dict, executor_output: dict) -> dict:
    """
    Coverage Healer (CODE-ONLY)
    ---------------------------
    Runs ONLY when:
      - Tests PASS
      - Coverage < threshold

    Responsibilities:
      ✔ Detect unreachable / ignorable code
      ✔ Suggest or apply safe exclusions
      ❌ MUST NOT generate tests
      ❌ MUST NOT call tester_agent
    """

    print("🧠 Coverage Healer triggered (code-only)")

    coverage = executor_output.get("coverage_percent")
    status = executor_output.get("status")

    # Safety checks
    if status != "pass":
        print("⛔ Tests did not pass — healer skipped")
        return executor_output

    if coverage is None or coverage >= COVERAGE_THRESHOLD:
        print("✅ Coverage acceptable — healer skipped")
        return executor_output

    if not os.path.exists("coverage.json"):
        print("⚠ coverage.json not found — healer skipped")
        return executor_output

    # -----------------------------
    # Load coverage report
    # -----------------------------
    with open("coverage.json") as f:
        coverage_data = json.load(f)

    dead_code_candidates = []

    for file, data in coverage_data.get("files", {}).items():
        missing_lines = data.get("missing_lines", [])

        # Healer is conservative:
        # Only consider very small gaps as potential dead code
        if 0 < len(missing_lines) <= 2:
            dead_code_candidates.append({
                "file": file,
                "lines": missing_lines
            })

    if not dead_code_candidates:
        print("ℹ No safe dead-code candidates found")
        return executor_output

    # -----------------------------
    # Report findings (NO mutation)
    # -----------------------------
    print("🩹 Potential dead / ignorable code detected:")

    for item in dead_code_candidates:
        print(f"  - {item['file']} → lines {item['lines']}")

    # Healer does NOT modify code automatically
    # It only reports safe candidates
    executor_output["healer_report"] = {
        "dead_code_candidates": dead_code_candidates,
        "action": "review_or_ignore"
    }

    executor_output["healed"] = False
    executor_output["coverage_healer_ran"] = True

    return executor_output
