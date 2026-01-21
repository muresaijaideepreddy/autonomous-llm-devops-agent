"""
Tester Agent
============
Automatically generates pytest unit tests using an LLM (Gemini).
Key features:
- Severity-based test count control
- Python syntax validation
- Retry mechanism with fallback tests
- Coverage-aware test generation (for Coverage Healer)
- SMART TEST PRESERVATION: Keeps passing tests, regenerates failing ones
"""

from dotenv import load_dotenv
load_dotenv()

import os
import ast
from typing import Dict, List, Optional, Set
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

def parse_code_structure(code: str) -> Dict[str, any]:
    """
    Parse Python code to extract structural components in a SINGLE pass.
    Returns a dict with:
    - imports: str (header code)
    - fixtures: Dict[name, code]
    - tests: Dict[name, code]
    """
    if not code.strip():
        return {"imports": "", "fixtures": {}, "tests": {}}

    try:
        tree = ast.parse(code)
        lines = code.split('\n')
        
        fixtures = {}
        tests = {}
        
        # 1. Identify start of first function (test or fixture) to separate imports
        first_func_line = None
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if first_func_line is None or node.lineno < first_func_line:
                    first_func_line = node.lineno

                # Check if it's a fixture
                is_fixture = False
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name) and decorator.id == "fixture":
                        is_fixture = True
                    elif isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
                        is_fixture = True
                
                # Check if it's a test
                is_test = node.name.startswith("test_")
                
                # Extract code block
                start = node.lineno - 1
                if node.decorator_list:
                    start = node.decorator_list[0].lineno - 1
                end = node.end_lineno
                func_code = '\n'.join(lines[start:end])
                
                if is_fixture:
                    fixtures[node.name] = func_code
                elif is_test:
                    tests[node.name] = func_code
        
        # Extract imports (everything before first function)
        imports = ""
        if first_func_line:
            imports = '\n'.join(lines[:first_func_line - 1]).strip()
        else:
            imports = code.strip()  # No functions, entire file is imports/globals
            
        return {
            "imports": imports,
            "fixtures": fixtures,
            "tests": tests
        }
            
    except Exception as e:
        print(f"⚠️ Error parsing code: {e}")
        return {"imports": "", "fixtures": {}, "tests": {}}

def get_existing_test_names(test_file_path: str) -> List[str]:
    """Extract existing test function names using optimized parser."""
    if not os.path.exists(test_file_path):
        return []
    try:
        with open(test_file_path, "r") as f:
            code = f.read()
        structure = parse_code_structure(code)
        return list(structure["tests"].keys())
    except Exception:
        return []


# -----------------------------
# NEW: SMART TEST PRESERVATION
# -----------------------------

def get_bad_test_names(executor_output: dict) -> Set[str]:
    """
    Extract names of tests that FAILED or had ERRORS.
    Returns a set of test function names to EXCLUDE.
    """
    if not executor_output:
        return set()
    
    bad_names = set()
    
    # Get failed test names
    failed_tests = executor_output.get("failed_tests", [])
    for test in failed_tests:
        if " - " in test:
            name = test.split(" - ")[0].strip()
        else:
            name = test.strip()
        if "::" in name:
            name = name.split("::")[-1]
        bad_names.add(name)
    
    # Parse ERROR tests from logs (fixture not found, etc.)
    logs = executor_output.get("logs", "")
    for line in logs.split("\n"):
        if "ERROR at setup of " in line:
            # Extract test name from "ERROR at setup of test_foo"
            parts = line.split("ERROR at setup of ")
            if len(parts) > 1:
                name = parts[1].strip().replace("_", "").replace(" ", "")
                # Get actual function name
                for word in parts[1].strip().split():
                    if word.startswith("test_"):
                        bad_names.add(word)
                        break
    
    # Also parse from short summary line: "ERROR tests/test_payments_auto.py::test_foo"
    for line in logs.split("\n"):
        if line.startswith("ERROR ") and "::" in line:
            name = line.split("::")[-1].strip()
            bad_names.add(name)
    
    return bad_names

def build_preserved_test_file(
    existing_code: str,
    failed_test_names: Set[str],
    new_test_code: str,
    all_passed: bool = False
) -> str:
    """
    Build a new test file by merging components.
    Uses optimized `parse_code_structure` to avoid redundant parsing.
    """
    # 1. Parse both files in one go
    existing = parse_code_structure(existing_code)
    new = parse_code_structure(new_test_code)
    
    # 2. Merge Fixtures (New > Existing)
    all_fixtures = {**existing["fixtures"], **new["fixtures"]}
    
    # 3. Filter Existing Tests (Keep only passing)
    passing_tests = {}
    if all_passed:
        passing_tests = existing["tests"]
    else:
        for name, code in existing["tests"].items():
            if name not in failed_test_names:
                passing_tests[name] = code

    # 4. Filter New Tests (Unique only)
    unique_new_tests = {}
    for name, code in new["tests"].items():
        if name not in passing_tests:
            unique_new_tests[name] = code
            
    # Include all unique new tests (no limit)
    selected_new_tests = unique_new_tests
    
    # --- BUILD FINAL ASSUMBLY ---
    parts = []
    
    # Header
    if existing["imports"]:
        parts.append(existing["imports"])
    elif new["imports"]: # Fallback to new imports if existing parsing failed
        parts.append(new["imports"])
        
    parts.append("") # Spacer
    
    # Fixtures
    if all_fixtures:
        parts.append("# --- Fixtures ---")
        parts.extend(all_fixtures.values())
        parts.append("")

    # Preserved Tests
    if passing_tests:
        parts.append("# --- Preserved Passing Tests ---")
        parts.extend(passing_tests.values())
        parts.append("")

    # New Tests
    if selected_new_tests:
        parts.append("# --- Newly Generated Tests ---")
        parts.extend(selected_new_tests.values())
        parts.append("")
        
    return "\n".join(parts).strip() + "\n"


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
        coverage_instruction += f"""
These line numbers are NOT covered: {uncovered_lines[:20]}

Generate pytest tests that EXECUTE these uncovered functions/lines.
Focus on edge cases, error paths, and boundary conditions.
"""

    # Avoid duplicate test generation
    existing_instruction = ""
    if existing_tests:
        existing_instruction = f"""
IMPORTANT: These tests ALREADY EXIST and PASS - DO NOT regenerate them:
{', '.join(existing_tests[:20])}

Generate NEW tests that cover DIFFERENT code paths.
"""

    prompt = f"""
You are a senior QA engineer writing pytest unit tests.

{coverage_instruction}
{existing_instruction}

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

ALWAYS include this import block at the top:
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
# TESTER AGENT
# -----------------------------

def tester_agent(plan: Dict) -> Dict:
    """
    Tester Agent - Smart Test Preservation
    
    NEW BEHAVIOR:
    1. Keeps tests that PASSED from previous run
    2. Removes tests that FAILED
    3. Generates new tests for uncovered code
    4. Merges passing + new tests
    
    This ensures coverage ACCUMULATES over runs instead of oscillating.
    """

    modules: List[str] = plan.get("modules_to_test", [])
    risk_level: str = plan.get("risk_level", "low")
    coverage_context: Optional[dict] = plan.get("coverage_context")
    
    # NEW: Get executor output to know which tests passed/failed
    executor_output: Optional[dict] = plan.get("executor_output")

    os.makedirs("tests", exist_ok=True)
    client = get_gemini_client()

    created_files: List[str] = []
    total_tests = 0
    tests_preserved = 0

    for module in modules:
        source_path = f"src/{module}.py"
        if not os.path.exists(source_path):
            continue

        with open(source_path, "r") as f:
            source_code = f.read()

        test_file_path = f"tests/test_{module}_auto.py"
        
        # Read existing test file
        existing_code = ""
        existing_test_names = []
        if os.path.exists(test_file_path):
            with open(test_file_path, "r") as f:
                existing_code = f.read()
            existing_test_names = get_existing_test_names(test_file_path)
        
        # Determine which tests to keep
        # Determine which tests to keep (exclude FAILURES and ERRORS)
        bad_test_names = get_bad_test_names(executor_output)
        
        # Calculate passing tests (existing minus bad ones)
        passing_test_names = [
            name for name in existing_test_names 
            if name not in bad_test_names
        ]
        
        print(f"📊 Test Status for {module}:")
        print(f"   Existing: {len(existing_test_names)}")
        print(f"   Passing (keeping): {len(passing_test_names)}")
        print(f"   Bad (removing): {len(bad_test_names)}")

        # Get module-specific coverage context
        module_coverage = None
        if coverage_context and module in coverage_context:
            module_coverage = coverage_context[module]

        # Generate new tests
        new_test_code = None

        for attempt in range(1, MAX_RETRIES + 1):
            print(f"🔁 Generating new tests for {module} (attempt {attempt})")

            generated = generate_tests_with_gemini(
                client=client,
                source_code=source_code,
                module=module,
                risk_level=risk_level,
                coverage_context=module_coverage,
                existing_tests=passing_test_names  # Tell LLM about passing tests to avoid duplicates
            )

            if is_valid_python(generated):
                new_test_code = generated
                break
            else:
                print("⚠️ Invalid Python generated, retrying...")

        if not new_test_code:
            print(f"🚨 Failed to generate valid tests for {module}, using fallback")
            new_test_code = fallback_test(module)

        # Build the final test file
        if existing_code.strip():
            # Merge: keep passing tests + add new unique tests
            final_code = build_preserved_test_file(
                existing_code=existing_code,
                failed_test_names=bad_test_names,
                new_test_code=new_test_code,
                all_passed=False # Always filter using bad_test_names
            )
            tests_preserved = len(passing_test_names)
        else:
            # No existing tests, use new code directly
            final_code = new_test_code
        
        # Count total tests
        final_test_count = final_code.count("def test_")
        new_test_count = final_test_count - tests_preserved
        
        # Write the final file
        with open(test_file_path, "w") as f:
            f.write(final_code)

        created_files.append(test_file_path)
        total_tests += final_test_count
        
        print(f"   ✅ Final: {final_test_count} tests ({tests_preserved} preserved + {new_test_count} new)")

    return {
        "test_files_created": created_files,
        "num_tests_generated": total_tests,
        "tests_preserved": tests_preserved
    }
