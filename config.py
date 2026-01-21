# Configuration for Autonomous Testing Framework
# ===============================================
# Centralized configuration file to avoid duplication.

# Coverage threshold for pass/fail determination
# If coverage >= COVERAGE_THRESHOLD, the run is considered "pass"
COVERAGE_THRESHOLD = 98

# Test directory
TEST_DIR = "tests"

# Enable coverage healing mode
ENABLE_COVERAGE_HEALING = True

# Maximum tests by severity level
MAX_TESTS_BY_SEVERITY = {
    "low": 12,
    "medium": 15,
    "high": 20
}

# LLM Configuration
GEMINI_MODEL = "models/gemini-2.5-flash"
MAX_RETRIES = 2
