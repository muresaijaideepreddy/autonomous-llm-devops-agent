

import sys
import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import json

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import *


@pytest.fixture
def payment_repo(tmp_path):
    repo_file = tmp_path / "payments.json"
    # Ensure the file is empty at the start of each test
    with open(repo_file, "w") as f:
        json.dump([], f)
    return PaymentRepository(str(repo_file))


def test_payment_initial_status_and_status_changes():
    payment = Payment("p1", 100, "USD", "u1")
    assert payment.payment_id == "p1"
    assert payment.amount == 100
    assert payment.currency == "USD"
    assert payment.user_id == "u1"
    assert payment.status == "CREATED"
    assert isinstance(payment.created_at, datetime)

    payment.mark_success()
    assert payment.status == "SUCCESS"

    payment.mark_failed()
    assert payment.status == "FAILED"


def test_wallet_credit_valid_amount():
    wallet = Wallet("u1")
    wallet.credit(100)
    assert wallet.balance == 100
    assert wallet.transactions == [("CREDIT", 100)]

    wallet.credit(50.5)
    assert wallet.balance == 150.5
    assert wallet.transactions == [("CREDIT", 100), ("CREDIT", 50.5)]


def test_wallet_debit_sufficient_and_insufficient_funds():
    wallet = Wallet("u1")
    wallet.credit(200)

    # Sufficient funds
    assert wallet.debit(100) is True
    assert wallet.balance == 100
    assert wallet.transactions == [("CREDIT", 200), ("DEBIT", 100)]

    # Insufficient funds
    assert wallet.debit(150) is False
    assert wallet.balance == 100  # Balance should not change
    assert len(wallet.transactions) == 2  # No new transaction


def test_wallet_credit_invalid_amount_raises_error():
    wallet = Wallet("u1")
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(0)
    assert wallet.balance == 0
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(-10)
    assert wallet.balance == 0


def test_payment_repo_save_and_load(payment_repo):
    payment = Payment("p_test_1", 200, "EUR", "u_test_1")
    payment_repo.save(payment)

    loaded_payments = payment_repo.get_by_user("u_test_1")
    assert len(loaded_payments) == 1
    assert loaded_payments[0]["payment_id"] == "p_test_1"
    assert loaded_payments[0]["amount"] == 200
    assert loaded_payments[0]["status"] == "CREATED"


def test_payment_repo_update_status(payment_repo):
    payment = Payment("p_test_2", 300, "USD", "u_test_2")
    payment_repo.save(payment)

    payment_repo.update_status("p_test_2", "SUCCESS")
    loaded_payments = payment_repo.get_by_user("u_test_2")
    assert loaded_payments[0]["status"] == "SUCCESS"

    payment_repo.update_status("non_existent_id", "REFUNDED") # Should not error
    loaded_payments = payment_repo.get_by_user("u_test_2")
    assert loaded_payments[0]["status"] == "SUCCESS"


def test_payment_repo_get_by_user(payment_repo):
    payment1 = Payment("p_test_3a", 100, "USD", "u_test_3")
    payment2 = Payment("p_test_3b", 200, "EUR", "u_test_3")
    payment3 = Payment("p_test_3c", 50, "INR", "u_test_other")
    payment_repo.save(payment1)
    payment_repo.save(payment2)
    payment_repo.save(payment3)

    user_payments = payment_repo.get_by_user("u_test_3")
    assert len(user_payments) == 2
    assert {p["payment_id"] for p in user_payments} == {"p_test_3a", "p_test_3b"}

    other_user_payments = payment_repo.get_by_user("u_test_other")
    assert len(other_user_payments) == 1
    assert other_user_payments[0]["payment_id"] == "p_test_3c"

    no_payments = payment_repo.get_by_user("non_existent_user")
    assert len(no_payments) == 0


def test_fraud_checker_non_fraudulent_payment():
    checker = FraudChecker()
    payment = Payment("p1", 500, "USD", "u1")
    assert checker.is_fraud(payment) is False
    payment = Payment("p2", 99999, "INR", "u1")
    assert checker.is_fraud(payment) is False


def test_fraud_checker_fraudulent_amount_and_currency():
    checker = FraudChecker()
    payment = Payment("p1", 100001, "USD", "u1") # Over limit
    assert checker.is_fraud(payment) is True
    payment = Payment("p2", 100, "JPY", "u1") # Invalid currency
    assert checker.is_fraud(payment) is True
    payment = Payment("p3", 100001, "JPY", "u1") # Both
    assert checker.is_fraud(payment) is True


def test_payment_gateway_charge_success_and_failure():
    gateway = PaymentGateway()
    payment = Payment("p1", 100, "USD", "u1")

    # Mock rand to always return a value < 8 (success)
    mock_rand_success = MagicMock(return_value=7)
    assert gateway.charge(payment, rand=mock_rand_success) is True

    # Mock rand to always return a value >= 8 (failure)
    mock_rand_failure = MagicMock(return_value=8)
    assert gateway.charge(payment, rand=mock_rand_failure) is False


def test_payment_service_add_funds():
    service = PaymentService(repo=MagicMock(), gateway=MagicMock(), fraud=MagicMock())
    balance = service.add_funds("user123", 100)
    assert balance == 100
    assert service.wallets["user123"].balance == 100

    balance = service.add_funds("user123", 50)
    assert balance == 150
    assert service.wallets["user123"].balance == 150


def test_payment_service_process_payment_success():
    mock_repo = MagicMock()
    mock_fraud = MagicMock(return_value=False)
    mock_gateway = MagicMock(return_value=True) # Gateway success

    service = PaymentService(repo=mock_repo, gateway=mock_gateway, fraud=mock_fraud)
    service.add_funds("user456", 200)

    result = service.process_payment("user456", 100, "USD")
    assert result is True
    assert service.wallets["user456"].balance == 100
    mock_fraud.is_fraud.assert_called_once()
    mock_gateway.charge.assert_called_once()
    mock_repo.save.assert_called_once()
    assert mock_repo.save.call_args[0][0].status == "SUCCESS"


def test_payment_service_process_payment_fraud_detected():
    mock_repo = MagicMock()
    mock_fraud = MagicMock(return_value=True) # Fraud detected
    mock_gateway = MagicMock()

    service = PaymentService(repo=mock_repo, gateway=mock_gateway, fraud=mock_fraud)
    service.add_funds("user789", 200)

    result = service.process_payment("user789", 150000, "USD") # Fraudulent amount
    assert result is False
    assert service.wallets["user789"].balance == 200 # Wallet not debited
    mock_fraud.is_fraud.assert_called_once()
    mock_gateway.charge.assert_not_called()
    mock_repo.save.assert_called_once()
    assert mock_repo.save.call_args[0][0].status == "FAILED"


def test_payment_service_process_payment_insufficient_balance():
    mock_repo = MagicMock()
    mock_fraud = MagicMock(return_value=False)
    mock_gateway = MagicMock()

    service = PaymentService(repo=mock_repo, gateway=mock_gateway, fraud=mock_fraud)
    service.add_funds("user101", 50)

    result = service.process_payment("user101", 100, "USD") # More than balance
    assert result is False
    assert service.wallets["user101"].balance == 50 # Wallet not debited
    mock_fraud.is_fraud.assert_called_once()
    mock_gateway.charge.assert_not_called()
    mock_repo.save.assert_called_once()
    assert mock_repo.save.call_args[0][0].status == "FAILED"


def test_payment_service_process_payment_gateway_failure():
    mock_repo = MagicMock()
    mock_fraud = MagicMock(return_value=False)
    mock_gateway = MagicMock(return_value=False) # Gateway failure

    service = PaymentService(repo=mock_repo, gateway=mock_gateway, fraud=mock_fraud)
    service.add_funds("user112", 200)

    result = service.process_payment("user112", 100, "USD")
    assert result is False
    assert service.wallets["user112"].balance == 200 # Wallet debited then credited back
    mock_fraud.is_fraud.assert_called_once()
    mock_gateway.charge.assert_called_once()
    mock_repo.save.assert_called_once()
    assert mock_repo.save.call_args[0][0].status == "FAILED"


def test_payment_service_process_payment_negative_amount_raises_error():
    service = PaymentService(repo=MagicMock(), gateway=MagicMock(), fraud=MagicMock())
    with pytest.raises(ValueError, match="Invalid amount"):
        service.process_payment("user123", -10, "USD")


def test_payment_service_refund_success(payment_repo):
    # Simulate a successful payment in the repo first
    user_id = "user_ref"
    amount = 75
    payment_id = str(uuid.uuid4())
    payment = Payment(payment_id, amount, "EUR", user_id)
    payment.mark_success()
    payment_repo.save(payment)

    service = PaymentService(repo=payment_repo, gateway=MagicMock(), fraud=MagicMock())
    service.add_funds(user_id, 100) # Initial wallet balance

    service.refund(payment_id)
    assert service.wallets[user_id].balance == (100 + amount)
    assert service.wallets[user_id].transactions[-1] == ("CREDIT", amount)

    # Verify status in repo is updated
    loaded_payments = payment_repo.get_by_user(user_id)
    assert loaded_payments[0]["status"] == "REFUNDED"


def test_payment_service_user_balance():
    service = PaymentService(repo=MagicMock(), gateway=MagicMock(), fraud=MagicMock())
    service.add_funds("user_bal", 100)
    service.add_funds("user_bal", 50)

    balance = service.user_balance("user_bal")
    assert balance == 150

    # Test for a user with no funds added yet
    balance_new_user = service.user_balance("new_user")
    assert balance_new_user == 0


def test_batch_payments(payment_repo):
    mock_fraud = MagicMock(side_effect=[False, True, False]) # 1st OK, 2nd fraud, 3rd OK
    mock_gateway = MagicMock(side_effect=[True, True]) # For 1st and 3rd successful charges

    service = PaymentService(repo=payment_repo, gateway=mock_gateway, fraud=mock_fraud)
    service.add_funds("batch_user", 200) # Enough for 1st and 3rd

    payments_to_process = [
        (50, "USD"),    # Should succeed
        (150000, "USD"), # Fraudulent amount, should fail
        (100, "EUR"),   # Should succeed
        (-10, "USD")    # Invalid amount, should fail
    ]

    results = batch_payments(service, "batch_user", payments_to_process)

    assert results == [True, False, True, False]
    assert service.wallets["batch_user"].balance == 50 # 200 - 50 - 100
    assert mock_fraud.is_fraud.call_count == 3 # Called for 3 valid payments
    assert mock_gateway.charge.call_count == 2 # Called for 1st and 3rd payments


def test_export_report_creation_and_content(tmp_path):
    report_path = tmp_path / "test_report.json"
    service = PaymentService(repo=MagicMock(), gateway=MagicMock(), fraud=MagicMock())

    service.add_funds("user_A", 100)
    service.add_funds("user_B", 200)
    service.wallets["user_A"].debit(30) # Simulate a transaction

    export_report(service, str(report_path))

    assert os.path.exists(report_path)
    with open(report_path, "r") as f:
        report_data = json.load(f)

    assert "user_A" in report_data
    assert report_data["user_A"]["balance"] == 70
    assert report_data["user_A"]["transactions"] == [["CREDIT", 100], ["DEBIT", 30]]

    assert "user_B" in report_data
    assert report_data["user_B"]["balance"] == 200
    assert report_data["user_B"]["transactions"] == [["CREDIT", 200]]