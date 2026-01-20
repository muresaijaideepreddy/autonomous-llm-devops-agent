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

# -----------------------------
# CONFIGURATION
# -----------------------------
COVERAGE_THRESHOLD = 98
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

def build_coverage_context(uncovered: Dict[str, List[int]]) -> Dict[str, dict]:
    """
    Build coverage context that Tester can use to generate targeted tests.
    """
    coverage_context = {}
    
    for file_path, lines in uncovered.items():
        if file_path.startswith("src/") and file_path.endswith(".py"):
            module = file_path[4:-3]  # Remove "src/" and ".py"
            coverage_context[module] = {
                "uncovered_lines": lines,
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
    
    # Build context for Tester
    coverage_context = build_coverage_context(uncovered)
    
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


# -----------------------------
# LEGACY HOOK (Backward Compatibility)
# -----------------------------

def healing_hook(planner_output: dict, executor_output: dict) -> dict:
    """Legacy compatibility wrapper."""
    return healing_agent(
        planner_output=planner_output,
        executor_output=executor_output
    )


# -----------------------------
# STANDALONE TEST
# -----------------------------

if __name__ == "__main__":
    sample_executor = {
        "status": "pass",
        "coverage_percent": 85.5
    }
    
    report = healing_agent(
        planner_output={},
        executor_output=sample_executor
    )
    
    print("\n📊 Full Report:")
    print(json.dumps(report, indent=2))
