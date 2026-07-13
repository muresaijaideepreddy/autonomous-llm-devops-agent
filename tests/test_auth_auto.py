import sys
import os
import pytest
import uuid
import json
from unittest.mock import patch, MagicMock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from auth import *

@pytest.fixture
def user():
    return User("testuser", "test@example.com", "password123", "user")

@pytest.fixture
def admin_user():
    return User("adminuser", "admin@example.com", "password123", "admin")

def test_user_initialization(user):
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.role == "user"
    assert user.is_active is True

def test_user_invalid_username():
    with pytest.raises(ValueError, match="Username must be at least 3 characters"):
        User("ab", "test@example.com", "password123")

def test_user_invalid_email():
    with pytest.raises(ValueError, match="Invalid email format"):
        User("testuser", "invalidemail", "password123")

def test_user_invalid_password():
    with pytest.raises(ValueError, match="Password must be at least 8 characters"):
        User("testuser", "test@example.com", "short")

def test_user_invalid_role():
    with pytest.raises(ValueError, match="Invalid role: invalid_role. Must be one of {'admin', 'user', 'guest'}"):
        User("testuser", "test@example.com", "password123", "invalid_role")

def test_verify_password(user):
    assert user.verify_password("password123") is True
    assert user.verify_password("wrongpassword") is False

def test_is_locked(user):
    assert user.is_locked() is False
    user.record_failed_login()
    assert user.is_locked() is False
    user.record_failed_login(5)
    assert user.is_locked() is True

def test_record_successful_login(user):
    user.record_failed_login()
    user.record_successful_login()
    assert user.failed_login_attempts == 0
    assert user.locked_until is None

def test_deactivate_user(user):
    user.deactivate()
    assert user.is_active is False

def test_to_dict(user):
    user_dict = user.to_dict()
    assert user_dict["username"] == "testuser"
    assert "user_id" in user_dict
    assert user_dict["is_active"] is True

def test_generate_token(user):
    token_manager = TokenManager()
    token = token_manager.generate_token(user)
    assert isinstance(token, str)

def test_validate_token_valid():
    token_manager = TokenManager()
    user = User("testuser", "test@example.com", "password123")
    token = token_manager.generate_token(user)
    result = token_manager.validate_token(token)
    assert result["valid"] is True

def test_validate_token_invalid_signature():
    token_manager = TokenManager()
    user = User("testuser", "test@example.com", "password123")
    token = token_manager.generate_token(user)
    tampered_token = token[:-1] + "x"
    result = token_manager.validate_token(tampered_token)
    assert result["valid"] is False

def test_revoke_token():
    token_manager = TokenManager()
    user = User("testuser", "test@example.com", "password123")
    token = token_manager.generate_token(user)
    token_manager.revoke_token(token)
    result = token_manager.validate_token(token)
    assert result["valid"] is False

def test_register_user():
    auth_service = AuthService()
    result = auth_service.register("newuser", "new@example.com", "securepassword", "user")
    assert result["success"] is True

def test_register_existing_username():
    auth_service = AuthService()
    auth_service.register("existinguser", "test@example.com", "password123")
    result = auth_service.register("existinguser", "new@example.com", "password123")
    assert result["success"] is False

def test_login_success(user):
    auth_service = AuthService()
    auth_service.register("testuser", "test@example.com", "password123")
    result = auth_service.login("testuser", "password123")
    assert result["success"] is True

def test_login_invalid_credentials(user):
    auth_service = AuthService()
    auth_service.register("testuser", "test@example.com", "password123")
    result = auth_service.login("testuser", "wrongpassword")
    assert result["success"] is False

def test_logout():
    auth_service = AuthService()
    user = User("testuser", "test@example.com", "password123")
    token_manager = TokenManager()
    token = token_manager.generate_token(user)
    result = auth_service.logout(token)
    assert result["success"] is True

def test_change_password(user):
    auth_service = AuthService()
    auth_service.register("testuser", "test@example.com", "password123")
    result = auth_service.change_password("testuser", "password123", "newpassword123")
    assert result["success"] is True
