from datetime import datetime, timezone
import uuid
import json
import os
import random


# -----------------------------
# DOMAIN MODELS
# -----------------------------

class Payment:
    def __init__(self, payment_id, amount, currency, user_id):
        self.payment_id = payment_id
        self.amount = amount
        self.currency = currency
        self.user_id = user_id
        self.created_at = datetime.now(timezone.utc)
        self.status = "CREATED"

    def mark_success(self):
        self.status = "SUCCESS"

    def mark_failed(self):
        self.status = "FAILED"


class Wallet:
    def __init__(self, user_id):
        self.user_id = user_id
        self.balance = 0
        self.transactions = []

    def credit(self, amount):
        if amount <= 0:
            raise ValueError("Invalid credit amount")
        self.balance += amount
        self.transactions.append(("CREDIT", amount))

    def debit(self, amount):
        if amount > self.balance:
            return False
        self.balance -= amount
        self.transactions.append(("DEBIT", amount))
        return True


# -----------------------------
# REPOSITORY
# -----------------------------

class PaymentRepository:
    def __init__(self, path="data/payments.json"):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w") as f:
                json.dump([], f)

    def save(self, payment):
        data = self._load()
        data.append({
            "payment_id": payment.payment_id,
            "amount": payment.amount,
            "currency": payment.currency,
            "user_id": payment.user_id,
            "status": payment.status,
            "created_at": payment.created_at.isoformat()
        })
        self._write(data)

    def update_status(self, payment_id, status):
        data = self._load()
        for p in data:
            if p["payment_id"] == payment_id:
                p["status"] = status
        self._write(data)

    def get_by_user(self, user_id):
        return [p for p in self._load() if p["user_id"] == user_id]

    def _load(self):
        with open(self.path, "r") as f:
            return json.load(f)

    def _write(self, data):
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)


# -----------------------------
# FRAUD & GATEWAY
# -----------------------------

class FraudChecker:
    def is_fraud(self, payment):
        if payment.amount > 100000:
            return True
        if payment.currency not in ["USD", "INR", "EUR"]:
            return True
        return False


class PaymentGateway:
    """
    Deterministic by default.
    Randomness can be injected for testing if needed.
    """
    def charge(self, payment, rand=random.randint):
        return rand(1, 10) < 8


# -----------------------------
# SERVICE
# -----------------------------

class PaymentService:
    def __init__(self, repo=None, gateway=None, fraud=None):
        self.repo = repo or PaymentRepository()
        self.gateway = gateway or PaymentGateway()
        self.fraud = fraud or FraudChecker()
        self.wallets = {}

    def _get_wallet(self, user_id):
        if user_id not in self.wallets:
            self.wallets[user_id] = Wallet(user_id)
        return self.wallets[user_id]

    def add_funds(self, user_id, amount):
        wallet = self._get_wallet(user_id)
        wallet.credit(amount)
        return wallet.balance

    def process_payment(self, user_id, amount, currency):
        if amount < 0:
            raise ValueError("Invalid amount")

        payment_id = str(uuid.uuid4())
        payment = Payment(payment_id, amount, currency, user_id)

        if self.fraud.is_fraud(payment):
            payment.mark_failed()
            self.repo.save(payment)
            return False

        wallet = self._get_wallet(user_id)
        if not wallet.debit(amount):
            payment.mark_failed()
            self.repo.save(payment)
            return False

        charged = self.gateway.charge(payment)
        if charged:
            payment.mark_success()
            self.repo.save(payment)
            return True
        else:
            wallet.credit(amount)
            payment.mark_failed()
            self.repo.save(payment)
            return False

    def refund(self, payment_id):
        payments = self.repo._load()
        for p in payments:
            if p["payment_id"] == payment_id:
                wallet = self._get_wallet(p["user_id"])
                wallet.credit(p["amount"])
                p["status"] = "REFUNDED"
        self.repo._write(payments)

    def user_balance(self, user_id):
        wallet = self._get_wallet(user_id)
        return wallet.balance


# -----------------------------
# BATCH OPERATIONS
# -----------------------------

def batch_payments(service, user_id, payments):
    results = []
    for amt, cur in payments:
        try:
            res = service.process_payment(user_id, amt, cur)
            results.append(res)
        except ValueError:
            results.append(False)
    return results


# -----------------------------
# OPTIONAL UTILITIES
# -----------------------------

def export_report(service, path="data/report.json"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    report = {}
    for user_id, wallet in service.wallets.items():
        report[user_id] = {
            "balance": wallet.balance,
            "transactions": [list(t) for t in wallet.transactions]
        }
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
