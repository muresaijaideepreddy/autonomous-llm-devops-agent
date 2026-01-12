import subprocess
import os
import time
import re
from typing import List, Optional

def executor_agent(test_info: dict, test_files: Optional[List[str]] = None) -> dict:
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )

    command = ["pytest", *test_files] if test_files else \
              test_info.get("execution_strategy", "pytest").split()

    try:
        start_time = time.time()

        result = subprocess.run(
            command,
            cwd=project_root,
            capture_output=True,
            text=True
        )

        execution_time_ms = int((time.time() - start_time) * 1000)
        logs = result.stdout + result.stderr
        fatal_errors = (
            "SyntaxError",
            "IndentationError",
            "ImportError",
            "ModuleNotFoundError",
            "ERROR collecting"
        )

        if any(err in logs for err in fatal_errors):
            return {
                "status": "error",
                "failed_tests": [],
                "passed_tests": [],
                "total_tests": 0,
                "logs": logs,
                "summary_report": "CI failed due to syntax/import error",
                "execution_time_ms": execution_time_ms
            }
        if "collected 0 items" in logs:
            return {
                "status": "no_tests",
                "failed_tests": [],
                "passed_tests": [],
                "total_tests": 0,
                "logs": logs,
                "summary_report": "No tests were collected",
                "execution_time_ms": execution_time_ms
            }
        total_tests = 0
        passed_count = 0
        failed_count = 0

        collected_match = re.search(r"collected (\d+) items", logs)
        if collected_match:
            total_tests = int(collected_match.group(1))

        passed_match = re.search(r"(\d+) passed", logs)
        if passed_match:
            passed_count = int(passed_match.group(1))

        failed_match = re.search(r"(\d+) failed", logs)
        if failed_match:
            failed_count = int(failed_match.group(1))
        failed_tests = []
        failed_files = set()

        for line in logs.splitlines():
            if "FAILED" in line and "::" in line:
                parts = line.split("::")
                failed_files.add(parts[0])
                failed_tests.append(parts[-1].strip())
        if result.returncode == 0:
            return {
                "status": "pass",
                "total_tests": total_tests,
                "passed_tests": passed_count,
                "failed_tests": [],
                "logs": logs,
                "summary_report": (
                    f"✅ All tests passed ({passed_count}/{total_tests})"
                ),
                "execution_time_ms": execution_time_ms
            }
        return {
            "status": "fail",
            "total_tests": total_tests,
            "passed_tests": passed_count,
            "failed_tests": failed_tests,
            "failed_test_files": list(failed_files),
            "logs": logs,
            "summary_report": (
                f"❌ {failed_count} failed, {passed_count} passed "
                f"(Total: {total_tests})"
            ),
            "execution_time_ms": execution_time_ms
        }

    except Exception as e:
        return {
            "status": "error",
            "failed_tests": [],
            "passed_tests": [],
            "total_tests": 0,
            "logs": str(e),
            "summary_report": "Executor crashed",
            "execution_time_ms": 0
        }
