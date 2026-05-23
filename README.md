# 🤖 Autonomous LLM DevOps Agent

An AI-powered autonomous CI/testing pipeline that uses **Google Gemini** to intelligently analyze code changes, generate targeted unit tests, execute them with coverage tracking, diagnose failures, and recommend healing actions — all without human intervention.

---

## 🏗️ Architecture

The system operates as a **multi-agent pipeline**, where each agent has a specialized role and communicates through structured schemas. The orchestrator controls execution flow and routes data between agents.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PIPELINE ORCHESTRATOR                        │
│                                                                     │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌─────────────┐  │
│   │ 🗂️       │    │ 🧪       │    │ ⚡       │    │ 🔍          │  │
│   │ Planner  │───▶│ Tester   │───▶│ Executor │───▶│ Failure     │  │
│   │          │    │          │    │          │    │ Analysis    │  │
│   └──────────┘    └──────────┘    └──────────┘    └──────┬──────┘  │
│        │               ▲                                  │        │
│        │               │          ┌──────────┐            │        │
│        │               └──────────│ 🩹       │◀───────────┘        │
│        │                          │ Healer   │                     │
│        │                          └──────────┘                     │
│        │                                                           │
│   Repo Event ──▶ Severity Classification ──▶ Test Generation       │
│                  ──▶ Execution ──▶ Analysis ──▶ Healing Report     │
└─────────────────────────────────────────────────────────────────────┘
```

### Agent Roles

| Agent | Description |
|-------|-------------|
| **Planner** | Analyzes the repo event (changed files + issue), classifies severity using Gemini LLM, and determines which modules need testing |
| **Tester** | Uses Gemini to generate targeted pytest unit tests with coverage-aware prompting, syntax validation, and retry/fallback mechanisms |
| **Executor** | Runs `pytest --cov` via subprocess, parses test results, extracts coverage data from `coverage.json` |
| **Failure Analysis** | Classifies failures using heuristics first (fast path), then falls back to Gemini LLM reasoning for ambiguous cases |
| **Healer** | Analyzes coverage gaps, identifies uncovered lines/functions, detects potential dead code, and builds coverage context for the Tester |

---

## 📁 Project Structure

```
autonomous-llm-devops-agent/
├── orchestrator.py          # Unified pipeline controller (CLI + Web UI)
├── output_handlers.py       # Pluggable output handlers (CLI, SSE)
├── config.py                # Centralized configuration
├── requirements.txt         # Python dependencies
│
├── agents/                  # AI agent implementations
│   ├── planner.py           # Issue analysis & severity classification
│   ├── tester.py            # LLM-powered test generation
│   ├── executor.py          # Test execution & coverage parsing
│   ├── failure_analysis.py  # Failure root-cause classification
│   └── healer.py            # Coverage gap analysis & reporting
│
├── src/                     # Source code under test
│   └── payments.py          # Payment processing domain (Payment, Wallet, etc.)
│
├── tests/                   # Auto-generated test files
│   └── test_payments_auto.py
│
├── schemas/                 # Agent I/O contracts
│   ├── agents_schemas.py    # Pydantic models
│   └── agent_schemas.md     # Schema documentation
│
├── data/                    # Runtime data
│   └── payments.json        # Payment repository storage
│
├── runs/                    # Pipeline run history (JSON)
├── metrics/                 # Pipeline metrics (JSONL)
└── coverage.json            # Latest pytest coverage report
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **Google Gemini API key** — obtain one from [Google AI Studio](https://aistudio.google.com/apikey)

### Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/muresaijaideepreddy/autonomous-llm-devops-agent.git
   cd autonomous-llm-devops-agent
   ```

2. **Create a virtual environment**

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**

   Create a `.env` file in the project root:

   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```

---

## 💻 Usage

### Run the Pipeline (CLI)

Execute the full autonomous pipeline with the default repo event:

```bash
python orchestrator.py
```

This triggers the pipeline with a sample event simulating a high-severity issue in `src/payments.py`.

### Custom Repo Event

Modify the `repo_event` dict in `orchestrator.py` or import and call programmatically:

```python
from orchestrator import run_pipeline

result = run_pipeline({
    "changed_files": ["src/payments.py"],
    "commit_id": "abc123",
    "issue": {
        "id": 1,
        "title": "Negative payment amount causes crash",
        "description": "System crashes when payment amount is negative",
        "severity": "high"
    }
})
```

### Run Individual Agents

Each agent can be tested independently:

```bash
# Test the planner agent
python agents/planner.py

# Test failure analysis
python agents/failure_analysis.py
```

### Run Tests Manually

```bash
# Run tests with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Run tests with JSON coverage report
pytest tests/ --cov=src --cov-report=json
```

---

## ⚙️ Configuration

All pipeline settings are centralized in `config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `COVERAGE_THRESHOLD` | `98` | Minimum coverage % to pass CI |
| `TEST_DIR` | `"tests"` | Directory for generated test files |
| `ENABLE_COVERAGE_HEALING` | `True` | Enable healer agent analysis |
| `MAX_TESTS_BY_SEVERITY` | `low: 12, medium: 15, high: 20` | Max tests generated per severity level |
| `GEMINI_MODEL` | `models/gemini-2.5-flash` | Gemini model for LLM calls |
| `MAX_RETRIES` | `2` | Retry attempts for test generation |

---

## 🔄 Pipeline Flow

1. **Repo Event** → The pipeline receives a JSON event describing changed files and an associated issue.

2. **Planner Agent** → Scans changed files under `src/`, classifies severity (using LLM if not provided), determines risk level and test types.

3. **Existing Test Check** → Discovers any existing `test_*.py` files in the test directory.

4. **Executor (Initial)** → Runs existing tests with coverage. If coverage ≥ 98%, the pipeline passes immediately.

5. **Healing Loop** → If coverage is below threshold, the pipeline enters an autonomous healing loop (up to `MAX_HEALING_ITERATIONS` passes):

   > **Iteration 1:** Tester generates tests → Executor runs them → check coverage → if ≥ 98%, done!
   >
   > **Iteration 2+:** Healer feeds `coverage_context` (uncovered lines/functions) back to Tester → Tester generates *targeted* tests → Executor runs → check again

6. **Results** → Pipeline state is saved to `runs/`, metrics (including iteration count) appended to `metrics/run_metrics.json`.

---

## 🩹 Healing Loop (Closed-Loop Architecture)

The healing loop is what makes this pipeline truly **autonomous** rather than just automated. Instead of running once and reporting gaps, it closes the feedback loop:

```
┌─────────────────────────────────────────────────────────┐
│                    HEALING LOOP                          │
│                                                         │
│   ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│   │ Tester   │───▶│ Executor │───▶│ Coverage ≥ 98%?  │  │
│   │          │    │          │    │                  │  │
│   └──────────┘    └──────────┘    └────────┬─────────┘  │
│        ▲                              No   │   Yes      │
│        │                                   │    │       │
│        │          ┌──────────┐             │    │       │
│        └──────────│ Healer   │◀────────────┘    │       │
│    coverage_ctx   │          │                  │       │
│                   └──────────┘            ✅ PASS       │
│                                                         │
│   Exit conditions:                                      │
│   • Coverage threshold met                              │
│   • Max iterations reached (default: 3)                 │
│   • Healer reports no healing needed                    │
│   • No coverage context available                       │
└─────────────────────────────────────────────────────────┘
```

**How it works:**

| Iteration | What Happens |
|-----------|-------------|
| 1 | Tester generates tests blind (no coverage context) |
| 2 | Healer identifies gaps → Tester targets uncovered lines/functions specifically |
| 3 | If still below threshold, Healer refines context → Tester makes a final targeted pass |

**Key data flow:** `healer_output["coverage_context"]` → `tester_plan["coverage_context"]`

This context includes per-module uncovered lines and function names, so the LLM prompt in iteration 2+ says things like: *"These FUNCTIONS have low coverage: `process_payment`, `refund`. These lines are NOT covered: [135, 158, 160]."*

---

## 📊 Output Modes

The orchestrator supports pluggable output handlers:

| Mode | Handler | Description |
|------|---------|-------------|
| **CLI** | `CLIOutputHandler` | Formatted terminal output with status icons |
| **SSE** | `SSEOutputHandler` | Server-Sent Events for real-time web UI streaming |

Custom handlers can be created by extending the `OutputHandler` abstract base class.

---

## 🧪 Sample Domain: Payments

The included `src/payments.py` module provides a realistic test target:

- **`Payment`** — Domain model with status lifecycle (CREATED → SUCCESS/FAILED)
- **`Wallet`** — User wallet with credit/debit and transaction history
- **`PaymentRepository`** — JSON-file-based persistence layer
- **`FraudChecker`** — Rule-based fraud detection (amount limits, currency validation)
- **`PaymentGateway`** — Simulated payment gateway with configurable randomness
- **`PaymentService`** — Orchestrates payment processing, refunds, and wallet management
- **`batch_payments()`** — Batch payment processing with error handling
- **`export_report()`** — Generates JSON reports from wallet data

---

## 📜 License

This project is for educational and research purposes.
