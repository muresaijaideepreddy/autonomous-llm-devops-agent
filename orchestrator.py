from agents.planner import planner_agent
from agents.tester import tester_agent
from agents.executor import executor_agent
from agents.failure_analysis import failure_analysis_agent
from agents.healer import healing_agent
from datetime import datetime, timezone
import json
import os
import uuid

# Import from centralized config
from config import COVERAGE_THRESHOLD, TEST_DIR, ENABLE_COVERAGE_HEALING

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
        # Pass executor_output so tester knows which tests passed/failed
        tester_plan = {
            **planner_output,
            "executor_output": executor_output  # For smart test preservation
        }
        tester_output = tester_agent(tester_plan)
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

        # 4c️⃣ FAILURE ANALYSIS (run before healing)
        failure_analysis = None
        if status in ("fail", "error"):
            log_step("Failure Analysis")
            failure_analysis = failure_analysis_agent(executor_output)
            pipeline_state["failure_analysis"] = failure_analysis
            log_error(f"Failure type: {failure_analysis.get('failure_type')}")
            log_info(f"Next action : {failure_analysis.get('next_step')}")

        # 4d️⃣ HEALER ANALYSIS + TARGETED TEST GENERATION
        if ENABLE_COVERAGE_HEALING and status == "pass" and coverage is not None and coverage < COVERAGE_THRESHOLD:
            log_step("Healer Agent (Analysis)")
            
            # Healer analyzes and reports gaps
            healer_report = healing_agent(
                planner_output=planner_output,
                executor_output=executor_output,
                failure_analysis=failure_analysis
            )
            pipeline_state["healer_report"] = healer_report
            
            # If healer found gaps, tester generates targeted tests
            if healer_report.get("needs_healing") and healer_report.get("coverage_context"):
                log_step("Tester Agent (Targeted Tests)")
                
                # Build targeted plan with coverage context from healer
                targeted_plan = {
                    "modules_to_test": healer_report.get("modules_needing_tests", []),
                    "risk_level": planner_output.get("risk_level", "medium"),
                    "coverage_context": healer_report.get("coverage_context"),
                    "executor_output": executor_output  # For smart test preservation
                }
                
                tester_output = tester_agent(targeted_plan)
                pipeline_state["tester_output"] = tester_output
                
                # Re-run executor with new targeted tests
                if tester_output.get("test_files_created"):
                    log_step("Executor Agent (Targeted Tests)")
                    executor_output = executor_agent({
                        "execution_strategy": "pytest",
                        "test_files": tester_output["test_files_created"]
                    })
                    
                    pipeline_state["executor_output"] = executor_output
                    status = executor_output.get("status")
                    coverage = executor_output.get("coverage_percent")
                    
                    if coverage is not None:
                        log_info(f"Coverage after targeted tests: {coverage:.2f}%")
    else:
        log_success("Coverage threshold satisfied — agents idle")

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

