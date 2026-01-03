This document defines the strict input and output schemas for all agents
used in the Autonomous LLM DevOps / Testing project.

These schemas act as a contract between agents and the orchestrator.

Rules:
- Agents must follow schemas exactly
- No free-form outputs
- Agents do NOT control execution flow
- Orchestrator controls the pipeline 

1. Repo Event Schema (Input to Planner Agent)

{
  "changed_files": ["src/payments.py"],
  "commit_id": "abc123",
  "issue": {
    "id": 1,
    "title": "Negative payment amount causes crash",
    "description": "System crashes when payment amount is negative",
    "severity": "high"
  }
} 

2. Planner Agent Output Schema

{
  "modules_to_test": ["payments"],
  "test_types": ["unit", "edge"],
  "risk_level": "high",
  "reason": "High severity issue in payments module"
} 

3. Tester Agent Input Schema

{
  "modules_to_test": ["payments"],
  "test_types": ["unit", "edge"],
  "issue": {
    "title": "Negative payment amount causes crash",
    "description": "System crashes when payment amount is negative"
  },
  "source_code": {
    "payments": "def process_payment(amount): ..."
  }
} 

4. Tester Agent Output Schema

{
  "test_files_created": [
    "tests/test_payments_auto.py"
  ],
  "num_tests_generated": 3
} 

5. Executor Agent Input Schema

{
  "test_files": [
    "tests/test_payments_auto.py"
  ],
  "command": "pytest"
} 

6. Executor Agent Output Schema

{
  "status": "fail",
  "failed_tests": [
    "test_negative_payment_amount"
  ],
  "summary": "process_payment does not handle negative amounts",
  "suggested_fix": "Add validation to raise ValueError for negative amounts"
}
 

7. Pipeline State Schema (Optional)

{
  "run_id": "run_001",
  "planner_output": {},
  "tester_output": {},
  "executor_output": {},
  "start_time": "2026-01-03T22:00:00",
  "end_time": "2026-01-03T22:01:10"
}
