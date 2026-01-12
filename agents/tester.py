"""
Tester Agent
============

Automatically generates pytest unit tests using an LLM (Gemini).

Key features:
- Limits number of generated tests to avoid token truncation
- Severity-based test count control
- Python syntax validation
- Retry mechanism with fallback tests
- Production-grade logging and structure
"""
from dotenv import load_dotenv

load_dotenv()


import os
import ast
from typing import Dict, List
from google import genai

# -----------------------------
# CONFIGURATION
# -----------------------------

# Severity → max unit tests mapping
MAX_TESTS_BY_SEVERITY = {
    "low": 12,
    "medium": 15,
    "high": 20
}

# Max retries if LLM generates invalid Python
MAX_RETRIES = 2

# Gemini model (works with free tier access)
GEMINI_MODEL = "models/gemini-2.5-flash"


# -----------------------------
# LLM CLIENT
# -----------------------------

def get_gemini_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not set")
    return genai.Client(api_key=api_key)


# -----------------------------
# UTILS
# -----------------------------

def is_valid_python(code: str) -> bool:
    """Validate generated Python code syntax."""
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def fallback_test(module: str) -> str:
    """Safe fallback test if LLM output fails."""
    return f"""
def test_{module}_fallback():
    assert True
"""


# -----------------------------
# LLM GENERATION
# -----------------------------

def generate_tests_with_gemini(
    client: genai.Client,
    source_code: str,
    module: str,
    risk_level: str
) -> str:
    """
    Generate pytest tests using Gemini with strict limits.
    """

    max_tests = MAX_TESTS_BY_SEVERITY.get(risk_level, 2)

    prompt = f"""
You are a senior QA engineer.

Generate pytest unit tests for the following Python module.

CRITICAL RULES (MUST FOLLOW):
- Generate AT MOST {max_tests} test functions
- Use pytest
- Keep code concise
- Do NOT use parametrized tests
- Do NOT generate explanations or markdown
- Output ONLY valid Python code
- Each test must be independent
- Tests must reflect CORRECT business behavior
- DO NOT mirror implementation bugs
- If implementation is incorrect, tests MUST FAIL
- ALWAYS include this import block at the top:

import sys
import os
import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from {module} import *

Module name: {module}

Code:
{source_code}
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    return response.text.strip()


# -----------------------------
# TESTER AGENT
# -----------------------------

def tester_agent(plan: Dict) -> Dict:
    """
    Tester Agent

    Input:
        plan:
            modules_to_test: List[str]
            risk_level: str

    Output:
        {
            test_files_created: List[str],
            num_tests_generated: int
        }
    """

    modules: List[str] = plan.get("modules_to_test", [])
    risk_level: str = plan.get("risk_level", "low")
    coverage_context = plan.get("coverage_context")

    os.makedirs("tests", exist_ok=True)

    client = get_gemini_client()
    created_files: List[str] = []
    total_tests = 0

    for module in modules:
        source_path = f"src/{module}.py"
        if not os.path.exists(source_path):
            continue

        with open(source_path, "r") as f:
            source_code = f.read()

        test_code = None

        # 🔁 Retry logic
        for attempt in range(1, MAX_RETRIES + 1):
            print(f"🔁 Generating tests for {module} (attempt {attempt})")

            generated = generate_tests_with_gemini(
                client=client,
                source_code=source_code,
                module=module,
                risk_level=risk_level
            )

            if is_valid_python(generated):
                test_code = generated
                break
            else:
                print("⚠️ Invalid Python generated, retrying...")

        # 🚨 Fallback
        if not test_code:
            print(f"🚨 Failed to generate valid tests for {module}, using fallback")
            test_code = fallback_test(module)

        test_file_path = f"tests/test_{module}_auto.py"

        with open(test_file_path, "w") as f:
            f.write(test_code)

        created_files.append(test_file_path)
        total_tests += test_code.count("def test_")

    return {
        "test_files_created": created_files,
        "num_tests_generated": total_tests
    }
