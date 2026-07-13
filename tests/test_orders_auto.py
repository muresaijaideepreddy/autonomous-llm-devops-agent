import sys
import os
import pytest
import uuid
import json
from unittest.mock import patch, MagicMock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from orders import *

@pytest.fixture
def order_item():
    return OrderItem(product_id="123", name="Test Product", price=10.0, quantity=2)

def test_order_item_subtotal(order_item):
    assert order_item.subtotal == 20.0

def test_order_item_update_quantity(order_item):
    order_item.update_quantity(3)
    assert order_item.quantity == 3
    assert order_item.subtotal == 30.0

def test_order_item_update_quantity_raises_value_error():
    order_item = OrderItem(product_id="123", name="Test Product", price=10.0)
    with pytest.raises(ValueError):
        order_item.update_quantity(0)

def test_order_item_negative_price_raises_value_error():
    with pytest.raises(ValueError):
        OrderItem(product_id="123", name="Test Product", price=-10.0)

def test_order_item_zero_quantity_raises_value_error():
    with pytest.raises(ValueError):
        OrderItem(product_id="123", name="Test Product", price=10.0, quantity=0)

@pytest.fixture
def cart():
    return Cart(user_id="user_001")

def test_cart_initialization(cart):
    assert cart.user_id == "user_001"
    assert cart.is_empty() is True

def test_cart_add_item(cart):
    cart.add_item(product_id="123", name="Test Product", price=10.0, quantity=2)
    assert cart.item_count == 2
    assert cart.total == 20.0

def test_cart_remove_item(cart):
    cart.add_item(product_id="123", name="Test Product", price=10.0, quantity=2)
    assert cart.remove_item("123") is True
    assert cart.is_empty() is True

def test_cart_remove_item_not_found(cart):
    assert cart.remove_item("nonexistent") is False

def test_cart_update_quantity(cart):
    cart.add_item(product_id="123", name="Test Product", price=10.0, quantity=2)
    assert cart.update_quantity("123", 3) is True
    assert cart.items["123"].quantity == 3
    assert cart.total == 30.0

def test_cart_update_quantity_not_found(cart):
    assert cart.update_quantity("nonexistent", 1) is False

def test_cart_update_quantity_raises_value_error(cart):
    cart.add_item(product_id="123", name="Test Product", price=10.0, quantity=2)
    assert cart.update_quantity("123", -1) is False

@pytest.fixture
def discount_engine():
    return DiscountEngine()

def test_discount_engine_add_discount(discount_engine):
    result = discount_engine.add_discount("SAVE10", "percentage", 10, min_order=50)
    assert result["success"] is True
    assert discount_engine.discounts["SAVE10"]["value"] == 10

def test_discount_engine_add_invalid_discount_type(discount_engine):
    result = discount_engine.add_discount("INVALID", "invalid_type", 10)
    assert result["success"] is False
    assert "Invalid discount type" in result["error"]

def test_discount_engine_apply_discount(discount_engine):
    discount_engine.add_discount("SAVE10", "percentage", 10, min_order=50)
    result = discount_engine.apply_discount("SAVE10", 100, item_count=1)
    assert result["success"] is True
    assert result["discount_amount"] == 10.0
    assert result["new_total"] == 90.0

def test_discount_engine_apply_discount_not_active(discount_engine):
    discount_engine.add_discount("SAVE10", "percentage", 10)
    discount_engine.deactivate("SAVE10")
    result = discount_engine.apply_discount("SAVE10", 100)
    assert result["success"] is False
    assert "Discount code is no longer active" in result["error"]

def test_order_initialization(order_item):
    order = Order(user_id="user_001", items=[order_item])
    assert order.user_id == "user_001"
    assert order.total == 21.6  # (20 subtotal - 0 discount + 8% tax)

def test_order_initialization_no_items_raises_value_error():
    with pytest.raises(ValueError):
        Order(user_id="user_001", items=[])

def test_order_transition_to_valid_status(order_item):
    order = Order(user_id="user_001", items=[order_item])
    assert order.transition_to("CONFIRMED") is True
    assert order.status == "CONFIRMED"

def test_order_transition_to_invalid_status(order_item):
    order = Order(user_id="user_001", items=[order_item])
    assert order.transition_to("SHIPPED") is False
    assert order.status == "CREATED"
