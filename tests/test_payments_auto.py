

import sys
import os
import pytest
from unittest.mock import Mock, patch

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import *


@pytest.fixture
def clean_payment_repo(tmp_path):
    repo_path = tmp_path / "test_payments.json"
    repo = PaymentRepository(repo_path)
    # Ensure file is empty at the start of each test
    with open(repo_path, "w") as f:
        json.dump([], f)
    return repo


@pytest.fixture
def mock_fraud_checker():
    return Mock(spec=FraudChecker)


@pytest.fixture
def mock_gateway():
    return Mock(spec=PaymentGateway)


def test_payment_init():
    payment = Payment("p1", 100, "USD", "u1")
    assert payment.payment_id == "p1"
    assert payment.amount == 100
    assert payment.currency == "USD"
    assert payment.user_id == "u1"
    assert payment.status == "CREATED"
    assert isinstance(payment.created_at, datetime)


def test_payment_status_changes():
    payment = Payment("p1", 100, "USD", "u1")
    payment.mark_success()
    assert payment.status == "SUCCESS"
    payment.mark_failed()
    assert payment.status == "FAILED"


def test_wallet_credit_valid_amount():
    wallet = Wallet("u1")
    wallet.credit(500)
    assert wallet.balance == 500
    assert wallet.transactions == [("CREDIT", 500)]


def test_wallet_credit_invalid_amount_raises_error():
    wallet = Wallet("u1")
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(0)
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(-100)
    assert wallet.balance == 0
    assert not wallet.transactions


def test_wallet_debit_success():
    wallet = Wallet("u1")
    wallet.credit(500)
    result = wallet.debit(200)
    assert result is True
    assert wallet.balance == 300
    assert wallet.transactions == [("CREDIT", 500), ("DEBIT", 200)]


def test_wallet_debit_insufficient_funds():
    wallet = Wallet("u1")
    wallet.credit(100)
    result = wallet.debit(200)
    assert result is False
    assert wallet.balance == 100
    assert wallet.transactions == [("CREDIT", 100)]


def test_payment_repository_save_and_load_payment(clean_payment_repo):
    payment = Payment("p1", 100, "USD", "u1")
    clean_payment_repo.save(payment)
    payments = clean_payment_repo._load()
    assert len(payments) == 1
    assert payments[0]["payment_id"] == "p1"
    assert payments[0]["status"] == "CREATED"


def test_payment_repository_update_status(clean_payment_repo):
    payment = Payment("p1", 100, "USD", "u1")
    clean_payment_repo.save(payment)
    clean_payment_repo.update_status("p1", "SUCCESS")
    payments = clean_payment_repo._load()
    assert payments[0]["status"] == "SUCCESS"


def test_payment_repository_get_by_user_id(clean_payment_repo):
    payment1 = Payment("p1", 100, "USD", "u1")
    payment2 = Payment("p2", 200, "EUR", "u2")
    payment3 = Payment("p3", 300, "INR", "u1")
    clean_payment_repo.save(payment1)
    clean_payment_repo.save(payment2)
    clean_payment_repo.save(payment3)

    user1_payments = clean_payment_repo.get_by_user("u1")
    assert len(user1_payments) == 2
    assert {p["payment_id"] for p in user1_payments} == {"p1", "p3"}


def test_fraud_checker_is_fraudulent():
    # High amount
    payment_high_amount = Payment("p1", 100001, "USD", "u1")
    assert FraudChecker().is_fraud(payment_high_amount) is True
    # Invalid currency
    payment_invalid_currency = Payment("p2", 500, "XYZ", "u2")
    assert FraudChecker().is_fraud(payment_invalid_currency) is True


def test_fraud_checker_is_not_fraudulent():
    payment_valid = Payment("p1", 500, "USD", "u1")
    assert FraudChecker().is_fraud(payment_valid) is False
    payment_boundary_amount = Payment("p2", 100000, "EUR", "u2")
    assert FraudChecker().is_fraud(payment_boundary_amount) is False


def test_payment_gateway_charge_succeeds():
    gateway = PaymentGateway()
    # Mock random.randint to always return a value < 8 (e.g., 7)
    with patch("random.randint", return_value=7):
        assert gateway.charge(Mock()) is True


def test_payment_gateway_charge_fails():
    gateway = PaymentGateway()
    # Mock random.randint to always return a value >= 8 (e.g., 8)
    with patch("random.randint", return_value=8):
        assert gateway.charge(Mock()) is False


def test_payment_service_add_funds():
    service = PaymentService()
    balance = service.add_funds("u1", 100)
    assert balance == 100
    assert service.user_balance("u1") == 100
    balance = service.add_funds("u1", 50)
    assert balance == 150
    assert service.user_balance("u1") == 150


def test_payment_service_process_payment_fails_on_fraud(
    clean_payment_repo, mock_fraud_checker, mock_gateway
):
    user_id = "u_fraud"
    amount = 100
    currency = "USD"
    mock_fraud_checker.is_fraud.return_value = True
    service = PaymentService(
        repo=clean_payment_repo, gateway=mock_gateway, fraud=mock_fraud_checker
    )
    service.add_funds(user_id, 200)

    result = service.process_payment(user_id, amount, currency)

    assert result is False
    assert service.user_balance(user_id) == 200  # Wallet should not be debited
    payments = clean_payment_repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    mock_gateway.charge.assert_not_called()


def test_payment_service_process_payment_fails_on_insufficient_wallet(
    clean_payment_repo, mock_fraud_checker, mock_gateway
):
    user_id = "u_insufficient"
    amount = 100
    currency = "USD"
    mock_fraud_checker.is_fraud.return_value = False
    service = PaymentService(
        repo=clean_payment_repo, gateway=mock_gateway, fraud=mock_fraud_checker
    )
    service.add_funds(user_id, 50)  # Only 50 funds

    result = service.process_payment(user_id, amount, currency)

    assert result is False
    assert service.user_balance(user_id) == 50  # Wallet balance should remain unchanged
    payments = clean_payment_repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    mock_gateway.charge.assert_not_called()


def test_payment_service_process_payment_fails_on_gateway_decline_and_refunds_wallet(
    clean_payment_repo, mock_fraud_checker, mock_gateway
):
    user_id = "u_gateway_fail"
    amount = 100
    currency = "USD"
    mock_fraud_checker.is_fraud.return_value = False
    mock_gateway.charge.return_value = False  # Gateway declines

    service = PaymentService(
        repo=clean_payment_repo, gateway=mock_gateway, fraud=mock_fraud_checker
    )
    service.add_funds(user_id, 200)

    result = service.process_payment(user_id, amount, currency)

    assert result is False
    assert (
        service.user_balance(user_id) == 200
    )  # Wallet debited then credited back
    payments = clean_payment_repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    mock_gateway.charge.assert_called_once()


def test_payment_service_process_payment_succeeds(
    clean_payment_repo, mock_fraud_checker, mock_gateway
):
    user_id = "u_success"
    amount = 100
    currency = "USD"
    mock_fraud_checker.is_fraud.return_value = False
    mock_gateway.charge.return_value = True  # Gateway approves

    service = PaymentService(
        repo=clean_payment_repo, gateway=mock_gateway, fraud=mock_fraud_checker
    )
    service.add_funds(user_id, 200)

    result = service.process_payment(user_id, amount, currency)

    assert result is True
    assert service.user_balance(user_id) == 100  # Wallet debited
    payments = clean_payment_repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "SUCCESS"
    mock_gateway.charge.assert_called_once()


def test_payment_service_refund_updates_status_and_credits_wallet(
    clean_payment_repo, mock_fraud_checker, mock_gateway
):
    user_id = "u_refund"
    amount = 100
    currency = "USD"
    mock_fraud_checker.is_fraud.return_value = False
    mock_gateway.charge.return_value = True

    service = PaymentService(
        repo=clean_payment_repo, gateway=mock_gateway, fraud=mock_fraud_checker
    )
    service.add_funds(user_id, 200)
    service.process_payment(user_id, amount, currency)
    assert service.user_balance(user_id) == 100
    initial_payments = clean_payment_repo.get_by_user(user_id)
    payment_id = initial_payments[0]["payment_id"]

    service.refund(payment_id)

    assert service.user_balance(user_id) == 200  # Wallet credited back
    updated_payments = clean_payment_repo._load()
    assert updated_payments[0]["status"] == "REFUNDED"


def test_batch_payments_processes_multiple_payments(
    clean_payment_repo, mock_fraud_checker, mock_gateway
):
    user_id = "u_batch"
    mock_fraud_checker.is_fraud.return_value = False
    mock_gateway.charge.side_effect = [True, False, True]  # Success, Failure, Success

    service = PaymentService(
        repo=clean_payment_repo, gateway=mock_gateway, fraud=mock_fraud_checker
    )
    service.add_funds(user_id, 500)

    payments_to_process = [
        (100, "USD"),  # Should succeed
        (50, "EUR"),  # Gateway fails, wallet refunded
        (200, "INR"),  # Should succeed
        (-10, "USD"),  # Invalid amount, ValueError caught by batch
    ]

    results = batch_payments(service, user_id, payments_to_process)

    assert results == [True, False, True, False]
    # Initial: 500
    # 1. 100 USD (Success): 500 - 100 = 400
    # 2. 50 EUR (Gateway Fail): 400 - 50 + 50 = 400
    # 3. 200 INR (Success): 400 - 200 = 200
    # 4. -10 USD (Invalid): 200 (no change)
    assert service.user_balance(user_id) == 200
    all_payments = clean_payment_repo.get_by_user(user_id)
    assert len(all_payments) == 3  # The invalid one doesn't create a payment object
    assert [p["status"] for p in all_payments].count("SUCCESS") == 2
    assert [p["status"] for p in all_payments].count("FAILED") == 1


def test_export_report(tmp_path):
    report_path = tmp_path / "test_report.json"
    service = PaymentService()
    service.add_funds("userA", 100)
    service.add_funds("userB", 200)
    wallet_a = service.wallets["userA"]
    wallet_a.transactions.append(("DEBIT", 50)) # Simulate a debit
    wallet_a.balance -= 50

    export_report(service, report_path)

    assert os.path.exists(report_path)
    with open(report_path, "r") as f:
        report_data = json.load(f)

    expected_report = {
        "userA": {"balance": 50, "transactions": [["CREDIT", 100], ["DEBIT", 50]]},
        "userB": {"balance": 200, "transactions": [["CREDIT", 200]]},
    }
    assert report_data == expected_report