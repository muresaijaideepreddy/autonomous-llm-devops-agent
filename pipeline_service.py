import os
import json
import subprocess
import sys

RUNS_DIR = "runs"

def run_pipeline_from_ui():
    """
    Executes the orchestrator (full CI pipeline).
    """
    subprocess.run([sys.executable, "orchestrator.py"], check=False)

def list_runs():
    if not os.path.exists(RUNS_DIR):
        return []
    return sorted(os.listdir(RUNS_DIR))

def load_run(run_file: str) -> dict:
    with open(os.path.join(RUNS_DIR, run_file)) as f:
        return json.load(f)

def get_latest_run():
    runs = list_runs()
    if not runs:
        return None
    return load_run(runs[-1])
