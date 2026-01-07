import sys
import os
import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import *

def test_process_payment_positive_amount_returns_true():
    amount = 100
    assert process_payment(amount) is True

def test_process_payment_zero_amount_returns_true():
    amount = 0
    assert process_payment(amount) is True

def test_process_payment_negative_amount_raises_value_error():
    amount = -10
    with pytest.raises(ValueError, match="Amount cannot be negative"):
        process_payment(amount)