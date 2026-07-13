"""
Notification System Module
============================
Multi-channel notifications with templates, delivery tracking, and retry logic.

Classes:
    - Notification: Notification domain model with delivery status
    - Template: Notification template with variable substitution
    - DeliveryChannel: Abstract channel (Email, SMS, Push)
    - NotificationService: Orchestrates notification delivery and preferences
"""

import uuid
import re
import time
from datetime import datetime, timezone
from typing import Optional


# -----------------------------
# DOMAIN MODELS
# -----------------------------

class Notification:
    VALID_CHANNELS = {"email", "sms", "push"}
    VALID_PRIORITIES = {"low", "normal", "high", "urgent"}
    VALID_STATUSES = {"pending", "sent", "delivered", "failed", "retrying"}

    def __init__(self, user_id: str, channel: str, subject: str, body: str, priority: str = "normal"):
        if channel not in self.VALID_CHANNELS:
            raise ValueError(f"Invalid channel: {channel}. Must be one of {self.VALID_CHANNELS}")
        if priority not in self.VALID_PRIORITIES:
            raise ValueError(f"Invalid priority: {priority}")
        if not subject or not body:
            raise ValueError("Subject and body cannot be empty")

        self.notification_id = str(uuid.uuid4())
        self.user_id = user_id
        self.channel = channel
        self.subject = subject
        self.body = body
        self.priority = priority
        self.status = "pending"
        self.created_at = datetime.now(timezone.utc)
        self.sent_at = None
        self.delivered_at = None
        self.retry_count = 0
        self.max_retries = 3
        self.error_message = None

    def mark_sent(self):
        self.status = "sent"
        self.sent_at = datetime.now(timezone.utc)

    def mark_delivered(self):
        self.status = "delivered"
        self.delivered_at = datetime.now(timezone.utc)

    def mark_failed(self, error: str = None):
        self.error_message = error
        if self.retry_count < self.max_retries:
            self.status = "retrying"
            self.retry_count += 1
        else:
            self.status = "failed"

    def can_retry(self) -> bool:
        return self.status == "retrying" and self.retry_count <= self.max_retries

    def to_dict(self) -> dict:
        return {
            "notification_id": self.notification_id,
            "user_id": self.user_id,
            "channel": self.channel,
            "subject": self.subject,
            "body": self.body,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
        }


# -----------------------------
# TEMPLATES
# -----------------------------

class Template:
    """Notification template with {{variable}} substitution."""

    def __init__(self, name: str, subject_template: str, body_template: str):
        if not name:
            raise ValueError("Template name cannot be empty")
        self.template_id = str(uuid.uuid4())
        self.name = name
        self.subject_template = subject_template
        self.body_template = body_template
        self.created_at = datetime.now(timezone.utc)

    def get_variables(self) -> set:
        """Extract all {{variable}} placeholders from template."""
        pattern = r"\{\{(\w+)\}\}"
        vars_in_subject = set(re.findall(pattern, self.subject_template))
        vars_in_body = set(re.findall(pattern, self.body_template))
        return vars_in_subject | vars_in_body

    def render(self, variables: dict) -> dict:
        """Render template with given variables. Returns rendered subject and body."""
        required_vars = self.get_variables()
        missing_vars = required_vars - set(variables.keys())
        if missing_vars:
            raise ValueError(f"Missing template variables: {missing_vars}")

        subject = self.subject_template
        body = self.body_template
        for key, value in variables.items():
            placeholder = "{{" + key + "}}"
            subject = subject.replace(placeholder, str(value))
            body = body.replace(placeholder, str(value))

        return {"subject": subject, "body": body}

    def to_dict(self) -> dict:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "subject_template": self.subject_template,
            "body_template": self.body_template,
            "variables": list(self.get_variables()),
        }


# -----------------------------
# DELIVERY CHANNELS
# -----------------------------

class DeliveryChannel:
    """Simulated delivery channel for notifications."""

    def __init__(self, channel_type: str, failure_rate: float = 0.0):
        if channel_type not in Notification.VALID_CHANNELS:
            raise ValueError(f"Invalid channel type: {channel_type}")
        if not 0 <= failure_rate <= 1:
            raise ValueError("Failure rate must be between 0 and 1")
        self.channel_type = channel_type
        self.failure_rate = failure_rate
        self.sent_count = 0
        self.failed_count = 0
        self.is_enabled = True

    def send(self, notification: Notification) -> bool:
        if not self.is_enabled:
            return False

        import random
        if random.random() < self.failure_rate:
            self.failed_count += 1
            return False

        self.sent_count += 1
        return True

    def disable(self):
        self.is_enabled = False

    def enable(self):
        self.is_enabled = True

    def get_stats(self) -> dict:
        total = self.sent_count + self.failed_count
        return {
            "channel": self.channel_type,
            "sent": self.sent_count,
            "failed": self.failed_count,
            "total": total,
            "success_rate": round(self.sent_count / total, 4) if total > 0 else 0,
            "is_enabled": self.is_enabled,
        }


# -----------------------------
# NOTIFICATION SERVICE
# -----------------------------

class NotificationService:
    """Orchestrates notification delivery with templates and preferences."""

    def __init__(self):
        self.notifications = {}  # notification_id -> Notification
        self.templates = {}  # template_name -> Template
        self.preferences = {}  # user_id -> {channel: bool}
        self.channels = {}  # channel_type -> DeliveryChannel
        self.history = []  # list of notification_ids in order

    def register_channel(self, channel_type: str, failure_rate: float = 0.0) -> dict:
        try:
            channel = DeliveryChannel(channel_type, failure_rate)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        self.channels[channel_type] = channel
        return {"success": True, "channel": channel_type}

    def add_template(self, name: str, subject: str, body: str) -> dict:
        if name in self.templates:
            return {"success": False, "error": f"Template '{name}' already exists"}
        try:
            template = Template(name, subject, body)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        self.templates[name] = template
        return {"success": True, "template": template.to_dict()}

    def set_preferences(self, user_id: str, preferences: dict) -> dict:
        valid_prefs = {}
        for channel, enabled in preferences.items():
            if channel in Notification.VALID_CHANNELS:
                valid_prefs[channel] = bool(enabled)
        self.preferences[user_id] = valid_prefs
        return {"success": True, "preferences": valid_prefs}

    def get_preferences(self, user_id: str) -> dict:
        return self.preferences.get(user_id, {ch: True for ch in Notification.VALID_CHANNELS})

    def send_notification(self, user_id: str, channel: str, subject: str, body: str, priority: str = "normal") -> dict:
        # Check user preferences
        prefs = self.get_preferences(user_id)
        if not prefs.get(channel, True):
            return {"success": False, "error": f"User has disabled {channel} notifications"}

        # Check channel availability
        if channel not in self.channels:
            return {"success": False, "error": f"Channel '{channel}' not registered"}

        delivery_channel = self.channels[channel]
        if not delivery_channel.is_enabled:
            return {"success": False, "error": f"Channel '{channel}' is currently disabled"}

        try:
            notification = Notification(user_id, channel, subject, body, priority)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        # Attempt delivery
        success = delivery_channel.send(notification)
        if success:
            notification.mark_sent()
            notification.mark_delivered()
        else:
            notification.mark_failed("Delivery failed")

        self.notifications[notification.notification_id] = notification
        self.history.append(notification.notification_id)
        return {"success": success, "notification": notification.to_dict()}

    def send_from_template(self, user_id: str, channel: str, template_name: str, variables: dict, priority: str = "normal") -> dict:
        if template_name not in self.templates:
            return {"success": False, "error": f"Template '{template_name}' not found"}

        template = self.templates[template_name]
        try:
            rendered = template.render(variables)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        return self.send_notification(user_id, channel, rendered["subject"], rendered["body"], priority)

    def get_user_notifications(self, user_id: str, status_filter: str = None) -> list:
        results = []
        for notif in self.notifications.values():
            if notif.user_id != user_id:
                continue
            if status_filter and notif.status != status_filter:
                continue
            results.append(notif.to_dict())
        return sorted(results, key=lambda x: x["created_at"], reverse=True)

    def retry_failed(self, notification_id: str) -> dict:
        if notification_id not in self.notifications:
            return {"success": False, "error": "Notification not found"}

        notification = self.notifications[notification_id]
        if not notification.can_retry():
            return {"success": False, "error": "Notification cannot be retried"}

        channel = self.channels.get(notification.channel)
        if not channel:
            return {"success": False, "error": "Channel not available"}

        success = channel.send(notification)
        if success:
            notification.mark_sent()
            notification.mark_delivered()
        else:
            notification.mark_failed("Retry delivery failed")

        return {"success": success, "notification": notification.to_dict()}

    def get_delivery_stats(self) -> dict:
        stats = {
            "total_notifications": len(self.notifications),
            "by_status": {},
            "by_channel": {},
        }
        for notif in self.notifications.values():
            stats["by_status"][notif.status] = stats["by_status"].get(notif.status, 0) + 1
            stats["by_channel"][notif.channel] = stats["by_channel"].get(notif.channel, 0) + 1
        return stats
