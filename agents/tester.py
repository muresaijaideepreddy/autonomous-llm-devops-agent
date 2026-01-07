"""
Tester Agent
============

Responsibility:
---------------
Automatically generates pytest test cases using an LLM based on
the Planner Agent’s output and the source code under test.

Role in Pipeline:
-----------------
Planner → Tester → Executor

- Planner decides *what* to test
- Tester generates *how* to test (pytest files)
- Executor runs the tests

This agent is designed to be deterministic in structure,
but intelligent in test generation via an LLM.
"""

import os
from typing import Dict, List
from openai import OpenAI

# Initialize OpenAI client (expects OPENAI_API_KEY in environment)
client = OpenAI()


def generate_tests_with_llm(
    module: str,
    source_code: str,
    risk_level: str
) -> str:
    """
    Calls OpenAI to generate pytest tests for a given module.

    Args:
        module (str): Name of the module under test (e.g., "payments")
        source_code (str): Source code of the module
        risk_level (str): Risk level from planner ("low" | "medium" | "high")

    Returns:
        str: Generated pytest test code
    """

    prompt = f"""
You are a senior QA engineer.

Task:
Generate production-quality pytest test cases for the following Python module.

Module name: {module}
Risk level: {risk_level}

Requirements:
- Use pytest
- Cover normal, edge, and failure cases
- Follow best testing practices
- Do NOT include explanations, only code
- Assume module is imported correctly

Source Code:
{source_code}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You generate high-quality automated tests."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )

    return response.choices[0].message.content.strip()


def tester_agent(plan: Dict) -> Dict:
    """
    Tester Agent (LLM-Based Test Generator)

    Input Schema (from Planner Agent):
    ---------------------------------
    {
        "modules_to_test": ["payments"],
        "test_types": ["unit", "edge"],
        "risk_level": "high"
    }

    Output Schema:
    --------------
    {
        "test_files_created": ["tests/test_payments_auto.py"],
        "num_tests_generated": 3
    }
    """

    modules: List[str] = plan.get("modules_to_test", [])
    risk_level: str = plan.get("risk_level", "low")

    # Ensure tests directory exists
    os.makedirs("tests", exist_ok=True)

    created_files: List[str] = []
    total_tests: int = 0

    for module in modules:
        source_path = f"src/{module}.py"

        # Skip if source file does not exist
        if not os.path.exists(source_path):
            continue

        # Read source code
        with open(source_path, "r") as f:
            source_code = f.read()

        # Generate tests using LLM
        test_code = generate_tests_with_llm(
            module=module,
            source_code=source_code,
            risk_level=risk_level
        )

        # Save generated tests
        test_file_path = f"tests/test_{module}_auto.py"
        with open(test_file_path, "w") as f:
            f.write(test_code)

        created_files.append(test_file_path)

        # Simple heuristic to count tests
        total_tests += test_code.count("def test_")

    return {
        "test_files_created": created_files,
        "num_tests_generated": total_tests
    }


# 🔹 Manual test hook (for local debugging only)
if __name__ == "__main__":
    sample_plan = {
        "modules_to_test": ["payments"],
        "test_types": ["unit", "edge"],
        "risk_level": "high"
    }

    output = tester_agent(sample_plan)
    print(output)
