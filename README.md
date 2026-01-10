# Autonomous LLM DevOps Agent 🚀

## Overview
This project implements an **Autonomous LLM‑Driven Continuous Integration (CI) System** that automatically plans, generates, validates, and executes software tests based on code changes and issue context. It demonstrates how **Large Language Models (LLMs)** can be safely and reliably integrated into real‑world DevOps pipelines.

---

## Key Features
- 🤖 **Planner Agent** to analyze code changes and assess risk/severity  
- 🧪 **LLM‑Powered Tester Agent** to automatically generate pytest unit tests  
- ⚙️ **Executor Agent** to run tests and collect CI results  
- 🔁 **Self‑healing pipeline** with retries, validation, and fallback tests  
- 📊 **Severity‑based test strategy** (low / medium / high)  
- 🔐 **CI‑safe design** (bounded generation, syntax validation, import handling)

---

## Project Architecture
Planner Agent → Tester Agent → Executor Agent
↑ ↓
└────────── Feedback & Logs ────┘


---

## Folder Structure
AgenticAI/
│
├── agents/
│ ├── planner.py # Decides modules and risk level
│ ├── tester.py # Generates and validates tests using LLM
│ └── executor.py # Runs pytest and reports results
│
├── src/
│ ├── init.py
│ └── payments.py # Example source module
│
├── tests/ # Auto‑generated tests
├── metrics/ # CI metrics (ignored in git)
├── runs/ # Pipeline run artifacts (ignored in git)
│
├── orchestrator.py # Main pipeline controller
├── .gitignore
├── .env.example
└── README.md



---

## How It Works
1. **Planner Agent**
   - Analyzes changed files and issue details
   - Determines affected modules
   - Assigns severity (low / medium / high), optionally using an LLM

2. **Tester Agent**
   - Uses an LLM (Gemini) to generate pytest unit tests
   - Limits number of tests based on severity
   - Validates Python syntax and retries on failure
   - Automatically fixes import paths
   - Falls back to safe tests if generation fails

3. **Executor Agent**
   - Runs pytest automatically
   - Detects pass / fail / no‑tests states
   - Collects logs and execution time

4. **Orchestrator**
   - Connects all agents into an end‑to‑end autonomous CI pipeline

---

## Severity‑Based Test Strategy
| Severity | Test Behavior |
|--------|--------------|
| Low    | Basic happy‑path tests |
| Medium | Edge cases + invalid inputs |
| High  | Boundary tests + exception handling |

---
