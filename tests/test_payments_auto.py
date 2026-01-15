

import sys
import os
import pytest
from datetime import datetime, timezone
import uuid
import json
import random

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import Payment, Wallet, PaymentRepository, FraudChecker, PaymentGateway, PaymentService, batch_payments, export_report


@pytest.fixture
def clean_payment_repo(tmp_path):
    repo_path = tmp_path / "test_payments.json"
    repo = PaymentRepository(path=repo_path)
    with open(repo_path, "w") as f:
        json.dump([], f)
    return repo


@pytest.fixture
def mock_fraud_checker_always_false():
    class MockFraudChecker(FraudChecker):
        def is_fraud(self, payment):
            return False
    return MockFraudChecker()


@pytest.fixture
def mock_fraud_checker_always_true():
    class MockFraudChecker(FraudChecker):
        def is_fraud(self, payment):
            return True
    return MockFraudChecker()


@pytest.fixture
def mock_gateway_always_success():
    class MockPaymentGateway(PaymentGateway):
        def charge(self, payment, rand=None):
            return True
    return MockPaymentGateway()


@pytest.fixture
def mock_gateway_always_fail():
    class MockPaymentGateway(PaymentGateway):
        def charge(self, payment, rand=None):
            return False
    return MockPaymentGateway()


def test_payment_init_and_status_changes():
    payment_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    payment = Payment(payment_id, 100, "USD", user_id)
    assert payment.payment_id == payment_id
    assert payment.amount == 100
    assert payment.currency == "USD"
    assert payment.user_id == user_id
    assert payment.status == "CREATED"
    assert isinstance(payment.created_at, datetime)
    assert payment.created_at.tzinfo == timezone.utc

    payment.mark_success()
    assert payment.status == "SUCCESS"
    payment.mark_failed()
    assert payment.status == "FAILED"


def test_wallet_init_and_credit():
    user_id = str(uuid.uuid4())
    wallet = Wallet(user_id)
    assert wallet.user_id == user_id
    assert wallet.balance == 0
    assert wallet.transactions == []

    wallet.credit(100)
    assert wallet.balance == 100
    assert wallet.transactions == [("CREDIT", 100)]


def test_wallet_credit_invalid_amount():
    user_id = str(uuid.uuid4())
    wallet = Wallet(user_id)
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(0)
    assert wallet.balance == 0
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(-10)
    assert wallet.balance == 0


def test_wallet_debit_sufficient_funds():
    user_id = str(uuid.uuid4())
    wallet = Wallet(user_id)
    wallet.credit(200)
    assert wallet.debit(150) is True
    assert wallet.balance == 50
    assert wallet.transactions == [("CREDIT", 200), ("DEBIT", 150)]


def test_wallet_debit_insufficient_funds():
    user_id = str(uuid.uuid4())
    wallet = Wallet(user_id)
    wallet.credit(50)
    assert wallet.debit(100) is False
    assert wallet.balance == 50
    assert wallet.transactions == [("CREDIT", 50)]


def test_payment_repository_init_and_save(clean_payment_repo):
    repo = clean_payment_repo
    user_id = str(uuid.uuid4())
    payment_id = str(uuid.uuid4())
    payment = Payment(payment_id, 150, "USD", user_id)
    repo.save(payment)

    loaded_data = repo._load()
    assert len(loaded_data) == 1
    saved_payment = loaded_data[0]
    assert saved_payment["payment_id"] == payment_id
    assert saved_payment["status"] == "CREATED"


def test_payment_repository_update_status(clean_payment_repo):
    repo = clean_payment_repo
    user_id = str(uuid.uuid4())
    payment1_id = str(uuid.uuid4())

    repo.save(Payment(payment1_id, 100, "USD", user_id))
    repo.update_status(payment1_id, "SUCCESS")
    
    loaded_data = repo._load()
    assert next(p for p in loaded_data if p["payment_id"] == payment1_id)["status"] == "SUCCESS"


def test_payment_repository_get_by_user(clean_payment_repo):
    repo = clean_payment_repo
    user1_id = str(uuid.uuid4())
    user2_id = str(uuid.uuid4())

    repo.save(Payment(str(uuid.uuid4()), 100, "USD", user1_id))
    repo.save(Payment(str(uuid.uuid4()), 200, "EUR", user2_id))
    repo.save(Payment(str(uuid.uuid4()), 300, "INR", user1_id))

    user1_payments = repo.get_by_user(user1_id)
    assert len(user1_payments) == 2
    assert all(p["user_id"] == user1_id for p in user1_payments)


def test_fraud_checker_is_fraud_amount_exceeds_limit():
    checker = FraudChecker()
    payment = Payment("pid", 100001, "USD", "uid")
    assert checker.is_fraud(payment) is True


def test_fraud_checker_is_fraud_unsupported_currency():
    checker = FraudChecker()
    payment = Payment("pid", 500, "JPY", "uid")
    assert checker.is_fraud(payment) is True


def test_fraud_checker_is_not_fraud_legit_payment():
    checker = FraudChecker()
    payment = Payment("pid", 500, "USD", "uid")
    assert checker.is_fraud(payment) is False


def test_payment_gateway_charge_success():
    gateway = PaymentGateway()
    payment = Payment("pid", 100, "USD", "uid")
    def mock_randint_success(a, b):
        return 5
    assert gateway.charge(payment, rand=mock_randint_success) is True


def test_payment_gateway_charge_failure():
    gateway = PaymentGateway()
    payment = Payment("pid", 100, "USD", "uid")
    def mock_randint_fail(a, b):
        return 8
    assert gateway.charge(payment, rand=mock_randint_fail) is False


def test_payment_service_add_funds(clean_payment_repo):
    service = PaymentService(repo=clean_payment_repo)
    user_id = str(uuid.uuid4())
    initial_balance = service.user_balance(user_id)
    assert initial_balance == 0

    new_balance = service.add_funds(user_id, 500)
    assert new_balance == 500
    assert service.user_balance(user_id) == 500


def test_payment_service_process_payment_invalid_amount(clean_payment_repo, mock_fraud_checker_always_false, mock_gateway_always_success):
    service = PaymentService(repo=clean_payment_repo, fraud=mock_fraud_checker_always_false, gateway=mock_gateway_always_success)
    user_id = str(uuid.uuid4())
    
    with pytest.raises(ValueError, match="Invalid amount"):
        service.process_payment(user_id, -100, "USD")
    
    assert len(clean_payment_repo._load()) == 0


def test_payment_service_process_payment_fraudulent(clean_payment_repo, mock_fraud_checker_always_true, mock_gateway_always_success):
    service = PaymentService(repo=clean_payment_repo, fraud=mock_fraud_checker_always_true, gateway=mock_gateway_always_success)
    user_id = str(uuid.uuid4())
    service.add_funds(user_id, 1000)

    result = service.process_payment(user_id, 100, "USD")
    assert result is False
    assert service.user_balance(user_id) == 1000

    payments = clean_payment_repo._load()
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"


def test_payment_service_process_payment_insufficient_funds(clean_payment_repo, mock_fraud_checker_always_false, mock_gateway_always_success):
    service = PaymentService(repo=clean_payment_repo, fraud=mock_fraud_checker_always_false, gateway=mock_gateway_always_success)
    user_id = str(uuid.uuid4())
    service.add_funds(user_id, 50)

    result = service.process_payment(user_id, 100, "USD")
    assert result is False
    assert service.user_balance(user_id) == 50

    payments = clean_payment_repo._load()
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"


def test_payment_service_process_payment_gateway_failure_refunds_wallet(clean_payment_repo, mock_fraud_checker_always_false, mock_gateway_always_fail):
    service = PaymentService(repo=clean_payment_repo, fraud=mock_fraud_checker_always_false, gateway=mock_gateway_always_fail)
    user_id = str(uuid.uuid4())
    service.add_funds(user_id, 200)

    result = service.process_payment(user_id, 100, "USD")
    assert result is False
    assert service.user_balance(user_id) == 200

    payments = clean_payment_repo._load()
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"


def test_payment_service_process_payment_success(clean_payment_repo, mock_fraud_checker_always_false, mock_gateway_always_success):
    service = PaymentService(repo=clean_payment_repo, fraud=mock_fraud_checker_always_false, gateway=mock_gateway_always_success)
    user_id = str(uuid.uuid4())
    service.add_funds(user_id, 200)

    result = service.process_payment(user_id, 100, "USD")
    assert result is True
    assert service.user_balance(user_id) == 100

    payments = clean_payment_repo._load()
    assert len(payments) == 1
    assert payments[0]["status"] == "SUCCESS"


def test_payment_service_refund_payment(clean_payment_repo, mock_fraud_checker_always_false, mock_gateway_always_success):
    service = PaymentService(repo=clean_payment_repo, fraud=mock_fraud_checker_always_false, gateway=mock_gateway_always_success)
    user_id = str(uuid.uuid4())
    service.add_funds(user_id, 200)

    service.process_payment(user_id, 100, "USD")
    assert service.user_balance(user_id) == 100

    payments = clean_payment_repo._load()
    payment_id_to_refund = payments[0]["payment_id"]

    service.refund(payment_id_to_refund)
    assert service.user_balance(user_id) == 200

    updated_payments = clean_payment_repo._load()
    assert next(p for p in updated_payments if p["payment_id"] == payment_id_to_refund)["status"] == "REFUNDED"


def test_batch_payments_mixed_results(clean_payment_repo, mock_fraud_checker_always_false):
    class AltGateway(PaymentGateway):
        def __init__(self):
            self.call_count = 0
        def charge(self, payment, rand=None):
            self.call_count += 1
            return self.call_count % 2 == 1 # Success on odd calls, Fail on even

    service = PaymentService(repo=clean_payment_repo, fraud=mock_fraud_checker_always_false, gateway=AltGateway())
    user_id = str(uuid.uuid4())
    service.add_funds(user_id, 500)

    payments_to_process = [(50, "USD"), (70, "EUR"), (100, "INR"), (20, "USD")]
    results = batch_payments(service, user_id, payments_to_process)

    assert results == [True, False, True, False]
    assert service.user_balance(user_id) == 350

    repo_payments = clean_payment_repo._load()
    assert [p["status"] for p in repo_payments] == ["SUCCESS", "FAILED", "SUCCESS", "FAILED"]


def test_export_report_content(clean_payment_repo, tmp_path):
    service = PaymentService(repo=clean_payment_repo)
    user1_id = str(uuid.uuid4())
    user2_id = str(uuid.uuid4())

    service.add_funds(user1_id, 100)
    service.add_funds(user2_id, 200)
    service.wallets[user1_id].debit(50)
    service.wallets[user2_id].credit(30)

    report_path = tmp_path / "test_report.json"
    export_report(service, path=report_path)

    assert os.path.exists(report_path)
    with open(report_path, "r") as f:
        report_data = json.load(f)

    assert user1_id in report_data
    assert report_data[user1_id]["balance"] == 50
    assert report_data[user1_id]["transactions"] == [["CREDIT", 100], ["DEBIT", 50]]

    assert user2_id in report_data
    assert report_data[user2_id]["balance"] == 230
    assert report_data[user2_id]["transactions"] == [["CREDIT", 200], ["CREDIT", 30]]