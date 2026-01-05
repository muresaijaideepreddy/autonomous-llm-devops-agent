import subprocess
import os
import time
from typing import Dict, List


def executor_agent(test_info: dict) -> dict:
    """
    Executes tests based on input from the tester agent.

    Input (test_info):
        execution_strategy: str (default: "pytest")

    Output:
        {
            status: "pass" | "fail" | "no_tests" | "error",
            passed_tests: List[str],
            failed_tests: List[str],
            logs: str,
            summary_report: str,
            execution_time_ms: int
        }
    """

    command = test_info.get("execution_strategy", "pytest")

    try:
        # 🔹 Ensure pytest runs from PROJECT ROOT
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..")
        )

        start_time = time.time()

        result = subprocess.run(
            command,
            shell=True,
            cwd=project_root,
            capture_output=True,
            text=True
        )

        end_time = time.time()
        execution_time_ms = int((end_time - start_time) * 1000)

        stdout = result.stdout + result.stderr

        # 🔹 Case 1: No tests found
        if "collected 0 items" in stdout:
            return {
                "status": "no_tests",
                "passed_tests": [],
                "failed_tests": [],
                "logs": stdout,
                "summary_report": "No tests found to execute",
                "execution_time_ms": execution_time_ms
            }

        # 🔹 Parse failed test names
        failed_tests: List[str] = []

        for line in stdout.splitlines():
            if "FAILED" in line and "::" in line:
                failed_tests.append(line.split("::")[-1].strip())

        # 🔹 Case 2: All tests passed
        if result.returncode == 0:
            return {
                "status": "pass",
                "passed_tests": ["all"],
                "failed_tests": [],
                "logs": stdout,
                "summary_report": "All tests passed",
                "execution_time_ms": execution_time_ms
            }

        # 🔹 Case 3: Tests failed
        return {
            "status": "fail",
            "passed_tests": [],
            "failed_tests": failed_tests if failed_tests else ["unknown_test_failure"],
            "logs": stdout,
            "summary_report": f"{len(failed_tests) or 1} test(s) failed",
            "execution_time_ms": execution_time_ms
        }

    except Exception as e:
        return {
            "status": "error",
            "passed_tests": [],
            "failed_tests": ["execution_error"],
            "logs": str(e),
            "summary_report": "Executor crashed",
            "execution_time_ms": 0
        }


# 🔹 Manual test hook
if __name__ == "__main__":
    test_info = {
        "execution_strategy": "pytest"
    }

    output = executor_agent(test_info)
    print(output)
