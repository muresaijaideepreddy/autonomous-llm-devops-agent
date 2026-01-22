"""
Unified Pipeline Orchestrator
==============================
Single orchestrator that works for both CLI and Web UI.
Uses pluggable output handlers for different output modes.
"""

from pathlib import Path
from agents.planner import planner_agent
from agents.tester import tester_agent
from agents.executor import executor_agent
from agents.failure_analysis import failure_analysis_agent
from agents.healer import healing_agent
from datetime import datetime, timezone
import json
import os
import uuid
from typing import AsyncGenerator

# Project root directory (where this file lives)
PROJECT_ROOT = Path(__file__).parent.absolute()

# Import from centralized config
from config import COVERAGE_THRESHOLD, TEST_DIR, ENABLE_COVERAGE_HEALING

# Import output handlers
from output_handlers import OutputHandler, CLIOutputHandler, SSEOutputHandler


# ─────────────────────────────────────────────
# UNIFIED ORCHESTRATOR
# ─────────────────────────────────────────────

class PipelineOrchestrator:
    """
    Unified pipeline orchestrator.
    Works with any output handler (CLI, SSE, etc.)
    """
    
    def __init__(self, output_handler: OutputHandler = None):
        self.run_id = f"run_{uuid.uuid4().hex[:8]}"
        self.start_time = None
        self.output = output_handler or CLIOutputHandler()
    
    def run_pipeline_sync(self, repo_event: dict) -> dict:
        """Synchronous wrapper for CLI usage."""
        import asyncio
        return asyncio.run(self._run_pipeline_internal(repo_event))
    
    async def _run_pipeline_streaming(self, repo_event: dict) -> AsyncGenerator[str, None]:
        """Stream pipeline execution as SSE events."""
        sse_handler = self.output if isinstance(self.output, SSEOutputHandler) else SSEOutputHandler()
        self.output = sse_handler
        
        async for event in self._run_pipeline_generator(repo_event):
            yield sse_handler.format_sse(event)
    
    async def _run_pipeline_generator(self, repo_event: dict) -> AsyncGenerator[dict, None]:
        """Internal generator that yields raw events."""
        # Ensure we're running from project root
        os.chdir(PROJECT_ROOT)
        
        self.start_time = datetime.now(timezone.utc)
        
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
        yield self.output.emit(
            "pipeline_start",
            message="Autonomous CI Pipeline Started",
            data={"run_id": self.run_id, "commit": repo_event.get("commit_id", "unknown")}
        )
        await self.output.delay(0.3)
        
        # ─────────────────────────────────────────
        # 1️⃣ PLANNER
        # ─────────────────────────────────────────
        yield self.output.emit("stage_start", "planner", "Analyzing repository event")
        await self.output.delay(0.2)
        
        yield self.output.emit("log", "planner", f"Processing changed files: {repo_event.get('changed_files', [])}")
        
        planner_output = planner_agent(repo_event)
        pipeline_state["planner_output"] = planner_output
        
        yield self.output.emit(
            "stage_complete", "planner",
            f"Identified modules: {planner_output.get('modules_to_test', [])}",
            data=planner_output
        )
        await self.output.delay(0.3)
        
        # ─────────────────────────────────────────
        # 2️⃣ COLLECT EXISTING TESTS
        # ─────────────────────────────────────────
        os.makedirs(TEST_DIR, exist_ok=True)
        test_files = [
            os.path.join(TEST_DIR, f)
            for f in os.listdir(TEST_DIR)
            if f.startswith("test_") and f.endswith(".py")
        ]
        
        yield self.output.emit("log", "planner", f"Existing tests found: {len(test_files)}")
        await self.output.delay(0.2)
        
        # ─────────────────────────────────────────
        # 3️⃣ EXECUTOR (EXISTING TESTS)
        # ─────────────────────────────────────────
        executor_output = None
        coverage = None
        status = None
        
        if test_files:
            yield self.output.emit("stage_start", "executor", "Running existing tests")
            await self.output.delay(0.2)
            
            yield self.output.emit("log", "executor", f"Found {len(test_files)} test file(s)")
            yield self.output.emit("log", "executor", "Collecting tests...")
            
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
            
            yield self.output.emit("log", "executor", f"Tests executed: {total}")
            yield self.output.emit("log", "executor", f"Passed: {passed} | Failed: {failed}")
            
            if coverage is not None:
                yield self.output.emit("log", "executor", f"Coverage: {coverage:.2f}%")
                if coverage >= COVERAGE_THRESHOLD:
                    yield self.output.emit("log", "executor", f"✓ Coverage meets threshold ({COVERAGE_THRESHOLD}%)")
                else:
                    yield self.output.emit("log", "executor", f"✗ Coverage below threshold ({COVERAGE_THRESHOLD}%)")
            
            yield self.output.emit(
                "stage_complete", "executor",
                executor_output.get("summary_report", "Tests completed"),
                data={"status": status, "coverage": coverage, "passed": passed, "total": total}
            )
            await self.output.delay(0.3)
        else:
            yield self.output.emit("log", "executor", "No existing tests detected")
            yield self.output.emit("log", "executor", "Will generate new tests...")
        
        # ─────────────────────────────────────────
        # 4️⃣ DECISION: SHOULD AGENTS RUN?
        # ─────────────────────────────────────────
        if coverage is None or coverage < COVERAGE_THRESHOLD:
            yield self.output.emit("log", None, f"Coverage below threshold ({COVERAGE_THRESHOLD}%) — activating agents")
            await self.output.delay(0.2)
            
            # 4a️⃣ TESTER
            yield self.output.emit("stage_start", "tester", "Generating new tests")
            await self.output.delay(0.2)
            
            tester_plan = {**planner_output}
            tester_output = tester_agent(tester_plan)
            pipeline_state["tester_output"] = tester_output
            
            num_tests = tester_output.get("num_tests_generated", 0)
            yield self.output.emit(
                "stage_complete", "tester",
                f"Generated {num_tests} test(s)",
                data=tester_output
            )
            await self.output.delay(0.3)
            
            # 4b️⃣ EXECUTOR (NEW TESTS)
            yield self.output.emit("stage_start", "executor", "Running generated tests")
            await self.output.delay(0.2)
            
            executor_output = executor_agent({
                "execution_strategy": "pytest",
                "test_files": tester_output.get("test_files_created", [])
            })
            
            pipeline_state["executor_output"] = executor_output
            status = executor_output.get("status")
            coverage = executor_output.get("coverage_percent")
            
            yield self.output.emit(
                "stage_complete", "executor",
                executor_output.get("summary_report", "Tests completed"),
                data={
                    "status": status,
                    "coverage": coverage,
                    "passed": executor_output.get("passed_tests", 0),
                    "total": executor_output.get("total_tests", 0)
                }
            )
            await self.output.delay(0.3)
            
            # 4c️⃣ COVERAGE REPORT
            if coverage is not None:
                uncovered = executor_output.get("uncovered_files", {})
                yield self.output.emit(
                    "coverage_report", "executor",
                    f"Coverage: {coverage:.2f}%",
                    data={
                        "coverage_percent": coverage,
                        "threshold": COVERAGE_THRESHOLD,
                        "meets_threshold": coverage >= COVERAGE_THRESHOLD,
                        "uncovered_files": uncovered
                    }
                )
                await self.output.delay(0.2)
            
            # 4d️⃣ FAILURE ANALYSIS
            failure_analysis = None
            if status in ("fail", "error"):
                yield self.output.emit("stage_start", "failure_analysis", "Analyzing failures")
                failure_analysis = failure_analysis_agent(executor_output)
                pipeline_state["failure_analysis"] = failure_analysis
                
                yield self.output.emit(
                    "stage_complete", "failure_analysis",
                    f"Failure type: {failure_analysis.get('failure_type')}",
                    data=failure_analysis
                )
                await self.output.delay(0.2)
            
            # 4e️⃣ HEALER
            yield self.output.emit("stage_start", "healer", "Analyzing coverage")
            await self.output.delay(0.2)
            yield self.output.emit("log", "healer", "Checking for coverage gaps...")
            
            healer_output = healing_agent(
                planner_output=planner_output,
                executor_output=executor_output,
                failure_analysis=failure_analysis
            )
            pipeline_state["healer_output"] = healer_output
            
            recommendations = healer_output.get("modules_needing_tests", [])
            if recommendations:
                yield self.output.emit("log", "healer", f"Found {len(recommendations)} module(s) with gaps")
            
            yield self.output.emit("stage_complete", "healer", "Analysis complete", data=healer_output)
        else:
            yield self.output.emit("log", None, "Coverage threshold satisfied — agents idle")
            yield self.output.emit("stage_skip", "tester", "Not required")
            yield self.output.emit("stage_skip", "healer", "Not required")
        
        await self.output.delay(0.3)
        
        # ─────────────────────────────────────────
        # 5️⃣ FINAL STATUS
        # ─────────────────────────────────────────
        passed_count = executor_output.get("passed_tests", 0) if executor_output else 0
        failed_count = len(executor_output.get("failed_tests", [])) if executor_output else 0
        total_count = executor_output.get("total_tests", 0) if executor_output else 0
        
        if coverage is not None and coverage >= COVERAGE_THRESHOLD:
            final_status = "pass"
            status_message = "CI PASSED"
        elif coverage is not None:
            final_status = "fail"
            status_message = "CI FAILED"
        else:
            final_status = "error"
            status_message = "CI ERROR"
        
        yield self.output.emit(
            "summary",
            message=status_message,
            data={
                "status": final_status,
                "passed": passed_count,
                "failed": failed_count,
                "total": total_count,
                "coverage": coverage,
                "coverage_threshold": COVERAGE_THRESHOLD
            }
        )
        
        # ─────────────────────────────────────────
        # 6️⃣ SAVE RUN
        # ─────────────────────────────────────────
        os.makedirs("runs", exist_ok=True)
        pipeline_state["end_time"] = datetime.now(timezone.utc).isoformat()
        
        with open(f"runs/{self.run_id}.json", "w") as f:
            json.dump(pipeline_state, f, indent=2)
        
        # Save metrics
        os.makedirs("metrics", exist_ok=True)
        metrics = {
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": final_status,
            "coverage": coverage,
            "passed_tests": passed_count,
            "failed_tests": failed_count,
            "total_tests": total_count,
            "execution_time_ms": executor_output.get("execution_time_ms", 0) if executor_output else 0
        }
        
        with open("metrics/run_metrics.json", "a") as f:
            f.write(json.dumps(metrics) + "\n")
        
        yield self.output.emit("pipeline_complete", data={"run_id": self.run_id})
    
    async def _run_pipeline_internal(self, repo_event: dict) -> dict:
        """Run pipeline and return final state (for CLI mode)."""
        pipeline_state = None
        async for event in self._run_pipeline_generator(repo_event):
            if event and event.get("type") == "pipeline_complete":
                # Load and return the saved state
                with open(f"runs/{self.run_id}.json") as f:
                    pipeline_state = json.load(f)
        return pipeline_state


# ─────────────────────────────────────────────
# CONVENIENCE FUNCTIONS
# ─────────────────────────────────────────────

def run_pipeline(repo_event: dict) -> dict:
    """Run pipeline synchronously (CLI mode)."""
    orchestrator = PipelineOrchestrator(CLIOutputHandler())
    return orchestrator.run_pipeline_sync(repo_event)


# For backward compatibility - StreamingOrchestrator class
class StreamingOrchestrator(PipelineOrchestrator):
    """Backward-compatible streaming orchestrator for UI."""
    
    def __init__(self):
        super().__init__(SSEOutputHandler())
    
    async def run_pipeline_streaming(self, repo_event: dict) -> AsyncGenerator[str, None]:
        """Stream pipeline execution events via SSE."""
        async for event in self._run_pipeline_streaming(repo_event):
            yield event


# ─────────────────────────────────────────────
# MANUAL RUN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    repo_event = {
        "changed_files": ["src/payments.py"],
        "commit_id": "abc123",
        "issue": {
            "id": 1,
            "title": "Negative payment amount causes crash",
            "description": "System crashes when payment amount is negative",
            "severity": "high"
        }
    }

    run_pipeline(repo_event)
