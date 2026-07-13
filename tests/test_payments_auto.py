import sys
import os
import pytest
import uuid
import json
from unittest.mock import patch, MagicMock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import *

@pytest.fixture
def wallet():
    return Wallet(user_id="user123")

def test_wallet_initial_balance(wallet):
    assert wallet.balance == 0

def test_wallet_credit_valid(wallet):
    wallet.credit(100)
    assert wallet.balance == 100

def test_wallet_credit_invalid(wallet):
    with pytest.raises(ValueError):
        wallet.credit(-50)

def test_wallet_debit_success(wallet):
    wallet.credit(100)
    assert wallet.debit(50) is True
    assert wallet.balance == 50

def test_wallet_debit_failure(wallet):
    wallet.credit(50)
    assert wallet.debit(100) is False
    assert wallet.balance == 50

@pytest.fixture
def payment_repo(tmp_path):
    return PaymentRepository(str(tmp_path / "payments.json"))

def test_payment_repository_initialization(payment_repo):
    assert os.path.exists(payment_repo.path)

def test_payment_repository_save(payment_repo):
    payment = Payment(payment_id=str(uuid.uuid4()), amount=100, currency="USD", user_id="user123")
    payment_repo.save(payment)
    payments = payment_repo._load()
    assert len(payments) == 1
    assert payments[0]["payment_id"] == payment.payment_id

def test_payment_repository_get_by_user(payment_repo):
    payment1 = Payment(payment_id=str(uuid.uuid4()), amount=100, currency="USD", user_id="user123")
    payment_repo.save(payment1)
    payment2 = Payment(payment_id=str(uuid.uuid4()), amount=200, currency="USD", user_id="user456")
    payment_repo.save(payment2)
    user_payments = payment_repo.get_by_user("user123")
    assert len(user_payments) == 1
    assert user_payments[0]["payment_id"] == payment1.payment_id

@pytest.fixture
def fraud_checker():
    return FraudChecker()

def test_fraud_checker_valid_transaction(fraud_checker):
    payment = Payment(payment_id=str(uuid.uuid4()), amount=50, currency="USD", user_id="user123")
    assert fraud_checker.is_fraud(payment) is False

def test_fraud_checker_high_amount(fraud_checker):
    payment = Payment(payment_id=str(uuid.uuid4()), amount=150000, currency="USD", user_id="user123")
    assert fraud_checker.is_fraud(payment) is True

def test_fraud_checker_invalid_currency(fraud_checker):
    payment = Payment(payment_id=str(uuid.uuid4()), amount=50, currency="INVALID", user_id="user123")
    assert fraud_checker.is_fraud(payment) is True

@pytest.fixture
def payment_service(payment_repo):
    return PaymentService(repo=payment_repo)

def test_payment_service_add_funds(payment_service):
    result = payment_service.add_funds("user123", 100)
    assert result == 100

def test_payment_service_process_payment_success(payment_service):
    payment_service.add_funds("user123", 100)
    result = payment_service.process_payment("user123", 50, "USD")
    assert result is True
    assert payment_service.user_balance("user123") == 50

def test_payment_service_process_payment_insufficient_funds(payment_service):
    payment_service.add_funds("user123", 50)
    result = payment_service.process_payment("user123", 100, "USD")
    assert result is False
    assert payment_service.user_balance("user123") == 50

def test_payment_service_process_payment_invalid_amount(payment_service):
    with pytest.raises(ValueError):
        payment_service.process_payment("user123", -50, "USD")

def test_payment_service_refund(payment_service):
    payment_service.add_funds("user123", 100)
    payment_service.process_payment("user123", 50, "USD")
    payments = payment_service.repo._load()
    payment_id = payments[0]["payment_id"]
    payment_service.refund(payment_id)
    assert payment_service.user_balance("user123") == 100
