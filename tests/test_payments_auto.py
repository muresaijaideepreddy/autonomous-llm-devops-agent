import sys
import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
import json
import uuid

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import *

@pytest.fixture
def sample_payment():
    return Payment("pay123", 100, "USD", "user1")

@pytest.fixture
def sample_wallet():
    return Wallet("user1")

@pytest.fixture
def payment_repo_path(tmp_path):
    repo_path = tmp_path / "payments.json"
    return repo_path

@pytest.fixture
def payment_repository(payment_repo_path):
    # Ensure a fresh repo for each test
    if os.path.exists(payment_repo_path):
        os.remove(repo_path)
    return PaymentRepository(str(repo_path))

@pytest.fixture
def mock_payment_service():
    service = PaymentService()
    service.repo = MagicMock(spec=PaymentRepository)
    service.gateway = MagicMock(spec=PaymentGateway)
    service.fraud = MagicMock(spec=FraudChecker)
    service.wallets = {}
    return service

def test_payment_init(sample_payment):
    assert sample_payment.payment_id == "pay123"
    assert sample_payment.amount == 100
    assert sample_payment.currency == "USD"
    assert sample_payment.user_id == "user1"
    assert sample_payment.status == "CREATED"
    assert isinstance(sample_payment.created_at, datetime)

def test_payment_mark_success(sample_payment):
    sample_payment.mark_success()
    assert sample_payment.status == "SUCCESS"

def test_payment_mark_failed(sample_payment):
    sample_payment.mark_failed()
    assert sample_payment.status == "FAILED"

def test_wallet_init(sample_wallet):
    assert sample_wallet.user_id == "user1"
    assert sample_wallet.balance == 0
    assert sample_wallet.transactions == []

def test_wallet_credit(sample_wallet):
    sample_wallet.credit(50)
    assert sample_wallet.balance == 50
    assert sample_wallet.transactions == [("CREDIT", 50)]

def test_wallet_debit_success(sample_wallet):
    sample_wallet.credit(100)
    result = sample_wallet.debit(30)
    assert result is True
    assert sample_wallet.balance == 70
    assert sample_wallet.transactions == [("CREDIT", 100), ("DEBIT", 30)]

def test_wallet_debit_insufficient_funds(sample_wallet):
    sample_wallet.credit(20)
    result = sample_wallet.debit(50)
    assert result is False
    assert sample_wallet.balance == 20
    assert sample_wallet.transactions == [("CREDIT", 20)]

def test_payment_repo_init(tmp_path):
    repo_path = tmp_path / "test_init.json"
    repo = PaymentRepository(str(repo_path))
    assert os.path.exists(repo_path)
    with open(repo_path, "r") as f:
        assert json.load(f) == []

def test_payment_repo_save_and_get_by_user(payment_repository):
    payment1 = Payment("pay1", 100, "USD", "userA")
    payment2 = Payment("pay2", 200, "EUR", "userB")
    payment3 = Payment("pay3", 150, "INR", "userA")

    payment_repository.save(payment1)
    payment_repository.save(payment2)
    payment_repository.save(payment3)

    user_a_payments = payment_repository.get_by_user("userA")
    assert len(user_a_payments) == 2
    assert user_a_payments[0]["payment_id"] == "pay1"
    assert user_a_payments[1]["payment_id"] == "pay3"

def test_payment_repo_update_status(payment_repository):
    payment = Payment("pay_update", 50, "USD", "userX")
    payment_repository.save(payment)
    payment_repository.update_status("pay_update", "SUCCESS")
    payments_data = payment_repository._load()
    assert payments_data[0]["status"] == "SUCCESS"

def test_fraud_checker_no_fraud():
    checker = FraudChecker()
    payment = Payment("p1", 500, "USD", "u1")
    assert checker.is_fraud(payment) is False

def test_fraud_checker_is_fraud():
    checker = FraudChecker()
    payment_high_amount = Payment("p2", 100001, "USD", "u1")
    assert checker.is_fraud(payment_high_amount) is True
    payment_invalid_currency = Payment("p3", 500, "GBP", "u1")
    assert checker.is_fraud(payment_invalid_currency) is True

def test_payment_service_process_payment_success(mock_payment_service):
    mock_payment_service.fraud.is_fraud.return_value = False
    mock_payment_service.gateway.charge.return_value = True
    mock_payment_service.add_funds("user1", 100)
    result = mock_payment_service.process_payment("user1", 50, "USD")
    assert result is True
    assert mock_payment_service.user_balance("user1") == 50
    mock_payment_service.repo.save.assert_called_once()
    saved_payment = mock_payment_service.repo.save.call_args[0][0]
    assert saved_payment.status == "SUCCESS"

def test_payment_service_process_payment_invalid_amount(mock_payment_service):
    with pytest.raises(ValueError, match="Invalid amount"):
        mock_payment_service.process_payment("user1", -10, "USD")
    mock_payment_service.repo.save.assert_not_called()

def test_payment_service_process_payment_fraud_detected(mock_payment_service):
    mock_payment_service.fraud.is_fraud.return_value = True
    result = mock_payment_service.process_payment("user1", 100, "USD")
    assert result is False
    mock_payment_service.repo.save.assert_called_once()
    saved_payment = mock_payment_service.repo.save.call_args[0][0]
    assert saved_payment.status == "FAILED"
    mock_payment_service.gateway.charge.assert_not_called()

def test_payment_service_process_payment_insufficient_funds(mock_payment_service):
    mock_payment_service.fraud.is_fraud.return_value = False
    mock_payment_service.add_funds("user1", 10)
    result = mock_payment_service.process_payment("user1", 50, "USD")
    assert result is False
    assert mock_payment_service.user_balance("user1") == 10
    mock_payment_service.repo.save.assert_called_once()
    saved_payment = mock_payment_service.repo.save.call_args[0][0]
    assert saved_payment.status == "FAILED"
    mock_payment_service.gateway.charge.assert_not_called()

def test_payment_service_process_payment_gateway_failure(mock_payment_service):
    mock_payment_service.fraud.is_fraud.return_value = False
    mock_payment_service.gateway.charge.return_value = False
    mock_payment_service.add_funds("user1", 100)
    result = mock_payment_service.process_payment("user1", 50, "USD")
    assert result is False
    assert mock_payment_service.user_balance("user1") == 100
    mock_payment_service.repo.save.assert_called_once()
    saved_payment = mock_payment_service.repo.save.call_args[0][0]
    assert saved_payment.status == "FAILED"

def test_payment_service_add_funds_and_user_balance(mock_payment_service):
    assert mock_payment_service.user_balance("user1") == 0
    balance_after_add = mock_payment_service.add_funds("user1", 150)
    assert balance_after_add == 150
    assert mock_payment_service.user_balance("user1") == 150

def test_payment_service_refund(mock_payment_service):
    payment_id = str(uuid.uuid4())
    user_id = "user_refund"
    amount = 75
    mock_payment_service.repo._load.return_value = [{
        "payment_id": payment_id,
        "amount": amount,
        "currency": "USD",
        "user_id": user_id,
        "status": "SUCCESS",
        "created_at": datetime.utcnow().isoformat()
    }]
    mock_payment_service.repo._write.return_value = None

    mock_payment_service.add_funds(user_id, 100)
    mock_payment_service.wallets[user_id].balance -= amount # Simulate debit
    assert mock_payment_service.user_balance(user_id) == 25

    mock_payment_service.refund(payment_id)
    assert mock_payment_service.user_balance(user_id) == 100
    mock_payment_service.repo._write.assert_called_once()
    updated_data = mock_payment_service.repo._write.call_args[0][0]
    assert updated_data[0]["status"] == "REFUNDED"

def test_batch_payments(mock_payment_service):
    mock_payment_service.fraud.is_fraud.side_effect = [False, True, False, False]
    mock_payment_service.gateway.charge.side_effect = [True, None, False, True] # None for when fraud prevents charge

    user_id = "user_batch"
    mock_payment_service.add_funds(user_id, 500)

    payments_to_process = [
        (50, "USD"),  # Success
        (200, "INR"), # Fraud
        (75, "EUR"),  # Gateway failure (debit & credit back)
        (100, "USD")  # Success
    ]

    results = batch_payments(mock_payment_service, user_id, payments_to_process)

    assert results == [True, False, False, True]
    assert mock_payment_service.user_balance(user_id) == 350 # 500 - 50 (P1) - 0 (P2) - 0 (P3 net) - 100 (P4) = 350