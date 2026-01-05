from agents.planner import planner_agent
from agents.executor import executor_agent
from datetime import datetime
import json
import os


def run_pipeline(repo_event: dict):
    print("🔹 Starting CI pipeline")

    # 1 Planner
    print("🔹 Running Planner Agent...")
    plan = planner_agent(repo_event)
    print("Planner output:", plan)

    # 2 Executor
    print("🔹 Running Executor Agent...")
    execution_input = {
        "execution_strategy": "pytest"
    }
    result = executor_agent(execution_input)
    print("Executor output:", result)

    # 3 CI-style status
    if result["status"] == "pass":
        print("CI PASSED")
    elif result["status"] == "fail":
        print("CI FAILED")
    else:
        print("NO TESTS EXECUTED")

    # 4 Save metrics
    os.makedirs("metrics", exist_ok=True)

    metrics = {
        "timestamp": datetime.utcnow().isoformat(),
        "status": result["status"],
        "failed_tests_count": len(result["failed_tests"]),
        "execution_time_ms": result["execution_time_ms"]
    }

    with open("metrics/run_metrics.json", "a") as f:
        f.write(json.dumps(metrics) + "\n")

    return result


# 🔹 Manual run
if __name__ == "__main__":
    repo_event = {
        "changed_files": ["src/payments.py"],
        "issue": {
            "title": "Negative amount crash",
            "severity": "high"
        }
    }

    run_pipeline(repo_event)
