import os
from google import genai

# -----------------------------
# LLM CLIENT
# -----------------------------

def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)

# -----------------------------
# SEVERITY CLASSIFIER (LLM)
# -----------------------------

def classify_severity_with_llm(issue: dict, changed_files: list) -> str:
    """
    Uses LLM to classify issue severity.
    Returns: low | medium | high
    """

    client = get_gemini_client()

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

    response = client.models.generate_content(
        model="models/gemini-2.5-flash",
        contents=prompt
    )

    severity = response.text.strip().lower()

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

    # Module detection
    for file in changed_files:
        if "payments" in file:
            modules_to_test.append("payments")
        elif "auth" in file:
            modules_to_test.append("auth")

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
