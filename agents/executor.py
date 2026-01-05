import subprocess
import os

def executor_agent(test_info: dict) -> dict:
    command = test_info.get("execution_strategy", "pytest")

    try:
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..")
        )

        result = subprocess.run(
            command,
            shell=True,
            cwd=project_root,
            capture_output=True,
            text=True
        )

        stdout = result.stdout + result.stderr

        if "collected 0 items" in stdout:
            return {
                "passed_tests": [],
                "failed_tests": [],
                "logs": stdout,
                "summary_report": "No tests found to execute"
            }

        if result.returncode == 0:
            return {
                "passed_tests": ["all"],
                "failed_tests": [],
                "logs": stdout,
                "summary_report": "All tests passed"
            }
        else:
            return {
                "passed_tests": [],
                "failed_tests": ["unknown_test_failure"],
                "logs": stdout,
                "summary_report": "Test execution failed"
            }

    except Exception as e:
        return {
            "passed_tests": [],
            "failed_tests": ["execution_error"],
            "logs": str(e),
            "summary_report": "Executor crashed"
        }


if __name__ == "__main__":
    test_info = {
        "execution_strategy": "pytest"
    }
    output = executor_agent(test_info)
    print(output)
