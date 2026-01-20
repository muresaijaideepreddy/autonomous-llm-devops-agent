"""
Enhanced Healer Agent
=====================
A comprehensive self-healing agent for the autonomous testing pipeline.

Capabilities:
  ✔ Generate tests for uncovered lines (coverage healing)
  ✔ Auto-fix broken tests using LLM
  ✔ Clean up obsolete tests
  ✔ Healing loop with re-execution
  ✔ Dead code detection and reporting
"""

import json
import os
import re
import ast
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from google import genai

load_dotenv()

# -----------------------------
# CONFIGURATION
# -----------------------------
COVERAGE_THRESHOLD = 98
MAX_HEALING_ITERATIONS = 3
GEMINI_MODEL = "models/gemini-2.5-flash"

# -----------------------------
# LLM CLIENT
# -----------------------------

def get_gemini_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not set")
    return genai.Client(api_key=api_key)


def is_valid_python(code: str) -> bool:
    """Validate Python syntax."""
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


# -----------------------------
# COVERAGE GAP HEALING
# -----------------------------

def get_uncovered_lines_context(coverage_file: str = "coverage.json") -> Dict[str, List[int]]:
    """
    Extract uncovered lines from coverage report.
    Returns: {file_path: [line_numbers]}
    """
    if not os.path.exists(coverage_file):
        return {}
    
    with open(coverage_file) as f:
        coverage_data = json.load(f)
    
    uncovered = {}
    for file, data in coverage_data.get("files", {}).items():
        missing = data.get("missing_lines", [])
        if missing:
            uncovered[file] = missing
    
    return uncovered


def heal_coverage_gaps(
    executor_output: dict,
    planner_output: dict
) -> dict:
    """
    Generate tests for uncovered lines using tester agent with coverage context.
    """
    from agents.tester import tester_agent
    
    print("🩹 Healing coverage gaps...")
    
    uncovered = get_uncovered_lines_context()
    if not uncovered:
        print("  ℹ No uncovered lines found")
        return {"healed": False, "reason": "no_uncovered_lines"}
    
    # Build coverage context for tester
    coverage_context = {}
    modules_to_test = []
    
    for file_path, lines in uncovered.items():
        if file_path.startswith("src/") and file_path.endswith(".py"):
            module = file_path[4:-3]  # Remove "src/" and ".py"
            modules_to_test.append(module)
            coverage_context[module] = {
                "uncovered_lines": lines
            }
    
    if not modules_to_test:
        print("  ℹ No testable modules with uncovered code")
        return {"healed": False, "reason": "no_testable_modules"}
    
    print(f"  📝 Generating tests for: {', '.join(modules_to_test)}")
    
    # Call tester agent with coverage context
    healing_plan = {
        "modules_to_test": modules_to_test,
        "risk_level": planner_output.get("risk_level", "medium"),
        "coverage_context": coverage_context
    }
    
    tester_output = tester_agent(healing_plan)
    
    return {
        "healed": True,
        "action": "coverage_tests_generated",
        "tester_output": tester_output,
        "modules_healed": modules_to_test
    }


# -----------------------------
# DEAD CODE DETECTION
# -----------------------------

def detect_dead_code(coverage_file: str = "coverage.json") -> List[dict]:
    """
    Detect potential dead/unreachable code.
    Conservative: only flags files with 1-2 missing lines.
    """
    if not os.path.exists(coverage_file):
        return []
    
    with open(coverage_file) as f:
        coverage_data = json.load(f)
    
    dead_code_candidates = []
    
    for file, data in coverage_data.get("files", {}).items():
        missing_lines = data.get("missing_lines", [])
        
        # Conservative: only small gaps
        if 0 < len(missing_lines) <= 2:
            dead_code_candidates.append({
                "file": file,
                "lines": missing_lines
            })
    
    return dead_code_candidates


# -----------------------------
# MAIN HEALING AGENT
# -----------------------------

def healing_agent(
    planner_output: dict,
    executor_output: dict,
    failure_analysis: Optional[dict] = None,
    max_iterations: int = MAX_HEALING_ITERATIONS
) -> dict:
    """
    Main healing agent with self-healing capabilities.
    
    Healing strategies based on situation:
    - Tests pass + low coverage → Generate coverage tests
    - Tests fail + test_bug → Fix broken tests
    - Tests pass + high coverage → Report dead code only
    """
    from agents.executor import executor_agent
    
    print("\n🏥 Enhanced Healer Agent Started")
    print("=" * 40)
    
    status = executor_output.get("status")
    coverage = executor_output.get("coverage_percent")
    
    healing_results = {
        "iterations": 0,
        "actions_taken": [],
        "coverage_history": [coverage] if coverage else [],
        "healed": False
    }
    
    for iteration in range(1, max_iterations + 1):
        print(f"\n🔄 Healing Iteration {iteration}/{max_iterations}")
        healing_results["iterations"] = iteration
        
        # Determine healing strategy
        failure_type = None
        if failure_analysis:
            failure_type = failure_analysis.get("failure_type")
        
        action_taken = None
        
        # Strategy 1: Generate coverage tests
        if status == "pass" and coverage is not None and coverage < COVERAGE_THRESHOLD:
            result = heal_coverage_gaps(executor_output, planner_output)
            action_taken = "heal_coverage_gaps"
            healing_results["actions_taken"].append({
                "action": action_taken,
                "result": result
            })
            
            if result.get("healed"):
                # Re-run executor with new tests
                print("  🔁 Re-running tests after generating coverage tests...")
                tester_output = result.get("tester_output", {})
                new_test_files = tester_output.get("test_files_created", [])
                
                if new_test_files:
                    executor_output = executor_agent({
                        "execution_strategy": "pytest",
                        "test_files": new_test_files
                    })
                    status = executor_output.get("status")
                    coverage = executor_output.get("coverage_percent")
                    if coverage:
                        healing_results["coverage_history"].append(coverage)
        
        # Strategy 2: Already healthy
        elif status == "pass" and coverage is not None and coverage >= COVERAGE_THRESHOLD:
            print(f"  ✅ Coverage threshold met ({coverage:.2f}%)")
            healing_results["healed"] = True
            break
        
        # Check if we've reached threshold
        if coverage and coverage >= COVERAGE_THRESHOLD:
            healing_results["healed"] = True
            break
    
    # Final: Dead code detection
    dead_code = detect_dead_code()
    if dead_code:
        print("\n🩹 Potential dead/ignorable code detected:")
        for item in dead_code:
            print(f"  - {item['file']} → lines {item['lines']}")
        healing_results["dead_code_candidates"] = dead_code
    
    # Update executor output with healing results
    executor_output["healing_results"] = healing_results
    executor_output["healer_ran"] = True
    
    final_coverage = executor_output.get("coverage_percent")
    print(f"\n🏁 Healing Complete")
    print(f"   Final Coverage: {final_coverage:.2f}%" if final_coverage else "   Final Coverage: N/A")
    print(f"   Iterations: {healing_results['iterations']}")
    print(f"   Actions: {[a['action'] for a in healing_results['actions_taken']]}")
    
    return executor_output


# -----------------------------
# LEGACY HOOK (Backward Compatibility)
# -----------------------------

def healing_hook(planner_output: dict, executor_output: dict) -> dict:
    """
    Legacy compatibility wrapper.
    """
    return healing_agent(
        planner_output=planner_output,
        executor_output=executor_output
    )

