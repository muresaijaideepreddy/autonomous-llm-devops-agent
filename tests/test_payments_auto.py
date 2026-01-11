import sys
import os
import pytest
from datetime import datetime
import uuid
import random
import json
import os

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import *


def test_payment_init():
    payment_id = str(uuid.uuid4())
    p = Payment(payment_id, 100, "USD", "user123")
    assert p.payment_id == payment_id
    assert p.amount == 100
    assert p.currency == "USD"
    assert p.user_id == "user123"
    assert p.status == "CREATED"
    assert isinstance(p.created_at, datetime)


def test_payment_status_changes():
    p = Payment("id1", 100, "USD", "user1")
    p.mark_success()
    assert p.status == "SUCCESS"
    p.mark_failed()
    assert p.status == "FAILED"


def test_wallet_init():
    w = Wallet("user123")
    assert w.user_id == "user123"
    assert w.balance == 0
    assert w.transactions == []


def test_wallet_credit():
    w = Wallet("user1")
    w.credit(50)
    assert w.balance == 50
    assert w.transactions == [("CREDIT", 50)]
    w.credit(20)
    assert w.balance == 70
    assert w.transactions == [("CREDIT", 50), ("CREDIT", 20)]


def test_wallet_debit_success():
    w = Wallet("user1")
    w.credit(100)
    result = w.debit(30)
    assert result is True
    assert w.balance == 70
    assert w.transactions == [("CREDIT", 100), ("DEBIT", 30)]


def test_wallet_debit_insufficient_funds():
    w = Wallet("user1")
    w.credit(50)
    result = w.debit(100)
    assert result is False
    assert w.balance == 50
    assert w.transactions == [("CREDIT", 50)]


def test_payment_repository_init_empty_file(tmp_path):
    repo_path = tmp_path / "test_payments.json"
    repo = PaymentRepository(str(repo_path))
    assert repo_path.exists()
    assert json.loads(repo_path.read_text()) == []


def test_payment_repository_save_and_load(tmp_path):
    repo_path = tmp_path / "test_payments.json"
    repo = PaymentRepository(str(repo_path))
    p = Payment("p1", 100, "USD", "u1")
    repo.save(p)
    loaded_data = repo._load()
    assert len(loaded_data) == 1
    assert loaded_data[0]["payment_id"] == "p1"
    assert loaded_data[0]["status"] == "CREATED"


def test_payment_repository_update_status(tmp_path):
    repo_path = tmp_path / "test_payments.json"
    repo = PaymentRepository(str(repo_path))
    p = Payment("p1", 100, "USD", "u1")
    repo.save(p)
    repo.update_status("p1", "SUCCESS")
    loaded_data = repo._load()
    assert loaded_data[0]["status"] == "SUCCESS"


def test_payment_repository_get_by_user(tmp_path):
    repo_path = tmp_path / "test_payments.json"
    repo = PaymentRepository(str(repo_path))
    repo.save(Payment("p1", 100, "USD", "u1"))
    repo.save(Payment("p2", 200, "INR", "u2"))
    repo.save(Payment("p3", 300, "EUR", "u1"))

    user1_payments = repo.get_by_user("u1")
    assert len(user1_payments) == 2
    assert {p["payment_id"] for p in user1_payments} == {"p1", "p3"}
    user2_payments = repo.get_by_user("u2")
    assert len(user2_payments) == 1
    assert user2_payments[0]["payment_id"] == "p2"
    user3_payments = repo.get_by_user("u3")
    assert len(user3_payments) == 0


def test_fraud_checker_is_fraud_conditions():
    checker = FraudChecker()
    # High amount fraud
    assert checker.is_fraud(Payment("id", 100001, "USD", "user")) is True
    # Invalid currency fraud
    assert checker.is_fraud(Payment("id", 50, "GBP", "user")) is True
    # Not fraud
    assert checker.is_fraud(Payment("id", 100000, "USD", "user")) is False
    assert checker.is_fraud(Payment("id", 100, "INR", "user")) is False


def test_payment_service_init():
    service = PaymentService()
    assert isinstance(service.repo, PaymentRepository)
    assert isinstance(service.gateway, PaymentGateway)
    assert isinstance(service.fraud, FraudChecker)
    assert service.wallets == {}


def test_payment_service_add_funds_and_user_balance():
    service = PaymentService()
    service.add_funds("user1", 100)
    assert service.user_balance("user1") == 100
    service.add_funds("user1", 50)
    assert service.user_balance("user1") == 150
    assert service.user_balance("user_new") == 0


def test_payment_service_process_payment_invalid_amount(mocker):
    service = PaymentService()
    with pytest.raises(ValueError, match="Invalid amount"):
        service.process_payment("user1", -10, "USD")


def test_payment_service_process_payment_fraudulent(mocker, tmp_path):
    mocker.patch.object(FraudChecker, 'is_fraud', return_value=True)
    mocker.patch.object(PaymentGateway, 'charge', return_value=True) # Should not be called
    
    repo_path = tmp_path / "test_payments.json"
    service = PaymentService()
    service.repo = PaymentRepository(str(repo_path)) # Override repo for testing file operations

    service.add_funds("user1", 100)
    result = service.process_payment("user1", 50, "USD")
    assert result is False
    assert service.user_balance("user1") == 100 # Funds not debited
    payments = service.repo.get_by_user("user1")
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"


def test_payment_service_process_payment_insufficient_funds(mocker, tmp_path):
    mocker.patch.object(FraudChecker, 'is_fraud', return_value=False)
    mocker.patch.object(PaymentGateway, 'charge', return_value=True) # Should not be called
    
    repo_path = tmp_path / "test_payments.json"
    service = PaymentService()
    service.repo = PaymentRepository(str(repo_path))

    service.add_funds("user1", 50)
    result = service.process_payment("user1", 100, "USD")
    assert result is False
    assert service.user_balance("user1") == 50 # Funds not debited
    payments = service.repo.get_by_user("user1")
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"


def test_payment_service_process_payment_gateway_failure(mocker, tmp_path):
    mocker.patch.object(FraudChecker, 'is_fraud', return_value=False)
    mocker.patch.object(PaymentGateway, 'charge', return_value=False) # Gateway fails
    
    repo_path = tmp_path / "test_payments.json"
    service = PaymentService()
    service.repo = PaymentRepository(str(repo_path))

    service.add_funds("user1", 100)
    result = service.process_payment("user1", 50, "USD")
    assert result is False
    assert service.user_balance("user1") == 100 # Funds debited then credited back
    payments = service.repo.get_by_user("user1")
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"


def test_payment_service_process_payment_success(mocker, tmp_path):
    mocker.patch.object(FraudChecker, 'is_fraud', return_value=False)
    mocker.patch.object(PaymentGateway, 'charge', return_value=True) # Gateway succeeds
    
    repo_path = tmp_path / "test_payments.json"
    service = PaymentService()
    service.repo = PaymentRepository(str(repo_path))

    service.add_funds("user1", 100)
    result = service.process_payment("user1", 50, "USD")
    assert result is True
    assert service.user_balance("user1") == 50 # Funds debited
    payments = service.repo.get_by_user("user1")
    assert len(payments) == 1
    assert payments[0]["status"] == "SUCCESS"


def test_payment_service_refund(tmp_path):
    repo_path = tmp_path / "test_payments.json"
    service = PaymentService()
    service.repo = PaymentRepository(str(repo_path))

    user_id = "user1"
    amount = 50
    service.add_funds(user_id, 100) # Initial balance: 100
    
    # Manually create a successful payment in the repo for refunding
    payment_id = str(uuid.uuid4())
    p = Payment(payment_id, amount, "USD", user_id)
    p.mark_success()
    service.repo.save(p)

    # Simulate wallet debit for this payment
    wallet = service._get_wallet(user_id)
    wallet.debit(amount)
    assert service.user_balance(user_id) == 50

    service.refund(payment_id)
    assert service.user_balance(user_id) == 100 # Funds credited back
    
    # Verify status in repo
    payments_in_repo = service.repo.get_by_user(user_id)
    refunded_payment = next((p for p in payments_in_repo if p["payment_id"] == payment_id), None)
    assert refunded_payment is not None
    assert refunded_payment["status"] == "REFUNDED"


def test_batch_payments(mocker):
    mocker.patch.object(FraudChecker, 'is_fraud', return_value=False)
    mocker.patch.object(PaymentGateway, 'charge', side_effect=[True, False, True]) # Mock gateway behavior

    service = PaymentService()
    service.add_funds("user_batch", 200)

    payments_to_process = [(50, "USD"), (70, "INR"), (30, "EUR")]
    results = batch_payments(service, "user_batch", payments_to_process)

    assert results == [True, False, True] # 1st success, 2nd gateway fail, 3rd success
    assert service.user_balance("user_batch") == 50 # 200 - 50 (for first) + 70 (refunded for second) - 30 (for third) = 190.
                                                    # Ah, the debit happens first. Initial 200.
                                                    # 1st payment: debit 50 -> 150. Gateway success. Final 150.
                                                    # 2nd payment: debit 70 -> 80. Gateway fail. Credit 70 -> 150. Final 150.
                                                    # 3rd payment: debit 30 -> 120. Gateway success. Final 120.
    assert service.user_balance("user_batch") == 120 # Corrected calculation


def test_export_report(tmp_path):
    report_path = tmp_path / "test_report.json"
    service = PaymentService()
    service.add_funds("u1", 100)
    service.process_payment("u1", 50, "USD")
    service.add_funds("u2", 200)

    export_report(service, str(report_path))
    assert report_path.exists()
    
    with open(report_path, "r") as f:
        report_data = json.load(f)
    
    assert "u1" in report_data
    assert "u2" in report_data
    assert report_data["u1"]["balance"] == 50
    assert len(report_data["u1"]["transactions"]) == 2 # credit, debit
    assert report_data["u2"]["balance"] == 200
    assert len(report_data["u2"]["transactions"]) == 1 # credit