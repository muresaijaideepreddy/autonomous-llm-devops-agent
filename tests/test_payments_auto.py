

import sys
import os
import pytest
from unittest.mock import patch
from datetime import datetime, timezone
import json # Used for repository and export_report tests

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import *

# --- Helper Mocks for PaymentService tests ---
# These mock classes allow injecting controlled behavior into PaymentService
# without depending on actual file system or random outcomes.

class MockRepo:
    def __init__(self):
        self.payments = []

    def save(self, payment):
        p_data = {
            "payment_id": payment.payment_id,
            "amount": payment.amount,
            "currency": payment.currency,
            "user_id": payment.user_id,
            "status": payment.status,
            "created_at": payment.created_at.isoformat()
        }
        self.payments.append(p_data)

    def update_status(self, payment_id, status):
        for p in self.payments:
            if p["payment_id"] == payment_id:
                p["status"] = status
                break

    def get_by_user(self, user_id):
        return [p for p in self.payments if p["user_id"] == user_id]

    def _load(self):
        return self.payments

    def _write(self, data):
        self.payments = data

class MockGateway:
    def __init__(self, charge_result=True):
        self._charge_result = charge_result

    def charge(self, payment, rand=None):
        return self._charge_result

class MockFraud:
    def __init__(self, is_fraud_result=False):
        self._is_fraud_result = is_fraud_result

    def is_fraud(self, payment):
        return self._is_fraud_result

# --- Tests ---

def test_payment_init_and_status_changes():
    payment_id = "test_payment_1"
    amount = 100
    currency = "USD"
    user_id = "user_123"
    payment = Payment(payment_id, amount, currency, user_id)

    assert payment.payment_id == payment_id
    assert payment.amount == amount
    assert payment.currency == currency
    assert payment.user_id == user_id
    assert payment.status == "CREATED"
    assert isinstance(payment.created_at, datetime)
    assert payment.created_at.tzinfo == timezone.utc

    payment.mark_success()
    assert payment.status == "SUCCESS"

    payment.mark_failed()
    assert payment.status == "FAILED"

def test_wallet_credit_valid():
    wallet = Wallet("user_1")
    initial_balance = wallet.balance
    credit_amount = 50
    wallet.credit(credit_amount)

    assert wallet.balance == initial_balance + credit_amount
    assert ("CREDIT", credit_amount) in wallet.transactions

def test_wallet_credit_invalid_raises_error():
    wallet = Wallet("user_2")
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(0)
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(-10)
    assert wallet.balance == 0
    assert not wallet.transactions

def test_wallet_debit_sufficient():
    wallet = Wallet("user_3")
    wallet.credit(100)
    debit_amount = 75
    result = wallet.debit(debit_amount)

    assert result is True
    assert wallet.balance == 25
    assert ("DEBIT", debit_amount) in wallet.transactions

def test_wallet_debit_insufficient():
    wallet = Wallet("user_4")
    wallet.credit(50)
    debit_amount = 75
    result = wallet.debit(debit_amount)

    assert result is False
    assert wallet.balance == 50
    assert ("DEBIT", debit_amount) not in wallet.transactions

def test_fraud_checker_is_not_fraud():
    fraud_checker = FraudChecker()
    payment = Payment("p1", 500, "USD", "u1")
    assert fraud_checker.is_fraud(payment) is False

def test_fraud_checker_is_fraud_amount():
    fraud_checker = FraudChecker()
    payment = Payment("p2", 100001, "USD", "u1")
    assert fraud_checker.is_fraud(payment) is True

def test_fraud_checker_is_fraud_currency():
    fraud_checker = FraudChecker()
    payment = Payment("p3", 500, "GBP", "u1")
    assert fraud_checker.is_fraud(payment) is True

def test_payment_gateway_charge_controlled_outcomes():
    gateway = PaymentGateway()

    with patch('random.randint', return_value=1) as mock_rand_success:
        payment = Payment("p_success", 100, "USD", "u1")
        assert gateway.charge(payment) is True
        mock_rand_success.assert_called_once_with(1, 10)

    with patch('random.randint', return_value=8) as mock_rand_fail:
        payment = Payment("p_fail", 100, "USD", "u1")
        assert gateway.charge(payment) is False
        mock_rand_fail.assert_called_once_with(1, 10)

def test_payment_repository_save_and_load(tmp_path):
    repo_path = tmp_path / "payments.json"
    repo = PaymentRepository(str(repo_path))

    payment = Payment("p_id_1", 100, "USD", "user_abc")
    repo.save(payment)

    loaded_data = repo._load()
    assert len(loaded_data) == 1
    assert loaded_data[0]["payment_id"] == payment.payment_id
    assert loaded_data[0]["status"] == "CREATED"

    payment2 = Payment("p_id_2", 200, "EUR", "user_abc")
    repo.save(payment2)
    loaded_data_2 = repo._load()
    assert len(loaded_data_2) == 2
    assert loaded_data_2[1]["payment_id"] == payment2.payment_id

def test_payment_repository_update_status_and_get_by_user(tmp_path):
    repo_path = tmp_path / "payments.json"
    repo = PaymentRepository(str(repo_path))

    payment1 = Payment("p_id_A", 100, "USD", "user_X")
    payment2 = Payment("p_id_B", 200, "EUR", "user_Y")
    payment3 = Payment("p_id_C", 50, "INR", "user_X")

    repo.save(payment1)
    repo.save(payment2)
    repo.save(payment3)

    repo.update_status("p_id_A", "SUCCESS")
    loaded_data = repo._load()
    assert next(p for p in loaded_data if p["payment_id"] == "p_id_A")["status"] == "SUCCESS"
    assert next(p for p in loaded_data if p["payment_id"] == "p_id_B")["status"] == "CREATED"

    user_x_payments = repo.get_by_user("user_X")
    assert len(user_x_payments) == 2
    assert {p["payment_id"] for p in user_x_payments} == {"p_id_A", "p_id_C"}
    assert all(p["user_id"] == "user_X" for p in user_x_payments)

    user_y_payments = repo.get_by_user("user_Y")
    assert len(user_y_payments) == 1
    assert user_y_payments[0]["payment_id"] == "p_id_B"

def test_payment_service_add_funds_and_user_balance():
    service = PaymentService(repo=MockRepo(), gateway=MockGateway(), fraud=MockFraud())
    user_id = "user_add_funds"

    balance1 = service.add_funds(user_id, 100)
    assert balance1 == 100
    assert service.user_balance(user_id) == 100

    balance2 = service.add_funds(user_id, 50)
    assert balance2 == 150
    assert service.user_balance(user_id) == 150

    user_id_2 = "user_add_funds_2"
    service.add_funds(user_id_2, 200)
    assert service.user_balance(user_id_2) == 200
    assert service.user_balance(user_id) == 150

def test_payment_service_process_payment_invalid_amount_raises_error():
    service = PaymentService(repo=MockRepo(), gateway=MockGateway(), fraud=MockFraud())
    user_id = "user_invalid_amt"
    service.add_funds(user_id, 100)

    with pytest.raises(ValueError, match="Invalid amount"):
        service.process_payment(user_id, -10, "USD")
    with pytest.raises(ValueError, match="Invalid amount"):
        service.process_payment(user_id, 0, "USD")

    assert service.user_balance(user_id) == 100

def test_payment_service_process_payment_fraudulent():
    mock_repo = MockRepo()
    mock_fraud = MockFraud(is_fraud_result=True)
    service = PaymentService(repo=mock_repo, gateway=MockGateway(), fraud=mock_fraud)
    user_id = "user_fraud"
    service.add_funds(user_id, 100)

    result = service.process_payment(user_id, 50, "USD")
    assert result is False
    assert service.user_balance(user_id) == 100
    assert len(mock_repo.payments) == 1
    assert mock_repo.payments[0]["status"] == "FAILED"
    assert mock_repo.payments[0]["user_id"] == user_id

def test_payment_service_process_payment_insufficient_wallet_balance():
    mock_repo = MockRepo()
    service = PaymentService(repo=mock_repo, gateway=MockGateway(), fraud=MockFraud())
    user_id = "user_insufficient"
    service.add_funds(user_id, 50)

    result = service.process_payment(user_id, 100, "USD")
    assert result is False
    assert service.user_balance(user_id) == 50
    assert len(mock_repo.payments) == 1
    assert mock_repo.payments[0]["status"] == "FAILED"
    assert mock_repo.payments[0]["user_id"] == user_id

def test_payment_service_process_payment_successful():
    mock_repo = MockRepo()
    mock_gateway = MockGateway(charge_result=True)
    service = PaymentService(repo=mock_repo, gateway=mock_gateway, fraud=MockFraud())
    user_id = "user_success"
    service.add_funds(user_id, 200)

    initial_balance = service.user_balance(user_id)
    payment_amount = 100
    result = service.process_payment(user_id, payment_amount, "USD")
    assert result is True
    assert service.user_balance(user_id) == initial_balance - payment_amount
    assert len(mock_repo.payments) == 1
    assert mock_repo.payments[0]["status"] == "SUCCESS"
    assert mock_repo.payments[0]["user_id"] == user_id
    assert mock_repo.payments[0]["amount"] == payment_amount

def test_payment_service_process_payment_gateway_failure_refunds():
    mock_repo = MockRepo()
    mock_gateway = MockGateway(charge_result=False)
    service = PaymentService(repo=mock_repo, gateway=mock_gateway, fraud=MockFraud())
    user_id = "user_gateway_fail"
    service.add_funds(user_id, 200)

    initial_balance = service.user_balance(user_id)
    payment_amount = 100
    result = service.process_payment(user_id, payment_amount, "USD")
    assert result is False
    assert service.user_balance(user_id) == initial_balance
    assert len(mock_repo.payments) == 1
    assert mock_repo.payments[0]["status"] == "FAILED"
    assert mock_repo.payments[0]["user_id"] == user_id
    assert mock_repo.payments[0]["amount"] == payment_amount

def test_payment_service_refund_existing_payment():
    mock_repo = MockRepo()
    mock_gateway = MockGateway(charge_result=True)
    service = PaymentService(repo=mock_repo, gateway=mock_gateway, fraud=MockFraud())
    user_id = "user_refund"
    service.add_funds(user_id, 200)

    payment_amount = 100
    service.process_payment(user_id, payment_amount, "USD")
    assert service.user_balance(user_id) == 100

    payment_id_to_refund = mock_repo.payments[0]["payment_id"]

    service.refund(payment_id_to_refund)
    assert service.user_balance(user_id) == 200
    assert mock_repo.payments[0]["status"] == "REFUNDED"
    assert service.wallets[user_id].transactions[-1] == ("CREDIT", payment_amount)

def test_batch_payments_mixed_results():
    mock_repo = MockRepo()
    mock_gateway = MockGateway(charge_result=True)
    mock_fraud = MockFraud()
    mock_fraud.is_fraud = lambda p: p.amount > 500 or p.currency == "GBP"

    service = PaymentService(repo=mock_repo, gateway=mock_gateway, fraud=mock_fraud)
    user_id = "batch_user"
    service.add_funds(user_id, 1000)

    payments_to_process = [
        (100, "USD"),
        (200, "EUR"),
        (700, "USD"),
        (-50, "USD"),
        (50, "GBP"),
        (150, "INR")
    ]

    results = batch_payments(service, user_id, payments_to_process)

    assert results == [True, True, False, False, False, True]
    assert service.user_balance(user_id) == 1000 - 100 - 200 - 150
    assert len(mock_repo.payments) == 5
    assert sum(1 for p in mock_repo.payments if p["status"] == "SUCCESS") == 3
    assert sum(1 for p in mock_repo.payments if p["status"] == "FAILED") == 2

def test_export_report_generates_correct_data(tmp_path):
    repo_path = tmp_path / "payments_export.json"
    report_path = tmp_path / "report.json"

    service = PaymentService(
        repo=PaymentRepository(str(repo_path)),
        gateway=MockGateway(charge_result=True),
        fraud=MockFraud(is_fraud_result=False)
    )

    user1 = "user_report_1"
    user2 = "user_report_2"

    service.add_funds(user1, 100)
    service.process_payment(user1, 20, "USD")
    service.process_payment(user1, 30, "EUR")

    service.add_funds(user2, 500)
    service.process_payment(user2, 100, "INR")

    export_report(service, str(report_path))

    with open(report_path, "r") as f:
        report_data = json.load(f)

    assert user1 in report_data
    assert user2 in report_data

    assert report_data[user1]["balance"] == 50
    assert len(report_data[user1]["transactions"]) == 3
    assert ["CREDIT", 100] in report_data[user1]["transactions"]
    assert ["DEBIT", 20] in report_data[user1]["transactions"]
    assert ["DEBIT", 30] in report_data[user1]["transactions"]

    assert report_data[user2]["balance"] == 400
    assert len(report_data[user2]["transactions"]) == 2
    assert ["CREDIT", 500] in report_data[user2]["transactions"]
    assert ["DEBIT", 100] in report_data[user2]["transactions"]

    assert os.path.exists(os.path.dirname(report_path))