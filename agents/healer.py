import json
import os
from agents.tester import tester_agent
from agents.executor import executor_agent

COVERAGE_THRESHOLD = 98


def healing_hook(planner_output: dict, executor_output: dict) -> dict:
    """
    Coverage Healer Agent
    Triggered ONLY when:
    - All tests pass
    - Coverage < threshold
    """

    print("🧠 Coverage Healer triggered...")

    coverage_percent = executor_output.get("coverage_percent")
    if coverage_percent is None or coverage_percent >= COVERAGE_THRESHOLD:
        print("✅ Coverage already sufficient, skipping healer")
        return executor_output

    # -----------------------------
    # 1️⃣ Load coverage.json
    # -----------------------------
    if not os.path.exists("coverage.json"):
        print("❌ coverage.json not found")
        return executor_output

    with open("coverage.json") as f:
        coverage_data = json.load(f)

    uncovered_files = {}
    for file, data in coverage_data.get("files", {}).items():
        missing = data.get("missing_lines", [])
        if missing:
            uncovered_files[file] = missing

    if not uncovered_files:
        print("✅ No uncovered lines found")
        return executor_output

    print("📉 Coverage gaps detected:")
    for f, lines in uncovered_files.items():
        print(f"  - {f}: {len(lines)} uncovered lines")

    # -----------------------------
    # 2️⃣ Ask Tester Agent to generate
    #     tests ONLY for uncovered lines
    # -----------------------------
    healer_plan = {
        "modules_to_test": [
            os.path.splitext(os.path.basename(f))[0]
            for f in uncovered_files.keys()
            if f.startswith("src/")
        ],
        "risk_level": "high",
        "coverage_context": uncovered_files,  # 🔑 NEW
    }

    tester_output = tester_agent(healer_plan)

    # -----------------------------
    # 3️⃣ Re‑run executor
    # -----------------------------
    executor_output = executor_agent({
        "test_files": tester_output["test_files_created"]
    })

    executor_output["healed"] = True
    executor_output["coverage_gap_fixed"] = True

    return executor_output
