"""
Healer Agent (Reporting-Only Mode)
==================================
Analyzes coverage gaps and reports uncovered lines.
Does NOT generate tests - that's the Tester's job.

Responsibilities:
  ✔ Analyze coverage.json for gaps
  ✔ Report uncovered lines per file
  ✔ Detect potential dead code
  ✔ Provide actionable report for Tester
"""

import json
import os
from typing import Dict, List, Optional

# Import from centralized config
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import COVERAGE_THRESHOLD

# -----------------------------
# CONFIGURATION
# -----------------------------
COVERAGE_FILE = "coverage.json"

# -----------------------------
# COVERAGE ANALYSIS
# -----------------------------

def get_uncovered_lines(coverage_file: str = COVERAGE_FILE) -> Dict[str, List[int]]:
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


def get_coverage_percent(coverage_file: str = COVERAGE_FILE) -> Optional[float]:
    """Get total coverage percentage."""
    if not os.path.exists(coverage_file):
        return None
    
    with open(coverage_file) as f:
        coverage_data = json.load(f)
    
    return coverage_data.get("totals", {}).get("percent_covered")


# -----------------------------
# FUNCTION NAME EXTRACTION
# -----------------------------

def get_uncovered_functions(coverage_file: str = COVERAGE_FILE) -> Dict[str, List[str]]:
    """
    Extract function names with 0% or low coverage.
    Returns: {file_path: [function_names]}
    """
    if not os.path.exists(coverage_file):
        return {}
    
    with open(coverage_file) as f:
        coverage_data = json.load(f)
    
    uncovered_funcs = {}
    
    for file, data in coverage_data.get("files", {}).items():
        functions = data.get("functions", {})
        file_funcs = []
        
        for func_name, func_data in functions.items():
            if not func_name:  # Skip empty function name (module level)
                continue
            summary = func_data.get("summary", {})
            percent = summary.get("percent_covered", 100)
            missing = summary.get("missing_lines", 0)
            
            # Include functions with <50% coverage or any missing lines
            if percent < 50 or missing > 0:
                file_funcs.append({
                    "name": func_name,
                    "coverage": percent,
                    "missing_lines": missing
                })
        
        if file_funcs:
            # Sort by coverage (lowest first) to prioritize
            file_funcs.sort(key=lambda x: x["coverage"])
            uncovered_funcs[file] = file_funcs
    
    return uncovered_funcs


# -----------------------------
# DEAD CODE DETECTION
# -----------------------------

def detect_dead_code(coverage_file: str = COVERAGE_FILE) -> List[dict]:
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
        
        # Conservative: only flag small gaps (likely dead code)
        if 0 < len(missing_lines) <= 2:
            dead_code_candidates.append({
                "file": file,
                "lines": missing_lines
            })
    
    return dead_code_candidates


# -----------------------------
# BUILD COVERAGE CONTEXT FOR TESTER
# -----------------------------

def build_coverage_context(
    uncovered: Dict[str, List[int]],
    uncovered_functions: Optional[Dict[str, List[dict]]] = None
) -> Dict[str, dict]:
    """
    Build coverage context that Tester can use to generate targeted tests.
    Now includes function names for better targeting.
    """
    coverage_context = {}
    
    for file_path, lines in uncovered.items():
        if file_path.startswith("src/") and file_path.endswith(".py"):
            module = file_path[4:-3]  # Remove "src/" and ".py"
            
            # Get function names for this file
            func_list = []
            if uncovered_functions and file_path in uncovered_functions:
                func_list = [f["name"] for f in uncovered_functions[file_path]]
            
            coverage_context[module] = {
                "uncovered_lines": lines,
                "uncovered_functions": func_list,
                "line_count": len(lines)
            }
    
    return coverage_context


# -----------------------------
# MAIN HEALING AGENT (REPORTING ONLY)
# -----------------------------

def healing_agent(
    planner_output: dict,
    executor_output: dict,
    failure_analysis: Optional[dict] = None
) -> dict:
    """
    Healer Agent - Reporting Mode
    
    Analyzes coverage gaps and returns a report.
    Does NOT generate tests (Tester handles that).
    
    Returns:
        {
            "needs_healing": bool,
            "coverage_percent": float,
            "coverage_gap": float,
            "uncovered_files": {...},
            "coverage_context": {...},  # For Tester
            "dead_code_candidates": [...],
            "recommendation": str
        }
    """
    print("\n📋 Healer Agent (Reporting Mode)")
    print("=" * 40)
    
    # Get current coverage
    coverage_percent = executor_output.get("coverage_percent")
    if coverage_percent is None:
        coverage_percent = get_coverage_percent()
    
    # Analyze uncovered lines
    uncovered = get_uncovered_lines()
    
    # Get uncovered function names for targeted testing
    uncovered_functions = get_uncovered_functions()
    
    # Build context for Tester (now includes function names)
    coverage_context = build_coverage_context(uncovered, uncovered_functions)
    
    # Detect dead code
    dead_code = detect_dead_code()
    
    # Determine if healing is needed
    needs_healing = coverage_percent is not None and coverage_percent < COVERAGE_THRESHOLD
    coverage_gap = COVERAGE_THRESHOLD - (coverage_percent or 0)
    
    # Build report
    report = {
        "needs_healing": needs_healing,
        "coverage_percent": coverage_percent,
        "coverage_threshold": COVERAGE_THRESHOLD,
        "coverage_gap": round(coverage_gap, 2) if coverage_gap > 0 else 0,
        "uncovered_files": uncovered,
        "coverage_context": coverage_context,
        "dead_code_candidates": dead_code,
        "modules_needing_tests": list(coverage_context.keys())
    }
    
    # Generate recommendation
    if not needs_healing:
        report["recommendation"] = "Coverage threshold met. No action needed."
        print(f"  ✅ Coverage: {coverage_percent:.2f}% (threshold: {COVERAGE_THRESHOLD}%)")
    else:
        total_uncovered = sum(len(lines) for lines in uncovered.values())
        report["recommendation"] = (
            f"Generate targeted tests for {total_uncovered} uncovered lines "
            f"across {len(coverage_context)} module(s)."
        )
        print(f"  ⚠️ Coverage: {coverage_percent:.2f}% (need {coverage_gap:.2f}% more)")
        print(f"  📝 Modules needing tests: {list(coverage_context.keys())}")
    
    if dead_code:
        print(f"  💀 Dead code candidates: {len(dead_code)} file(s)")
        for item in dead_code:
            print(f"     - {item['file']}: lines {item['lines']}")
    
    print("=" * 40)
    
    return report




