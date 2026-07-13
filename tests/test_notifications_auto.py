import sys
import os
import pytest
import uuid
import json
from unittest.mock import patch, MagicMock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from notifications import *

def test_notification_initialization_valid():
    notification = Notification(user_id='user123', channel='email', subject='Test Subject', body='Test Body', priority='normal')
    assert notification.user_id == 'user123'
    assert notification.channel == 'email'
    assert notification.subject == 'Test Subject'
    assert notification.body == 'Test Body'
    assert notification.priority == 'normal'
    assert notification.status == 'pending'

def test_notification_initialization_invalid_channel():
    with pytest.raises(ValueError) as excinfo:
        Notification(user_id='user123', channel='invalid', subject='Subject', body='Body')
    assert str(excinfo.value) == "Invalid channel: invalid. Must be one of {'sms', 'push', 'email'}"

def test_notification_initialization_invalid_priority():
    with pytest.raises(ValueError) as excinfo:
        Notification(user_id='user123', channel='email', subject='Subject', body='Body', priority='invalid')
    assert str(excinfo.value) == "Invalid priority: invalid"

def test_notification_initialization_empty_subject_body():
    with pytest.raises(ValueError) as excinfo:
        Notification(user_id='user123', channel='email', subject='', body='')
    assert str(excinfo.value) == "Subject and body cannot be empty"

def test_notification_mark_sent():
    notification = Notification(user_id='user123', channel='email', subject='Subject', body='Body')
    notification.mark_sent()
    assert notification.status == 'sent'
    assert notification.sent_at is not None

def test_notification_mark_delivered():
    notification = Notification(user_id='user123', channel='email', subject='Subject', body='Body')
    notification.mark_delivered()
    assert notification.status == 'delivered'
    assert notification.delivered_at is not None

def test_notification_mark_failed_can_retry():
    notification = Notification(user_id='user123', channel='email', subject='Subject', body='Body')
    notification.mark_failed("Error occurred")
    assert notification.status == 'retrying'
    assert notification.retry_count == 1

def test_notification_mark_failed_exceeds_retries():
    notification = Notification(user_id='user123', channel='email', subject='Subject', body='Body')
    for _ in range(4):
        notification.mark_failed("Error occurred")
    assert notification.status == 'failed'
    assert notification.retry_count == 3

def test_template_initialization_valid():
    template = Template(name='Template1', subject_template='Subject {{var}}', body_template='Body {{var}}')
    assert template.name == 'Template1'

def test_template_initialization_empty_name():
    with pytest.raises(ValueError) as excinfo:
        Template(name='', subject_template='Subject {{var}}', body_template='Body {{var}}')
    assert str(excinfo.value) == "Template name cannot be empty"

def test_template_get_variables():
    template = Template(name='Template1', subject_template='Subject {{var1}}', body_template='Body {{var2}}')
    variables = template.get_variables()
    assert variables == {'var1', 'var2'}

def test_template_render_success():
    template = Template(name='Template1', subject_template='Subject {{name}}', body_template='Body {{name}}')
    rendered = template.render({'name': 'Alice'})
    assert rendered['subject'] == 'Subject Alice'
    assert rendered['body'] == 'Body Alice'

def test_template_render_missing_variable():
    template = Template(name='Template1', subject_template='Subject {{name}}', body_template='Body {{name}}')
    with pytest.raises(ValueError) as excinfo:
        template.render({'other': 'value'})
    assert str(excinfo.value) == "Missing template variables: {'name'}"

def test_delivery_channel_initialization_valid():
    channel = DeliveryChannel(channel_type='email', failure_rate=0.1)
    assert channel.channel_type == 'email'
    assert channel.failure_rate == 0.1

def test_delivery_channel_initialization_invalid_type():
    with pytest.raises(ValueError) as excinfo:
        DeliveryChannel(channel_type='invalid', failure_rate=0.0)
    assert str(excinfo.value) == "Invalid channel type: invalid"

def test_delivery_channel_initialization_invalid_failure_rate():
    with pytest.raises(ValueError) as excinfo:
        DeliveryChannel(channel_type='email', failure_rate=1.1)
    assert str(excinfo.value) == "Failure rate must be between 0 and 1"

def test_delivery_channel_send_success(monkeypatch):
    channel = DeliveryChannel(channel_type='email', failure_rate=0.0)
    notification = Notification(user_id='user123', channel='email', subject='Subject', body='Body')
    result = channel.send(notification)
    assert result is True
    assert channel.sent_count == 1

def test_delivery_channel_send_failure(monkeypatch):
    channel = DeliveryChannel(channel_type='email', failure_rate=1.0)  # 100% failure
    notification = Notification(user_id='user123', channel='email', subject='Subject', body='Body')
    result = channel.send(notification)
    assert result is False
    assert channel.failed_count == 1
