"""
Order Management Module
=========================
Order lifecycle, cart management, discounts, and order history.

Classes:
    - OrderItem: Individual item in an order/cart
    - Cart: Shopping cart with add/remove/update
    - DiscountEngine: Discount calculation (percentage, flat, buy-X-get-Y)
    - Order: Order with state machine lifecycle
    - OrderService: Orchestrates order operations
"""

import uuid
from datetime import datetime, timezone
from typing import Optional


# -----------------------------
# DOMAIN MODELS
# -----------------------------

class OrderItem:
    def __init__(self, product_id: str, name: str, price: float, quantity: int = 1):
        if price < 0:
            raise ValueError("Price cannot be negative")
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        self.item_id = str(uuid.uuid4())
        self.product_id = product_id
        self.name = name
        self.price = round(price, 2)
        self.quantity = quantity

    @property
    def subtotal(self) -> float:
        return round(self.price * self.quantity, 2)

    def update_quantity(self, new_quantity: int):
        if new_quantity <= 0:
            raise ValueError("Quantity must be positive")
        self.quantity = new_quantity

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "product_id": self.product_id,
            "name": self.name,
            "price": self.price,
            "quantity": self.quantity,
            "subtotal": self.subtotal,
        }


# -----------------------------
# CART
# -----------------------------

class Cart:
    def __init__(self, user_id: str):
        self.cart_id = str(uuid.uuid4())
        self.user_id = user_id
        self.items = {}  # product_id -> OrderItem
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at

    def add_item(self, product_id: str, name: str, price: float, quantity: int = 1):
        if product_id in self.items:
            existing = self.items[product_id]
            existing.update_quantity(existing.quantity + quantity)
        else:
            self.items[product_id] = OrderItem(product_id, name, price, quantity)
        self.updated_at = datetime.now(timezone.utc)

    def remove_item(self, product_id: str) -> bool:
        if product_id not in self.items:
            return False
        del self.items[product_id]
        self.updated_at = datetime.now(timezone.utc)
        return True

    def update_quantity(self, product_id: str, quantity: int) -> bool:
        if product_id not in self.items:
            return False
        try:
            self.items[product_id].update_quantity(quantity)
        except ValueError:
            return False
        self.updated_at = datetime.now(timezone.utc)
        return True

    def clear(self):
        self.items.clear()
        self.updated_at = datetime.now(timezone.utc)

    @property
    def total(self) -> float:
        return round(sum(item.subtotal for item in self.items.values()), 2)

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items.values())

    def is_empty(self) -> bool:
        return len(self.items) == 0

    def to_dict(self) -> dict:
        return {
            "cart_id": self.cart_id,
            "user_id": self.user_id,
            "items": [item.to_dict() for item in self.items.values()],
            "total": self.total,
            "item_count": self.item_count,
        }


# -----------------------------
# DISCOUNT ENGINE
# -----------------------------

class DiscountEngine:
    """Calculates discounts on order totals."""

    VALID_TYPES = {"percentage", "flat", "buy_x_get_y"}

    def __init__(self):
        self.discounts = {}  # code -> discount_config

    def add_discount(self, code: str, discount_type: str, value: float,
                     min_order: float = 0, max_uses: int = -1, buy_x: int = 0, get_y: int = 0) -> dict:
        if discount_type not in self.VALID_TYPES:
            return {"success": False, "error": f"Invalid discount type: {discount_type}"}
        if code in self.discounts:
            return {"success": False, "error": f"Discount code '{code}' already exists"}
        if discount_type == "percentage" and not (0 < value <= 100):
            return {"success": False, "error": "Percentage must be between 0 and 100"}
        if discount_type == "flat" and value <= 0:
            return {"success": False, "error": "Flat discount must be positive"}

        self.discounts[code] = {
            "code": code,
            "type": discount_type,
            "value": value,
            "min_order": min_order,
            "max_uses": max_uses,
            "uses": 0,
            "buy_x": buy_x,
            "get_y": get_y,
            "is_active": True,
        }
        return {"success": True, "discount": self.discounts[code]}

    def apply_discount(self, code: str, order_total: float, item_count: int = 0) -> dict:
        if code not in self.discounts:
            return {"success": False, "error": "Invalid discount code"}

        discount = self.discounts[code]

        if not discount["is_active"]:
            return {"success": False, "error": "Discount code is no longer active"}

        if discount["max_uses"] > 0 and discount["uses"] >= discount["max_uses"]:
            return {"success": False, "error": "Discount code has been fully used"}

        if order_total < discount["min_order"]:
            return {"success": False, "error": f"Minimum order amount is ${discount['min_order']}"}

        if discount["type"] == "percentage":
            discount_amount = round(order_total * discount["value"] / 100, 2)
        elif discount["type"] == "flat":
            discount_amount = min(discount["value"], order_total)
        elif discount["type"] == "buy_x_get_y":
            if item_count >= discount["buy_x"] + discount["get_y"]:
                discount_amount = round(order_total * discount["get_y"] / item_count, 2)
            else:
                return {"success": False, "error": f"Need at least {discount['buy_x'] + discount['get_y']} items"}
        else:
            discount_amount = 0

        discount["uses"] += 1
        new_total = round(max(0, order_total - discount_amount), 2)

        return {
            "success": True,
            "original_total": order_total,
            "discount_amount": discount_amount,
            "new_total": new_total,
            "code": code,
        }

    def deactivate(self, code: str) -> bool:
        if code not in self.discounts:
            return False
        self.discounts[code]["is_active"] = False
        return True


# -----------------------------
# ORDER
# -----------------------------

class Order:
    """Order with state machine lifecycle."""

    VALID_TRANSITIONS = {
        "CREATED": {"CONFIRMED", "CANCELLED"},
        "CONFIRMED": {"SHIPPED", "CANCELLED"},
        "SHIPPED": {"DELIVERED"},
        "DELIVERED": {"RETURNED"},
        "CANCELLED": set(),
        "RETURNED": set(),
    }

    TAX_RATE = 0.08  # 8% tax

    def __init__(self, user_id: str, items: list, discount_amount: float = 0):
        if not items:
            raise ValueError("Order must have at least one item")

        self.order_id = str(uuid.uuid4())
        self.user_id = user_id
        self.items = items
        self.status = "CREATED"
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at
        self.status_history = [{"status": "CREATED", "timestamp": self.created_at.isoformat()}]

        subtotal = sum(item.subtotal for item in items)
        self.subtotal = round(subtotal, 2)
        self.discount_amount = round(min(discount_amount, subtotal), 2)
        self.tax = round((subtotal - self.discount_amount) * self.TAX_RATE, 2)
        self.total = round(self.subtotal - self.discount_amount + self.tax, 2)

    def transition_to(self, new_status: str) -> bool:
        allowed = self.VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            return False
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
        self.status_history.append({
            "status": new_status,
            "timestamp": self.updated_at.isoformat()
        })
        return True

    def can_cancel(self) -> bool:
        return "CANCELLED" in self.VALID_TRANSITIONS.get(self.status, set())

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "status": self.status,
            "items": [item.to_dict() for item in self.items],
            "subtotal": self.subtotal,
            "discount_amount": self.discount_amount,
            "tax": self.tax,
            "total": self.total,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status_history": self.status_history,
        }


# -----------------------------
# ORDER SERVICE
# -----------------------------

class OrderService:
    """Orchestrates order creation, status updates, and history."""

    def __init__(self, discount_engine: DiscountEngine = None):
        self.orders = {}  # order_id -> Order
        self.user_orders = {}  # user_id -> [order_id]
        self.carts = {}  # user_id -> Cart
        self.discount_engine = discount_engine or DiscountEngine()

    def get_or_create_cart(self, user_id: str) -> Cart:
        if user_id not in self.carts:
            self.carts[user_id] = Cart(user_id)
        return self.carts[user_id]

    def add_to_cart(self, user_id: str, product_id: str, name: str, price: float, quantity: int = 1) -> dict:
        cart = self.get_or_create_cart(user_id)
        try:
            cart.add_item(product_id, name, price, quantity)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        return {"success": True, "cart": cart.to_dict()}

    def checkout(self, user_id: str, discount_code: str = None) -> dict:
        if user_id not in self.carts or self.carts[user_id].is_empty():
            return {"success": False, "error": "Cart is empty"}

        cart = self.carts[user_id]
        discount_amount = 0

        if discount_code:
            result = self.discount_engine.apply_discount(discount_code, cart.total, cart.item_count)
            if not result["success"]:
                return result
            discount_amount = result["discount_amount"]

        items = list(cart.items.values())
        try:
            order = Order(user_id, items, discount_amount)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        self.orders[order.order_id] = order
        if user_id not in self.user_orders:
            self.user_orders[user_id] = []
        self.user_orders[user_id].append(order.order_id)

        # Clear the cart after successful checkout
        cart.clear()

        return {"success": True, "order": order.to_dict()}

    def update_order_status(self, order_id: str, new_status: str) -> dict:
        if order_id not in self.orders:
            return {"success": False, "error": "Order not found"}

        order = self.orders[order_id]
        if not order.transition_to(new_status):
            return {
                "success": False,
                "error": f"Cannot transition from '{order.status}' to '{new_status}'"
            }

        return {"success": True, "order": order.to_dict()}

    def cancel_order(self, order_id: str) -> dict:
        if order_id not in self.orders:
            return {"success": False, "error": "Order not found"}

        order = self.orders[order_id]
        if not order.can_cancel():
            return {"success": False, "error": f"Cannot cancel order in '{order.status}' status"}

        order.transition_to("CANCELLED")
        return {"success": True, "order": order.to_dict()}

    def get_order(self, order_id: str) -> Optional[dict]:
        order = self.orders.get(order_id)
        return order.to_dict() if order else None

    def get_user_orders(self, user_id: str, status_filter: str = None) -> list:
        order_ids = self.user_orders.get(user_id, [])
        results = []
        for oid in order_ids:
            order = self.orders.get(oid)
            if order:
                if status_filter and order.status != status_filter:
                    continue
                results.append(order.to_dict())
        return sorted(results, key=lambda x: x["created_at"], reverse=True)

    def get_order_summary(self) -> dict:
        summary = {"total_orders": len(self.orders), "by_status": {}, "total_revenue": 0}
        for order in self.orders.values():
            summary["by_status"][order.status] = summary["by_status"].get(order.status, 0) + 1
            if order.status not in ("CANCELLED", "RETURNED"):
                summary["total_revenue"] = round(summary["total_revenue"] + order.total, 2)
        return summary
