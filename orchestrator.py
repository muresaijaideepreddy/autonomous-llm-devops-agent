from agents.planner import planner_agent
from agents.tester import tester_agent
from agents.executor import executor_agent
from agents.failure_analysis1 import failure_analysis_agent
from datetime import datetime
import json
import os
import uuid

def run_pipeline(repo_event: dict) -> dict:
    print("🔹 Starting Autonomous CI Pipeline")

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    start_time = datetime.utcnow()

    pipeline_state = {
        "run_id": run_id,
        "planner_output": None,
        "tester_output": None,
        "executor_output": None,
        "failure_analysis": None,
        "start_time": start_time.isoformat(),
        "end_time": None
    }

    # 🔹 1. PLANNER AGENT
    print("\n🔹 Running Planner Agent...")
    planner_output = planner_agent(repo_event)
    pipeline_state["planner_output"] = planner_output

    # 🔹 2. TESTER AGENT
    print("\n🔹 Running Tester Agent...")
    tester_output = tester_agent(planner_output)
    pipeline_state["tester_output"] = tester_output

    execution_input = {
        "execution_strategy": "pytest",
        "test_files": tester_output["test_files_created"]
    }

    # 🔹 3. EXECUTOR AGENT
    print("\n🔹 Running Executor Agent...")
    executor_output = executor_agent(execution_input)
    pipeline_state["executor_output"] = executor_output

    status = executor_output["status"]

    # 🔹 4. FAILURE ANALYSIS (NEW & IMPORTANT)
    if status in ("fail", "error"):
        print("\n🔍 Running Failure Analysis Agent...")
        failure_analysis = failure_analysis_agent(executor_output)
        pipeline_state["failure_analysis"] = failure_analysis

        next_step = failure_analysis["next_step"]

        if next_step == "healer":
            print("🩺 Infra / Syntax issue → Send to Healer Agent")
        elif next_step == "regenerate_tests":
            print("🔁 Test bug detected → Regenerate tests using LLM")
        elif next_step == "suggest_code_fix":
            print("🛠️ Code bug detected → Provide fix suggestions")
        else:
            print("❓ Unknown failure path")

    # 🔹 5. CI STATUS (FINAL MEANINGFUL STATUS)
    if status == "pass":
        print("\n✅ Code is good to go")
    elif status == "fail":
        print("\n❌ Tests failed — analysis generated")
    elif status == "no_tests":
        print("\n⚠️ No tests generated")
    else:
        print("\n🚨 CI Infrastructure Error")

    # 🔹 6. SAVE METRICS
    os.makedirs("metrics", exist_ok=True)

    metrics = {
        "run_id": run_id,
        "timestamp": datetime.utcnow().isoformat(),
        "status": status,
        "failed_tests_count": len(executor_output.get("failed_tests", [])),
        "execution_time_ms": executor_output.get("execution_time_ms", 0)
    }

    with open("metrics/run_metrics.json", "a") as f:
        f.write(json.dumps(metrics) + "\n")

    # 🔹 7. SAVE PIPELINE STATE
    os.makedirs("runs", exist_ok=True)
    pipeline_state["end_time"] = datetime.utcnow().isoformat()

    with open(f"runs/{run_id}.json", "w") as f:
        json.dump(pipeline_state, f, indent=2)

    return pipeline_state


# 🔹 MANUAL RUN
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
