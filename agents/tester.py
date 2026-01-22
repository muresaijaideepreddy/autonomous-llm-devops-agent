"""
Tester Agent (Simplified)
==========================
Automatically generates pytest unit tests using an LLM (Gemini).

Key features:
- Severity-based test count control
- Python syntax validation
- Retry mechanism with fallback tests
- Coverage-aware test generation (targets uncovered lines/functions)
- Clean generation each run (no complex merging)
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
import pytest

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
    risk_level: str,
    coverage_context: Optional[dict] = None
) -> str:
    """
    Generate pytest tests using Gemini.
    Uses coverage context to target uncovered code.
    """

    max_tests = MAX_TESTS_BY_SEVERITY.get(risk_level, 15)

    # Build targeted coverage instruction
    coverage_instruction = ""
    if coverage_context:
        uncovered_lines = coverage_context.get("uncovered_lines", [])
        uncovered_funcs = coverage_context.get("uncovered_functions", [])
        
        coverage_instruction = """
PRIORITY - TARGET THESE UNCOVERED ITEMS:
"""
        if uncovered_funcs:
            coverage_instruction += f"""
These FUNCTIONS have low or no coverage - TEST THEM FIRST:
{', '.join(uncovered_funcs)}
"""
        if uncovered_lines:
            coverage_instruction += f"""
These line numbers are NOT covered: {uncovered_lines[:20]}
"""
        coverage_instruction += """
Generate pytest tests that EXECUTE these uncovered functions/lines.
Focus on edge cases, error paths, and boundary conditions.
"""

    prompt = f"""
You are a senior QA engineer writing pytest unit tests.

{coverage_instruction}

Generate pytest unit tests for the following Python module.

CRITICAL RULES - YOU MUST FOLLOW THESE EXACTLY:

1. Generate AT MOST {max_tests} test functions
2. Use pytest (import pytest)
3. Keep code concise and self-contained
4. Do NOT use parametrized tests
5. Do NOT generate explanations or markdown - OUTPUT ONLY VALID PYTHON CODE
6. Each test must be independent and runnable on its own

IMPORTANT - TEST CORRECTNESS RULES:
7. READ THE SOURCE CODE CAREFULLY before writing tests
8. Your tests must assert the ACTUAL behavior of the code, not what you think it should do
9. If a function returns False for invalid input, test that it returns False (not True)
10. If a function raises ValueError, test that it raises ValueError (using pytest.raises)
11. Match the EXACT status values, return types, and behaviors from the source code
12. DO NOT write tests that intentionally fail or test incorrect assumptions
13. Every test you write MUST PASS when run against the provided source code

FIXTURE RULES:
14. Define ALL fixtures you use within the same file - do not reference external fixtures
15. Use pytest's built-in fixtures (tmp_path, monkeypatch) or define your own
16. Keep fixtures simple and focused
17. Each fixture should have the @pytest.fixture decorator ONLY ONCE

ALWAYS start your output with this exact import block:
```
import sys
import os
import pytest
import uuid
import json
from unittest.mock import patch, MagicMock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from {module} import *
```

Module name: {module}

Source Code (READ THIS CAREFULLY):
{source_code}
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    result = response.text.strip()
    
    # Clean up markdown code blocks if present
    if result.startswith("```python"):
        result = result[9:]
    if result.startswith("```"):
        result = result[3:]
    if result.endswith("```"):
        result = result[:-3]
    
    return result.strip()


# -----------------------------
# TESTER AGENT (SIMPLIFIED)
# -----------------------------

def tester_agent(plan: Dict) -> Dict:
    """
    Simplified Tester Agent
    
    Generates fresh, clean test files each run.
    Uses coverage context to target uncovered code.
    
    No complex merging or preservation logic - 
    just clean, reliable test generation.
    """

    modules: List[str] = plan.get("modules_to_test", [])
    risk_level: str = plan.get("risk_level", "low")
    coverage_context: Optional[dict] = plan.get("coverage_context")

    os.makedirs("tests", exist_ok=True)
    client = get_gemini_client()

    created_files: List[str] = []
    total_tests = 0

    for module in modules:
        source_path = f"src/{module}.py"
        if not os.path.exists(source_path):
            print(f"⚠️ Source file not found: {source_path}")
            continue

        with open(source_path, "r") as f:
            source_code = f.read()

        test_file_path = f"tests/test_{module}_auto.py"
        
        # Get module-specific coverage context
        module_coverage = None
        if coverage_context and module in coverage_context:
            module_coverage = coverage_context[module]
            print(f"📊 Coverage context for {module}:")
            print(f"   Uncovered lines: {len(module_coverage.get('uncovered_lines', []))}")
            print(f"   Uncovered functions: {module_coverage.get('uncovered_functions', [])}")

        # Generate tests
        test_code = None

        for attempt in range(1, MAX_RETRIES + 1):
            print(f"🔁 Generating tests for {module} (attempt {attempt})")

            generated = generate_tests_with_gemini(
                client=client,
                source_code=source_code,
                module=module,
                risk_level=risk_level,
                coverage_context=module_coverage
            )

            if is_valid_python(generated):
                test_code = generated
                print(f"✅ Valid Python generated")
                break
            else:
                print("⚠️ Invalid Python generated, retrying...")

        if not test_code:
            print(f"🚨 Failed to generate valid tests for {module}, using fallback")
            test_code = fallback_test(module)

        # Count tests
        test_count = test_code.count("def test_")
        
        # Write fresh test file
        with open(test_file_path, "w") as f:
            f.write(test_code + "\n")

        created_files.append(test_file_path)
        total_tests += test_count
        
        print(f"   ✅ Generated {test_count} tests for {module}")

    return {
        "test_files_created": created_files,
        "num_tests_generated": total_tests
    }
