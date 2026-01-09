import time
from pipeline_service import (
    run_pipeline_from_ui,
    list_runs,
    load_run
)

# -------------------------------
# PIPELINE ACTIONS
# -------------------------------

def trigger_pipeline_run():
    """
    Runs the full pipeline from UI.
    """
    run_pipeline_from_ui()
    time.sleep(1)

# -------------------------------
# DATA LOADERS
# -------------------------------

def get_available_runs():
    return list_runs()

def get_run_data(run_file):
    return load_run(run_file)

# -------------------------------
# FORMAT HELPERS
# -------------------------------

def risk_badge(risk):
    return {
        "low": "🟢 LOW",
        "medium": "🟡 MEDIUM",
        "high": "🔴 HIGH"
    }.get(risk, risk)

def status_badge(status):
    return {
        "pass": "✅ PASSED",
        "fail": "❌ FAILED",
        "no_tests": "⚠️ NO TESTS",
        "error": "🚨 ERROR"
    }.get(status, status)
