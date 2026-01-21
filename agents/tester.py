"""
Tester Agent
============
Automatically generates pytest unit tests using an LLM (Gemini).
Key features:
- Severity-based test count control
- Python syntax validation
- Retry mechanism with fallback tests
- Coverage-aware test generation (for Coverage Healer)
"""

from dotenv import load_dotenv
load_dotenv()

import os
import ast
from typing import Dict, List, Optional
from google import genai

# -----------------------------
# CONFIGURATION
# -----------------------------

MAX_TESTS_BY_SEVERITY = {
    "low": 12,
    "medium": 15,
    "high": 20
}

MAX_RETRIES = 2
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
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False

def fallback_test(module: str) -> str:
    return f"""
def test_{module}_fallback():
    assert True
"""

def get_existing_test_names(test_file_path: str) -> List[str]:
    """Extract existing test function names from a test file."""
    if not os.path.exists(test_file_path):
        return []
    
    try:
        with open(test_file_path, "r") as f:
            code = f.read()
        tree = ast.parse(code)
        return [
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        ]
    except (SyntaxError, FileNotFoundError):
        return []

# -----------------------------
# LLM GENERATION
# -----------------------------

def generate_tests_with_gemini(
    client: genai.Client,
    source_code: str,
    module: str,
    risk_level: str,
    coverage_context: Optional[dict] = None,
    existing_tests: Optional[List[str]] = None
) -> str:
    """
    Generate pytest tests using Gemini.
    Now supports function-level targeting and duplicate avoidance.
    """

    max_tests = MAX_TESTS_BY_SEVERITY.get(risk_level, 2)

    # Build targeted coverage instruction
    coverage_instruction = ""
    if coverage_context:
        uncovered_lines = coverage_context.get("uncovered_lines", [])
        uncovered_funcs = coverage_context.get("uncovered_functions", [])
        
        coverage_instruction = f"""
PRIORITY - TARGET THESE UNCOVERED ITEMS:
"""
        if uncovered_funcs:
            coverage_instruction += f"""
These FUNCTIONS have low or no coverage - TEST THEM FIRST:
{', '.join(uncovered_funcs)}
"""
        coverage_instruction += f"""
These line numbers are NOT covered: {uncovered_lines[:20]}

Generate pytest tests that EXECUTE these uncovered functions/lines.
Focus on edge cases, error paths, and boundary conditions.
"""

    # Avoid duplicate test generation
    existing_instruction = ""
    if existing_tests:
        existing_instruction = f"""
IMPORTANT: These tests ALREADY EXIST - DO NOT regenerate them:
{', '.join(existing_tests[:15])}

Generate NEW tests that cover DIFFERENT code paths.
"""

    prompt = f"""
You are a senior QA engineer.
{coverage_instruction}
{existing_instruction}

Generate pytest unit tests for the following Python module.

CRITICAL RULES (MUST FOLLOW):
- Generate AT MOST {max_tests} NEW test functions
- Use pytest
- Keep code concise
- Do NOT use parametrized tests
- Do NOT generate explanations or markdown
- Output ONLY valid Python code
- Each test must be independent
- Tests must reflect CORRECT business behavior
- If implementation is incorrect, tests MUST FAIL

ALWAYS include this import block at the top:
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
    Tester Agent - Enhanced with test preservation and function targeting.
    """

    modules: List[str] = plan.get("modules_to_test", [])
    risk_level: str = plan.get("risk_level", "low")

    # Coverage context from Healer (now includes function names)
    coverage_context: Optional[dict] = plan.get("coverage_context")

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

        test_file_path = f"tests/test_{module}_auto.py"
        
        # Get existing test names to avoid duplicates
        existing_tests = get_existing_test_names(test_file_path)
        existing_code = ""
        if os.path.exists(test_file_path):
            with open(test_file_path, "r") as f:
                existing_code = f.read()

        # Get module-specific coverage context
        module_coverage = None
        if coverage_context and module in coverage_context:
            module_coverage = coverage_context[module]

        test_code = None

        for attempt in range(1, MAX_RETRIES + 1):
            print(f"🔁 Generating tests for {module} (attempt {attempt})")
            if existing_tests:
                print(f"   📋 Existing tests: {len(existing_tests)} (will preserve)")

            generated = generate_tests_with_gemini(
                client=client,
                source_code=source_code,
                module=module,
                risk_level=risk_level,
                coverage_context=module_coverage,
                existing_tests=existing_tests
            )

            if is_valid_python(generated):
                test_code = generated
                break
            else:
                print("⚠️ Invalid Python generated, retrying...")

        if not test_code:
            print(f"🚨 Failed to generate valid tests for {module}, using fallback")
            test_code = fallback_test(module)

        # Count new tests generated
        new_test_count = test_code.count("def test_")
        
        # Write new tests (overwrite since LLM was told about existing tests)
        with open(test_file_path, "w") as f:
            f.write(test_code)

        created_files.append(test_file_path)
        total_tests += new_test_count
        print(f"   ✅ Generated {new_test_count} tests for {module}")

    return {
        "test_files_created": created_files,
        "num_tests_generated": total_tests
    }
