"""
Inventory Management Module
=============================
Product catalog, stock management, reservations, and warehouse tracking.

Classes:
    - Product: Product domain model with stock tracking
    - Warehouse: Multi-warehouse support with transfer capabilities
    - StockReservation: Reservation system (reserve → confirm/release)
    - InventoryService: Orchestrates inventory operations
"""

import uuid
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional


# -----------------------------
# DOMAIN MODELS
# -----------------------------

class Product:
    VALID_CATEGORIES = {"electronics", "clothing", "food", "books", "toys", "other"}

    def __init__(self, name: str, sku: str, price: float, category: str = "other", stock: int = 0):
        if not name or len(name.strip()) == 0:
            raise ValueError("Product name cannot be empty")
        if price < 0:
            raise ValueError("Price cannot be negative")
        if stock < 0:
            raise ValueError("Initial stock cannot be negative")
        if category not in self.VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {category}")

        self.product_id = str(uuid.uuid4())
        self.name = name.strip()
        self.sku = sku
        self.price = round(price, 2)
        self.category = category
        self.stock = stock
        self.reserved = 0
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at
        self.is_active = True

    @property
    def available_stock(self) -> int:
        return max(0, self.stock - self.reserved)

    def add_stock(self, quantity: int):
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        self.stock += quantity
        self.updated_at = datetime.now(timezone.utc)

    def remove_stock(self, quantity: int) -> bool:
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if quantity > self.available_stock:
            return False
        self.stock -= quantity
        self.updated_at = datetime.now(timezone.utc)
        return True

    def update_price(self, new_price: float):
        if new_price < 0:
            raise ValueError("Price cannot be negative")
        self.price = round(new_price, 2)
        self.updated_at = datetime.now(timezone.utc)

    def deactivate(self):
        self.is_active = False
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "sku": self.sku,
            "price": self.price,
            "category": self.category,
            "stock": self.stock,
            "reserved": self.reserved,
            "available_stock": self.available_stock,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# -----------------------------
# STOCK RESERVATION
# -----------------------------

class StockReservation:
    """Represents a temporary stock reservation that must be confirmed or released."""

    STATUSES = {"pending", "confirmed", "released", "expired"}

    def __init__(self, product_id: str, quantity: int, ttl_minutes: int = 30):
        if quantity <= 0:
            raise ValueError("Reservation quantity must be positive")
        self.reservation_id = str(uuid.uuid4())
        self.product_id = product_id
        self.quantity = quantity
        self.status = "pending"
        self.created_at = datetime.now(timezone.utc)
        self.expires_at = self.created_at + timedelta(minutes=ttl_minutes)

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at and self.status == "pending"

    def confirm(self):
        if self.status != "pending":
            raise ValueError(f"Cannot confirm reservation in '{self.status}' status")
        if self.is_expired():
            self.status = "expired"
            raise ValueError("Reservation has expired")
        self.status = "confirmed"

    def release(self):
        if self.status not in ("pending", "expired"):
            raise ValueError(f"Cannot release reservation in '{self.status}' status")
        self.status = "released"

    def to_dict(self) -> dict:
        return {
            "reservation_id": self.reservation_id,
            "product_id": self.product_id,
            "quantity": self.quantity,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }


# -----------------------------
# WAREHOUSE
# -----------------------------

class Warehouse:
    def __init__(self, name: str, location: str, capacity: int = 10000):
        if capacity <= 0:
            raise ValueError("Warehouse capacity must be positive")
        self.warehouse_id = str(uuid.uuid4())
        self.name = name
        self.location = location
        self.capacity = capacity
        self.stock = {}  # sku -> quantity

    @property
    def total_items(self) -> int:
        return sum(self.stock.values())

    @property
    def remaining_capacity(self) -> int:
        return max(0, self.capacity - self.total_items)

    def add_stock(self, sku: str, quantity: int) -> bool:
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if quantity > self.remaining_capacity:
            return False
        self.stock[sku] = self.stock.get(sku, 0) + quantity
        return True

    def remove_stock(self, sku: str, quantity: int) -> bool:
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        current = self.stock.get(sku, 0)
        if quantity > current:
            return False
        self.stock[sku] = current - quantity
        if self.stock[sku] == 0:
            del self.stock[sku]
        return True

    def get_stock(self, sku: str) -> int:
        return self.stock.get(sku, 0)

    def to_dict(self) -> dict:
        return {
            "warehouse_id": self.warehouse_id,
            "name": self.name,
            "location": self.location,
            "capacity": self.capacity,
            "total_items": self.total_items,
            "remaining_capacity": self.remaining_capacity,
            "stock": dict(self.stock),
        }


# -----------------------------
# INVENTORY SERVICE
# -----------------------------

class InventoryService:
    """Orchestrates inventory operations across products and warehouses."""

    def __init__(self):
        self.products = {}  # product_id -> Product
        self.skus = {}  # sku -> product_id
        self.reservations = {}  # reservation_id -> StockReservation
        self.warehouses = {}  # warehouse_id -> Warehouse
        self.low_stock_threshold = 10

    def add_product(self, name: str, sku: str, price: float, category: str = "other", stock: int = 0) -> dict:
        if sku in self.skus:
            return {"success": False, "error": f"SKU '{sku}' already exists"}

        try:
            product = Product(name, sku, price, category, stock)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        self.products[product.product_id] = product
        self.skus[sku] = product.product_id
        return {"success": True, "product": product.to_dict()}

    def get_product(self, product_id: str) -> Optional[dict]:
        product = self.products.get(product_id)
        if not product:
            return None
        return product.to_dict()

    def search_products(self, query: str = "", category: str = None, in_stock_only: bool = False) -> list:
        results = []
        for product in self.products.values():
            if not product.is_active:
                continue
            if query and query.lower() not in product.name.lower():
                continue
            if category and product.category != category:
                continue
            if in_stock_only and product.available_stock <= 0:
                continue
            results.append(product.to_dict())
        return results

    def restock(self, product_id: str, quantity: int) -> dict:
        if product_id not in self.products:
            return {"success": False, "error": "Product not found"}
        try:
            self.products[product_id].add_stock(quantity)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        return {"success": True, "new_stock": self.products[product_id].stock}

    def reserve_stock(self, product_id: str, quantity: int) -> dict:
        if product_id not in self.products:
            return {"success": False, "error": "Product not found"}

        product = self.products[product_id]
        if quantity > product.available_stock:
            return {"success": False, "error": "Insufficient stock"}

        try:
            reservation = StockReservation(product_id, quantity)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        product.reserved += quantity
        self.reservations[reservation.reservation_id] = reservation
        return {"success": True, "reservation": reservation.to_dict()}

    def confirm_reservation(self, reservation_id: str) -> dict:
        if reservation_id not in self.reservations:
            return {"success": False, "error": "Reservation not found"}

        reservation = self.reservations[reservation_id]
        product = self.products.get(reservation.product_id)

        try:
            reservation.confirm()
        except ValueError as e:
            if product:
                product.reserved -= reservation.quantity
            return {"success": False, "error": str(e)}

        if product:
            product.reserved -= reservation.quantity
            product.stock -= reservation.quantity

        return {"success": True, "reservation": reservation.to_dict()}

    def release_reservation(self, reservation_id: str) -> dict:
        if reservation_id not in self.reservations:
            return {"success": False, "error": "Reservation not found"}

        reservation = self.reservations[reservation_id]
        product = self.products.get(reservation.product_id)

        try:
            reservation.release()
        except ValueError as e:
            return {"success": False, "error": str(e)}

        if product:
            product.reserved -= reservation.quantity

        return {"success": True, "reservation": reservation.to_dict()}

    def get_low_stock_alerts(self) -> list:
        alerts = []
        for product in self.products.values():
            if product.is_active and product.available_stock <= self.low_stock_threshold:
                alerts.append({
                    "product_id": product.product_id,
                    "name": product.name,
                    "sku": product.sku,
                    "available_stock": product.available_stock,
                    "threshold": self.low_stock_threshold,
                })
        return alerts

    def transfer_stock(self, from_warehouse_id: str, to_warehouse_id: str, sku: str, quantity: int) -> dict:
        if from_warehouse_id not in self.warehouses:
            return {"success": False, "error": "Source warehouse not found"}
        if to_warehouse_id not in self.warehouses:
            return {"success": False, "error": "Destination warehouse not found"}

        source = self.warehouses[from_warehouse_id]
        dest = self.warehouses[to_warehouse_id]

        if not source.remove_stock(sku, quantity):
            return {"success": False, "error": "Insufficient stock in source warehouse"}
        if not dest.add_stock(sku, quantity):
            source.add_stock(sku, quantity)  # Rollback
            return {"success": False, "error": "Destination warehouse at capacity"}

        return {"success": True, "transferred": quantity, "sku": sku}

    def add_warehouse(self, name: str, location: str, capacity: int = 10000) -> dict:
        try:
            warehouse = Warehouse(name, location, capacity)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        self.warehouses[warehouse.warehouse_id] = warehouse
        return {"success": True, "warehouse": warehouse.to_dict()}
