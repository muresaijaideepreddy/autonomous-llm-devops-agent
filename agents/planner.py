def planner_agent(repo_event: dict) -> dict:
    changed_files = repo_event.get("changed_files", [])
    issue = repo_event.get("issue", {})

    modules_to_test = []
    test_types = ["unit"]
    risk_level = "low"

    # Simple module detection
    for file in changed_files:
        if "payments" in file:
            modules_to_test.append("payments")
        elif "auth" in file:
            modules_to_test.append("auth")

    # Risk logic
    severity = issue.get("severity", "low")
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


if __name__ == "__main__":
    repo_event = {
        "changed_files": ["src/payments.py"],
        "issue": {
            "title": "Negative amount crash",
            "severity": "high"
        }
    }

    print(planner_agent(repo_event))
