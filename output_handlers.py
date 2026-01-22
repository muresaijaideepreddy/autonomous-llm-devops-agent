"""
Output Handlers for Pipeline Orchestrator
==========================================
Pluggable output handlers for different output modes (CLI, Web UI, etc.)
"""

from datetime import datetime, timezone
from abc import ABC, abstractmethod
import json


class OutputHandler(ABC):
    """Base class for pipeline output handlers."""
    
    @abstractmethod
    def emit(self, event_type: str, stage: str = None, message: str = None, data: dict = None):
        """Emit an event. Implementation varies by handler type."""
        pass
    
    @abstractmethod
    async def delay(self, seconds: float):
        """Add delay between steps (useful for UI animations)."""
        pass


class CLIOutputHandler(OutputHandler):
    """Output handler for command-line interface."""
    
    def emit(self, event_type: str, stage: str = None, message: str = None, data: dict = None):
        if event_type == "pipeline_start":
            print(f"\n▶ {message}")
            if data:
                print(f"  • Run ID: {data.get('run_id')}")
                print(f"  • Commit: {data.get('commit')}")
        
        elif event_type == "stage_start":
            print(f"\n▶ {stage.title() if stage else ''} Agent")
            if message:
                print(f"  • {message}")
        
        elif event_type == "stage_complete":
            if message:
                print(f"  ✔ {message}")
        
        elif event_type == "log":
            if message:
                print(f"  • {message}")
        
        elif event_type == "stage_skip":
            print(f"  ⊘ {stage.title() if stage else ''}: {message}")
        
        elif event_type == "summary":
            print(f"\n{'='*50}")
            print(f"  {message}")
            if data:
                print(f"  Passed: {data.get('passed', 0)} | Failed: {data.get('failed', 0)}")
                if data.get('coverage') is not None:
                    print(f"  Coverage: {data['coverage']:.2f}%")
            print(f"{'='*50}")
        
        elif event_type == "pipeline_complete":
            print(f"\n✓ Pipeline complete")
    
    async def delay(self, seconds: float):
        # No delay needed for CLI
        pass


class SSEOutputHandler(OutputHandler):
    """Output handler for Server-Sent Events (Web UI)."""
    
    def __init__(self):
        self.events = []
    
    def emit(self, event_type: str, stage: str = None, message: str = None, data: dict = None):
        import asyncio
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
    
    def format_sse(self, event: dict) -> str:
        """Format event as SSE data line."""
        return f"data: {json.dumps(event)}\n\n"
    
    async def delay(self, seconds: float):
        import asyncio
        await asyncio.sleep(seconds)
