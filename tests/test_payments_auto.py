import sys
import os
import pytest
from datetime import datetime
import uuid
import json
from unittest.mock import MagicMock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import *

@pytest.fixture
def clean_payment_repo(tmp_path):
    """Fixture to provide a PaymentRepository with a temporary, clean file."""
    repo_path = tmp_path / "payments.json"
    repo = PaymentRepository(str(repo_path))
    # Ensure the file is empty at the start of each test
    with open(repo_path, "w") as f:
        json.dump([], f)
    return repo

@pytest.fixture
def payment_service_with_mocked_repo(tmp_path):
    """Fixture to provide a PaymentService with a mocked PaymentRepository path."""
    repo_path = tmp_path / "payments.json"
    service = PaymentService()
    service.repo = PaymentRepository(str(repo_path))
    # Ensure the file is empty for the service's repo
    with open(repo_path, "w") as f:
        json.dump([], f)
    return service

# Payment Class Tests
def test_payment_init_and_initial_status():
    payment_id = str(uuid.uuid4())
    amount = 100.0
    currency = "USD"
    user_id = "user123"
    payment = Payment(payment_id, amount, currency, user_id)

    assert payment.payment_id == payment_id
    assert payment.amount == amount
    assert payment.currency == currency
    assert payment.user_id == user_id
    assert payment.status == "CREATED"
    assert isinstance(payment.created_at, datetime)

def test_payment_status_transitions():
    payment = Payment(str(uuid.uuid4()), 50.0, "EUR", "user456")
    
    payment.mark_success()
    assert payment.status == "SUCCESS"

    payment.mark_failed()
    assert payment.status == "FAILED"

# Wallet Class Tests
def test_wallet_init_balance_and_transactions():
    user_id = "wallet_user"
    wallet = Wallet(user_id)

    assert wallet.user_id == user_id
    assert wallet.balance == 0
    assert wallet.transactions == []

def test_wallet_credit_valid_amount():
    wallet = Wallet("user_credit")
    wallet.credit(100)
    assert wallet.balance == 100
    assert ("CREDIT", 100) in wallet.transactions

    wallet.credit(50.50)
    assert wallet.balance == 150.50
    assert ("CREDIT", 50.50) in wallet.transactions

def test_wallet_credit_invalid_amount_raises_error():
    wallet = Wallet("user_credit_invalid")
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(0)
    assert wallet.balance == 0
    assert not wallet.transactions
    
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(-10)
    assert wallet.balance == 0
    assert not wallet.transactions

def test_wallet_debit_sufficient_funds():
    wallet = Wallet("user_debit")
    wallet.credit(200)
    
    assert wallet.debit(50) is True
    assert wallet.balance == 150
    assert ("DEBIT", 50) in wallet.transactions

def test_wallet_debit_insufficient_funds():
    wallet = Wallet("user_debit_insufficient")
    wallet.credit(50)
    
    assert wallet.debit(100) is False
    assert wallet.balance == 50 # Balance should not change
    assert ("DEBIT", 100) not in wallet.transactions # No transaction should be recorded

# PaymentRepository Tests
def test_repository_save_and_retrieve_by_user(clean_payment_repo):
    repo = clean_payment_repo
    user_id = "repo_user_1"
    payment1 = Payment("p1", 100, "USD", user_id)
    payment2 = Payment("p2", 200, "INR", user_id)
    payment3 = Payment("p3", 50, "EUR", "repo_user_2")

    repo.save(payment1)
    repo.save(payment2)
    repo.save(payment3)

    user_payments = repo.get_by_user(user_id)
    assert len(user_payments) == 2
    assert any(p["payment_id"] == "p1" for p in user_payments)
    assert any(p["payment_id"] == "p2" for p in user_payments)
    assert all(p["user_id"] == user_id for p in user_payments)

def test_repository_update_status(clean_payment_repo):
    repo = clean_payment_repo
    payment = Payment("p_update", 100, "USD", "user_update")
    repo.save(payment)
    
    repo.update_status("p_update", "SUCCESS")
    
    updated_payments = repo.get_by_user("user_update")
    assert len(updated_payments) == 1
    assert updated_payments[0]["status"] == "SUCCESS"

# FraudChecker Tests
def test_fraud_checker_is_fraud_conditions():
    fraud_checker = FraudChecker()
    
    # High amount
    payment_high_amount = Payment("f1", 100001, "USD", "fraud_user")
    assert fraud_checker.is_fraud(payment_high_amount) is True

    # Invalid currency
    payment_invalid_currency = Payment("f2", 500, "GBP", "fraud_user")
    assert fraud_checker.is_fraud(payment_invalid_currency) is True

    # Both conditions (should be True if any is true)
    payment_both_fraud = Payment("f3", 100001, "GBP", "fraud_user")
    assert fraud_checker.is_fraud(payment_both_fraud) is True

def test_fraud_checker_is_not_fraud_condition():
    fraud_checker = FraudChecker()
    payment_valid = Payment("v1", 99999, "INR", "valid_user")
    assert fraud_checker.is_fraud(payment_valid) is False

# PaymentService Tests
def test_payment_service_process_payment_raises_on_negative_amount(payment_service_with_mocked_repo):
    service = payment_service_with_mocked_repo
    with pytest.raises(ValueError, match="Invalid amount"):
        service.process_payment("u1", -100, "USD")

def test_payment_service_process_payment_handles_fraud(payment_service_with_mocked_repo):
    service = payment_service_with_mocked_repo
    service.fraud.is_fraud = MagicMock(return_value=True) # Mock fraud detection
    
    result = service.process_payment("u1", 500, "USD")
    
    assert result is False
    service.fraud.is_fraud.assert_called_once()
    
    payments = service.repo.get_by_user("u1")
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"

def test_payment_service_process_payment_handles_insufficient_balance(payment_service_with_mocked_repo):
    service = payment_service_with_mocked_repo
    service.add_funds("u2", 100) # Add some funds
    
    result = service.process_payment("u2", 200, "USD") # Try to process more than balance
    
    assert result is False
    assert service.user_balance("u2") == 100 # Balance should remain unchanged
    
    payments = service.repo.get_by_user("u2")
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"

def test_payment_service_process_payment_successful_charge(payment_service_with_mocked_repo, monkeypatch):
    service = payment_service_with_mocked_repo
    service.add_funds("u3", 500)

    # Mock PaymentGateway.charge to always return True
    monkeypatch.setattr(service.gateway, 'charge', lambda payment: True)
    
    result = service.process_payment("u3", 150, "USD")
    
    assert result is True
    assert service.user_balance("u3") == 350 # 500 - 150
    
    payments = service.repo.get_by_user("u3")
    assert len(payments) == 1
    assert payments[0]["status"] == "SUCCESS"
    assert payments[0]["amount"] == 150

def test_payment_service_process_payment_gateway_charge_failure(payment_service_with_mocked_repo, monkeypatch):
    service = payment_service_with_mocked_repo
    service.add_funds("u4", 500)

    # Mock PaymentGateway.charge to always return False
    monkeypatch.setattr(service.gateway, 'charge', lambda payment: False)
    
    result = service.process_payment("u4", 150, "USD")
    
    assert result is False
    assert service.user_balance("u4") == 500 # Wallet should be credited back
    
    payments = service.repo.get_by_user("u4")
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    assert payments[0]["amount"] == 150

def test_payment_service_add_funds_and_user_balance(payment_service_with_mocked_repo):
    service = payment_service_with_mocked_repo
    user_id = "fund_user"
    
    balance_after_first_add = service.add_funds(user_id, 250)
    assert balance_after_first_add == 250
    assert service.user_balance(user_id) == 250

    balance_after_second_add = service.add_funds(user_id, 75)
    assert balance_after_second_add == 325
    assert service.user_balance(user_id) == 325

def test_payment_service_refund_existing_payment(payment_service_with_mocked_repo, monkeypatch):
    service = payment_service_with_mocked_repo
    user_id = "refund_user"
    initial_funds = 500
    payment_amount = 100
    
    service.add_funds(user_id, initial_funds)
    monkeypatch.setattr(service.gateway, 'charge', lambda payment: True) # Ensure charge is successful
    
    service.process_payment(user_id, payment_amount, "USD")
    
    # Get the payment_id from the saved payment
    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 1
    payment_id_to_refund = payments[0]["payment_id"]
    
    assert service.user_balance(user_id) == initial_funds - payment_amount
    assert payments[0]["status"] == "SUCCESS"

    service.refund(payment_id_to_refund)
    
    # Check wallet balance after refund
    assert service.user_balance(user_id) == initial_funds # Should be back to initial funds
    
    # Check payment status in repository after refund
    refunded_payments = service.repo.get_by_user(user_id)
    assert len(refunded_payments) == 1
    assert refunded_payments[0]["status"] == "REFUNDED"

# Batch Payments Test
def test_batch_payments_functionality(payment_service_with_mocked_repo, monkeypatch):
    service = payment_service_with_mocked_repo
    user_id = "batch_user"
    service.add_funds(user_id, 1000)

    # Mock gateway for predictable results
    gateway_calls = [True, False, True, True] # Success, Failure, Success, Success
    mock_charge = MagicMock(side_effect=gateway_calls)
    monkeypatch.setattr(service.gateway, 'charge', mock_charge)
    
    # Process payments:
    # 1. 100 USD (Success)
    # 2. 200 EUR (Gateway Fail, credited back)
    # 3. 50 USD (Success)
    # 4. 400 INR (Success)
    # 5. 100001 USD (Fraud) - This will be caught by fraud checker first, gateway won't be called.
    # 6. -50 USD (Invalid amount)
    payments_to_process = [
        (100, "USD"),
        (200, "EUR"),
        (50, "USD"),
        (400, "INR"),
        (100001, "USD"), # Fraud
        (-50, "USD"),   # Invalid amount
    ]

    results = batch_payments(service, user_id, payments_to_process)

    assert results == [True, False, True, True, False, False]
    
    # Expected final balance: 1000 - 100 (1) + 200 (2 credited back) - 50 (3) - 400 (4) = 650
    assert service.user_balance(user_id) == 450 # 1000 - 100 - 50 - 400 = 450. Payment 2 was debited then credited back.
    
    # Verify payments in repo
    all_payments = service.repo.get_by_user(user_id)
    assert len(all_payments) == 6 # All payments should be recorded
    success_payments = [p for p in all_payments if p["status"] == "SUCCESS"]
    failed_payments = [p for p in all_payments if p["status"] == "FAILED"]
    
    assert len(success_payments) == 3
    assert len(failed_payments) == 3 # Gateway fail, Fraud, Invalid Amount

def test_export_report_generates_correct_json(payment_service_with_mocked_repo, tmp_path):
    service = payment_service_with_mocked_repo
    user1 = "u_rep1"
    user2 = "u_rep2"
    
    service.add_funds(user1, 100)
    service.process_payment(user1, 20, "USD") # Assume success for simplicity, gateway not mocked here
    
    service.add_funds(user2, 50)
    
    report_path = tmp_path / "report.json"
    export_report(service, str(report_path))
    
    with open(report_path, "r") as f:
        report_data = json.load(f)
    
    assert user1 in report_data
    assert user2 in report_data
    
    assert report_data[user1]["balance"] == 80
    assert report_data[user1]["transactions"] == [["CREDIT", 100], ["DEBIT", 20]]
    
    assert report_data[user2]["balance"] == 50
    assert report_data[user2]["transactions"] == [["CREDIT", 50]]

def test_payment_service_get_wallet_creates_if_not_exists(payment_service_with_mocked_repo):
    service = payment_service_with_mocked_repo
    user_id = "new_wallet_user"

    assert user_id not in service.wallets
    wallet = service._get_wallet(user_id)
    assert user_id in service.wallets
    assert isinstance(wallet, Wallet)
    assert wallet.user_id == user_id
    assert service._get_wallet(user_id) is wallet # Ensure same instance is returned

def test_payment_service_get_wallet_returns_existing_wallet(payment_service_with_mocked_repo):
    service = payment_service_with_mocked_repo
    user_id = "existing_wallet_user"
    existing_wallet = Wallet(user_id)
    service.wallets[user_id] = existing_wallet

    retrieved_wallet = service._get_wallet(user_id)
    assert retrieved_wallet is existing_wallet
    assert service.wallets[user_id] is existing_wallet