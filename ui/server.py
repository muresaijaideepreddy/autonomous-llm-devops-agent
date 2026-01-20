"""
Dashboard Server for Autonomous Testing Framework
==================================================
Serves dashboard UI and provides API endpoints for run data.
Does NOT modify orchestrator or any existing code.
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pathlib import Path
import json
import os
import asyncio

from streaming_orchestrator import StreamingOrchestrator

# -----------------------------
# CONFIGURATION
# -----------------------------
PROJECT_ROOT = Path(__file__).parent.parent
RUNS_DIR = PROJECT_ROOT / "runs"
METRICS_FILE = PROJECT_ROOT / "metrics" / "run_metrics.json"
COVERAGE_FILE = PROJECT_ROOT / "coverage.json"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Autonomous Testing Dashboard")


# -----------------------------
# PIPELINE EXECUTION ENDPOINTS
# -----------------------------

@app.post("/api/run")
async def trigger_pipeline(request: Request):
    """Trigger a new pipeline run and return the run ID."""
    try:
        body = await request.json()
    except:
        body = {}
    
    repo_event = body.get("repo_event", {
        "changed_files": ["src/payments.py"],
        "commit_id": "manual_run",
        "issue": {
            "id": 1,
            "title": "Manual pipeline trigger",
            "description": "Triggered from dashboard",
            "severity": "medium"
        }
    })
    
    orchestrator = StreamingOrchestrator()
    return {"run_id": orchestrator.run_id, "status": "Use /api/run/stream to get live updates"}


@app.get("/api/run/stream")
async def stream_pipeline(commit_id: str = "manual_run"):
    """Stream pipeline execution events via Server-Sent Events."""
    
    repo_event = {
        "changed_files": ["src/payments.py"],
        "commit_id": commit_id,
        "issue": {
            "id": 1,
            "title": "Manual pipeline trigger",
            "description": "Triggered from dashboard",
            "severity": "medium"
        }
    }
    
    orchestrator = StreamingOrchestrator()
    
    async def event_generator():
        async for event in orchestrator.run_pipeline_streaming(repo_event):
            yield event
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# -----------------------------
# API ENDPOINTS
# -----------------------------

@app.get("/api/runs")
async def get_all_runs():
    """Get list of all pipeline runs with basic info, sorted by timestamp (newest first)"""
    runs = []
    
    if RUNS_DIR.exists():
        for run_file in RUNS_DIR.glob("run_*.json"):
            try:
                with open(run_file) as f:
                    data = json.load(f)
                    runs.append({
                        "run_id": data.get("run_id"),
                        "start_time": data.get("start_time"),
                        "end_time": data.get("end_time"),
                        "status": data.get("executor_output", {}).get("status"),
                        "coverage": data.get("executor_output", {}).get("coverage_percent"),
                        "passed": data.get("executor_output", {}).get("passed_tests", 0),
                        "failed": len(data.get("executor_output", {}).get("failed_tests", [])),
                        "total": data.get("executor_output", {}).get("total_tests", 0)
                    })
            except Exception:
                continue
    
    # Sort by start_time descending (newest first)
    runs.sort(key=lambda r: r.get("start_time") or "", reverse=True)
    
    return {"runs": runs}


@app.get("/api/runs/{run_id}")
async def get_run_detail(run_id: str):
    """Get detailed info for a specific run"""
    run_file = RUNS_DIR / f"{run_id}.json"
    
    if not run_file.exists():
        return JSONResponse({"error": "Run not found"}, status_code=404)
    
    with open(run_file) as f:
        return json.load(f)


@app.get("/api/metrics")
async def get_metrics():
    """Get historical metrics from run_metrics.json"""
    metrics = []
    
    if METRICS_FILE.exists():
        with open(METRICS_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        metrics.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    
    # Return last 50 metrics
    return {"metrics": metrics[-50:]}


@app.get("/api/coverage")
async def get_coverage():
    """Get current coverage data"""
    if not COVERAGE_FILE.exists():
        return {"error": "No coverage data"}
    
    with open(COVERAGE_FILE) as f:
        return json.load(f)


@app.post("/api/coverage/run")
async def run_coverage():
    """
    Run pytest with coverage and return results.
    This generates fresh coverage.json that can be used by the pipeline.
    """
    import subprocess
    
    try:
        # Run pytest with coverage
        result = subprocess.run(
            [
                "pytest",
                "--cov=src",
                "--cov-report=term",
                "--cov-report=json",
                "tests/"
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )
        
        # Parse coverage.json if it exists
        coverage_data = None
        if COVERAGE_FILE.exists():
            with open(COVERAGE_FILE) as f:
                coverage_data = json.load(f)
        
        # Extract test results from output
        output = result.stdout + result.stderr
        
        # Count passed/failed from output
        import re
        passed = 0
        failed = 0
        total = 0
        
        passed_match = re.search(r"(\d+) passed", output)
        if passed_match:
            passed = int(passed_match.group(1))
        
        failed_match = re.search(r"(\d+) failed", output)
        if failed_match:
            failed = int(failed_match.group(1))
        
        collected_match = re.search(r"collected (\d+) item", output)
        if collected_match:
            total = int(collected_match.group(1))
        
        coverage_percent = None
        if coverage_data:
            coverage_percent = coverage_data.get("totals", {}).get("percent_covered")
        
        return {
            "success": True,
            "coverage_percent": coverage_percent,
            "passed": passed,
            "failed": failed,
            "total": total,
            "returncode": result.returncode,
            "output": output[-2000:],  # Last 2000 chars of output
            "uncovered_files": {
                file: data.get("missing_lines", [])
                for file, data in (coverage_data or {}).get("files", {}).items()
                if data.get("missing_lines")
            } if coverage_data else {}
        }
        
    except subprocess.TimeoutExpired:
        return {"error": "Coverage run timed out", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


@app.get("/api/latest")
async def get_latest_run():
    """Get the most recent run by actual timestamp"""
    if not RUNS_DIR.exists():
        return {"error": "No runs found"}
    
    run_files = list(RUNS_DIR.glob("run_*.json"))
    
    if not run_files:
        return {"error": "No runs found"}
    
    # Load all runs and find the one with latest start_time
    latest_run = None
    latest_time = ""
    
    for run_file in run_files:
        try:
            with open(run_file) as f:
                data = json.load(f)
                start_time = data.get("start_time", "")
                if start_time > latest_time:
                    latest_time = start_time
                    latest_run = data
        except Exception:
            continue
    
    if latest_run:
        return latest_run
    
    return {"error": "No valid runs found"}


# -----------------------------
# STATIC FILES & HTML
# -----------------------------

@app.get("/")
async def serve_dashboard():
    """Serve the main dashboard HTML"""
    return FileResponse(STATIC_DIR / "index.html")


# Mount static files for CSS/JS
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# -----------------------------
# RUN SERVER
# -----------------------------
if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Dashboard Server...")
    print("📊 Dashboard: http://localhost:8081")
    uvicorn.run(app, host="0.0.0.0", port=8081)
