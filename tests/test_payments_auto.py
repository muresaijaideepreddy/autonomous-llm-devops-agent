import sys
import os
import pytest
from datetime import datetime
import uuid
import random
import json
from unittest.mock import patch, MagicMock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import Payment, Wallet, PaymentRepository, FraudChecker, PaymentGateway, PaymentService
from payments import batch_payments, generate_dummy_data, export_report


# Fixture for PaymentRepository tests to use a temporary file path
@pytest.fixture
def repo_path(tmp_path):
    path = tmp_path / "test_payments.json"
    # Ensure an empty file exists for a fresh start, as PaymentRepository expects it or creates it
    if not path.exists():
        path.write_text("[]")
    yield str(path)
    # Cleanup after test if needed, though tmp_path handles directory cleanup


# Fixture for PaymentService tests to use mocked dependencies and a controlled repo
@pytest.fixture
def payment_service(mocker, tmp_path):
    # Create a real PaymentRepository instance with a temporary file path
    service_repo_path = tmp_path / "service_payments.json"
    mock_repo_instance = PaymentRepository(str(service_repo_path))
    # Ensure the repo file is empty for the start of each test
    with open(service_repo_path, "w") as f:
        json.dump([], f)

    # Mock the PaymentRepository class so PaymentService.__init__ gets our controlled instance
    mocker.patch('payments.PaymentRepository', return_value=mock_repo_instance)
    
    # Mock the PaymentGateway and FraudChecker classes
    mock_gateway_class = mocker.patch('payments.PaymentGateway')
    mock_fraud_checker_class = mocker.patch('payments.FraudChecker')

    # Instantiate PaymentService. Its __init__ will use the mocked classes.
    service = PaymentService()

    # Access the actual mock instances that PaymentService now holds
    service.gateway = mock_gateway_class.return_value 
    service.fraud = mock_fraud_checker_class.return_value 
    service.repo = mock_repo_instance # Ensure the repo is our real instance from the fixture

    service.wallets = {} # Ensure wallets are fresh for each test

    # Set default mock behaviors for gateway and fraud checker
    service.gateway.charge.return_value = True # Default to success for gateway
    service.fraud.is_fraud.return_value = False # Default to not fraud

    return service


# --- Payment Class Tests ---
def test_payment_init():
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

def test_payment_status_changes():
    payment = Payment("id", 100, "USD", "user")
    
    payment.mark_success()
    assert payment.status == "SUCCESS"
    
    payment.mark_failed()
    assert payment.status == "FAILED"

# --- Wallet Class Tests ---
def test_wallet_init():
    user_id = "user1"
    wallet = Wallet(user_id)
    assert wallet.user_id == user_id
    assert wallet.balance == 0
    assert wallet.transactions == []

def test_wallet_credit_valid_amount():
    wallet = Wallet("user1")
    wallet.credit(100)
    assert wallet.balance == 100
    assert wallet.transactions == [("CREDIT", 100)]
    wallet.credit(50.5)
    assert wallet.balance == 150.5
    assert wallet.transactions == [("CREDIT", 100), ("CREDIT", 50.5)]

def test_wallet_credit_invalid_amount_raises_error():
    wallet = Wallet("user1")
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(0)
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(-10)
    assert wallet.balance == 0
    assert wallet.transactions == []

def test_wallet_debit_behavior():
    wallet = Wallet("user1")
    wallet.credit(200)

    # Test sufficient funds
    result_sufficient = wallet.debit(150)
    assert result_sufficient is True
    assert wallet.balance == 50
    assert wallet.transactions == [("CREDIT", 200), ("DEBIT", 150)]

    # Test insufficient funds
    result_insufficient = wallet.debit(100)
    assert result_insufficient is False
    assert wallet.balance == 50 # Balance should not change
    assert wallet.transactions == [("CREDIT", 200), ("DEBIT", 150)] # No new debit transaction

# --- FraudChecker Tests ---
def test_fraud_checker_not_fraudulent():
    checker = FraudChecker()
    payment = Payment("id", 1000, "USD", "user")
    assert checker.is_fraud(payment) is False

def test_fraud_checker_fraudulent_cases():
    checker = FraudChecker()
    # Case 1: Large amount
    payment_large_amount = Payment("id1", 100001, "USD", "user") # Amount > 100000
    assert checker.is_fraud(payment_large_amount) is True

    # Case 2: Invalid currency
    payment_invalid_currency = Payment("id2", 500, "GBP", "user") # Not USD, INR, EUR
    assert checker.is_fraud(payment_invalid_currency) is True

# --- PaymentRepository Tests ---
def test_payment_repository_init_creates_file(repo_path):
    os.remove(repo_path) # Remove it to test creation
    repo = PaymentRepository(repo_path)
    assert os.path.exists(repo_path)
    with open(repo_path, "r") as f:
        assert json.load(f) == [] # Should be initialized as empty list

def test_payment_repository_save_and_retrieve(repo_path):
    repo = PaymentRepository(repo_path)
    user_id = "test_user_save"
    payment1 = Payment("p1", 100, "USD", user_id)
    payment2 = Payment("p2", 200, "INR", "another_user")
    
    repo.save(payment1)
    repo.save(payment2)
    
    loaded_payments = repo._load()
    assert len(loaded_payments) == 2
    
    user_payments = repo.get_by_user(user_id)
    assert len(user_payments) == 1
    assert user_payments[0]["payment_id"] == "p1"
    assert user_payments[0]["amount"] == 100
    assert user_payments[0]["user_id"] == user_id
    assert user_payments[0]["status"] == "CREATED"

def test_payment_repository_update_status(repo_path):
    repo = PaymentRepository(repo_path)
    payment_id = "p_update"
    payment = Payment(payment_id, 50, "USD", "user_update")
    repo.save(payment)

    repo.update_status(payment_id, "SUCCESS")

    loaded_payments = repo._load()
    assert loaded_payments[0]["payment_id"] == payment_id
    assert loaded_payments[0]["status"] == "SUCCESS"

# --- PaymentService Tests ---
def test_payment_service_process_payment_negative_amount_raises_error(payment_service):
    user_id = "user_negative_amount"
    with pytest.raises(ValueError, match="Invalid amount"):
        payment_service.process_payment(user_id, -100, "USD")
    
    assert len(payment_service.repo.get_by_user(user_id)) == 0

def test_payment_service_process_payment_fraudulent_declined(payment_service):
    user_id = "user_fraud"
    amount = 500
    currency = "USD"
    
    payment_service.fraud.is_fraud.return_value = True # Simulate fraud
    
    result = payment_service.process_payment(user_id, amount, currency)
    assert result is False
    
    payments = payment_service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    assert payment_service.user_balance(user_id) == 0

def test_payment_service_process_payment_insufficient_funds_declined(payment_service):
    user_id = "user_insufficient"
    amount = 200
    currency = "USD"

    payment_service.add_funds(user_id, 100) # Wallet balance is 100

    result = payment_service.process_payment(user_id, amount, currency)
    assert result is False

    payments = payment_service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    assert payment_service.user_balance(user_id) == 100 # Balance should be restored if debit failed

def test_payment_service_process_payment_gateway_declined_refunds_wallet(payment_service):
    user_id = "user_gateway_fail"
    amount = 100
    currency = "USD"

    payment_service.add_funds(user_id, 200) # Initial balance
    payment_service.gateway.charge.return_value = False # Simulate gateway failure

    result = payment_service.process_payment(user_id, amount, currency)
    assert result is False

    payments = payment_service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    assert payment_service.user_balance(user_id) == 200 # Balance should be debited and then credited back

def test_payment_service_process_payment_successful(payment_service):
    user_id = "user_success"
    amount = 100
    currency = "USD"

    payment_service.add_funds(user_id, 200) # Initial balance
    payment_service.gateway.charge.return_value = True # Simulate gateway success

    result = payment_service.process_payment(user_id, amount, currency)
    assert result is True

    payments = payment_service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "SUCCESS"
    assert payment_service.user_balance(user_id) == 100 # Balance should be debited

def test_payment_service_funds_management(payment_service):
    user_id = "user_funds_manage"
    
    assert payment_service.user_balance(user_id) == 0

    new_balance = payment_service.add_funds(user_id, 500)
    assert new_balance == 500
    assert payment_service.user_balance(user_id) == 500

    new_balance = payment_service.add_funds(user_id, 250)
    assert new_balance == 750
    assert payment_service.user_balance(user_id) == 750
    
    assert payment_service.user_balance("non_existent_user") == 0


def test_payment_service_refund_updates_status_and_credits_wallet(payment_service):
    user_id = "user_refund"
    payment_id = str(uuid.uuid4())
    amount = 150
    currency = "USD"

    payment_service.add_funds(user_id, 200) # Initial balance
    payment_service.gateway.charge.return_value = True

    # Manually create and save a payment to simulate it being in the repo
    payment = Payment(payment_id, amount, currency, user_id)
    payment.mark_success() # Assume it was successful
    payment_service.repo.save(payment)
    
    # Manually debit wallet to reflect the 'successful' payment for this specific test
    wallet = payment_service._get_wallet(user_id)
    wallet.debit(amount)
    assert wallet.balance == 50 # 200 - 150

    payment_service.refund(payment_id)

    assert payment_service.user_balance(user_id) == 200 # Original 200 (150 debited, 150 credited back)

    payments_in_repo = payment_service.repo.get_by_user(user_id)
    assert len(payments_in_repo) == 1
    assert payments_in_repo[0]["payment_id"] == payment_id
    assert payments_in_repo[0]["status"] == "REFUNDED"


# --- Utility Functions Tests ---
def test_batch_payments_mixed_results(payment_service, mocker):
    user_id = "user_batch"
    payments_data = [(10, "USD"), (20, "EUR"), (30, "INR")]

    mock_process = mocker.patch.object(payment_service, 'process_payment', side_effect=[True, False, True])
    
    payment_service.add_funds(user_id, 1000)

    results = batch_payments(payment_service, user_id, payments_data)
    
    assert results == [True, False, True]
    assert mock_process.call_count == 3
    mock_process.assert_has_calls([
        mocker.call(user_id, 10, "USD"),
        mocker.call(user_id, 20, "EUR"),
        mocker.call(user_id, 30, "INR")
    ])

def test_export_report_content(payment_service, tmp_path):
    report_path = tmp_path / "test_report.json"
    user_id1 = "user_report_1"
    user_id2 = "user_report_2"

    payment_service.add_funds(user_id1, 100)
    payment_service.add_funds(user_id2, 200)

    payment_service.wallets[user_id1].debit(50)
    payment_service.wallets[user_id2].credit(30)

    export_report(payment_service, str(report_path))

    assert report_path.exists()
    with open(report_path, "r") as f:
        report_data = json.load(f)

    expected_report = {
        user_id1: {
            "balance": 50,
            "transactions": [["CREDIT", 100], ["DEBIT", 50]]
        },
        user_id2: {
            "balance": 230,
            "transactions": [["CREDIT", 200], ["CREDIT", 30]]
        }
    }
    
    assert report_data == expected_report