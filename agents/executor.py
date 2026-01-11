import subprocess
import os
import time
from typing import List, Optional

def executor_agent(test_info: dict, test_files: Optional[List[str]] = None) -> dict:
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )

    if test_files:
        command = ["pytest", *test_files]
    else:
        command = test_info.get("execution_strategy", "pytest").split()

    try:
        start_time = time.time()

        result = subprocess.run(
            command,
            cwd=project_root,
            capture_output=True,
            text=True
        )

        execution_time_ms = int((time.time() - start_time) * 1000)
        stdout = result.stdout + result.stderr

        # -----------------------------
        # 1️⃣ EXECUTION / SYNTAX ERRORS
        # -----------------------------
        fatal_keywords = [
            "SyntaxError",
            "IndentationError",
            "ImportError",
            "ModuleNotFoundError",
            "ERROR collecting"
        ]

        if any(k in stdout for k in fatal_keywords):
            return {
                "status": "error",
                "failure_type": "CODE_EXECUTION_ERROR",
                "next_agent": "code_healer",
                "confidence": 0.95,
                "failed_tests": [],
                "logs": stdout,
                "summary_report": "Code cannot execute (syntax/import error)",
                "execution_time_ms": execution_time_ms
            }

        # -----------------------------
        # 2️⃣ NO TESTS
        # -----------------------------
        if "collected 0 items" in stdout:
            return {
                "status": "no_tests",
                "failure_type": "NO_TESTS",
                "next_agent": "tester_agent",
                "confidence": 0.9,
                "failed_tests": [],
                "logs": stdout,
                "summary_report": "No tests collected",
                "execution_time_ms": execution_time_ms
            }

        # -----------------------------
        # 3️⃣ PARSE FAILURES
        # -----------------------------
        failed_tests = []
        failed_files = set()

        for line in stdout.splitlines():
            if "FAILED" in line and "::" in line:
                parts = line.split("::")
                failed_files.add(parts[0])
                failed_tests.append(parts[-1].strip())

        # -----------------------------
        # 4️⃣ ALL PASSED
        # -----------------------------
        if result.returncode == 0:
            return {
                "status": "pass",
                "failure_type": None,
                "next_agent": None,
                "confidence": 1.0,
                "passed_tests": ["all"],
                "failed_tests": [],
                "logs": stdout,
                "summary_report": "All tests passed",
                "execution_time_ms": execution_time_ms
            }

        # -----------------------------
        # 5️⃣ ASSERTION FAILURES → classify
        # -----------------------------
        assertion_count = stdout.count("AssertionError")

        if assertion_count > 0:
            return {
                "status": "fail",
                "failure_type": "CODE_LOGIC_BUG",
                "next_agent": "failure_analysis_agent",
                "confidence": 0.8,
                "failed_tests": failed_tests,
                "failed_test_files": list(failed_files),
                "logs": stdout,
                "summary_report": f"{len(failed_tests)} test(s) failed due to logic mismatch",
                "execution_time_ms": execution_time_ms
            }

        # -----------------------------
        # 6️⃣ FALLBACK → likely bad test
        # -----------------------------
        return {
            "status": "fail",
            "failure_type": "TEST_GENERATION_BUG",
            "next_agent": "test_healer",
            "confidence": 0.6,
            "failed_tests": failed_tests or ["unknown_test_failure"],
            "failed_test_files": list(failed_files),
            "logs": stdout,
            "summary_report": "Test behavior inconsistent or invalid",
            "execution_time_ms": execution_time_ms
        }

    except Exception as e:
        return {
            "status": "error",
            "failure_type": "EXECUTOR_CRASH",
            "next_agent": "infra_healer",
            "confidence": 1.0,
            "failed_tests": [],
            "logs": str(e),
            "summary_report": "Executor crashed",
            "execution_time_ms": 0
        }
