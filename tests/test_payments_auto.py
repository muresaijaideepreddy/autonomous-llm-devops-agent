import sys
import os
import pytest
import uuid
import json
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import *


@pytest.fixture
def tmp_payment_repo_path(tmp_path):
    """Provides a temporary file path for the PaymentRepository."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir / "payments.json"


@pytest.fixture
def payment_repo(tmp_payment_repo_path):
    """Initializes a PaymentRepository with a temporary path."""
    return PaymentRepository(path=tmp_payment_repo_path)


@pytest.fixture
def mock_uuid_fixed(monkeypatch):
    """Mocks uuid.uuid4 to return a predictable UUID."""
    fixed_uuid = "12345678-1234-5678-1234-567812345678"
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(fixed_uuid))
    return fixed_uuid


@pytest.fixture
def mock_gateway_charge_success(monkeypatch):
    """Mocks PaymentGateway.charge to always return True."""
    monkeypatch.setattr(PaymentGateway, "charge", lambda self, payment: True)


@pytest.fixture
def mock_gateway_charge_fail(monkeypatch):
    """Mocks PaymentGateway.charge to always return False."""
    monkeypatch.setattr(PaymentGateway, "charge", lambda self, payment: False)


@pytest.fixture
def mock_fraud_checker_safe(monkeypatch):
    """Mocks FraudChecker.is_fraud to always return False."""
    monkeypatch.setattr(FraudChecker, "is_fraud", lambda self, payment: False)


@pytest.fixture
def mock_fraud_checker_fraud(monkeypatch):
    """Mocks FraudChecker.is_fraud to always return True."""
    monkeypatch.setattr(FraudChecker, "is_fraud", lambda self, payment: True)


@pytest.fixture
def payment_service_instance(payment_repo):
    """Provides a PaymentService instance with a temporary repository."""
    return PaymentService(repo=payment_repo)


def test_payment_init_and_status_changes():
    """Tests Payment initialization and status change methods."""
    payment_id = str(uuid.uuid4())
    payment = Payment(payment_id, 100, "USD", "user123")

    assert payment.payment_id == payment_id
    assert payment.amount == 100
    assert payment.currency == "USD"
    assert payment.user_id == "user123"
    assert payment.status == "CREATED"
    assert isinstance(payment.created_at, datetime)

    payment.mark_success()
    assert payment.status == "SUCCESS"

    payment.mark_failed()
    assert payment.status == "FAILED"


def test_wallet_credit_valid_and_invalid():
    """Tests Wallet credit for valid and invalid amounts."""
    wallet = Wallet("user1")
    assert wallet.balance == 0
    assert wallet.transactions == []

    wallet.credit(100)
    assert wallet.balance == 100
    assert wallet.transactions == [("CREDIT", 100)]

    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(0)
    assert wallet.balance == 100  # Balance should not change
    assert wallet.transactions == [("CREDIT", 100)] # Transactions should not change

    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(-50)
    assert wallet.balance == 100
    assert wallet.transactions == [("CREDIT", 100)]


def test_wallet_debit_success_and_fail():
    """Tests Wallet debit for sufficient and insufficient funds."""
    wallet = Wallet("user1")
    wallet.credit(200)

    # Sufficient funds
    result = wallet.debit(100)
    assert result is True
    assert wallet.balance == 100
    assert wallet.transactions == [("CREDIT", 200), ("DEBIT", 100)]

    # Insufficient funds
    result = wallet.debit(150)
    assert result is False
    assert wallet.balance == 100  # Balance should not change
    assert wallet.transactions == [("CREDIT", 200), ("DEBIT", 100)] # Transactions should not change


def test_payment_repository_operations(payment_repo, mock_uuid_fixed):
    """Tests PaymentRepository save, update_status, and get_by_user methods."""
    user_id = "test_user_repo"
    payment_id1 = mock_uuid_fixed
    payment_id2 = str(uuid.uuid4()) # Use actual uuid for second payment to ensure it's different

    # Test save
    payment1 = Payment(payment_id1, 100, "USD", user_id)
    payment_repo.save(payment1)
    loaded_data = payment_repo._load()
    assert len(loaded_data) == 1
    assert loaded_data[0]["payment_id"] == payment_id1
    assert loaded_data[0]["status"] == "CREATED"

    # Test get_by_user
    user_payments = payment_repo.get_by_user(user_id)
    assert len(user_payments) == 1
    assert user_payments[0]["payment_id"] == payment_id1

    # Add another payment for a different user
    payment_other_user = Payment(payment_id2, 50, "EUR", "other_user")
    payment_repo.save(payment_other_user)
    loaded_data = payment_repo._load()
    assert len(loaded_data) == 2
    user_payments = payment_repo.get_by_user(user_id)
    assert len(user_payments) == 1 # Still only one for 'test_user_repo'

    # Test update_status
    payment_repo.update_status(payment_id1, "SUCCESS")
    updated_data = payment_repo._load()
    found_payment = next((p for p in updated_data if p["payment_id"] == payment_id1), None)
    assert found_payment is not None
    assert found_payment["status"] == "SUCCESS"


def test_fraud_checker_is_fraud_conditions():
    """Tests FraudChecker for different fraud conditions."""
    checker = FraudChecker()

    # High amount
    payment_high_amount = Payment("id", 100001, "USD", "user")
    assert checker.is_fraud(payment_high_amount) is True

    # Unsupported currency
    payment_bad_currency = Payment("id", 100, "JPY", "user")
    assert checker.is_fraud(payment_bad_currency) is True

    # Valid payment
    payment_valid = Payment("id", 500, "EUR", "user")
    assert checker.is_fraud(payment_valid) is False


def test_payment_gateway_charge_outcomes(monkeypatch):
    """Tests PaymentGateway charge for success and failure outcomes by mocking random."""
    gateway = PaymentGateway()
    payment = Payment("id", 100, "USD", "user")

    # Force success (rand(1,10) < 8 -> e.g., 1-7)
    monkeypatch.setattr(random, "randint", lambda a, b: 5)
    assert gateway.charge(payment) is True

    # Force failure (rand(1,10) < 8 -> e.g., 8-10)
    monkeypatch.setattr(random, "randint", lambda a, b: 9)
    assert gateway.charge(payment) is False


def test_payment_service_add_funds_and_user_balance(payment_service_instance):
    """Tests PaymentService add_funds and user_balance methods."""
    user_id = "user_funds"
    service = payment_service_instance

    assert service.user_balance(user_id) == 0

    balance = service.add_funds(user_id, 500)
    assert balance == 500
    assert service.user_balance(user_id) == 500

    balance = service.add_funds(user_id, 250)
    assert balance == 750
    assert service.user_balance(user_id) == 750


def test_payment_service_process_payment_invalid_amount(payment_service_instance):
    """Tests PaymentService.process_payment with an invalid amount."""
    user_id = "user_invalid_amount"
    service = payment_service_instance

    with pytest.raises(ValueError, match="Invalid amount"):
        service.process_payment(user_id, 0, "USD")

    with pytest.raises(ValueError, match="Invalid amount"):
        service.process_payment(user_id, -100, "USD")


def test_payment_service_process_payment_fraud_detected(payment_service_instance, mock_fraud_checker_fraud):
    """Tests PaymentService.process_payment when fraud is detected."""
    user_id = "user_fraud"
    amount = 100
    currency = "USD"
    service = payment_service_instance

    # Add funds for other tests, but expect fraud to short-circuit
    service.add_funds(user_id, 1000)
    initial_balance = service.user_balance(user_id)

    result = service.process_payment(user_id, amount, currency)
    assert result is False

    # Verify wallet balance is unchanged
    assert service.user_balance(user_id) == initial_balance

    # Verify payment status in repo is FAILED
    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    assert payments[0]["amount"] == amount


def test_payment_service_process_payment_insufficient_funds(payment_service_instance, mock_fraud_checker_safe):
    """Tests PaymentService.process_payment with insufficient wallet funds."""
    user_id = "user_insufficient"
    amount = 500
    currency = "USD"
    service = payment_service_instance

    # Add less funds than required
    service.add_funds(user_id, 100)
    initial_balance = service.user_balance(user_id) # 100

    result = service.process_payment(user_id, amount, currency)
    assert result is False

    # Verify wallet balance is unchanged
    assert service.user_balance(user_id) == initial_balance

    # Verify payment status in repo is FAILED
    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    assert payments[0]["amount"] == amount


def test_payment_service_process_payment_gateway_failure(payment_service_instance, mock_fraud_checker_safe, mock_gateway_charge_fail):
    """Tests PaymentService.process_payment when gateway charge fails."""
    user_id = "user_gateway_fail"
    amount = 200
    currency = "USD"
    service = payment_service_instance

    service.add_funds(user_id, 500)
    initial_balance = service.user_balance(user_id) # 500

    result = service.process_payment(user_id, amount, currency)
    assert result is False

    # Verify wallet balance is restored (initial_balance - amount + amount)
    assert service.user_balance(user_id) == initial_balance

    # Verify payment status in repo is FAILED
    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    assert payments[0]["amount"] == amount


def test_payment_service_process_payment_success(payment_service_instance, mock_fraud_checker_safe, mock_gateway_charge_success, mock_uuid_fixed):
    """Tests a full successful PaymentService.process_payment flow."""
    user_id = "user_success"
    amount = 150
    currency = "EUR"
    service = payment_service_instance

    service.add_funds(user_id, 500)
    initial_balance = service.user_balance(user_id) # 500

    result = service.process_payment(user_id, amount, currency)
    assert result is True

    # Verify wallet balance is debited
    assert service.user_balance(user_id) == initial_balance - amount # 350

    # Verify payment status in repo is SUCCESS
    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["payment_id"] == mock_uuid_fixed
    assert payments[0]["status"] == "SUCCESS"
    assert payments[0]["amount"] == amount


def test_payment_service_refund(payment_service_instance, mock_uuid_fixed, mock_fraud_checker_safe, mock_gateway_charge_success):
    """Tests PaymentService refund functionality."""
    user_id = "user_refund"
    amount = 100
    currency = "USD"
    service = payment_service_instance

    service.add_funds(user_id, 200)
    initial_balance = service.user_balance(user_id) # 200

    # Process a successful payment first
    service.process_payment(user_id, amount, currency)
    payment_id = mock_uuid_fixed
    assert service.user_balance(user_id) == initial_balance - amount # 100

    # Refund the payment
    service.refund(payment_id)

    # Verify wallet balance is credited back
    assert service.user_balance(user_id) == initial_balance # 200

    # Verify payment status in repo is REFUNDED
    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["payment_id"] == payment_id
    assert payments[0]["status"] == "REFUNDED"


def test_batch_payments_functionality(payment_service_instance, mock_fraud_checker_safe, mock_gateway_charge_success, mock_gateway_charge_fail):
    """Tests the batch_payments utility function with mixed results."""
    user_id = "user_batch"
    service = payment_service_instance
    service.add_funds(user_id, 1000)

    # Payments: 1 success, 1 insufficient funds, 1 invalid amount, 1 gateway failure
    payments_to_process = [
        (100, "USD"),  # Should succeed
        (800, "USD"),  # Should fail due to insufficient funds (1000-100 = 900, but next payment needs 800, so 100 remaining)
        (0, "USD"),    # Should fail due to invalid amount
        (50, "USD")    # Should fail due to gateway failure (mocked later)
    ]

    # Mock gateway charge failure for the 4th payment
    with patch.object(service.gateway, 'charge', side_effect=[True, True, True, False]) as mock_charge:
        results = batch_payments(service, user_id, payments_to_process)
        
        assert results == [True, False, False, False] # Insufficient funds is also a False result

        # Verify final balance: 1000 (initial) - 100 (successful) = 900
        assert service.user_balance(user_id) == 900

        # Verify payment statuses in repo
        user_payments = service.repo.get_by_user(user_id)
        assert len(user_payments) == 4 # All attempts are saved
        assert user_payments[0]["status"] == "SUCCESS"
        assert user_payments[1]["status"] == "FAILED" # Insufficient funds
        assert user_payments[2]["status"] == "FAILED" # Invalid amount is caught by service then saved as FAILED
        assert user_payments[3]["status"] == "FAILED" # Gateway failure


def test_export_report_generates_file(payment_service_instance, tmp_path, mock_fraud_checker_safe, mock_gateway_charge_success):
    """Tests if export_report correctly generates a JSON file."""
    user1 = "user_report1"
    user2 = "user_report2"
    service = payment_service_instance
    report_path = tmp_path / "report_data" / "report.json"

    # Setup some wallet states
    service.add_funds(user1, 100)
    service.process_payment(user1, 50, "USD") # Balance: 50
    service.add_funds(user2, 200) # Balance: 200

    export_report(service, str(report_path))

    assert report_path.exists()

    with open(report_path, "r") as f:
        report_data = json.load(f)

    assert user1 in report_data
    assert report_data[user1]["balance"] == 50
    assert ("CREDIT", 100) in [tuple(t) for t in report_data[user1]["transactions"]]
    assert ("DEBIT", 50) in [tuple(t) for t in report_data[user1]["transactions"]]

    assert user2 in report_data
    assert report_data[user2]["balance"] == 200
    assert ("CREDIT", 200) in [tuple(t) for t in report_data[user2]["transactions"]]
    assert len(report_data[user2]["transactions"]) == 1 # Only one credit transaction
