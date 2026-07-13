import sys
import os
import pytest
import uuid
import json
from unittest.mock import patch, MagicMock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from inventory import *

@pytest.fixture
def product_fixture():
    return Product(name="Test Product", sku="TP001", price=9.99, category="electronics", stock=100)

def test_product_initialization(product_fixture):
    assert product_fixture.name == "Test Product"
    assert product_fixture.sku == "TP001"
    assert product_fixture.price == 9.99
    assert product_fixture.category == "electronics"
    assert product_fixture.stock == 100
    assert product_fixture.available_stock == 100

def test_product_empty_name():
    with pytest.raises(ValueError, match="Product name cannot be empty"):
        Product(name="", sku="TP002", price=10.00)

def test_product_negative_price():
    with pytest.raises(ValueError, match="Price cannot be negative"):
        Product(name="Test Product", sku="TP003", price=-5.00)

def test_product_negative_stock():
    with pytest.raises(ValueError, match="Initial stock cannot be negative"):
        Product(name="Test Product", sku="TP004", price=10.00, stock=-1)

def test_product_invalid_category():
    with pytest.raises(ValueError, match="Invalid category: invalid"):
        Product(name="Test Product", sku="TP005", price=10.00, category="invalid")

def test_add_stock(product_fixture):
    product_fixture.add_stock(50)
    assert product_fixture.stock == 150

def test_add_stock_negative_quantity(product_fixture):
    with pytest.raises(ValueError, match="Quantity must be positive"):
        product_fixture.add_stock(-10)

def test_remove_stock(product_fixture):
    result = product_fixture.remove_stock(50)
    assert result is True
    assert product_fixture.stock == 50

def test_remove_stock_exceeds_available(product_fixture):
    result = product_fixture.remove_stock(200)
    assert result is False
    assert product_fixture.stock == 100

def test_remove_stock_negative_quantity(product_fixture):
    with pytest.raises(ValueError, match="Quantity must be positive"):
        product_fixture.remove_stock(-10)

def test_update_price(product_fixture):
    product_fixture.update_price(12.50)
    assert product_fixture.price == 12.50

def test_update_price_negative(product_fixture):
    with pytest.raises(ValueError, match="Price cannot be negative"):
        product_fixture.update_price(-1.00)

def test_deactivate(product_fixture):
    product_fixture.deactivate()
    assert product_fixture.is_active is False

def test_reservation_initialization():
    reservation = StockReservation(product_id="1234", quantity=5)
    assert reservation.quantity == 5
    assert reservation.status == "pending"

def test_reservation_invalid_quantity():
    with pytest.raises(ValueError, match="Reservation quantity must be positive"):
        StockReservation(product_id="1234", quantity=-3)

def test_confirm_reservation(reservation):
    reservation = StockReservation(product_id="1234", quantity=5)
    reservation.confirm()
    assert reservation.status == "confirmed"

def test_release_reservation(reservation):
    reservation = StockReservation(product_id="1234", quantity=5)
    reservation.release()
    assert reservation.status == "released"

def test_release_reservation_invalid_status():
    reservation = StockReservation(product_id="1234", quantity=5)
    reservation.release()
    with pytest.raises(ValueError, match="Cannot release reservation in 'released' status"):
        reservation.release()

def test_warehouse_initialization():
    warehouse = Warehouse(name="Test Warehouse", location="Location", capacity=10000)
    assert warehouse.name == "Test Warehouse"
    assert warehouse.location == "Location"
    assert warehouse.capacity == 10000

def test_warehouse_negative_capacity():
    with pytest.raises(ValueError, match="Warehouse capacity must be positive"):
        Warehouse(name="Invalid Warehouse", location="Location", capacity=-100)

def test_add_stock_to_warehouse():
    warehouse = Warehouse(name="Test Warehouse", location="Location", capacity=10000)
    assert warehouse.add_stock("TP001", 100) is True
    assert warehouse.get_stock("TP001") == 100

def test_remove_stock_from_warehouse():
    warehouse = Warehouse(name="Test Warehouse", location="Location", capacity=10000)
    warehouse.add_stock("TP001", 100)
    assert warehouse.remove_stock("TP001", 50) is True
    assert warehouse.get_stock("TP001") == 50
