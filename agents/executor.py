import subprocess
import os
import time
from typing import Dict, List, Optional


def executor_agent(test_info: dict, test_files: Optional[List[str]] = None) -> dict:
    """
    Executes pytest tests and returns structured results
    (Designed for self-healing test regeneration)
    """

    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )

    # 🔹 Build pytest command
    if test_files:
        test_targets = " ".join(test_files)
        command = f"pytest {test_targets}"
    else:
        command = test_info.get("execution_strategy", "pytest")

    try:
        start_time = time.time()

        result = subprocess.run(
            command,
            shell=True,
            cwd=project_root,
            capture_output=True,
            text=True
        )

        execution_time_ms = int((time.time() - start_time) * 1000)
        stdout = result.stdout + result.stderr

        # 🔹 No tests collected
        if "collected 0 items" in stdout:
            return {
                "status": "no_tests",
                "passed_tests": [],
                "failed_tests": [],
                "logs": stdout,
                "summary_report": "No tests found",
                "execution_time_ms": execution_time_ms
            }

        # 🔹 Extract failed tests
        failed_tests = []
        for line in stdout.splitlines():
            if "FAILED" in line and "::" in line:
                failed_tests.append(line.split("::")[-1].strip())

        # 🔹 All tests passed
        if result.returncode == 0:
            return {
                "status": "pass",
                "passed_tests": ["all"],
                "failed_tests": [],
                "logs": stdout,
                "summary_report": "All tests passed",
                "execution_time_ms": execution_time_ms
            }

        # 🔹 Tests failed (important for self-healing)
        return {
            "status": "fail",
            "passed_tests": [],
            "failed_tests": failed_tests or ["unknown_failure"],
            "failed_test_files": test_files,
            "logs": stdout,
            "summary_report": f"{len(failed_tests) or 1} test(s) failed",
            "execution_time_ms": execution_time_ms
        }

    except Exception as e:
        return {
            "status": "error",
            "passed_tests": [],
            "failed_tests": ["executor_crash"],
            "logs": str(e),
            "summary_report": "Executor crashed",
            "execution_time_ms": 0
        }


# 🔹 Manual test
if __name__ == "__main__":
    test_info = {"execution_strategy": "pytest"}
    test_files = ["tests/test_payments_auto.py"]

    output = executor_agent(test_info, test_files)
    print(output)
