

import sys
import os
import pytest
from unittest.mock import MagicMock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import *

@pytest.fixture
def temp_repo_path(tmp_path):
    file_path = tmp_path / "test_payments.json"
    return str(file_path)

@pytest.fixture
def clean_repo(temp_repo_path):
    repo = PaymentRepository(path=temp_repo_path)
    # Ensure the file is empty before each test
    with open(temp_repo_path, "w") as f:
        json.dump([], f)
    return repo

@pytest.fixture
def sample_payment_data():
    return {
        "payment_id": str(uuid.uuid4()),
        "amount": 100,
        "currency": "USD",
        "user_id": "u456"
    }

@pytest.fixture
def mock_payment_service():
    mock_repo = MagicMock(spec=PaymentRepository)
    mock_gateway = MagicMock(spec=PaymentGateway)
    mock_fraud_checker = MagicMock(spec=FraudChecker)
    service = PaymentService(repo=mock_repo, gateway=mock_gateway, fraud=mock_fraud_checker)
    return service, mock_repo, mock_gateway, mock_fraud_checker


def test_payment_initialization_and_status_changes():
    payment_id = str(uuid.uuid4())
    amount = 50.0
    currency = "EUR"
    user_id = "user1"
    payment = Payment(payment_id, amount, currency, user_id)

    assert payment.payment_id == payment_id
    assert payment.amount == amount
    assert payment.currency == currency
    assert payment.user_id == user_id
    assert payment.status == "CREATED"
    assert isinstance(payment.created_at, datetime)
    assert payment.created_at.tzinfo == timezone.utc

    payment.mark_success()
    assert payment.status == "SUCCESS"

    payment.mark_failed()
    assert payment.status == "FAILED"

def test_wallet_credit_and_initialization():
    user_id = "user1"
    wallet = Wallet(user_id)
    assert wallet.user_id == user_id
    assert wallet.balance == 0
    assert wallet.transactions == []

    wallet.credit(100)
    assert wallet.balance == 100
    assert wallet.transactions == [("CREDIT", 100)]
    wallet.credit(50.5)
    assert wallet.balance == 150.5
    assert wallet.transactions == [("CREDIT", 100), ("CREDIT", 50.5)]

def test_wallet_credit_invalid_amount():
    wallet = Wallet("u1")
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(0)
    assert wallet.balance == 0
    assert not wallet.transactions
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(-10)
    assert wallet.balance == 0
    assert not wallet.transactions

def test_wallet_debit_scenarios():
    wallet = Wallet("u1")
    wallet.credit(200)

    result_success = wallet.debit(150)
    assert result_success is True
    assert wallet.balance == 50
    assert wallet.transactions == [("CREDIT", 200), ("DEBIT", 150)]

    result_insufficient = wallet.debit(100)
    assert result_insufficient is False
    assert wallet.balance == 50
    assert wallet.transactions == [("CREDIT", 200), ("DEBIT", 150)]

def test_repo_initialization_creates_file(tmp_path):
    file_path = tmp_path / "new_payments.json"
    repo = PaymentRepository(path=str(file_path))
    assert file_path.exists()
    with open(file_path, "r") as f:
        assert json.load(f) == []

def test_repo_save_update_get_flow(clean_repo, sample_payment_data):
    payment_id = sample_payment_data["payment_id"]
    user_id = sample_payment_data["user_id"]
    payment = Payment(**sample_payment_data)

    clean_repo.save(payment)
    loaded_data = clean_repo._load()
    assert len(loaded_data) == 1
    assert loaded_data[0]["payment_id"] == payment_id
    assert loaded_data[0]["status"] == "CREATED"

    clean_repo.update_status(payment_id, "SUCCESS")
    updated_data = clean_repo._load()
    assert updated_data[0]["status"] == "SUCCESS"

    user_payments = clean_repo.get_by_user(user_id)
    assert len(user_payments) == 1
    assert user_payments[0]["payment_id"] == payment_id
    assert user_payments[0]["status"] == "SUCCESS"

    payment2 = Payment("p_other", 200, "EUR", "user_other")
    clean_repo.save(payment2)
    user_payments_other = clean_repo.get_by_user("user_other")
    assert len(user_payments_other) == 1
    assert user_payments_other[0]["payment_id"] == "p_other"

def test_fraud_checker_detection_scenarios():
    fraud_checker = FraudChecker()

    payment_high_amount = Payment("id1", 100000.01, "USD", "u1")
    assert fraud_checker.is_fraud(payment_high_amount) is True

    payment_unsupported_currency = Payment("id2", 100, "BTC", "u1")
    assert fraud_checker.is_fraud(payment_unsupported_currency) is True

    payment_not_fraud = Payment("id3", 500, "USD", "u1")
    assert fraud_checker.is_fraud(payment_not_fraud) is False

def test_payment_gateway_charge_outcomes():
    gateway = PaymentGateway()
    payment = Payment("id", 100, "USD", "u1")

    mock_rand_success = MagicMock(return_value=7)
    assert gateway.charge(payment, rand=mock_rand_success) is True
    mock_rand_success.assert_called_once_with(1, 10)

    mock_rand_failure = MagicMock(return_value=8)
    assert gateway.charge(payment, rand=mock_rand_failure) is False
    mock_rand_failure.assert_called_once_with(1, 10)

def test_service_add_funds(mock_payment_service):
    service, _, _, _ = mock_payment_service
    user_id = "userA"
    assert service.user_balance(user_id) == 0

    new_balance = service.add_funds(user_id, 200)
    assert new_balance == 200
    assert service.user_balance(user_id) == 200

def test_service_process_payment_negative_amount(mock_payment_service):
    service, mock_repo, mock_gateway, mock_fraud_checker = mock_payment_service
    with pytest.raises(ValueError, match="Invalid amount"):
        service.process_payment("u1", -10, "USD")
    mock_repo.save.assert_not_called()
    mock_gateway.charge.assert_not_called()
    mock_fraud_checker.is_fraud.assert_not_called()

def test_service_process_payment_fraudulent(mock_payment_service):
    service, mock_repo, mock_gateway, mock_fraud_checker = mock_payment_service
    mock_fraud_checker.is_fraud.return_value = True

    result = service.process_payment("u1", 100, "USD")
    assert result is False
    mock_fraud_checker.is_fraud.assert_called_once()
    mock_repo.save.assert_called_once()
    assert mock_repo.save.call_args[0][0].status == "FAILED"
    mock_gateway.charge.assert_not_called()
    assert service.user_balance("u1") == 0

def test_service_process_payment_insufficient_funds(mock_payment_service):
    service, mock_repo, mock_gateway, mock_fraud_checker = mock_payment_service
    mock_fraud_checker.is_fraud.return_value = False
    service.add_funds("u1", 50)

    result = service.process_payment("u1", 100, "USD")
    assert result is False
    mock_fraud_checker.is_fraud.assert_called_once()
    mock_repo.save.assert_called_once()
    assert mock_repo.save.call_args[0][0].status == "FAILED"
    mock_gateway.charge.assert_not_called()
    assert service.user_balance("u1") == 50

def test_service_process_payment_gateway_failure_refunds_wallet(mock_payment_service):
    service, mock_repo, mock_gateway, mock_fraud_checker = mock_payment_service
    mock_fraud_checker.is_fraud.return_value = False
    mock_gateway.charge.return_value = False
    service.add_funds("u1", 200)

    result = service.process_payment("u1", 100, "USD")
    assert result is False
    mock_fraud_checker.is_fraud.assert_called_once()
    mock_gateway.charge.assert_called_once()
    mock_repo.save.assert_called_once()
    assert mock_repo.save.call_args[0][0].status == "FAILED"
    assert service.user_balance("u1") == 200

def test_service_process_payment_successful(mock_payment_service):
    service, mock_repo, mock_gateway, mock_fraud_checker = mock_payment_service
    mock_fraud_checker.is_fraud.return_value = False
    mock_gateway.charge.return_value = True
    service.add_funds("u1", 200)

    result = service.process_payment("u1", 100, "USD")
    assert result is True
    mock_fraud_checker.is_fraud.assert_called_once()
    mock_gateway.charge.assert_called_once()
    mock_repo.save.assert_called_once()
    assert mock_repo.save.call_args[0][0].status == "SUCCESS"
    assert service.user_balance("u1") == 100

import sys
import os
import pytest
from unittest import mock
import json
import shutil
import uuid

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

# Ensure the src directory exists in the path for imports
if not os.path.exists(SRC_DIR):
    # Fallback for alternative project structures, e.g., if tests are in root
    SRC_DIR = os.path.abspath(os.path.dirname(__file__)) # Assume payments.py is next to test file
    sys.path.insert(0, SRC_DIR)

from payments import *

@pytest.fixture(autouse=True)
def cleanup_data_dir():
    """Removes the 'data' directory before and after each test."""
    data_dir = os.path.join(ROOT_DIR, "data")
    if os.path.exists(data_dir):
        shutil.rmtree(data_dir)
    yield
    if os.path.exists(data_dir):
        shutil.rmtree(data_dir)

@pytest.fixture
def temp_repo(tmp_path):
    """Provides a PaymentRepository instance with a temporary file path."""
    repo_path = tmp_path / "payments.json"
    return PaymentRepository(path=str(repo_path))

@pytest.fixture
def payment_service(temp_repo):
    """Provides a PaymentService instance with mocked dependencies and a temporary repo."""
    gateway_mock = mock.Mock(spec=PaymentGateway)
    fraud_mock = mock.Mock(spec=FraudChecker)
    # Default mocks for happy path, specific tests will override as needed
    gateway_mock.charge.return_value = True
    fraud_mock.is_fraud.return_value = False
    service = PaymentService(repo=temp_repo, gateway=gateway_mock, fraud=fraud_mock)
    return service, gateway_mock, fraud_mock

def test_wallet_credit_invalid_amount():
    """
    Covers Wallet.credit lines:
    - 43: if amount <= 0:
    - 44: raise ValueError("Invalid credit amount")
    """
    wallet = Wallet("user123")
    initial_balance = wallet.balance
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(0)
    assert wallet.balance == initial_balance
    with pytest.raises(ValueError, match="Invalid credit amount"):
        wallet.credit(-10)
    assert wallet.balance == initial_balance

def test_wallet_debit_insufficient_funds():
    """
    Covers Wallet.debit lines:
    - 52: if amount > self.balance:
    - 53: return False
    """
    wallet = Wallet("user123")
    wallet.credit(50) # Ensure some balance, but not enough for debit
    initial_balance = wallet.balance
    result = wallet.debit(100)
    assert not result
    assert wallet.balance == initial_balance

def test_payment_repo_update_status_no_match(temp_repo):
    """
    Covers PaymentRepository.update_status line:
    - 98: for p in data:
    Ensures the loop is entered but no payment matches the ID.
    """
    payment_id_1 = str(uuid.uuid4())
    payment_1 = Payment(payment_id_1, 100, "USD", "user_repo_1")
    temp_repo.save(payment_1)

    non_existent_payment_id = str(uuid.uuid4())
    temp_repo.update_status(non_existent_payment_id, "SUCCESS")

    saved_payments = temp_repo._load()
    assert len(saved_payments) == 1
    assert saved_payments[0]["payment_id"] == payment_id_1
    assert saved_payments[0]["status"] == "CREATED" # Status should not have changed

def test_fraud_checker_high_amount_fraud():
    """
    Covers FraudChecker.is_fraud lines:
    - 119: if payment.amount > 100000:
    - 120: return True
    """
    fraud_checker = FraudChecker()
    payment = Payment(str(uuid.uuid4()), 100001, "USD", "user_fraud_high_amount")
    assert fraud_checker.is_fraud(payment)

def test_fraud_checker_invalid_currency_fraud():
    """
    Covers FraudChecker.is_fraud lines:
    - 121: if payment.currency not in ["USD", "INR", "EUR"]:
    - 122: return True
    """
    fraud_checker = FraudChecker()
    payment = Payment(str(uuid.uuid4()), 500, "XYZ", "user_fraud_invalid_currency")
    assert fraud_checker.is_fraud(payment)

def test_payment_gateway_charge_declined(mocker):
    """
    Covers PaymentGateway.charge line:
    - 126: return rand(1, 10) < 8 (specifically the False outcome)
    """
    gateway = PaymentGateway()
    mocker.patch('random.randint', return_value=8) # Makes rand(1, 10) < 8 return False
    payment = Payment(str(uuid.uuid4()), 100, "USD", "user_charge")
    assert not gateway.charge(payment)

def test_payment_service_add_funds_new_user(payment_service):
    """
    Covers PaymentService._get_wallet lines:
    - 130: def _get_wallet(self, user_id):
    - 131: if user_id not in self.wallets:
    - 132: self.wallets[user_id] = Wallet(user_id)
    Covers PaymentService.add_funds lines:
    - 135: def add_funds(self, user_id, amount):
    - 136: wallet = self._get_wallet(user_id)
    Covers Wallet.credit line:
    - 45: self.balance += amount (implicitly via valid amount)
    Covers PaymentService.user_balance line:
    - 174: def user_balance(self, user_id):
    """
    service, _, _ = payment_service
    user_id = "new_user_add_funds"
    
    balance = service.add_funds(user_id, 200)
    assert balance == 200
    assert service.user_balance(user_id) == 200

def test_process_payment_negative_amount_raises_error(payment_service):
    """
    Covers PaymentService.process_payment lines:
    - 139: if amount < 0:
    - 141: raise ValueError("Invalid amount")
    """
    service, _, _ = payment_service
    user_id = "user_neg_amt"
    with pytest.raises(ValueError, match="Invalid amount"):
        service.process_payment(user_id, -50, "USD")

def test_process_payment_fraud_declined(payment_service):
    """
    Covers PaymentService.process_payment lines:
    - 22: self.status = "CREATED" (via Payment object creation)
    - 142: payment_id = str(uuid.uuid4())
    - 143: payment = Payment(payment_id, amount, currency, user_id)
    - 144: if self.fraud.is_fraud(payment):
    - 146: payment.mark_failed()
    - 147: self.repo.save(payment)
    - 148: return False
    """
    service, gateway_mock, fraud_mock = payment_service
    user_id = "user_fraud_declined"
    amount = 100001 # Triggers fraud by amount
    currency = "USD"

    fraud_mock.is_fraud.return_value = True

    result = service.process_payment(user_id, amount, currency)
    assert not result
    fraud_mock.is_fraud.assert_called_once()
    gateway_mock.charge.assert_not_called()

    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    assert service.user_balance(user_id) == 0

def test_process_payment_insufficient_funds_declined(payment_service):
    """
    Covers PaymentService.process_payment lines:
    - 149: wallet = self._get_wallet(user_id)
    - 150: if not wallet.debit(amount):
    - 152: payment.mark_failed()
    - 153: self.repo.save(payment)
    - 154: return False
    """
    service, gateway_mock, fraud_mock = payment_service
    user_id = "user_insufficient_funds"
    amount = 200
    currency = "USD"

    service.add_funds(user_id, 100) # Add some funds, but not enough
    fraud_mock.is_fraud.return_value = False

    result = service.process_payment(user_id, amount, currency)
    assert not result
    fraud_mock.is_fraud.assert_called_once()
    gateway_mock.charge.assert_not_called()

    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    assert service.user_balance(user_id) == 100 # Wallet balance should be untouched

def test_process_payment_gateway_declined_refunds_wallet(payment_service):
    """
    Covers PaymentService.process_payment lines:
    - 155: charged = self.gateway.charge(payment)
    - 156: if charged: (evaluates to False)
    - 158: else:
    - 159: wallet.credit(amount)
    - 160: payment.mark_failed()
    - 161: self.repo.save(payment)
    """
    service, gateway_mock, fraud_mock = payment_service
    user_id = "user_gateway_declined"
    amount = 150
    currency = "USD"

    service.add_funds(user_id, 200)
    fraud_mock.is_fraud.return_value = False
    gateway_mock.charge.return_value = False # Gateway declines

    result = service.process_payment(user_id, amount, currency)
    assert not result
    fraud_mock.is_fraud.assert_called_once()
    gateway_mock.charge.assert_called_once()

    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "FAILED"
    assert service.user_balance(user_id) == 200 # Funds should be returned to wallet

def test_payment_service_refund_existent_payment(payment_service):
    """
    Covers PaymentService.refund lines for an existing payment:
    - 164: def refund(self, payment_id):
    - 165: payments = self.repo._load()
    - 166: for p in payments:
    - 167: if p["payment_id"] == payment_id:
    - 168: wallet = self._get_wallet(p["user_id"])
    - 169: wallet.credit(p["amount"])
    - 170: p["status"] = "REFUNDED"
    - 173: self.repo._write(payments)
    """
    service, _, _ = payment_service
    user_id = "user_refund_existent"
    amount = 100

    service.add_funds(user_id, 500)
    service.gateway.charge.return_value = True # Ensure payment succeeds
    
    service.process_payment(user_id, amount, "USD")
    successful_payments = service.repo.get_by_user(user_id)
    assert len(successful_payments) == 1
    payment_id_to_refund = successful_payments[0]["payment_id"]
    initial_balance_after_payment = service.user_balance(user_id) # Should be 400

    service.refund(payment_id_to_refund)

    assert service.user_balance(user_id) == initial_balance_after_payment + amount
    updated_payments = service.repo.get_by_user(user_id)
    assert len(updated_payments) == 1
    assert updated_payments[0]["status"] == "REFUNDED"

def test_payment_service_refund_non_existent_payment(payment_service):
    """
    Covers PaymentService.refund lines when no payment matches the ID:
    - 164: def refund(self, payment_id):
    - 165: payments = self.repo._load()
    - 166: for p in payments: (loop is entered)
    - 173: self.repo._write(payments) (repo written back, unchanged)
    Line 167 `if p["payment_id"] == payment_id:` is evaluated to False for all elements.
    """
    service, _, _ = payment_service
    user_id = "user_refund_non_existent"
    amount = 100

    service.add_funds(user_id, 500)
    service.gateway.charge.return_value = True
    service.process_payment(user_id, amount, "USD")

    non_existent_payment_id = str(uuid.uuid4())
    
    service.refund(non_existent_payment_id)

    assert service.user_balance(user_id) == 400 # Balance should be unchanged
    payments = service.repo.get_by_user(user_id)
    assert len(payments) == 1
    assert payments[0]["status"] == "SUCCESS" # Status should be unchanged

def test_batch_payments_with_value_error(payment_service):
    """
    Covers batch_payments function lines:
    - 182: def batch_payments(service, user_id, payments):
    - 183: results = []
    - 184: for amt, cur in payments:
    - 185: try:
    - 186: res = service.process_payment(user_id, amt, cur)
    - 187: results.append(res)
    - 188: except ValueError:
    - 189: results.append(False)
    """
    service, _, _ = payment_service
    user_id = "user_batch_error"
    service.add_funds(user_id, 500)

    payments_batch = [
        (50, "USD"),
        (-10, "USD"), # This will cause a ValueError in process_payment
        (100, "INR")
    ]
    service.gateway.charge.return_value = True # Ensure valid payments succeed

    results = batch_payments(service, user_id, payments_batch)
    
    assert results == [True, False, True]
    assert service.user_balance(user_id) == 350
    assert len(service.repo.get_by_user(user_id)) == 2

def test_export_report_with_data(payment_service, tmp_path):
    """
    Covers export_report function lines:
    - 197: def export_report(service, path="data/report.json"):
    - 198: os.makedirs(os.path.dirname(path), exist_ok=True)
    - 199: report = {}
    - 200: for user_id, wallet in service.wallets.items():
    - 204: with open(path, "w") as f:
    - 205: json.dump(report, f, indent=2)
    """
    service, _, _ = payment_service
    user_id_1 = "user_report_1"
    user_id_2 = "user_report_2"

    service.add_funds(user_id_1, 100)
    service.add_funds(user_id_2, 200)
    
    service.gateway.charge.return_value = True
    service.process_payment(user_id_1, 50, "USD")
    service.process_payment(user_id_2, 75, "INR")

    report_path = tmp_path / "data" / "report.json"
    
    export_report(service, path=str(report_path))

    assert os.path.exists(report_path)
    with open(report_path, "r") as f:
        report_data = json.load(f)

    expected_report = {
        user_id_1: {
            "balance": 50,
            "transactions": [["CREDIT", 100], ["DEBIT", 50]]
        },
        user_id_2: {
            "balance": 125,
            "transactions": [["CREDIT", 200], ["DEBIT", 75]]
        }
    }
    assert report_data == expected_report