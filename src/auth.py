"""
Authentication & Authorization Module
=======================================
User registration, login, JWT token management, and role-based access control.

Classes:
    - User: User domain model with password hashing
    - TokenManager: JWT token generation and validation
    - AuthService: Registration, login, and session management
    - RateLimiter: Brute-force protection with account lockout
"""

import hashlib
import hmac
import json
import os
import time
import uuid
import base64
from datetime import datetime, timezone, timedelta


# -----------------------------
# DOMAIN MODELS
# -----------------------------

class User:
    VALID_ROLES = {"admin", "user", "guest"}

    def __init__(self, username: str, email: str, password: str, role: str = "user"):
        if not username or len(username) < 3:
            raise ValueError("Username must be at least 3 characters")
        if "@" not in email or "." not in email:
            raise ValueError("Invalid email format")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        if role not in self.VALID_ROLES:
            raise ValueError(f"Invalid role: {role}. Must be one of {self.VALID_ROLES}")

        self.user_id = str(uuid.uuid4())
        self.username = username
        self.email = email.lower()
        self.password_hash = self._hash_password(password)
        self.role = role
        self.created_at = datetime.now(timezone.utc)
        self.is_active = True
        self.last_login = None
        self.failed_login_attempts = 0
        self.locked_until = None

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = "devops_agent_salt_2026"
        return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()

    def verify_password(self, password: str) -> bool:
        return self.password_hash == self._hash_password(password)

    def is_locked(self) -> bool:
        if self.locked_until is None:
            return False
        if datetime.now(timezone.utc) > self.locked_until:
            self.locked_until = None
            self.failed_login_attempts = 0
            return False
        return True

    def record_failed_login(self, max_attempts: int = 5, lockout_minutes: int = 15):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= max_attempts:
            self.locked_until = datetime.now(timezone.utc) + timedelta(minutes=lockout_minutes)

    def record_successful_login(self):
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_login = datetime.now(timezone.utc)

    def deactivate(self):
        self.is_active = False

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }


# -----------------------------
# TOKEN MANAGEMENT
# -----------------------------

class TokenManager:
    """Simple JWT-like token manager using HMAC signatures."""

    def __init__(self, secret_key: str = "default_secret_key_2026", token_ttl_minutes: int = 60):
        self.secret_key = secret_key
        self.token_ttl = timedelta(minutes=token_ttl_minutes)
        self.revoked_tokens = set()

    def generate_token(self, user: User) -> str:
        payload = {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + self.token_ttl).isoformat(),
            "token_id": str(uuid.uuid4()),
        }
        payload_json = json.dumps(payload, sort_keys=True)
        payload_b64 = base64.b64encode(payload_json.encode()).decode()
        signature = hmac.new(self.secret_key.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        return f"{payload_b64}.{signature}"

    def validate_token(self, token: str) -> dict:
        if not token or "." not in token:
            return {"valid": False, "error": "Malformed token"}

        if token in self.revoked_tokens:
            return {"valid": False, "error": "Token has been revoked"}

        try:
            payload_b64, signature = token.rsplit(".", 1)
        except ValueError:
            return {"valid": False, "error": "Invalid token format"}

        expected_sig = hmac.new(self.secret_key.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return {"valid": False, "error": "Invalid signature"}

        try:
            payload_json = base64.b64decode(payload_b64).decode()
            payload = json.loads(payload_json)
        except Exception:
            return {"valid": False, "error": "Cannot decode payload"}

        expires_at = datetime.fromisoformat(payload["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            return {"valid": False, "error": "Token expired"}

        return {"valid": True, "payload": payload}

    def revoke_token(self, token: str):
        self.revoked_tokens.add(token)


# -----------------------------
# RATE LIMITER
# -----------------------------

class RateLimiter:
    """Simple in-memory rate limiter for login attempts."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}  # ip -> list of timestamps

    def is_allowed(self, ip_address: str) -> bool:
        now = time.time()
        if ip_address not in self.requests:
            self.requests[ip_address] = []

        # Clean old entries
        self.requests[ip_address] = [
            t for t in self.requests[ip_address]
            if now - t < self.window_seconds
        ]

        if len(self.requests[ip_address]) >= self.max_requests:
            return False

        self.requests[ip_address].append(now)
        return True

    def get_remaining(self, ip_address: str) -> int:
        now = time.time()
        if ip_address not in self.requests:
            return self.max_requests
        recent = [t for t in self.requests[ip_address] if now - t < self.window_seconds]
        return max(0, self.max_requests - len(recent))

    def reset(self, ip_address: str):
        self.requests.pop(ip_address, None)


# -----------------------------
# AUTH SERVICE
# -----------------------------

class AuthService:
    """Main authentication service orchestrating users, tokens, and rate limiting."""

    def __init__(self, token_manager: TokenManager = None, rate_limiter: RateLimiter = None):
        self.users = {}  # username -> User
        self.emails = {}  # email -> username (for uniqueness check)
        self.token_manager = token_manager or TokenManager()
        self.rate_limiter = rate_limiter or RateLimiter()

    def register(self, username: str, email: str, password: str, role: str = "user") -> dict:
        if username in self.users:
            return {"success": False, "error": "Username already exists"}

        email_lower = email.lower()
        if email_lower in self.emails:
            return {"success": False, "error": "Email already registered"}

        try:
            user = User(username, email, password, role)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        self.users[username] = user
        self.emails[email_lower] = username
        return {"success": True, "user": user.to_dict()}

    def login(self, username: str, password: str, ip_address: str = "127.0.0.1") -> dict:
        if not self.rate_limiter.is_allowed(ip_address):
            return {"success": False, "error": "Rate limit exceeded. Try again later."}

        if username not in self.users:
            return {"success": False, "error": "Invalid credentials"}

        user = self.users[username]

        if not user.is_active:
            return {"success": False, "error": "Account is deactivated"}

        if user.is_locked():
            return {"success": False, "error": "Account is locked due to too many failed attempts"}

        if not user.verify_password(password):
            user.record_failed_login()
            remaining = 5 - user.failed_login_attempts
            return {"success": False, "error": f"Invalid credentials. {max(0, remaining)} attempts remaining"}

        user.record_successful_login()
        token = self.token_manager.generate_token(user)
        return {"success": True, "token": token, "user": user.to_dict()}

    def logout(self, token: str) -> dict:
        self.token_manager.revoke_token(token)
        return {"success": True, "message": "Logged out successfully"}

    def get_user(self, username: str) -> dict:
        if username not in self.users:
            return {"success": False, "error": "User not found"}
        return {"success": True, "user": self.users[username].to_dict()}

    def deactivate_user(self, username: str, admin_token: str) -> dict:
        result = self.token_manager.validate_token(admin_token)
        if not result["valid"]:
            return {"success": False, "error": "Invalid or expired token"}

        if result["payload"]["role"] != "admin":
            return {"success": False, "error": "Admin privileges required"}

        if username not in self.users:
            return {"success": False, "error": "User not found"}

        self.users[username].deactivate()
        return {"success": True, "message": f"User {username} deactivated"}

    def change_password(self, username: str, old_password: str, new_password: str) -> dict:
        if username not in self.users:
            return {"success": False, "error": "User not found"}

        user = self.users[username]
        if not user.verify_password(old_password):
            return {"success": False, "error": "Current password is incorrect"}

        if len(new_password) < 8:
            return {"success": False, "error": "New password must be at least 8 characters"}

        user.password_hash = user._hash_password(new_password)
        return {"success": True, "message": "Password changed successfully"}

    def list_users(self, admin_token: str) -> dict:
        result = self.token_manager.validate_token(admin_token)
        if not result["valid"]:
            return {"success": False, "error": "Invalid or expired token"}

        if result["payload"]["role"] != "admin":
            return {"success": False, "error": "Admin privileges required"}

        return {
            "success": True,
            "users": [u.to_dict() for u in self.users.values()]
        }
