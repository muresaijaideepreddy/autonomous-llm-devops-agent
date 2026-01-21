import sys
import os
import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from payments import *


@pytest.fixture
def temp_repo_path(tmp_path):
    """Provides a temporary file path for PaymentRepository."""
    repo_dir = tmp_path / "data"
    repo_dir.mkdir()
    return repo_dir / "payments.json"


@pytest.fixture
def clean_service(tmp_path):
    """Provides a fresh PaymentService instance with a temporary repository."""
    repo_path = tmp_path / "data" / "payments.json"
    repo_path.parent.mkdir(exist_ok=True)
    repo = PaymentRepository(path=str(repo_path))
    return PaymentService(repo=repo)


# NEW TESTS START HERE


def test_payment_repository_get_by_user_existing(temp_repo_path):
    repo = PaymentRepository(path=str(temp_repo_path))
    user1_id = "user123"
    user2_id = "user456"
    payment1 = Payment(str(uuid.uuid4()), 100, "USD", user1_id)
    payment2 = Payment(str(uuid.uuid4()), 200, "EUR", user2_id)
    payment3 = Payment(str(uuid.uuid4()), 150, "INR", user1_id)

    repo.save(payment1)
    repo.save(payment2)
    repo.save(payment3)

    user1_payments = repo.get_by_user(user1_id)
    assert len(user1_payments) == 2
    assert {p["payment_id"] for p in user1_payments} == {payment1.payment_id, payment3.payment_id}
    assert all(p["user_id"] == user1_id for p in user1_payments)


def test_payment_repository_get_by_user_no_payments(temp_repo_path):
    repo = PaymentRepository(path=str(temp_repo_path))
    user1_id = "user123"
    payment1 = Payment(str(uuid.uuid4()), 100, "USD", user1_id)
    repo.save(payment1)

    non_existent_user_id = "user789"
    user_payments = repo.get_by_user(non_existent_user_id)
    assert len(user_payments) == 0


def test_fraud_checker_amount_boundary_not_fraud():
    fraud_checker = FraudChecker()
    payment = Payment("id123", 100000, "USD", "user1")
    assert not fraud_checker.is_fraud(payment)


def test_fraud_checker_unsupported_currency_type():
    fraud_checker = FraudChecker()
    payment = Payment("id123", 500, "XBT", "user1")  # XBT is not USD, INR, EUR
    assert fraud_checker.is_fraud(payment)


def test_wallet_debit_exact_balance():
    wallet = Wallet("user123")
    wallet.credit(500)
    assert wallet.balance == 500
    assert wallet.debit(500) is True
    assert wallet.balance == 0
    assert wallet.transactions == [("CREDIT", 500), ("DEBIT", 500)]


def test_payment_service_process_payment_invalid_amount_raises_error(clean_service):
    user_id = "user123"
    with pytest.raises(ValueError, match="Invalid amount"):
        clean_service.process_payment(user_id, 0, "USD")
    with pytest.raises(ValueError, match="Invalid amount"):
        clean_service.process_payment(user_id, -100, "USD")


def test_payment_service_refund_non_existent_payment(clean_service):
    user_id = "user123"
    clean_service.add_funds(user_id, 500)
    clean_service.process_payment(user_id, 100, "USD")

    initial_balance = clean_service.user_balance(user_id)
    initial_repo_data = clean_service.repo._load()

    non_existent_payment_id = str(uuid.uuid4())
    clean_service.refund(non_existent_payment_id)

    # Assert no change in balance or repo state
    assert clean_service.user_balance(user_id) == initial_balance
    assert clean_service.repo._load() == initial_repo_data


def test_payment_service_refund_failed_payment(clean_service):
    user_id = "user123"
    clean_service.add_funds(user_id, 50) # Not enough for 100
    
    # This payment will fail due to insufficient funds
    initial_balance = clean_service.user_balance(user_id)
    result = clean_service.process_payment(user_id, 100, "USD")
    assert result is False
    assert clean_service.user_balance(user_id) == initial_balance # Funds should be returned

    payments = clean_service.repo.get_by_user(user_id)
    assert len(payments) == 1
    failed_payment = payments[0]
    assert failed_payment["status"] == "FAILED"

    # Attempt to refund the failed payment
    clean_service.refund(failed_payment["payment_id"])

    # Wallet balance should now increase as refund effectively adds credit
    assert clean_service.user_balance(user_id) == initial_balance + failed_payment["amount"]
    
    # Check status in repo
    updated_payments = clean_service.repo.get_by_user(user_id)
    assert len(updated_payments) == 1
    assert updated_payments[0]["payment_id"] == failed_payment["payment_id"]
    assert updated_payments[0]["status"] == "REFUNDED"


def test_payment_service_refund_updates_status_in_repo(clean_service):
    user_id = "user123"
    clean_service.add_funds(user_id, 500)
    
    # Process a successful payment
    result = clean_service.process_payment(user_id, 100, "USD")
    assert result is True

    payments_before_refund = clean_service.repo.get_by_user(user_id)
    assert len(payments_before_refund) == 1
    successful_payment = payments_before_refund[0]
    assert successful_payment["status"] == "SUCCESS"

    # Refund the successful payment
    clean_service.refund(successful_payment["payment_id"])

    # Verify status in repository is updated to REFUNDED
    payments_after_refund = clean_service.repo.get_by_user(user_id)
    assert len(payments_after_refund) == 1
    assert payments_after_refund[0]["payment_id"] == successful_payment["payment_id"]
    assert payments_after_refund[0]["status"] == "REFUNDED"


def test_batch_payments_mixed_results(clean_service):
    user_id = "user123"
    clean_service.add_funds(user_id, 200) # Funds for some, but not all

    # Mock gateway to ensure specific failures
    class MockGatewayFailure(PaymentGateway):
        def charge(self, payment, rand=None):
            return False # Always fail

    clean_service.gateway = MockGatewayFailure()

    payments_batch = [
        (50, "USD"),    # Should succeed (funds available)
        (100, "EUR"),   # Should succeed (funds available, total 150/200 spent)
        (100001, "USD"),# Should be fraud (amount > 100000)
        (75, "INR"),    # Should fail insufficient funds (remaining funds 50, needs 75)
        (0, "USD"),     # Should raise ValueError and return False by batch_payments
        (25, "USD"),    # This payment should be able to process after fraud/value error
    ]

    results = batch_payments(clean_service, user_id, payments_batch)

    # Expected results: Success, Success, Fraud(False), InsufficientFunds(False), InvalidAmount(False), Success
    assert results == [True, True, False, False, False, True]
    
    # Verify final balance: Initial 200 - 50 - 100 + 75 (debited and refunded by gateway failure) = 125
    # Let's trace carefully:
    # 1. (50, USD): Balance 200 -> 150. Status CREATED->SUCCESS. Result True.
    # 2. (100, EUR): Balance 150 -> 50. Status CREATED->SUCCESS. Result True.
    # 3. (100001, USD): Fraud. Balance 50. Status CREATED->FAILED. Result False.
    # 4. (75, INR): Insufficient funds. Balance 50. Status CREATED->FAILED. Result False.
    # 5. (0, USD): ValueError. Balance 50. Result False.
    # 6. (25, USD): Balance 50 -> 25. Status CREATED->SUCCESS. Result True.
    # So final balance should be 25.
    assert clean_service.user_balance(user_id) == 25

    all_payments = clean_service.repo.get_by_user(user_id)
    assert len(all_payments) == 5 # The invalid amount payment is not saved
    assert sum(1 for p in all_payments if p["status"] == "SUCCESS") == 3
    assert sum(1 for p in all_payments if p["status"] == "FAILED") == 2


def test_batch_payments_empty_list(clean_service):
    user_id = "user123"
    clean_service.add_funds(user_id, 100)
    results = batch_payments(clean_service, user_id, [])
    assert results == []
    assert clean_service.user_balance(user_id) == 100 # Balance remains unchanged


def test_export_report_no_wallets(tmp_path):
    service = PaymentService() # No wallets initialized
    report_path = tmp_path / "report.json"
    export_report(service, path=str(report_path))

    assert report_path.exists()
    with open(report_path, "r") as f:
        data = json.load(f)
        assert data == {}


def test_export_report_multiple_wallets_and_transactions(tmp_path):
    service = PaymentService()
    user1 = "user1"
    user2 = "user2"

    service.add_funds(user1, 100)
    service.process_payment(user1, 30, "USD")

    service.add_funds(user2, 500)
    service.process_payment(user2, 100, "EUR")
    service.process_payment(user2, 50, "INR")

    report_path = tmp_path / "report.json"
    export_report(service, path=str(report_path))

    assert report_path.exists()
    with open(report_path, "r") as f:
        data = json.load(f)

    assert data[user1]["balance"] == 70
    assert len(data[user1]["transactions"]) == 2
    assert ["CREDIT", 100] in data[user1]["transactions"]
    assert ["DEBIT", 30] in data[user1]["transactions"]

    assert data[user2]["balance"] == 350
    assert len(data[user2]["transactions"]) == 3
    assert ["CREDIT", 500] in data[user2]["transactions"]
    assert ["DEBIT", 100] in data[user2]["transactions"]
    assert ["DEBIT", 50] in data[user2]["transactions"]


def test_payment_gateway_charge_deterministic_behavior():
    gateway = PaymentGateway()
    payment = Payment("id", 100, "USD", "user")

    # Force success
    mock_rand_success = lambda a, b: 1
    assert gateway.charge(payment, rand=mock_rand_success) is True

    # Force failure
    mock_rand_failure = lambda a, b: 9
    assert gateway.charge(payment, rand=mock_rand_failure) is False


def test_payment_repository_update_non_existent_payment(temp_repo_path):
    repo = PaymentRepository(path=str(temp_repo_path))
    payment1_id = str(uuid.uuid4())
    payment1 = Payment(payment1_id, 100, "USD", "user1")
    repo.save(payment1)

    initial_repo_data = repo._load()
    
    non_existent_payment_id = str(uuid.uuid4())
    repo.update_status(non_existent_payment_id, "REFUNDED")

    # Assert that the repository data remains unchanged
    assert repo._load() == initial_repo_data
    
    # Specifically, payment1's status should not have changed
    updated_payment1_in_repo = next(p for p in repo._load() if p["payment_id"] == payment1_id)
    assert updated_payment1_in_repo["status"] == "CREATED"