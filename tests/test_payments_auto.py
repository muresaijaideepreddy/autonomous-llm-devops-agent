import sys
import os
import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import *

import uuid
from unittest.mock import patch # For mocking random

@pytest.fixture
def temp_repo_path(tmp_path):
    repo_dir = tmp_path / "data"
    repo_dir.mkdir(exist_ok=True)
    return repo_dir / "payments.json"

@pytest.fixture
def clear_payment_repo(temp_repo_path):
    # Ensure the file is empty at the start of each test
    with open(temp_repo_path, "w") as f:
        json.dump([], f)
    yield


# --- Payment Class Tests ---
def test_payment_creation():
    payment_id = str(uuid.uuid4())
    amount = 100.50
    currency = "USD"
    user_id = "user123"
    payment = Payment(payment_id, amount, currency, user_id)

    assert payment.payment_id == payment_id
    assert payment.amount == amount
    assert payment.currency == currency
    assert payment.user_id == user_id
    assert payment.status == "CREATED"
    assert isinstance(payment.created_at, datetime)

def test_payment_status_update():
    payment = Payment(str(uuid.uuid4()), 100, "USD", "user1")
    assert payment.status == "CREATED"

    payment.mark_success()
    assert payment.status == "SUCCESS"

    payment.mark_failed()
    assert payment.status == "FAILED"


# --- Wallet Class Tests ---
def test_wallet_initialization():
    user_id = "user123"
    wallet = Wallet(user_id)
    assert wallet.user_id == user_id
    assert wallet.balance == 0
    assert wallet.transactions == []

def test_wallet_credit_adds_amount():
    wallet = Wallet("user1")
    initial_balance = wallet.balance
    amount_to_credit = 500

    # CORRECT BUSINESS BEHAVIOR: balance should increase by amount
    wallet.credit(amount_to_credit)
    assert wallet.balance == initial_balance + amount_to_credit
    assert ("CREDIT", amount_to_credit) in wallet.transactions

def test_wallet_debit_successful():
    wallet = Wallet("user1")
    wallet.balance = 1000  # Manually set initial balance for testing
    amount_to_debit = 300
    initial_balance = wallet.balance

    result = wallet.debit(amount_to_debit)
    assert result is True
    assert wallet.balance == initial_balance - amount_to_debit
    assert ("DEBIT", amount_to_debit) in wallet.transactions

def test_wallet_debit_insufficient_funds():
    wallet = Wallet("user1")
    wallet.balance = 200
    amount_to_debit = 300
    initial_balance = wallet.balance

    result = wallet.debit(amount_to_debit)
    assert result is False
    assert wallet.balance == initial_balance  # Balance should not change
    assert ("DEBIT", amount_to_debit) not in wallet.transactions


# --- PaymentRepository Tests ---
def test_payment_repo_init_and_save(temp_repo_path, clear_payment_repo):
    repo = PaymentRepository(path=temp_repo_path)
    payment_id = str(uuid.uuid4())
    payment = Payment(payment_id, 150, "EUR", "user_abc")
    repo.save(payment)

    loaded_data = repo._load()
    assert len(loaded_data) == 1
    assert loaded_data[0]["payment_id"] == payment_id
    assert loaded_data[0]["status"] == "CREATED"

def test_payment_repo_update_status(temp_repo_path, clear_payment_repo):
    repo = PaymentRepository(path=temp_repo_path)
    payment1_id = str(uuid.uuid4())
    payment2_id = str(uuid.uuid4())
    payment1 = Payment(payment1_id, 100, "USD", "userA")
    payment2 = Payment(payment2_id, 200, "INR", "userB")
    repo.save(payment1)
    repo.save(payment2)

    repo.update_status(payment1_id, "SUCCESS")
    loaded_data = repo._load()

    assert any(p["payment_id"] == payment1_id and p["status"] == "SUCCESS" for p in loaded_data)
    assert any(p["payment_id"] == payment2_id and p["status"] == "CREATED" for p in loaded_data)

def test_payment_repo_get_by_user(temp_repo_path, clear_payment_repo):
    repo = PaymentRepository(path=temp_repo_path)
    user1_id = "userX"
    user2_id = "userY"
    payment1 = Payment(str(uuid.uuid4()), 50, "USD", user1_id)
    payment2 = Payment(str(uuid.uuid4()), 75, "EUR", user2_id)
    payment3 = Payment(str(uuid.uuid4()), 120, "USD", user1_id)
    repo.save(payment1)
    repo.save(payment2)
    repo.save(payment3)

    user1_payments = repo.get_by_user(user1_id)
    assert len(user1_payments) == 2
    assert all(p["user_id"] == user1_id for p in user1_payments)
    assert {p["amount"] for p in user1_payments} == {50, 120}

    user2_payments = repo.get_by_user(user2_id)
    assert len(user2_payments) == 1
    assert all(p["user_id"] == user2_id for p in user2_payments)
    assert {p["amount"] for p in user2_payments} == {75}

    no_payments = repo.get_by_user("non_existent_user")
    assert len(no_payments) == 0


# --- FraudChecker Tests ---
def test_fraud_checker_is_fraud_high_amount():
    fraud_checker = FraudChecker()
    payment = Payment(str(uuid.uuid4()), 100001, "USD", "user1")
    assert fraud_checker.is_fraud(payment) is True

def test_fraud_checker_is_fraud_unsupported_currency():
    fraud_checker = FraudChecker()
    payment = Payment(str(uuid.uuid4()), 500, "GBP", "user1")
    assert fraud_checker.is_fraud(payment) is True

def test_fraud_checker_is_not_fraud():
    fraud_checker = FraudChecker()
    payment = Payment(str(uuid.uuid4()), 50000, "INR", "user1")
    assert fraud_checker.is_fraud(payment) is False


# --- PaymentService Tests ---
@pytest.fixture
def payment_service_with_mocks(temp_repo_path):
    service = PaymentService()
    service.repo = PaymentRepository(path=temp_repo_path)
    service.wallets = {} # Ensure wallets are fresh for each test
    return service

def test_payment_service_process_payment_negative_amount(payment_service_with_mocks):
    service = payment_service_with_mocks
    user_id = "user_neg"
    amount = -100
    currency = "USD"

    with pytest.raises(ValueError, match="Invalid amount"):
        service.process_payment(user_id, amount, currency)

    assert len(service.repo.get_by_user(user_id)) == 0

def test_payment_service_process_payment_fraud_check_fails(payment_service_with_mocks):
    service = payment_service_with_mocks
    user_id = "user_fraud"

    service.process_payment(user_id, 100001, "USD")
    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"

    service.process_payment(user_id, 500, "JPY")
    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 2
    assert all(p["status"] == "FAILED" for p in payments)

def test_payment_service_process_payment_insufficient_wallet_balance(payment_service_with_mocks):
    service = payment_service_with_mocks
    user_id = "user_low_funds"
    
    # Manually set wallet balance for predictable results, bypassing add_funds (which uses buggy credit)
    wallet = service._get_wallet(user_id)
    wallet.balance = 100 
    
    result = service.process_payment(user_id, 200, "USD")
    assert result is False
    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    assert service.user_balance(user_id) == 100 # Balance should not change

def test_payment_service_process_payment_successful_charge(payment_service_with_mocks, mocker):
    service = payment_service_with_mocks
    user_id = "user_success"
    amount = 100
    service._get_wallet(user_id).balance = 500 # Manually set initial balance

    mocker.patch.object(service.gateway, 'charge', return_value=True)

    initial_balance = service.user_balance(user_id)
    result = service.process_payment(user_id, amount, "USD")
    assert result is True
    assert service.user_balance(user_id) == initial_balance - amount

    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "SUCCESS"

def test_payment_service_process_payment_gateway_declined_and_refunded(payment_service_with_mocks, mocker):
    service = payment_service_with_mocks
    user_id = "user_declined"
    amount = 100
    service._get_wallet(user_id).balance = 500 # Manually set initial balance

    mocker.patch.object(service.gateway, 'charge', return_value=False)

    initial_balance = service.user_balance(user_id)
    result = service.process_payment(user_id, amount, "USD")
    assert result is False

    # EXPECTED BEHAVIOR: Wallet balance should be restored to initial state
    assert service.user_balance(user_id) == initial_balance

    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"

def test_payment_service_add_funds(payment_service_with_mocks):
    service = payment_service_with_mocks
    user_id = "user_add_funds"
    amount_to_add = 200

    initial_balance = service.user_balance(user_id) # Should be 0 initially
    new_balance = service.add_funds(user_id, amount_to_add)

    # EXPECTED BEHAVIOR: Balance should increase by amount_to_add
    assert new_balance == initial_balance + amount_to_add
    assert service.user_balance(user_id) == initial_balance + amount_to_add

def test_payment_service_user_balance(payment_service_with_mocks):
    service = payment_service_with_mocks
    user_id = "user_balance"
    wallet = service._get_wallet(user_id)
    wallet.balance = 123.45

    balance = service.user_balance(user_id)
    assert balance == 123.45

def test_payment_service_refund_payment(payment_service_with_mocks, mocker):
    service = payment_service_with_mocks
    user_id = "user_refund"
    original_amount = 150
    wallet = service._get_wallet(user_id)
    wallet.balance = 1000 # Manually set initial balance
    initial_wallet_balance = wallet.balance

    # Simulate a successful payment first
    mocker.patch.object(service.gateway, 'charge', return_value=True)
    service.process_payment(user_id, original_amount, "USD")
    
    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 1
    successful_payment_id = payments[0]["payment_id"]
    assert payments[0]["status"] == "SUCCESS"
    assert service.user_balance(user_id) == initial_wallet_balance - original_amount

    # Perform refund
    service.refund(successful_payment_id)

    # EXPECTED BEHAVIOR: Payment status should be "REFUNDED"
    updated_payments = service.repo._load()
    refunded_payment = next((p for p in updated_payments if p["payment_id"] == successful_payment_id), None)
    assert refunded_payment is not None
    assert refunded_payment["status"] == "REFUNDED"

    # EXPECTED BEHAVIOR: Wallet balance should be restored to initial balance
    assert service.user_balance(user_id) == initial_wallet_balance