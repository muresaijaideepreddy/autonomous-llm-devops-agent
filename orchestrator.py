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
    # 2️⃣ COLLECT CURRENT TESTS (IF ANY)
    # ─────────────────────────────────────────
    os.makedirs(TEST_DIR, exist_ok=True)
    test_files = [
        os.path.join(TEST_DIR, f)
        for f in os.listdir(TEST_DIR)
        if f.startswith("test_") and f.endswith(".py")
    ]

    # ─────────────────────────────────────────
    # 3️⃣ EXECUTOR (RUN EXISTING TESTS FIRST)
    # ─────────────────────────────────────────
    executor_output = None
    coverage = None
    status = None

    if test_files:
        print("\n🔹 Running Executor Agent (existing tests)...")
        executor_output = executor_agent({
            "execution_strategy": "pytest",
            "test_files": test_files
        })
        pipeline_state["executor_output"] = executor_output
        status = executor_output.get("status")
        coverage = executor_output.get("coverage_percent")

        if coverage is not None:
            print(f"📊 Current Coverage: {coverage:.2f}%")
    else:
        print("\nℹ️ No tests found yet")

    # ─────────────────────────────────────────
    # 4️⃣ DECISION: SHOULD AGENTS RUN?
    # ─────────────────────────────────────────
    if coverage is None or coverage < COVERAGE_THRESHOLD:
        print("\n🧪 Coverage below threshold → activating agents")

        # 4a️⃣ TESTER
        print("\n🔹 Running Tester Agent...")
        tester_output = tester_agent(planner_output)
        pipeline_state["tester_output"] = tester_output

        # 4b️⃣ EXECUTOR AGAIN (WITH NEW TESTS)
        print("\n🔹 Re-running Executor Agent...")
        executor_output = executor_agent({
            "execution_strategy": "pytest",
            "test_files": tester_output["test_files_created"]
        })
        pipeline_state["executor_output"] = executor_output

        status = executor_output.get("status")
        coverage = executor_output.get("coverage_percent")

        if coverage is not None:
            print(f"📊 Coverage after tester: {coverage:.2f}%")

        # 4 c️⃣  COVERAGE HEALER (ONLY IF TESTS PASS)
        if (
            ENABLE_COVERAGE_HEALING
            and status == "pass"
            and coverage is not None
            and coverage < COVERAGE_THRESHOLD
        ):
            print(f"\n🧠 Coverage Healing triggered ({coverage:.2f}%)")

            executor_output = healing_hook(
                planner_output=planner_output,
                executor_output=executor_output
            )
            pipeline_state["executor_output"] = executor_output

            status = executor_output.get("status")
            coverage = executor_output.get("coverage_percent")

            if coverage is not None:
                print(f"📈 Coverage after healing: {coverage:.2f}%")

    else:
        print("\n🔒 Coverage ≥ threshold → agents idle")

    # ─────────────────────────────────────────
    # 5️⃣ FAILURE ANALYSIS
    # ─────────────────────────────────────────
    if status in ("fail", "error"):
        print("\n🔍 Running Failure Analysis Agent...")
        failure_analysis = failure_analysis_agent(executor_output)
        pipeline_state["failure_analysis"] = failure_analysis

        print(f"🛠️ Failure type: {failure_analysis.get('failure_type')}")
        print(f"➡️ Next step: {failure_analysis.get('next_step')}")

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
        if executor_output else 0
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
