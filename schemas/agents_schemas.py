from typing import List, Dict
from pydantic import BaseModel

class PlannerOutput(BaseModel):
    modules_to_test: List[str]
    test_types: List[str]
    risk_level: str
    reason: str

class TesterOutput(BaseModel):
    test_files_created: List[str]
    num_tests_generated: int

class ExecutorOutput(BaseModel):
    status: str
    failed_tests: List[str]
    summary_report: str
    execution_time_ms: int
