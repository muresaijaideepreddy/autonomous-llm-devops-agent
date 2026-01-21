import sys
import os
import pytest
import uuid
from unittest.mock import MagicMock, patch

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import *


# -------------------------
# PASSING TESTS (Few)
# -------------------------

# --- Fixtures ---
@pytest.fixture
def tmp_path_repo(tmp_path):
    repo_path = tmp_path / "payments.json"
    repo = PaymentRepository(str(repo_path))
    return repo
@pytest.fixture
def payment_service(tmp_path_repo):
    service = PaymentService(repo=tmp_path_repo)
    return service
@pytest.fixture
def sample_payment():
    return Payment(str(uuid.uuid4()), 100, "USD", "user123")

# --- Preserved Passing Tests ---
def test_payment_creation_pass():
    payment = Payment(str(uuid.uuid4()), 100, "USD", "user1")
    assert payment.status == "CREATED"
def test_wallet_credit_pass():
    wallet = Wallet("user1")
    wallet.credit(100)
    assert wallet.balance == 100
def test_payment_gateway_always_succeeds():
    """
    FAIL: gateway success is random
    """
    gateway = PaymentGateway()
    payment = Payment(str(uuid.uuid4()), 100, "USD", "user6")

    with patch("random.randint", return_value=10):
        result = gateway.charge(payment)
        assert result is True  # ❌ charge returns False for >=8

# --- Newly Generated Tests ---
def test_payment_mark_failed_status(sample_payment):
    sample_payment.mark_failed()
    assert sample_payment.status == "FAILED"
def test_wallet_credit_invalid_amount_raises_error():
    wallet = Wallet("user123")
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(0)
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(-10)
    assert wallet.balance == 0
    assert wallet.transactions == []
def test_wallet_debit_insufficient_funds_returns_false():
    wallet = Wallet("user123")
    wallet.credit(50)
    assert wallet.debit(100) is False
    assert wallet.balance == 50
    assert wallet.transactions == [("CREDIT", 50)]
def test_payment_repo_update_status(tmp_path_repo):
    payment_id = str(uuid.uuid4())
    payment = Payment(payment_id, 50, "USD", "userABC")
    tmp_path_repo.save(payment)

    tmp_path_repo.update_status(payment_id, "REFUNDED")
    
    saved_payments = tmp_path_repo._load()
    assert len(saved_payments) == 1
    assert saved_payments[0]["payment_id"] == payment_id
    assert saved_payments[0]["status"] == "REFUNDED"
def test_payment_repo_get_by_user_no_payments(tmp_path_repo):
    payment1 = Payment(str(uuid.uuid4()), 100, "USD", "user1")
    payment2 = Payment(str(uuid.uuid4()), 200, "EUR", "user2")
    tmp_path_repo.save(payment1)
    tmp_path_repo.save(payment2)

    user_payments = tmp_path_repo.get_by_user("user3")
    assert user_payments == []
def test_fraud_checker_high_amount_is_fraud():
    fraud_checker = FraudChecker()
    payment = Payment(str(uuid.uuid4()), 100001, "USD", "userABC")
    assert fraud_checker.is_fraud(payment) is True
def test_fraud_checker_unsupported_currency_is_fraud():
    fraud_checker = FraudChecker()
    payment = Payment(str(uuid.uuid4()), 100, "JPY", "userABC") # JPY is not in ["USD", "INR", "EUR"]
    assert fraud_checker.is_fraud(payment) is True
def test_payment_gateway_charge_failure(monkeypatch):
    gateway = PaymentGateway()
    payment = Payment(str(uuid.uuid4()), 100, "USD", "userABC")

    # Mock random.randint to always return a value that makes charge fail (e.g., 9 or 10)
    monkeypatch.setattr('random.randint', lambda a, b: 9) # 9 < 8 is False
    assert gateway.charge(payment) is False
def test_payment_service_process_payment_invalid_amount_raises_error(payment_service):
    user_id = "user123"
    with pytest.raises(ValueError, match="Invalid amount"):
        payment_service.process_payment(user_id, 0, "USD")
    with pytest.raises(ValueError, match="Invalid amount"):
        payment_service.process_payment(user_id, -10, "USD")
def test_payment_service_process_payment_fraudulent_fails(payment_service, monkeypatch):
    user_id = "user456"
    amount = 150000 # Fraudulent amount
    currency = "USD"

    # Ensure no gateway interaction if fraud detected
    mock_gateway = MagicMock(spec=PaymentGateway)
    payment_service.gateway = mock_gateway

    result = payment_service.process_payment(user_id, amount, currency)
    assert result is False

    # Check payment status in repo
    payments_in_repo = payment_service.repo.get_by_user(user_id)
    assert len(payments_in_repo) == 1
    assert payments_in_repo[0]["status"] == "FAILED"
    mock_gateway.charge.assert_not_called() # Gateway should not be called if fraud detected
def test_payment_service_process_payment_insufficient_funds_fails(payment_service, monkeypatch):
    user_id = "user789"
    amount = 100
    currency = "USD"
    
    # Add some funds, but not enough for the payment
    payment_service.add_funds(user_id, 50)
    
    # Ensure no gateway interaction if debit fails
    mock_gateway = MagicMock(spec=PaymentGateway)
    payment_service.gateway = mock_gateway

    result = payment_service.process_payment(user_id, amount, currency)
    assert result is False

    # Check payment status in repo
    payments_in_repo = payment_service.repo.get_by_user(user_id)
    assert len(payments_in_repo) == 1
    assert payments_in_repo[0]["status"] == "FAILED"
    assert payment_service.user_balance(user_id) == 50 # Balance should be unchanged
    mock_gateway.charge.assert_not_called()
def test_payment_service_process_payment_gateway_failure_refunds_wallet(payment_service, monkeypatch):
    user_id = "userA"
    amount = 50
    currency = "USD"

    payment_service.add_funds(user_id, 100) # Initial balance
    
    # Mock PaymentGateway to always fail
    monkeypatch.setattr(payment_service.gateway, 'charge', lambda p: False)

    initial_balance = payment_service.user_balance(user_id)
    result = payment_service.process_payment(user_id, amount, currency)
    
    assert result is False
    # Wallet should be debited then credited back, so balance should revert to initial
    assert payment_service.user_balance(user_id) == initial_balance 

    # Check payment status in repo
    payments_in_repo = payment_service.repo.get_by_user(user_id)
    assert len(payments_in_repo) == 1
    assert payments_in_repo[0]["status"] == "FAILED"
def test_payment_service_refund_payment_adds_funds_and_updates_status(payment_service, monkeypatch):
    user_id = "userB"
    amount = 75
    currency = "USD"

    payment_service.add_funds(user_id, 100)
    
    # Ensure payment succeeds initially
    monkeypatch.setattr(payment_service.gateway, 'charge', lambda p: True)
    
    payment_service.process_payment(user_id, amount, currency)
    
    # Get the payment_id of the successful payment
    payments_in_repo = payment_service.repo.get_by_user(user_id)
    assert len(payments_in_repo) == 1
    successful_payment_id = payments_in_repo[0]["payment_id"]
    
    initial_balance_after_payment = payment_service.user_balance(user_id)
    assert initial_balance_after_payment == (100 - 75)

    payment_service.refund(successful_payment_id)
    
    # Wallet balance should be credited back
    assert payment_service.user_balance(user_id) == 100
    
    # Payment status should be REFUNDED in the repository
    refunded_payments_in_repo = payment_service.repo._load()
    assert len(refunded_payments_in_repo) == 1
    assert refunded_payments_in_repo[0]["payment_id"] == successful_payment_id
    assert refunded_payments_in_repo[0]["status"] == "REFUNDED"
def test_batch_payments_mixed_results(payment_service, monkeypatch):
    user_id = "userBatch"
    payment_service.add_funds(user_id, 200) # Initial funds

    # Make gateway deterministic: succeed for first, fail for second, then succeed
    gateway_results = iter([True, False, True]) # These will be used for (50, USD), (100, USD), (20, USD)
    monkeypatch.setattr(payment_service.gateway, 'charge', lambda p: next(gateway_results))

    payments_to_process = [
        (50, "USD"),      # Success (gateway True)
        (100, "USD"),     # Gateway failure (gateway False) -> wallet refunded, status FAILED
        (150000, "USD"),  # Fraudulent -> status FAILED (gateway not called)
        (20, "USD"),      # Success (gateway True)
        (-5, "USD")       # Invalid amount -> ValueError, results.append(False)
    ]

    results = batch_payments(payment_service, user_id, payments_to_process)

    # Expected results: [True, False, False, True, False]
    assert results == [True, False, False, True, False]

    # Check wallet balance:
    # Initial: 200
    # Process 50 (success): 200 - 50 = 150
    # Process 100 (gateway fail): 150 - 100 + 100 = 150 (balance unchanged)
    # Process 150000 (fraud): 150 (balance unchanged)
    # Process 20 (success): 150 - 20 = 130
    # Process -5 (invalid): 130 (balance unchanged)
    assert payment_service.user_balance(user_id) == 130

    # Check repository statuses
    repo_payments = payment_service.repo.get_by_user(user_id)
    # Should be 4 payments saved: (50), (100), (150000), (20)
    # Invalid amount (-5) does not create a Payment object and is not saved to repo.
    assert len(repo_payments) == 4
    
    statuses = sorted([p["status"] for p in repo_payments])
    # One SUCCESS (50), one FAILED (100, gateway), one FAILED (150000, fraud), one SUCCESS (20)
    assert statuses.count("SUCCESS") == 2
    assert statuses.count("FAILED") == 2
def test_export_report_multiple_users_and_transactions(payment_service, tmp_path, monkeypatch):
    report_path = tmp_path / "report.json"

    user1 = "userX"
    user2 = "userY"

    # Setup user1 transactions
    payment_service.add_funds(user1, 100)
    monkeypatch.setattr(payment_service.gateway, 'charge', lambda p: True) # Ensure payments succeed
    payment_service.process_payment(user1, 30, "USD") # Balance 70, 1 debit
    payment_service.process_payment(user1, 20, "EUR") # Balance 50, 2 debits

    # Setup user2 transactions
    payment_service.add_funds(user2, 500)
    payment_service.process_payment(user2, 150, "INR") # Balance 350, 1 debit
    payment_service.add_funds(user2, 50) # Balance 400, 1 credit

    export_report(payment_service, str(report_path))

    assert os.path.exists(report_path)
    with open(report_path, "r") as f:
        report_data = json.load(f)

    expected_report = {
        user1: {
            "balance": 50,
            "transactions": [
                ["CREDIT", 100],
                ["DEBIT", 30],
                ["DEBIT", 20]
            ]
        },
        user2: {
            "balance": 400,
            "transactions": [
                ["CREDIT", 500],
                ["DEBIT", 150],
                ["CREDIT", 50]
            ]
        }
    }
    
    # Sort transactions for deterministic comparison as order in report might vary by Python version/runtime
    for user_id in expected_report:
        report_data[user_id]["transactions"].sort()
        expected_report[user_id]["transactions"].sort()

    assert report_data == expected_report
