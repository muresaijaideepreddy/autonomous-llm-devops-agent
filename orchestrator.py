from agents.planner import planner_agent
from agents.tester import tester_agent
from agents.executor import executor_agent
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
        "start_time": start_time.isoformat(),
        "end_time": None
    }

    # 🔹 1. PLANNER AGENT
    print("\n🔹 Running Planner Agent...")
    planner_output = planner_agent(repo_event)
    pipeline_state["planner_output"] = planner_output
    print("Planner Output:", planner_output)

    # 🔹 2. TESTER AGENT
    print("\n🔹 Running Tester Agent...")
    tester_output = tester_agent(planner_output)

    execution_input = {
        "execution_strategy": "pytest",
        "test_files": tester_output["test_files_created"]
    }

    pipeline_state["tester_output"] = tester_output
    print("Tester Output:", tester_output)

    # 🔹 3. EXECUTOR AGENT
    print("\n🔹 Running Executor Agent...")
     
    executor_output = executor_agent(execution_input)
    pipeline_state["executor_output"] = executor_output
    print("Executor Output:", executor_output)

    # 🔹 4. CI STATUS
    status = executor_output["status"]

    if status == "pass":
        print("\n✅ CI PASSED")
    elif status == "fail":
        print("\n❌ CI FAILED")
    elif status == "no_tests":
        print("\n⚠️ NO TESTS EXECUTED")
    else:
        print("\n🚨 CI ERROR")

    # 🔹 5. SAVE METRICS
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

    # 🔹 6. SAVE PIPELINE STATE (OPTIONAL BUT IMPRESSIVE)
    os.makedirs("runs", exist_ok=True)
    pipeline_state["end_time"] = datetime.utcnow().isoformat()

    with open(f"runs/{run_id}.json", "w") as f:
        json.dump(pipeline_state, f, indent=2)

    return executor_output


# 🔹 MANUAL RUN (SIMULATED GITHUB EVENT)
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
