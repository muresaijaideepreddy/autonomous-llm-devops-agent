from agents.planner import planner_agent
from agents.tester import tester_agent
from agents.executor import executor_agent
from agents.failure_analysis import failure_analysis_agent
from agents.healer import healing_hook

from datetime import datetime, timezone
import json
import os
import uuid

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

COVERAGE_THRESHOLD = 98
ENABLE_COVERAGE_HEALING = True
TEST_DIR = "tests"

# ─────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────

def run_pipeline(repo_event: dict) -> dict:
    print("🔹 Starting Autonomous CI Pipeline")

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    start_time = datetime.now(timezone.utc)

    pipeline_state = {
        "run_id": run_id,
        "planner_output": None,
        "tester_output": None,
        "executor_output": None,
        "failure_analysis": None,
        "start_time": start_time.isoformat(),
        "end_time": None
    }

    # ─────────────────────────────────────────
    # 1️⃣ PLANNER
    # ─────────────────────────────────────────
    print("\n🔹 Running Planner Agent...")
    planner_output = planner_agent(repo_event)
    pipeline_state["planner_output"] = planner_output

    # ─────────────────────────────────────────
    # 2️⃣ TESTER (FREEZE TESTS ONCE THEY EXIST)
    # ─────────────────────────────────────────
    print("\n🔹 Running Tester Agent...")

    os.makedirs(TEST_DIR, exist_ok=True)
    existing_tests = [
        os.path.join(TEST_DIR, f)
        for f in os.listdir(TEST_DIR)
        if f.startswith("test_") and f.endswith(".py")
    ]

    if existing_tests:
        print("🔒 Reusing existing tests (coverage already converged)")
        tester_output = {
            "test_files_created": existing_tests,
            "num_tests_generated": 0
        }
    else:
        tester_output = tester_agent(planner_output)

    pipeline_state["tester_output"] = tester_output

    # ─────────────────────────────────────────
    # 3️⃣ EXECUTOR
    # ─────────────────────────────────────────
    print("\n🔹 Running Executor Agent...")
    executor_output = executor_agent({
        "execution_strategy": "pytest",
        "test_files": tester_output["test_files_created"]
    })
    pipeline_state["executor_output"] = executor_output

    status = executor_output.get("status")
    coverage = executor_output.get("coverage_percent")

    # ─────────────────────────────────────────
    # 4️⃣ ONE‑SHOT COVERAGE HEALING (ONLY ONCE)
    # ─────────────────────────────────────────
    if (
        ENABLE_COVERAGE_HEALING
        and status == "pass"
        and coverage is not None
        and coverage < COVERAGE_THRESHOLD
    ):
        print(f"\n🧠 Coverage Healing triggered ({coverage:.2f}%)")

        try:
            executor_output = healing_hook(
                planner_output=planner_output,
                executor_output=executor_output
            )
            pipeline_state["executor_output"] = executor_output

            status = executor_output.get("status", status)
            coverage = executor_output.get("coverage_percent", coverage)

        except Exception as e:
            print("⚠️ Coverage healing skipped:", e)

    # ─────────────────────────────────────────
    # 5️⃣ FAILURE ANALYSIS
    # ─────────────────────────────────────────
    if status in ("fail", "error"):
        print("\n🔍 Running Failure Analysis Agent...")
        failure_analysis = failure_analysis_agent(executor_output)
        pipeline_state["failure_analysis"] = failure_analysis

        next_step = failure_analysis.get("next_step")

        if next_step == "suggest_code_fix":
            print("🛠️ Code bug detected")
        elif next_step == "regenerate_tests":
            print("🔁 Test bug detected")
        elif next_step == "regenerate_tests_for_coverage":
            print("📉 Coverage gap detected")
        elif next_step == "manual_review":
            print("👨‍💻 Manual review required")
        else:
            print(f"⚠️ Unhandled pipeline action: {next_step}")

    # ─────────────────────────────────────────
    # 6️⃣ FINAL STATUS
    # ─────────────────────────────────────────
    if status == "pass":
        print("\n✅ CI PASSED")
        if coverage is not None:
            print(f"📊 Coverage : {coverage:.2f}%")

    elif status == "fail":
        passed = executor_output.get("passed_tests", 0)
        failed = len(executor_output.get("failed_tests", []))

        print("\nTest Results Summary")
        print(f"Passed : {passed}")
        print(f"Failed : {failed}")

        if coverage is not None:
            print(f"📊 Coverage : {coverage:.2f}%")

    else:
        print("\n🚨 CI Infrastructure Error")

    # ─────────────────────────────────────────
    # 7️⃣ SAVE METRICS
    # ─────────────────────────────────────────
    os.makedirs("metrics", exist_ok=True)

    metrics = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "coverage": coverage,
        "execution_time_ms": executor_output.get("execution_time_ms", 0)
    }

    with open("metrics/run_metrics.json", "a") as f:
        f.write(json.dumps(metrics) + "\n")

    # ─────────────────────────────────────────
    # 8️⃣ SAVE RUN STATE
    # ─────────────────────────────────────────
    os.makedirs("runs", exist_ok=True)
    pipeline_state["end_time"] = datetime.now(timezone.utc).isoformat()

    with open(f"runs/{run_id}.json", "w") as f:
        json.dump(pipeline_state, f, indent=2)

    return pipeline_state


# ─────────────────────────────────────────────
# MANUAL RUN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    repo_event = {
        "changed_files": ["src/payments.py"],
        "commit_id": "abc123",
        "issue": {
            "id": 1,
            "title": "Negative payment amount causes crash",
            "description": "System crashes when payment amount is negative",
            "severity": "high"
        }
    }

    run_pipeline(repo_event)
