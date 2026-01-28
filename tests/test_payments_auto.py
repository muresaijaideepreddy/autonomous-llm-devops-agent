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

# Fixtures
@pytest.fixture
def payment_repo(tmp_path):
    """Provides a PaymentRepository instance with a temporary file path."""
    repo_path = tmp_path / "payments.json"
    repo = PaymentRepository(path=str(repo_path))
    return repo

@pytest.fixture
def empty_payment_service(payment_repo):
    """Provides a PaymentService instance with a temporary repo and default dependencies."""
    # Using default FraudChecker and PaymentGateway instances which can be mocked in tests
    service = PaymentService(repo=payment_repo)
    return service

@pytest.fixture
def sample_payment():
    """Provides a sample Payment object."""
    return Payment(str(uuid.uuid4()), 100, "USD", "user123")

# Tests

# Test 1: Payment Class - Initial status and marking
def test_payment_initial_status_and_marking(sample_payment):
    assert sample_payment.status == "CREATED"
    assert isinstance(sample_payment.created_at, datetime)

    sample_payment.mark_success()
    assert sample_payment.status == "SUCCESS"

    sample_payment.mark_failed()
    assert sample_payment.status == "FAILED"

# Test 2: Wallet Class - Credit valid and invalid
def test_wallet_credit_valid_and_invalid():
    wallet = Wallet("user_test")
    assert wallet.balance == 0
    
    wallet.credit(100)
    assert wallet.balance == 100
    assert wallet.transactions == [("CREDIT", 100)]

    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(0)
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(-50)
    assert wallet.balance == 100 # Balance should not change after invalid credit
    assert wallet.transactions == [("CREDIT", 100)] # Transactions should not change

# Test 3: Wallet Class - Debit success and failure
def test_wallet_debit_success_and_failure():
    wallet = Wallet("user_test")
    wallet.credit(200)
    assert wallet.balance == 200

    # Successful debit
    result = wallet.debit(100)
    assert result is True
    assert wallet.balance == 100
    assert wallet.transactions == [("CREDIT", 200), ("DEBIT", 100)]

    # Insufficient funds debit
    result = wallet.debit(150)
    assert result is False
    assert wallet.balance == 100 # Balance should not change
    assert wallet.transactions == [("CREDIT", 200), ("DEBIT", 100)] # Transactions should not change

# Test 4: PaymentRepository - Save, update_status, get_by_user
def test_payment_repo_save_update_get(payment_repo):
    user_id = "test_user_repo"
    payment1_id = str(uuid.uuid4())
    payment2_id = str(uuid.uuid4())
    payment1 = Payment(payment1_id, 50, "USD", user_id)
    payment2 = Payment(payment2_id, 75, "EUR", "another_user")

    payment_repo.save(payment1)
    payment_repo.save(payment2)

    loaded_payments_all = payment_repo._load()
    assert len(loaded_payments_all) == 2
    
    # Update status
    payment_repo.update_status(payment1_id, "SUCCESS")
    updated_payments = payment_repo._load()
    assert next(p["status"] for p in updated_payments if p["payment_id"] == payment1_id) == "SUCCESS"

    # Get by user
    user_payments = payment_repo.get_by_user(user_id)
    assert len(user_payments) == 1
    assert user_payments[0]["payment_id"] == payment1_id
    assert user_payments[0]["user_id"] == user_id
    assert user_payments[0]["status"] == "SUCCESS"

# Test 5: FraudChecker - Scenarios
def test_fraud_checker_scenarios():
    fraud_checker = FraudChecker()

    # Not fraud
    p_not_fraud = Payment("id1", 500, "USD", "user1")
    assert fraud_checker.is_fraud(p_not_fraud) is False

    # High amount fraud
    p_high_amount = Payment("id2", 100001, "USD", "user1")
    assert fraud_checker.is_fraud(p_high_amount) is True

    # Invalid currency fraud
    p_invalid_currency = Payment("id3", 500, "JPY", "user1")
    assert fraud_checker.is_fraud(p_invalid_currency) is True

# Test 6: PaymentGateway - Charge deterministic
def test_payment_gateway_charge_deterministic():
    gateway = PaymentGateway()
    payment = Payment("id", 100, "USD", "user")

    # Mock random.randint to ensure success (returns 1, 1 < 8)
    with patch('random.randint', return_value=1) as mock_randint_success:
        assert gateway.charge(payment) is True
        mock_randint_success.assert_called_once_with(1, 10)

    # Mock random.randint to ensure failure (returns 8, 8 < 8 is False)
    with patch('random.randint', return_value=8) as mock_randint_failure:
        assert gateway.charge(payment) is False
        mock_randint_failure.assert_called_once_with(1, 10)

# Test 7: PaymentService - Add funds
def test_payment_service_add_funds(empty_payment_service):
    user_id = "user_add_funds"
    initial_balance = empty_payment_service.user_balance(user_id)
    assert initial_balance == 0

    new_balance = empty_payment_service.add_funds(user_id, 500)
    assert new_balance == 500
    assert empty_payment_service.user_balance(user_id) == 500

    new_balance = empty_payment_service.add_funds(user_id, 200)
    assert new_balance == 700

# Test 8: PaymentService - Process payment invalid amount
def test_payment_service_process_payment_invalid_amount(empty_payment_service):
    user_id = "user_invalid_amount"
    with pytest.raises(ValueError, match="Invalid amount"):
        empty_payment_service.process_payment(user_id, 0, "USD")
    with pytest.raises(ValueError, match="Invalid amount"):
        empty_payment_service.process_payment(user_id, -10, "USD")

# Test 9: PaymentService - Process payment fraud
def test_payment_service_process_payment_fraud(payment_repo):
    mock_fraud_checker = MagicMock(spec=FraudChecker)
    mock_fraud_checker.is_fraud.return_value = True # Always fraud

    service = PaymentService(repo=payment_repo, fraud=mock_fraud_checker)
    user_id = "user_fraud"
    amount = 50

    result = service.process_payment(user_id, amount, "USD")
    assert result is False

    mock_fraud_checker.is_fraud.assert_called_once()
    
    payments = payment_repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    assert service.user_balance(user_id) == 0 # Wallet balance should be untouched

# Test 10: PaymentService - Process payment insufficient funds
def test_payment_service_process_payment_insufficient_funds(empty_payment_service):
    user_id = "user_insufficient_funds"
    initial_balance = 100
    empty_payment_service.add_funds(user_id, initial_balance)
    assert empty_payment_service.user_balance(user_id) == initial_balance

    amount_to_debit = 150 
    result = empty_payment_service.process_payment(user_id, amount_to_debit, "USD")
    assert result is False

    assert empty_payment_service.user_balance(user_id) == initial_balance # Balance unchanged
    
    payments = empty_payment_service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"

# Test 11: PaymentService - Process payment gateway failure and refund
def test_payment_service_process_payment_gateway_failure_and_refund(payment_repo):
    mock_gateway = MagicMock(spec=PaymentGateway)
    mock_gateway.charge.return_value = False # Always fail gateway charge

    service = PaymentService(repo=payment_repo, gateway=mock_gateway)
    user_id = "user_gateway_fail_refund"
    initial_funds = 200
    service.add_funds(user_id, initial_funds)

    amount = 100
    result = service.process_payment(user_id, amount, "USD")
    assert result is False

    # Wallet should have been debited and then credited back
    assert service.user_balance(user_id) == initial_funds
    mock_gateway.charge.assert_called_once()

    payments_after_attempt = payment_repo.get_by_user(user_id)
    failed_payment_id = payments_after_attempt[0]["payment_id"]
    assert payments_after_attempt[0]["status"] == "FAILED"

    # Now, test refund for the FAILED payment
    service.refund(failed_payment_id)

    # Balance will increase by 'amount' after refund, as funds were already credited back after gateway failure
    assert service.user_balance(user_id) == initial_funds + amount 
    
    refunded_payments = payment_repo._load()
    refunded_payment = next(p for p in refunded_payments if p["payment_id"] == failed_payment_id)
    assert refunded_payment["status"] == "REFUNDED"

# Test 12: PaymentService - Process payment success and user balance
def test_payment_service_process_payment_success_and_user_balance(payment_repo):
    mock_gateway = MagicMock(spec=PaymentGateway)
    mock_gateway.charge.return_value = True

    service = PaymentService(repo=payment_repo, gateway=mock_gateway)
    user_id = "user_success_balance"
    initial_funds = 500
    service.add_funds(user_id, initial_funds)

    amount1 = 100
    result1 = service.process_payment(user_id, amount1, "USD")
    assert result1 is True
    assert service.user_balance(user_id) == initial_funds - amount1

    amount2 = 50
    result2 = service.process_payment(user_id, amount2, "EUR")
    assert result2 is True
    assert service.user_balance(user_id) == initial_funds - amount1 - amount2

    payments = payment_repo.get_by_user(user_id)
    assert len(payments) == 2
    assert all(p["status"] == "SUCCESS" for p in payments)

# Test 13: Batch operations - batch_payments mixed results
def test_batch_payments_mixed_results(payment_repo):
    mock_fraud = MagicMock(spec=FraudChecker)
    mock_gateway = MagicMock(spec=PaymentGateway)
    service = PaymentService(repo=payment_repo, fraud=mock_fraud, gateway=mock_gateway)

    user_id = "user_batch"
    service.add_funds(user_id, 1000)

    # Setup mock behaviors for the sequence of payments
    mock_fraud.is_fraud.side_effect = [True, False, False] # 1st fraud, 2nd & 3rd not fraud
    mock_gateway.charge.side_effect = [False, True] # For non-fraudulent payments: 1st gateway fail, 2nd gateway success

    payments_to_process = [
        (200, "USD"),  # Payment 1: Fraud -> False
        (150, "EUR"),  # Payment 2: Not fraud, Gateway failure -> False
        (100, "INR"),  # Payment 3: Not fraud, Gateway success -> True
        (0, "USD")     # Payment 4: Invalid amount (ValueError) -> False
    ]

    results = batch_payments(service, user_id, payments_to_process)

    assert results == [False, False, True, False]
    assert service.user_balance(user_id) == 1000 - 100 # Only the successful payment (100) debited

    repo_payments = payment_repo.get_by_user(user_id)
    assert len(repo_payments) == 3 # Invalid amount payment is not saved to repo
    assert sum(1 for p in repo_payments if p["status"] == "FAILED") == 2
    assert sum(1 for p in repo_payments if p["status"] == "SUCCESS") == 1

# Test 14: Optional utilities - export_report generates correct data
def test_export_report_generates_correct_data(empty_payment_service, tmp_path):
    user_id_1 = "user_report_1"
    user_id_2 = "user_report_2"

    empty_payment_service.add_funds(user_id_1, 100)
    empty_payment_service.add_funds(user_id_2, 200)

    # Process payments to generate transactions and update balances
    mock_gateway = MagicMock(spec=PaymentGateway)
    mock_gateway.charge.return_value = True # Ensure success for processed payments
    service_for_report = PaymentService(repo=empty_payment_service.repo, gateway=mock_gateway)
    service_for_report.wallets = empty_payment_service.wallets # Link to the same wallets

    service_for_report.process_payment(user_id_1, 50, "USD") # Balance user1: 100 -> 50
    service_for_report.process_payment(user_id_2, 75, "EUR") # Balance user2: 200 -> 125

    report_path = tmp_path / "report.json"
    export_report(service_for_report, path=str(report_path))

    assert os.path.exists(report_path)

    with open(report_path, "r") as f:
        report_data = json.load(f)

    assert user_id_1 in report_data
    assert report_data[user_id_1]["balance"] == 50
    assert report_data[user_id_1]["transactions"] == [["CREDIT", 100], ["DEBIT", 50]]

    assert user_id_2 in report_data
    assert report_data[user_id_2]["balance"] == 125
    assert report_data[user_id_2]["transactions"] == [["CREDIT", 200], ["DEBIT", 75]]

    assert len(report_data) == 2
