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
def repo_path(tmp_path):
    """Provides a temporary file path for the PaymentRepository."""
    return tmp_path / "test_payments.json"


@pytest.fixture
def repository(repo_path):
    """Returns a PaymentRepository instance initialized with a temporary path."""
    repo = PaymentRepository(str(repo_path))
    # Ensure the file is empty at the start of each test
    with open(repo.path, "w") as f:
        json.dump([], f)
    return repo


@pytest.fixture
def mock_uuid(monkeypatch):
    """Mocks uuid.uuid4 to return a predictable UUID string."""
    mock_id = "test-payment-id-123"
    monkeypatch.setattr(uuid, "uuid4", lambda: mock_id)
    return mock_id


def test_payment_init_status():
    """Test Payment object initialization and default status."""
    payment = Payment("id123", 100, "USD", "userA")
    assert payment.payment_id == "id123"
    assert payment.amount == 100
    assert payment.currency == "USD"
    assert payment.user_id == "userA"
    assert payment.status == "CREATED"
    assert isinstance(payment.created_at, datetime)
    assert payment.created_at.tzinfo == timezone.utc


def test_payment_mark_success_and_failed():
    """Test marking payment status as SUCCESS and FAILED."""
    payment1 = Payment("id1", 50, "USD", "user1")
    payment1.mark_success()
    assert payment1.status == "SUCCESS"

    payment2 = Payment("id2", 75, "EUR", "user2")
    payment2.mark_failed()
    assert payment2.status == "FAILED"


def test_wallet_credit_success():
    """Test successful credit to a wallet."""
    wallet = Wallet("user1")
    wallet.credit(100)
    assert wallet.balance == 100
    assert wallet.transactions == [("CREDIT", 100)]
    wallet.credit(50.5)
    assert wallet.balance == 150.5
    assert wallet.transactions == [("CREDIT", 100), ("CREDIT", 50.5)]


def test_wallet_credit_invalid_amount():
    """Test credit with invalid (non-positive) amount raises ValueError."""
    wallet = Wallet("user1")
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(0)
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(-10)
    assert wallet.balance == 0
    assert not wallet.transactions


def test_wallet_debit_success_and_fail():
    """Test successful and unsuccessful debit from a wallet."""
    wallet = Wallet("user1")
    wallet.credit(200)

    # Test successful debit
    result_success = wallet.debit(100)
    assert result_success is True
    assert wallet.balance == 100
    assert wallet.transactions == [("CREDIT", 200), ("DEBIT", 100)]

    # Test unsuccessful debit (insufficient funds)
    result_fail = wallet.debit(150)
    assert result_fail is False
    assert wallet.balance == 100  # Balance should be unchanged
    assert wallet.transactions == [("CREDIT", 200), ("DEBIT", 100)] # Transactions should be unchanged


def test_payment_repo_save_and_get_by_user(repository):
    """Test saving payments and retrieving them by user ID."""
    payment1 = Payment("p1", 100, "USD", "userA")
    payment2 = Payment("p2", 200, "EUR", "userB")
    payment3 = Payment("p3", 150, "INR", "userA")

    repository.save(payment1)
    repository.save(payment2)
    repository.save(payment3)

    user_a_payments = repository.get_by_user("userA")
    assert len(user_a_payments) == 2
    assert {p["payment_id"] for p in user_a_payments} == {"p1", "p3"}
    assert all(p["user_id"] == "userA" for p in user_a_payments)

    user_b_payments = repository.get_by_user("userB")
    assert len(user_b_payments) == 1
    assert user_b_payments[0]["payment_id"] == "p2"

    user_c_payments = repository.get_by_user("userC")
    assert len(user_c_payments) == 0


def test_payment_repo_update_status(repository):
    """Test updating the status of a payment in the repository."""
    payment = Payment("update_id", 500, "USD", "user_update")
    repository.save(payment)
    assert repository.get_by_user("user_update")[0]["status"] == "CREATED"

    repository.update_status("update_id", "SUCCESS")
    updated_payment = repository.get_by_user("user_update")[0]
    assert updated_payment["status"] == "SUCCESS"

    # Test updating a non-existent payment_id
    repository.update_status("non_existent_id", "FAILED")
    still_updated_payment = repository.get_by_user("user_update")[0]
    assert still_updated_payment["status"] == "SUCCESS"  # Should remain unchanged


def test_fraud_checker_rules():
    """Test FraudChecker for various fraud scenarios."""
    fraud_checker = FraudChecker()

    # Amount too high
    payment_high_amount = Payment("f1", 100001, "USD", "userF")
    assert fraud_checker.is_fraud(payment_high_amount) is True

    # Invalid currency
    payment_bad_currency = Payment("f2", 500, "XYZ", "userF")
    assert fraud_checker.is_fraud(payment_bad_currency) is True

    # Both conditions met
    payment_both_bad = Payment("f3", 100002, "ABC", "userF")
    assert fraud_checker.is_fraud(payment_both_bad) is True

    # No fraud
    payment_ok = Payment("f4", 99999, "INR", "userF")
    assert fraud_checker.is_fraud(payment_ok) is False


def test_payment_gateway_charge_outcomes(monkeypatch):
    """Test PaymentGateway.charge with deterministic success and failure."""
    gateway = PaymentGateway()
    payment = Payment("g1", 100, "USD", "userG")

    # Force success (rand(1,10) < 8 means 1-7 pass, 8-10 fail)
    # Mock rand to return 7
    with patch('random.randint', return_value=7):
        assert gateway.charge(payment) is True

    # Force failure
    # Mock rand to return 8
    with patch('random.randint', return_value=8):
        assert gateway.charge(payment) is False


def test_payment_service_add_funds(repository):
    """Test adding funds to a user's wallet via PaymentService."""
    service = PaymentService(repo=repository)
    user_id = "user_add_funds"

    initial_balance = service.user_balance(user_id)
    assert initial_balance == 0

    service.add_funds(user_id, 100)
    assert service.user_balance(user_id) == 100

    service.add_funds(user_id, 200)
    assert service.user_balance(user_id) == 300

    # Test invalid amount for add_funds (internally calls wallet.credit)
    with pytest.raises(ValueError, match="Invalid credit amount"):
        service.add_funds(user_id, -50)
    assert service.user_balance(user_id) == 300


def test_payment_service_process_payment_invalid_amount(repository):
    """Test processing payment with an invalid amount (<= 0)."""
    service = PaymentService(repo=repository)
    user_id = "user_invalid_amt"

    with pytest.raises(ValueError, match="Invalid amount"):
        service.process_payment(user_id, 0, "USD")
    with pytest.raises(ValueError, match="Invalid amount"):
        service.process_payment(user_id, -10, "USD")

    # No payments should be saved for invalid amounts
    assert not repository.get_by_user(user_id)


def test_payment_service_process_payment_fraud(repository, mock_uuid):
    """Test payment service handling of fraudulent payments."""
    mock_fraud = MagicMock(spec=FraudChecker)
    mock_fraud.is_fraud.return_value = True # Simulate fraud
    service = PaymentService(repo=repository, fraud=mock_fraud)

    user_id = "user_fraud"
    result = service.process_payment(user_id, 100, "USD")
    assert result is False

    # Verify fraud checker was called
    mock_fraud.is_fraud.assert_called_once()

    # Verify payment was saved with FAILED status
    payments = repository.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["payment_id"] == mock_uuid
    assert payments[0]["status"] == "FAILED"
    assert service.user_balance(user_id) == 0 # Wallet should not be affected


def test_payment_service_process_payment_insufficient_funds_and_gateway_failure_rollback(repository, mock_uuid):
    """
    Test payment service handling of insufficient funds and gateway charge failure with rollback.
    Combines two scenarios to stay within test function limit.
    """
    mock_gateway = MagicMock(spec=PaymentGateway)
    mock_fraud = MagicMock(spec=FraudChecker)
    mock_fraud.is_fraud.return_value = False # No fraud for these tests
    service = PaymentService(repo=repository, gateway=mock_gateway, fraud=mock_fraud)

    user_id_funds = "user_funds_test"
    user_id_gateway = "user_gateway_test"

    # --- Scenario 1: Insufficient Funds ---
    service.add_funds(user_id_funds, 50) # Wallet has 50
    result_funds = service.process_payment(user_id_funds, 100, "USD") # Try to pay 100
    assert result_funds is False
    assert service.user_balance(user_id_funds) == 50 # Balance should be unchanged

    # Verify payment was saved with FAILED status
    payments_funds = repository.get_by_user(user_id_funds)
    assert len(payments_funds) == 1
    assert payments_funds[0]["payment_id"] == mock_uuid
    assert payments_funds[0]["status"] == "FAILED"
    mock_fraud.is_fraud.assert_called_once() # Called for this payment
    mock_gateway.charge.assert_not_called() # Gateway should not be called if debit fails

    # --- Scenario 2: Gateway Charge Failure (with rollback) ---
    mock_fraud.is_fraud.reset_mock() # Reset mock for next payment
    mock_fraud.is_fraud.return_value = False
    mock_gateway.charge.return_value = False # Simulate gateway failure

    service.add_funds(user_id_gateway, 200) # Wallet has 200
    initial_balance_gateway = service.user_balance(user_id_gateway)
    result_gateway = service.process_payment(user_id_gateway, 100, "USD") # Try to pay 100
    assert result_gateway is False
    assert service.user_balance(user_id_gateway) == initial_balance_gateway # Balance should be rolled back to 200

    # Verify payment was saved with FAILED status
    payments_gateway = repository.get_by_user(user_id_gateway)
    assert len(payments_gateway) == 1
    assert payments_gateway[0]["payment_id"] == mock_uuid
    assert payments_gateway[0]["status"] == "FAILED"
    mock_fraud.is_fraud.assert_called_once() # Called for this payment
    mock_gateway.charge.assert_called_once() # Gateway should have been called


def test_payment_service_process_payment_success(repository, mock_uuid):
    """Test a successful payment process from PaymentService."""
    mock_gateway = MagicMock(spec=PaymentGateway)
    mock_gateway.charge.return_value = True # Simulate successful charge
    mock_fraud = MagicMock(spec=FraudChecker)
    mock_fraud.is_fraud.return_value = False # No fraud
    service = PaymentService(repo=repository, gateway=mock_gateway, fraud=mock_fraud)

    user_id = "user_success"
    service.add_funds(user_id, 500)
    initial_balance = service.user_balance(user_id)

    result = service.process_payment(user_id, 150, "USD")
    assert result is True
    assert service.user_balance(user_id) == initial_balance - 150

    # Verify mocks were called
    mock_fraud.is_fraud.assert_called_once()
    mock_gateway.charge.assert_called_once()

    # Verify payment was saved with SUCCESS status
    payments = repository.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["payment_id"] == mock_uuid
    assert payments[0]["status"] == "SUCCESS"


def test_payment_service_refund_and_user_balance(repository, mock_uuid):
    """Test refund functionality and user balance retrieval."""
    mock_gateway = MagicMock(spec=PaymentGateway)
    mock_gateway.charge.return_value = True
    mock_fraud = MagicMock(spec=FraudChecker)
    mock_fraud.is_fraud.return_value = False
    service = PaymentService(repo=repository, gateway=mock_gateway, fraud=mock_fraud)

    user_id = "user_refund"
    service.add_funds(user_id, 200) # Wallet has 200
    assert service.user_balance(user_id) == 200

    # Process a successful payment
    service.process_payment(user_id, 50, "USD") # Wallet debited, now 150
    assert service.user_balance(user_id) == 150

    payment_id = mock_uuid # The ID used for the processed payment

    # Refund the payment
    service.refund(payment_id)
    assert service.user_balance(user_id) == 200 # Wallet credited back to 200

    # Verify payment status in repository is REFUNDED
    payments = repository.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["payment_id"] == payment_id
    assert payments[0]["status"] == "REFUNDED"


def test_batch_payments(repository, mock_uuid):
    """Test batch_payments function with mixed success and failures."""
    mock_gateway = MagicMock(spec=PaymentGateway)
    # Configure gateway for mixed results: first success, then fail, then success
    mock_gateway.charge.side_effect = [True, False, True]
    mock_fraud = MagicMock(spec=FraudChecker)
    mock_fraud.is_fraud.side_effect = [False, False, False] # No fraud

    service = PaymentService(repo=repository, gateway=mock_gateway, fraud=mock_fraud)
    user_id = "batch_user"
    service.add_funds(user_id, 500) # Initial balance for user

    payments_to_process = [
        (50, "USD"), # Success
        (100, "EUR"), # Gateway fails, rollback
        (10, "INR") # Success
    ]

    # Mock uuid.uuid4 to return distinct IDs for each payment in batch
    with patch('uuid.uuid4', side_effect=["id-batch-1", "id-batch-2", "id-batch-3"]) as mock_uuid_calls:
        results = batch_payments(service, user_id, payments_to_process)

    assert results == [True, False, True]
    assert service.user_balance(user_id) == (500 - 50 - 10) # 500 - 50 (success) + 100 (rollback) - 100 (failed gateway, but was debited before rollback) - 10 (success)
    # The math above is wrong:
    # 500 (initial) - 50 (first payment) = 450
    # 450 - 100 (second payment debit) = 350, then +100 (rollback) = 450
    # 450 - 10 (third payment) = 440
    assert service.user_balance(user_id) == 440

    all_payments = repository.get_by_user(user_id)
    assert len(all_payments) == 3
    assert {p["status"] for p in all_payments} == {"SUCCESS", "FAILED"}
    assert next(p for p in all_payments if p["payment_id"] == "id-batch-1")["status"] == "SUCCESS"
    assert next(p for p in all_payments if p["payment_id"] == "id-batch-2")["status"] == "FAILED"
    assert next(p for p in all_payments if p["payment_id"] == "id-batch-3")["status"] == "SUCCESS"


def test_batch_payments_with_invalid_amount(repository):
    """Test batch_payments function with an invalid amount causing ValueError."""
    service = PaymentService(repo=repository) # Use default mocks if not needed
    user_id = "batch_invalid_user"
    service.add_funds(user_id, 100)

    payments_to_process = [
        (50, "USD"),
        (0, "EUR"), # Invalid amount
        (20, "INR")
    ]

    with patch('uuid.uuid4', side_effect=["id-b-1", "id-b-2", "id-b-3"]):
        results = batch_payments(service, user_id, payments_to_process)

    assert results == [True, False, True] # Second payment is False due to ValueError
    assert service.user_balance(user_id) == (100 - 50 - 20) # 30
    all_payments = repository.get_by_user(user_id)
    assert len(all_payments) == 2 # Only valid payments are processed and saved
    assert {p["status"] for p in all_payments} == {"SUCCESS"} # No FAILED status from ValueError
    assert next(p for p in all_payments if p["payment_id"] == "id-b-1")["status"] == "SUCCESS"
    assert next(p for p in all_payments if p["payment_id"] == "id-b-3")["status"] == "SUCCESS"


def test_export_report(repository, tmp_path, mock_uuid):
    """Test the export_report utility function."""
    service = PaymentService(repo=repository)
    user_id_1 = "user_report_1"
    user_id_2 = "user_report_2"

    service.add_funds(user_id_1, 100)
    service.add_funds(user_id_2, 200)

    # Process some payments to generate transactions
    with patch('random.randint', return_value=1): # Force gateway success
        with patch('uuid.uuid4', side_effect=["pay1", "pay2", "pay3"]):
            service.process_payment(user_id_1, 30, "USD")
            service.process_payment(user_id_2, 50, "EUR")
            service.process_payment(user_id_1, 20, "INR")

    # The mock uuid is "pay1", "pay2", "pay3"
    # Wallet for user_report_1: 100(credit), 30(debit), 20(debit) -> balance 50
    # Wallet for user_report_2: 200(credit), 50(debit) -> balance 150

    report_path = tmp_path / "test_report.json"
    export_report(service, str(report_path))

    assert report_path.exists()
    with open(report_path, "r") as f:
        report = json.load(f)

    assert user_id_1 in report
    assert report[user_id_1]["balance"] == 50
    assert report[user_id_1]["transactions"] == [["CREDIT", 100], ["DEBIT", 30], ["DEBIT", 20]]

    assert user_id_2 in report
    assert report[user_id_2]["balance"] == 150
    assert report[user_id_2]["transactions"] == [["CREDIT", 200], ["DEBIT", 50]]
