"""
Streaming Orchestrator for Live Pipeline UI
============================================
Wraps the main orchestrator to emit Server-Sent Events for real-time UI updates.
"""

import asyncio
import json
import uuid
import os
import sys
from datetime import datetime, timezone
from typing import AsyncGenerator
from pathlib import Path

# Add parent directory (project root) to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

from agents.planner import planner_agent
from agents.tester import tester_agent
from agents.executor import executor_agent
from agents.failure_analysis import failure_analysis_agent
from agents.healer import healing_agent

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
COVERAGE_THRESHOLD = 98
ENABLE_COVERAGE_HEALING = True
TEST_DIR = "tests"


class StreamingOrchestrator:
    """
    Orchestrator that yields SSE events for each pipeline stage.
    """
    
    def __init__(self):
        self.run_id = f"run_{uuid.uuid4().hex[:8]}"
        self.start_time = None
        self.events = []
        
    def emit(self, event_type: str, stage: str = None, message: str = None, data: dict = None):
        """Create an SSE event."""
        event = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        if stage:
            event["stage"] = stage
        if message:
            event["message"] = message
        if data:
            event["data"] = data
        self.events.append(event)
        return event
    
    async def run_pipeline_streaming(self, repo_event: dict) -> AsyncGenerator[str, None]:
        """
        Run the pipeline and yield SSE events for each step.
        """
        self.start_time = datetime.now(timezone.utc)
        project_root = Path(__file__).parent.parent
        os.chdir(project_root)
        
        pipeline_state = {
            "run_id": self.run_id,
            "planner_output": None,
            "tester_output": None,
            "executor_output": None,
            "failure_analysis": None,
            "start_time": self.start_time.isoformat(),
            "end_time": None
        }
        
        # ─────────────────────────────────────────
        # PIPELINE START
        # ─────────────────────────────────────────
        yield self._format_sse(self.emit(
            "pipeline_start",
            message="Autonomous CI Pipeline Started",
            data={
                "run_id": self.run_id,
                "commit": repo_event.get("commit_id", "unknown")
            }
        ))
        await asyncio.sleep(0.3)
        
        # ─────────────────────────────────────────
        # 1️⃣ PLANNER
        # ─────────────────────────────────────────
        yield self._format_sse(self.emit("stage_start", "planner", "Analyzing repository event"))
        await asyncio.sleep(0.2)
        
        yield self._format_sse(self.emit("log", "planner", f"Processing changed files: {repo_event.get('changed_files', [])}"))
        await asyncio.sleep(0.1)
        
        planner_output = planner_agent(repo_event)
        pipeline_state["planner_output"] = planner_output
        
        yield self._format_sse(self.emit(
            "stage_complete", 
            "planner", 
            f"Identified modules: {planner_output.get('modules_to_test', [])}",
            data=planner_output
        ))
        await asyncio.sleep(0.3)
        
        # ─────────────────────────────────────────
        # 2️⃣ COLLECT EXISTING TESTS
        # ─────────────────────────────────────────
        test_dir = project_root / TEST_DIR
        test_dir.mkdir(exist_ok=True)
        test_files = [
            str(test_dir / f)
            for f in os.listdir(test_dir)
            if f.startswith("test_") and f.endswith(".py")
        ]
        
        yield self._format_sse(self.emit("log", "planner", f"Existing tests found: {len(test_files)}"))
        await asyncio.sleep(0.2)
        
        # ─────────────────────────────────────────
        # 3️⃣ EXECUTOR (EXISTING TESTS)
        # ─────────────────────────────────────────
        executor_output = None
        coverage = None
        status = None
        
        if test_files:
            yield self._format_sse(self.emit("stage_start", "executor", "Running existing tests"))
            await asyncio.sleep(0.2)
            
            yield self._format_sse(self.emit("log", "executor", f"Found {len(test_files)} test file(s)"))
            await asyncio.sleep(0.1)
            
            yield self._format_sse(self.emit("log", "executor", "Initializing pytest runner..."))
            await asyncio.sleep(0.1)
            
            yield self._format_sse(self.emit("log", "executor", "Collecting tests..."))
            await asyncio.sleep(0.1)
            
            executor_output = executor_agent({
                "execution_strategy": "pytest",
                "test_files": test_files
            })
            
            pipeline_state["executor_output"] = executor_output
            status = executor_output.get("status")
            coverage = executor_output.get("coverage_percent")
            passed = executor_output.get("passed_tests", 0)
            total = executor_output.get("total_tests", 0)
            failed = len(executor_output.get("failed_tests", []))
            
            yield self._format_sse(self.emit("log", "executor", f"Tests executed: {total}"))
            await asyncio.sleep(0.1)
            
            yield self._format_sse(self.emit("log", "executor", f"Passed: {passed} | Failed: {failed}"))
            await asyncio.sleep(0.1)
            
            if coverage is not None:
                yield self._format_sse(self.emit("log", "executor", f"Coverage: {coverage:.2f}%"))
                await asyncio.sleep(0.1)
                
                # Coverage status message
                if coverage >= COVERAGE_THRESHOLD:
                    yield self._format_sse(self.emit("log", "executor", f"✓ Coverage meets threshold ({COVERAGE_THRESHOLD}%)"))
                else:
                    yield self._format_sse(self.emit("log", "executor", f"✗ Coverage below threshold ({COVERAGE_THRESHOLD}%)"))
                await asyncio.sleep(0.1)
            
            yield self._format_sse(self.emit(
                "stage_complete",
                "executor",
                executor_output.get("summary_report", "Tests completed"),
                data={
                    "status": status,
                    "coverage": coverage,
                    "passed": passed,
                    "total": total
                }
            ))
            await asyncio.sleep(0.3)
        else:
            yield self._format_sse(self.emit("log", "executor", "No existing tests detected"))
            yield self._format_sse(self.emit("log", "executor", "Will generate new tests..."))
        
        # ─────────────────────────────────────────
        # 4️⃣ DECISION: SHOULD AGENTS RUN?
        # ─────────────────────────────────────────
        if coverage is None or coverage < COVERAGE_THRESHOLD:
            yield self._format_sse(self.emit("log", None, f"Coverage below threshold ({COVERAGE_THRESHOLD}%) — activating agents"))
            await asyncio.sleep(0.2)
            
            # 4a️⃣ TESTER
            yield self._format_sse(self.emit("stage_start", "tester", "Generating new tests"))
            await asyncio.sleep(0.2)
            
            tester_output = tester_agent(planner_output)
            pipeline_state["tester_output"] = tester_output
            
            num_tests = tester_output.get("num_tests_generated", 0)
            yield self._format_sse(self.emit(
                "stage_complete",
                "tester",
                f"Generated {num_tests} test(s)",
                data=tester_output
            ))
            await asyncio.sleep(0.3)
            
            # 4b️⃣ EXECUTOR (NEW TESTS)
            yield self._format_sse(self.emit("stage_start", "executor", "Running generated tests"))
            await asyncio.sleep(0.2)
            
            executor_output = executor_agent({
                "execution_strategy": "pytest",
                "test_files": tester_output.get("test_files_created", [])
            })
            
            pipeline_state["executor_output"] = executor_output
            status = executor_output.get("status")
            coverage = executor_output.get("coverage_percent")
            
            yield self._format_sse(self.emit(
                "stage_complete",
                "executor",
                executor_output.get("summary_report", "Tests completed"),
                data={
                    "status": status,
                    "coverage": coverage,
                    "passed": executor_output.get("passed_tests", 0),
                    "total": executor_output.get("total_tests", 0)
                }
            ))
            await asyncio.sleep(0.3)
            
            # 4c️⃣ EMIT COVERAGE DETAILS
            if coverage is not None:
                uncovered = executor_output.get("uncovered_files", {})
                yield self._format_sse(self.emit(
                    "coverage_report",
                    "executor",
                    f"Coverage: {coverage:.2f}%",
                    data={
                        "coverage_percent": coverage,
                        "threshold": COVERAGE_THRESHOLD,
                        "meets_threshold": coverage >= COVERAGE_THRESHOLD,
                        "uncovered_files": uncovered
                    }
                ))
                await asyncio.sleep(0.2)
            
            # 4d️⃣ FAILURE ANALYSIS
            failure_analysis = None
            if status in ("fail", "error"):
                yield self._format_sse(self.emit("stage_start", "failure_analysis", "Analyzing failures"))
                failure_analysis = failure_analysis_agent(executor_output)
                pipeline_state["failure_analysis"] = failure_analysis
                
                yield self._format_sse(self.emit(
                    "stage_complete",
                    "failure_analysis",
                    f"Failure type: {failure_analysis.get('failure_type')}",
                    data=failure_analysis
                ))
                await asyncio.sleep(0.2)
            
            # 4e️⃣ HEALER (Analysis mode)
            yield self._format_sse(self.emit("stage_start", "healer", "Analyzing coverage"))
            await asyncio.sleep(0.2)
            
            yield self._format_sse(self.emit("log", "healer", "Checking for coverage gaps..."))
            
            executor_output = healing_agent(
                planner_output=planner_output,
                executor_output=executor_output,
                failure_analysis=failure_analysis
            )
            
            pipeline_state["executor_output"] = executor_output
            healing_results = executor_output.get("healing_results", {})
            recommendations = healing_results.get("recommendations", [])
            
            if recommendations:
                yield self._format_sse(self.emit("log", "healer", f"Found {len(recommendations)} file(s) with gaps"))
            
            yield self._format_sse(self.emit(
                "stage_complete",
                "healer",
                "Analysis complete",
                data=healing_results
            ))
        else:
            yield self._format_sse(self.emit("log", None, "Coverage threshold satisfied — agents idle"))
            yield self._format_sse(self.emit("stage_skip", "tester", "Not required"))
            yield self._format_sse(self.emit("stage_skip", "healer", "Not required"))
        
        await asyncio.sleep(0.3)
        
        # ─────────────────────────────────────────
        # 5️⃣ FINAL STATUS
        # ─────────────────────────────────────────
        passed_count = executor_output.get("passed_tests", 0) if executor_output else 0
        failed_count = len(executor_output.get("failed_tests", [])) if executor_output else 0
        total_count = executor_output.get("total_tests", 0) if executor_output else 0
        
        yield self._format_sse(self.emit(
            "summary",
            message="CI PASSED" if status == "pass" else "CI FAILED" if status == "fail" else "CI ERROR",
            data={
                "status": status,
                "passed": passed_count,
                "failed": failed_count,
                "total": total_count,
                "coverage": coverage
            }
        ))
        
        # ─────────────────────────────────────────
        # 7️⃣ SAVE RUN
        # ─────────────────────────────────────────
        runs_dir = project_root / "runs"
        runs_dir.mkdir(exist_ok=True)
        pipeline_state["end_time"] = datetime.now(timezone.utc).isoformat()
        
        with open(runs_dir / f"{self.run_id}.json", "w") as f:
            json.dump(pipeline_state, f, indent=2)
        
        # Save metrics
        metrics_dir = project_root / "metrics"
        metrics_dir.mkdir(exist_ok=True)
        
        metrics = {
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "coverage": coverage,
            "execution_time_ms": executor_output.get("execution_time_ms", 0) if executor_output else 0
        }
        
        with open(metrics_dir / "run_metrics.json", "a") as f:
            f.write(json.dumps(metrics) + "\n")
        
        yield self._format_sse(self.emit("pipeline_complete", data={"run_id": self.run_id}))
    
    def _format_sse(self, event: dict) -> str:
        """Format event as SSE data line."""
        return f"data: {json.dumps(event)}\n\n"

