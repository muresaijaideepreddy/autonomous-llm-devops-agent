import sys
import os
import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import *

def test_process_payment_positive_amount_success():
    assert process_payment(100) is True

def test_process_payment_zero_amount_success():
    assert process_payment(0) is True

def test_process_payment_negative_amount_raises_error():
    with pytest.raises(ValueError) as excinfo:
        process_payment(-10)
    assert "Amount cannot be negative" in str(excinfo.value)