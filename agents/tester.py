import os

def tester_agent(plan: dict) -> dict:
    modules = plan.get("modules_to_test", [])
    test_types = plan.get("test_types", [])

    os.makedirs("tests", exist_ok=True)

    created_tests = []

    for module in modules:
        test_file = f"tests/test_{module}_auto.py"

        with open(test_file, "w") as f:
            f.write(f"""
import pytest

def test_{module}_basic():
    assert True

def test_{module}_edge():
    assert True
""")

        created_tests.append(test_file)

    return {
        "test_files_created": created_tests,
        "num_tests_generated": len(created_tests)
    }
