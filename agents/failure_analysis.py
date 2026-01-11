"""
Failure Analysis Agent
======================

Responsibilities:
- Classify test failures
- Decide pipeline action:
    * healer
    * regenerate_tests
    * suggest_code_fix
- Use Gemini LLM when heuristic rules are insufficient
"""

import os
from typing import Dict, List
from google import genai
from dotenv import load_dotenv

load_dotenv()

# -----------------------------
# Gemini Client
# -----------------------------

GEMINI_MODEL = "models/gemini-2.5-flash"

def get_gemini_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)

# -----------------------------
# LLM Reasoning
# -----------------------------

def gemini_failure_reasoning(
    failed_tests: List[str],
    logs: str
) -> Dict:
    """
    Uses Gemini to classify failure root cause
    """
    client = get_gemini_client()

    prompt = f"""
You are a senior software engineer analyzing CI test failures.

Your task:
- Determine whether the failure is caused by:
  1. CODE_BUG
  2. TEST_BUG
  3. INFRA_ERROR

Return STRICT JSON only in this format:

{{
  "failure_type": "code_bug | test_bug | infra_error",
  "reason": "short explanation",
  "suggested_fix": "what should be changed",
  "confidence": "high | medium | low"
}}

Failed tests:
{failed_tests}

Pytest logs:
{logs[:1500]}
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    try:
        return eval(response.text.strip())
    except Exception:
        return {
            "failure_type": "unknown",
            "reason": "LLM output could not be parsed",
            "suggested_fix": "Manual inspection required",
            "confidence": "low"
        }

# -----------------------------
# Failure Analysis Agent
# -----------------------------

def failure_analysis_agent(executor_output: dict) -> dict:
    """
    Decides how the pipeline should react to failures
    """

    status = executor_output.get("status")
    failed_tests = executor_output.get("failed_tests", [])
    logs = executor_output.get("logs", "")

    # -----------------------------------
    # 1️⃣ Infra / syntax / pytest crash
    # -----------------------------------
    if status == "error":
        return {
            "failure_type": "infra_error",
            "reason": "Pytest failed to run (syntax/import/runtime error)",
            "next_step": "healer",
            "details": logs[:800]
        }

    # -----------------------------------
    # 2️⃣ Heuristic-based fast checks
    # -----------------------------------
    if "AssertionError" in logs:
        return {
            "failure_type": "code_bug",
            "reason": "Assertion failed → business logic mismatch",
            "next_step": "suggest_code_fix",
            "confidence": "high",
            "failed_tests": failed_tests
        }

    if "TypeError" in logs or "ValueError" in logs:
        return {
            "failure_type": "test_bug",
            "reason": "Invalid inputs or incorrect test assumptions",
            "next_step": "regenerate_tests",
            "confidence": "medium",
            "failed_tests": failed_tests
        }

    # -----------------------------------
    # 3️⃣ Unknown → Ask Gemini
    # -----------------------------------
    llm_analysis = gemini_failure_reasoning(
        failed_tests=failed_tests,
        logs=logs
    )

    # -----------------------------------
    # 4️⃣ Decide pipeline action
    # -----------------------------------
    failure_type = llm_analysis.get("failure_type", "unknown")

    if failure_type == "infra_error":
        next_step = "healer"
    elif failure_type == "test_bug":
        next_step = "regenerate_tests"
    elif failure_type == "code_bug":
        next_step = "suggest_code_fix"
    else:
        next_step = "manual_review"

    return {
        "analysis_summary": "Failure analyzed using Gemini LLM",
        "failure_type": failure_type,
        "reason": llm_analysis.get("reason"),
        "suggested_fix": llm_analysis.get("suggested_fix"),
        "confidence": llm_analysis.get("confidence"),
        "next_step": next_step,
        "failed_tests": failed_tests
    }

# -----------------------------
# Manual Debug Hook
# -----------------------------
if __name__ == "__main__":
    sample_executor_output = {
        "status": "fail",
        "failed_tests": ["test_batch_payments", "test_export_report"],
        "logs": "AssertionError: assert 120 == 50"
    }

    result = failure_analysis_agent(sample_executor_output)
    print(result)
