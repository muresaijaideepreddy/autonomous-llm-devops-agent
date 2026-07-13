import os
import sys
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Import from centralized config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OPENAI_MODEL

# -----------------------------
# LLM CLIENT
# -----------------------------

def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)

# -----------------------------
# SEVERITY CLASSIFIER (LLM)
# -----------------------------

def classify_severity_with_llm(issue: dict, changed_files: list) -> str:
    """
    Uses LLM to classify issue severity.
    Returns: low | medium | high
    """

    client = get_openai_client()

    title = issue.get("title", "")
    description = issue.get("description", "")

    prompt = f"""
Classify the issue severity as one of:
LOW, MEDIUM, HIGH

Rules:
- HIGH: crashes, data loss, payments, auth, security
- MEDIUM: incorrect behavior with workaround
- LOW: cosmetic, refactor, logs

Issue title: {title}
Issue description: {description}
Changed files: {changed_files}

Output ONLY one word.
"""

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}]
    )

    # Token usage tracking
    usage = response.usage
    print(f"\n📊 [Planner] OpenAI Token Usage:")
    print(f"   Model: {OPENAI_MODEL}")
    print(f"   Prompt tokens:     {usage.prompt_tokens}")
    print(f"   Completion tokens: {usage.completion_tokens}")
    print(f"   Total tokens:      {usage.total_tokens}")

    severity = response.choices[0].message.content.strip().lower()

    if severity not in {"low", "medium", "high"}:
        return "low"

    return severity

# -----------------------------
# PLANNER AGENT
# -----------------------------

def planner_agent(repo_event: dict) -> dict:
    changed_files = repo_event.get("changed_files", [])
    issue = repo_event.get("issue", {})

    modules_to_test = []
    test_types = ["unit"]
    risk_level = "low"

    # Module detection - Dynamic (scans any src/*.py file)
    for file in changed_files:
        if file.startswith("src/") and file.endswith(".py"):
            module_name = file[4:-3]  # Extract "payments" from "src/payments.py"
            if module_name not in modules_to_test:
                modules_to_test.append(module_name)

    # Severity decision
    if "severity" in issue:
        severity = issue["severity"].lower()
    else:
        severity = classify_severity_with_llm(issue, changed_files)

    # Risk mapping
    if severity == "high":
        risk_level = "high"
        test_types.append("edge")
    elif severity == "medium":
        risk_level = "medium"

    reason = f"{severity} severity issue affecting {modules_to_test}"

    return {
        "modules_to_test": modules_to_test,
        "test_types": test_types,
        "risk_level": risk_level,
        "reason": reason
    }

# -----------------------------
# LOCAL TEST
# -----------------------------

if __name__ == "__main__":
    repo_event = {
        "changed_files": ["src/payments.py"],
        "issue": {
            "title": "Negative amount crashes payment flow",
            "description": "Processing -10 causes runtime exception"
        }
    }

    print(planner_agent(repo_event))
