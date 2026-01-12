import os
import json
from typing import Dict, List
from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_MODEL = "models/gemini-2.5-flash"


def get_gemini_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)


def _safe_json_parse(text: str) -> Dict:
    """
    Safely parse LLM JSON output.
    Never crashes CI.
    """
    try:
        return json.loads(text)
    except Exception:
        return {
            "failure_type": "unknown",
            "reason": "LLM output could not be parsed",
            "suggested_fix": "Manual inspection required",
            "confidence": "low"
        }


def gemini_failure_reasoning(
    failed_tests: List[str],
    logs: str
) -> Dict:
    """
    Uses Gemini to classify failure root cause.
    Always returns a structured dict.
    """

    client = get_gemini_client()

    prompt = f"""
You are a senior software engineer analyzing CI test failures.

Classify the failure into ONE category:
1. code_bug
2. test_bug
3. infra_error
4. coverage_gap

Return STRICT JSON only in this format:
{{
  "failure_type": "code_bug | test_bug | infra_error | coverage_gap",
  "reason": "short explanation",
  "suggested_fix": "what should be changed",
  "confidence": "high | medium | low"
}}

Failed tests:
{failed_tests}

Logs:
{logs[:1500]}
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    return _safe_json_parse(response.text.strip())


def failure_analysis_agent(executor_output: dict) -> dict:
    """
    Single source of truth for CI failure classification.
    This function NEVER returns an unknown path.
    """

    status = executor_output.get("status")
    failed_tests = executor_output.get("failed_tests", [])
    logs = executor_output.get("logs", "")
    coverage = executor_output.get("coverage_percent")

    # --------------------------------------------------
    # 1️⃣ Infra / execution errors
    # --------------------------------------------------
    if status == "error":
        return {
            "failure_type": "infra_error",
            "reason": "Pytest failed to execute (syntax/import/runtime error)",
            "next_step": "healer",
            "confidence": "high",
            "details": logs[:800]
        }

    # --------------------------------------------------
    # 2️⃣ Coverage gate failure
    # --------------------------------------------------
    if coverage is not None and coverage < 98:
        return {
            "failure_type": "coverage_gap",
            "reason": f"Coverage below threshold ({coverage}%)",
            "next_step": "regenerate_tests_for_coverage",
            "confidence": "high",
            "coverage_percent": coverage,
            "uncovered_lines": executor_output.get("uncovered_lines", [])
        }

    # --------------------------------------------------
    # 3️⃣ Fast heuristic checks
    # --------------------------------------------------
    if "AssertionError" in logs:
        return {
            "failure_type": "code_bug",
            "reason": "Assertion failure indicates business logic mismatch",
            "next_step": "suggest_code_fix",
            "confidence": "high",
            "failed_tests": failed_tests
        }

    if any(err in logs for err in ("TypeError", "ValueError", "IndexError", "KeyError")):
        return {
            "failure_type": "test_bug",
            "reason": "Invalid inputs or incorrect test assumptions",
            "next_step": "regenerate_tests",
            "confidence": "medium",
            "failed_tests": failed_tests
        }

    # --------------------------------------------------
    # 4️⃣ LLM fallback (NO UNKNOWN PATH)
    # --------------------------------------------------
    llm_result = gemini_failure_reasoning(
        failed_tests=failed_tests,
        logs=logs
    )

    failure_type = llm_result.get("failure_type", "unknown")

    if failure_type == "infra_error":
        next_step = "healer"
    elif failure_type == "test_bug":
        next_step = "regenerate_tests"
    elif failure_type == "coverage_gap":
        next_step = "regenerate_tests_for_coverage"
    else:
        next_step = "suggest_code_fix"

    return {
        "analysis_summary": "Failure analyzed using Gemini LLM",
        "failure_type": failure_type,
        "reason": llm_result.get("reason"),
        "suggested_fix": llm_result.get("suggested_fix"),
        "confidence": llm_result.get("confidence"),
        "next_step": next_step,
        "failed_tests": failed_tests
    }


# --------------------------------------------------
# Manual Debug Hook
# --------------------------------------------------
if __name__ == "__main__":
    sample_executor_output = {
        "status": "fail",
        "failed_tests": ["test_batch_payments"],
        "logs": "AssertionError: assert 120 == 50",
        "coverage_percent": 76
    }

    print(json.dumps(
        failure_analysis_agent(sample_executor_output),
        indent=2
    ))
