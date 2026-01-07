"""
Tester Agent
============
Auto-generates pytest test cases using Google Gemini LLM.

Responsibilities:
- Read planner output
- Read relevant source code
- Prompt Gemini to generate pytest tests
- Persist tests to /tests directory
- Return strict schema output to orchestrator

Design Notes:
- Uses Gemini free API (no billing required)
- Deterministic temperature for CI stability
- Clean fallback if source file missing
"""

import os
from typing import Dict, List
import google.generativeai as genai

# 🔹 Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise EnvironmentError("GEMINI_API_KEY environment variable not set")

genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-1.5-flash"

def generate_tests_with_gemini(prompt: str) -> str:
    """
    Calls Gemini LLM to generate pytest-compatible test code.
    """
    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.2,
            "max_output_tokens": 1024
        }
    )
    return response.text.strip()


def tester_agent(plan: Dict) -> Dict:
    """
    Tester Agent
    ------------
    Input:
        plan:
            modules_to_test: List[str]
            test_types: List[str]
            risk_level: str

    Output:
        {
            "test_files_created": List[str],
            "num_tests_generated": int
        }
    """

    modules: List[str] = plan.get("modules_to_test", [])
    risk_level: str = plan.get("risk_level", "low")

    os.makedirs("tests", exist_ok=True)

    created_files: List[str] = []
    total_tests = 0

    for module in modules:
        source_path = f"src/{module}.py"

        if not os.path.exists(source_path):
            print(f"⚠️ Source file not found: {source_path}")
            continue

        # 🔹 Read source code
        with open(source_path, "r") as f:
            source_code = f.read()

        # 🔹 Build LLM prompt
        prompt = f"""
You are a senior QA engineer.

Generate pytest test cases for the following Python module.

Module name: {module}
Risk level: {risk_level}

Rules:
- Use pytest
- Include edge cases
- Follow best testing practices
- Only output valid Python code
- Do NOT include explanations or markdown

Python code:
{source_code}
"""

        # 🔹 Call Gemini
        test_code = generate_tests_with_gemini(prompt)

        # 🔹 Save generated tests
        test_file_path = f"tests/test_{module}_auto.py"
        with open(test_file_path, "w") as f:
            f.write(test_code)

        created_files.append(test_file_path)
        total_tests += test_code.count("def test_")

        print(f"✅ Generated tests for {module}: {test_file_path}")

    return {
        "test_files_created": created_files,
        "num_tests_generated": total_tests
    }
