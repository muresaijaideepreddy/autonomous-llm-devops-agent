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
# CI‑STYLE LOGGING HELPERS
# ─────────────────────────────────────────────
def log_step(title):
    print(f"\n▶ {title}")

def log_info(msg):
    print(f"  • {msg}")

def log_success(msg):
    print(f"  ✔ {msg}")

def log_warn(msg):
    print(f"  ⚠ {msg}")

def log_error(msg):
    print(f"  ✖ {msg}")

def log_summary(passed, failed, coverage=None):
    print("\n📋 Test Summary")
    print(f"  ✔ Passed : {passed}")
    print(f"  ✖ Failed : {failed}")
    if coverage is not None:
        print(f"  📊 Coverage : {coverage:.2f}%")

# ─────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────
def run_pipeline(repo_event: dict) -> dict:
    log_step("Autonomous CI Pipeline Started")

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    start_time = datetime.now(timezone.utc)

    log_info(f"Run ID  : {run_id}")
    log_info(f"Commit  : {repo_event.get('commit_id')}")

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
    log_step("Planner Agent")
    log_info("Analyzing repository event")

    planner_output = planner_agent(repo_event)
    pipeline_state["planner_output"] = planner_output

    # ─────────────────────────────────────────
    # 2️⃣ COLLECT EXISTING TESTS
    # ─────────────────────────────────────────
    os.makedirs(TEST_DIR, exist_ok=True)
    test_files = [
        os.path.join(TEST_DIR, f)
        for f in os.listdir(TEST_DIR)
        if f.startswith("test_") and f.endswith(".py")
    ]

    log_info(f"Existing tests found: {len(test_files)}")

    # ─────────────────────────────────────────
    # 3️⃣ EXECUTOR (EXISTING TESTS)
    # ─────────────────────────────────────────
    executor_output = None
    coverage = None
    status = None

    if test_files:
        log_step("Executor Agent (Existing Tests)")
        executor_output = executor_agent({
            "execution_strategy": "pytest",
            "test_files": test_files
        })

        pipeline_state["executor_output"] = executor_output
        status = executor_output.get("status")
        coverage = executor_output.get("coverage_percent")

        if coverage is not None:
            log_info(f"Coverage: {coverage:.2f}%")
    else:
        log_warn("No existing tests detected")

    # ─────────────────────────────────────────
    # 4️⃣ DECISION: SHOULD AGENTS RUN?
    # ─────────────────────────────────────────
    if coverage is None or coverage < COVERAGE_THRESHOLD:
        log_warn("Coverage below threshold — activating agents")

        # 4a️⃣ TESTER
        log_step("Tester Agent")
        tester_output = tester_agent(planner_output)
        pipeline_state["tester_output"] = tester_output

        # 4b️⃣ EXECUTOR (NEW TESTS)
        log_step("Executor Agent (Generated Tests)")
        executor_output = executor_agent({
            "execution_strategy": "pytest",
            "test_files": tester_output["test_files_created"]
        })

        pipeline_state["executor_output"] = executor_output
        status = executor_output.get("status")
        coverage = executor_output.get("coverage_percent")

        if coverage is not None:
            log_info(f"Coverage after tester: {coverage:.2f}%")

        # 4c️⃣ COVERAGE HEALING
        if (
            ENABLE_COVERAGE_HEALING
            and status == "pass"
            and coverage is not None
            and coverage < COVERAGE_THRESHOLD
        ):
            log_warn(f"Coverage healing triggered ({coverage:.2f}%)")

            executor_output = healing_hook(
                planner_output=planner_output,
                executor_output=executor_output
            )

            pipeline_state["executor_output"] = executor_output
            status = executor_output.get("status")
            coverage = executor_output.get("coverage_percent")

            if coverage is not None:
                log_info(f"Coverage after healing: {coverage:.2f}%")
    else:
        log_success("Coverage threshold satisfied — agents idle")

    # ─────────────────────────────────────────
    # 5️⃣ FAILURE ANALYSIS
    # ─────────────────────────────────────────
    if status in ("fail", "error"):
        log_step("Failure Analysis")

        failure_analysis = failure_analysis_agent(executor_output)
        pipeline_state["failure_analysis"] = failure_analysis

        log_error(f"Failure type: {failure_analysis.get('failure_type')}")
        log_info(f"Next action : {failure_analysis.get('next_step')}")

    # ─────────────────────────────────────────
    # 6️⃣ FINAL STATUS
    # ─────────────────────────────────────────
    log_step("Final CI Status")

    if status == "pass":
        passed = executor_output.get("passed_tests", 0)
        failed = 0
        log_success("CI PASSED")
        log_summary(passed, failed, coverage)

    elif status == "fail":
        passed = executor_output.get("passed_tests", 0)
        failed = len(executor_output.get("failed_tests", []))
        log_error("CI FAILED")
        log_summary(passed, failed, coverage)

    else:
        log_error("CI Infrastructure Error")

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
