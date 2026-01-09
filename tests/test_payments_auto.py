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
    with pytest.raises(ValueError, match="Amount cannot be negative"):
        process_payment(-50)


def test_process_payment_large_amount_success():
    assert process_payment(999999) is True