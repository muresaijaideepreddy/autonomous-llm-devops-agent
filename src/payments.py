def process_payment(amount: int) -> bool:
    if amount < 0:
        raise ValueError("Amount cannot be negative")
    return True
