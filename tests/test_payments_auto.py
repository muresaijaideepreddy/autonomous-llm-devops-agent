

import sys
import os
import pytest
from datetime import datetime, timezone
import uuid
import json

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import *

@pytest.fixture
def temp_repo_path(tmp_path):
    repo_dir = tmp_path / "data"
    repo_dir.mkdir(exist_ok=True)
    return repo_dir / "payments.json"

@pytest.fixture
def empty_payment_repository(temp_repo_path):
    if os.path.exists(temp_repo_path):
        os.remove(temp_repo_path)
    return PaymentRepository(path=str(temp_repo_path))

def test_payment_creation_and_status_change():
    payment_id = str(uuid.uuid4())
    payment = Payment(payment_id, 100, "USD", "user1")
    assert payment.payment_id == payment_id
    assert payment.amount == 100
    assert payment.currency == "USD"
    assert payment.user_id == "user1"
    assert payment.status == "CREATED"
    assert isinstance(payment.created_at, datetime)
    assert payment.created_at.tzinfo == timezone.utc

    payment.mark_success()
    assert payment.status == "SUCCESS"
    payment.mark_failed()
    assert payment.status == "FAILED"

def test_wallet_credit():
    wallet = Wallet("user1")
    assert wallet.balance == 0
    wallet.credit(50)
    assert wallet.balance == 50
    assert wallet.transactions == [("CREDIT", 50)]

    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(0)
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(-10)
    assert wallet.balance == 50

def test_wallet_debit_success_and_fail():
    wallet = Wallet("user1")
    wallet.credit(100)
    assert wallet.balance == 100

    result = wallet.debit(30)
    assert result is True
    assert wallet.balance == 70
    assert wallet.transactions == [("CREDIT", 100), ("DEBIT", 30)]

    result = wallet.debit(100)
    assert result is False
    assert wallet.balance == 70
    assert len(wallet.transactions) == 2

def test_payment_repository_operations(empty_payment_repository):
    repo = empty_payment_repository
    user_id = "test_user_repo"
    payment1_id = str(uuid.uuid4())
    payment2_id = str(uuid.uuid4())

    payment1 = Payment(payment1_id, 100, "USD", user_id)
    payment2 = Payment(payment2_id, 200, "EUR", "another_user")
    
    repo.save(payment1)
    repo.save(payment2)

    user_payments = repo.get_by_user(user_id)
    assert len(user_payments) == 1
    assert user_payments[0]["payment_id"] == payment1_id
    assert user_payments[0]["status"] == "CREATED"

    repo.update_status(payment1_id, "SUCCESS")
    updated_payments = repo.get_by_user(user_id)
    assert updated_payments[0]["status"] == "SUCCESS"

    another_user_payments = repo.get_by_user("another_user")
    assert another_user_payments[0]["status"] == "CREATED"

def test_fraud_checker_is_fraud():
    checker = FraudChecker()
    payment_high_amount = Payment("id1", 100001, "USD", "user1")
    assert checker.is_fraud(payment_high_amount) is True

    payment_invalid_currency = Payment("id2", 500, "BTC", "user1")
    assert checker.is_fraud(payment_invalid_currency) is True

    payment_valid = Payment("id3", 500, "USD", "user1")
    assert checker.is_fraud(payment_valid) is False

    payment_valid_eur = Payment("id4", 90000, "EUR", "user2")
    assert checker.is_fraud(payment_valid_eur) is False

def test_payment_gateway_charge():
    gateway = PaymentGateway()
    payment = Payment("pid", 100, "USD", "user1")

    success_rand = lambda a, b: 5 
    assert gateway.charge(payment, rand=success_rand) is True

    failure_rand = lambda a, b: 9 
    assert gateway.charge(payment, rand=failure_rand) is False

def test_payment_service_add_funds():
    service = PaymentService()
    user_id = "test_user_add_funds"
    
    assert service.user_balance(user_id) == 0

    new_balance = service.add_funds(user_id, 100)
    assert new_balance == 100
    assert service.user_balance(user_id) == 100

    service.add_funds(user_id, 50)
    assert service.user_balance(user_id) == 150

def test_payment_service_process_payment_invalid_amount():
    service = PaymentService()
    user_id = "test_user_invalid_amount"
    with pytest.raises(ValueError, match="Invalid amount"):
        service.process_payment(user_id, -10, "USD")
    with pytest.raises(ValueError, match="Invalid amount"):
        service.process_payment(user_id, 0, "USD")

def test_payment_service_process_payment_fraudulent(empty_payment_repository):
    class MockFraudChecker(FraudChecker):
        def is_fraud(self, payment):
            return True
    
    service = PaymentService(repo=empty_payment_repository, fraud=MockFraudChecker())
    user_id = "user_fraud"
    service.add_funds(user_id, 100)

    result = service.process_payment(user_id, 50, "USD")
    assert result is False
    
    payments = empty_payment_repository.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    assert service.user_balance(user_id) == 100

def test_payment_service_process_payment_insufficient_funds(empty_payment_repository):
    service = PaymentService(repo=empty_payment_repository)
    user_id = "user_insufficient"
    service.add_funds(user_id, 50)

    result = service.process_payment(user_id, 100, "USD")
    assert result is False
    
    payments = empty_payment_repository.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    assert service.user_balance(user_id) == 50

def test_payment_service_process_payment_gateway_failure(empty_payment_repository):
    class MockGatewayFailure(PaymentGateway):
        def charge(self, payment, rand=None):
            return False
            
    service = PaymentService(repo=empty_payment_repository, gateway=MockGatewayFailure())
    user_id = "user_gateway_fail"
    service.add_funds(user_id, 200)
    
    initial_balance = service.user_balance(user_id)
    
    result = service.process_payment(user_id, 100, "USD")
    assert result is False
    
    assert service.user_balance(user_id) == initial_balance
    
    payments = empty_payment_repository.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"

def test_payment_service_process_payment_success(empty_payment_repository):
    class MockGatewaySuccess(PaymentGateway):
        def charge(self, payment, rand=None):
            return True

    service = PaymentService(repo=empty_payment_repository, gateway=MockGatewaySuccess())
    user_id = "user_success"
    service.add_funds(user_id, 200)
    
    initial_balance = service.user_balance(user_id)
    
    result = service.process_payment(user_id, 100, "USD")
    assert result is True
    
    assert service.user_balance(user_id) == initial_balance - 100
    
    payments = empty_payment_repository.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "SUCCESS"

def test_payment_service_refund_payment(empty_payment_repository):
    class MockGatewaySuccess(PaymentGateway):
        def charge(self, payment, rand=None):
            return True

    service = PaymentService(repo=empty_payment_repository, gateway=MockGatewaySuccess())
    user_id = "user_refund"
    service.add_funds(user_id, 200)
    
    service.process_payment(user_id, 100, "USD")
    assert service.user_balance(user_id) == 100
    
    payments = empty_payment_repository.get_by_user(user_id)
    assert len(payments) == 1
    payment_id_to_refund = payments[0]["payment_id"]
    
    service.refund(payment_id_to_refund)
    
    assert service.user_balance(user_id) == 200
    
    updated_payments = empty_payment_repository.get_by_user(user_id)
    assert updated_payments[0]["status"] == "REFUNDED"

def test_batch_payments_scenarios(empty_payment_repository):
    class MockGatewayDeterministic(PaymentGateway):
        def charge(self, payment, rand=None):
            return payment.amount == 100 and payment.currency == "USD"

    class MockFraudChecker(FraudChecker):
        def is_fraud(self, payment):
            return payment.currency == "EUR" or super().is_fraud(payment)
            
    service = PaymentService(repo=empty_payment_repository, gateway=MockGatewayDeterministic(), fraud=MockFraudChecker())
    user_id = "user_batch"
    service.add_funds(user_id, 300)

    payments_to_process = [(100, "USD"), (50, "USD"), (75, "EUR"), (-10, "USD")]

    results = batch_payments(service, user_id, payments_to_process)

    assert results == [True, False, False, False]
    
    assert service.user_balance(user_id) == 300 - 100

    user_payments = empty_payment_repository.get_by_user(user_id)
    assert len(user_payments) == 3
    
    payment_100_usd = next(p for p in user_payments if p["amount"] == 100 and p["currency"] == "USD")
    payment_50_usd = next(p for p in user_payments if p["amount"] == 50 and p["currency"] == "USD")
    payment_75_eur = next(p for p in user_payments if p["amount"] == 75 and p["currency"] == "EUR")

    assert payment_100_usd["status"] == "SUCCESS"
    assert payment_50_usd["status"] == "FAILED"
    assert payment_75_eur["status"] == "FAILED"

def test_export_report_content(tmp_path):
    report_dir = tmp_path / "data"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / "report.json"
    
    service = PaymentService()
    user1_id = "user_report_1"
    user2_id = "user_report_2"

    service.add_funds(user1_id, 100)
    service.add_funds(user2_id, 50)
    service.add_funds(user1_id, 20)

    export_report(service, str(report_path))

    assert report_path.exists()
    
    with open(report_path, "r") as f:
        report_data = json.load(f)

    expected_transactions_user1 = [["CREDIT", 100], ["CREDIT", 20]]
    expected_transactions_user2 = [["CREDIT", 50]]

    assert report_data[user1_id]["balance"] == 120
    assert report_data[user1_id]["transactions"] == expected_transactions_user1
    
    assert report_data[user2_id]["balance"] == 50
    assert report_data[user2_id]["transactions"] == expected_transactions_user2
    
    assert len(report_data) == 2