from agents.tester import tester_agent
from agents.executor import executor_agent

def healing_hook(planner_output: dict) -> dict:
    print("🧠 Self‑healing triggered...")

    tester_output = tester_agent(planner_output)
    executor_output = executor_agent({
        "test_files": tester_output["test_files_created"]
    })

    executor_output["healed"] = True
    return executor_output
