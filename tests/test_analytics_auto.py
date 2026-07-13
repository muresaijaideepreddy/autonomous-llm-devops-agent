import sys
import os
import pytest
import uuid
import json
from unittest.mock import patch, MagicMock

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, SRC_DIR)

from analytics import *

def test_event_creation_success():
    event = Event("page_view", user_id="user_123")
    assert event.event_type == "page_view"
    assert event.user_id == "user_123"

def test_event_creation_invalid_type():
    with pytest.raises(ValueError):
        Event("invalid_event_type")

def test_event_to_dict():
    event = Event("click", user_id="user_456", properties={"key": "value"})
    event_dict = event.to_dict()
    assert event_dict["event_type"] == "click"
    assert event_dict["user_id"] == "user_456"
    assert event_dict["properties"] == {"key": "value"}

def test_metric_collector_record_success():
    collector = MetricCollector()
    collector.record("metric1", 10)
    assert collector.get_count("metric1") == 1
    assert collector.get_sum("metric1") == 10

def test_metric_collector_record_invalid_value():
    collector = MetricCollector()
    with pytest.raises(TypeError):
        collector.record("metric2", "non_numeric")

def test_metric_collector_get_average_empty():
    collector = MetricCollector()
    assert collector.get_average("metric3") is None

def test_metric_collector_get_summary():
    collector = MetricCollector()
    collector.record("metric4", 20)
    collector.record("metric4", 30)
    summary = collector.get_summary("metric4")
    assert summary["count"] == 2
    assert summary["sum"] == 50

def test_time_series_bucket_invalid_interval():
    with pytest.raises(ValueError):
        TimeSeriesBucket("invalid_interval")

def test_time_series_bucket_event_bucketing():
    bucket = TimeSeriesBucket("hour")
    now = datetime.now(timezone.utc)
    events = [
        Event("page_view", properties={"time": "1"}, timestamp=now),
        Event("page_view", properties={"time": "2"}, timestamp=now + timedelta(hours=1)),
    ]
    result = bucket.bucket_events(events)
    assert len(result) == 2

def test_trend_analyzer_growth_rate():
    values = [10, 20, 30]
    assert TrendAnalyzer.growth_rate(values) == 200.0

def test_trend_analyzer_growth_rate_no_change():
    values = [10, 10, 10]
    assert TrendAnalyzer.growth_rate(values) is None

def test_trend_analyzer_moving_average_success():
    values = [10, 20, 30]
    result = TrendAnalyzer.moving_average(values, window=2)
    assert result == [15.0, 25.0]

def test_trend_analyzer_moving_average_invalid_window():
    with pytest.raises(ValueError):
        TrendAnalyzer.moving_average([1, 2, 3], window=0)

def test_trend_analyzer_detect_anomalies_success():
    values = [10, 20, 70, 15, 10]
    anomalies = TrendAnalyzer.detect_anomalies(values)
    assert len(anomalies) == 1

def test_trend_analyzer_is_trending_up():
    values = [1, 2, 3, 2]
    assert TrendAnalyzer.is_trending_up(values) == False

def test_analytics_service_track_event_success():
    service = AnalyticsService()
    response = service.track_event("signup", user_id="user_789")
    assert response["success"] is True

def test_analytics_service_track_event_invalid_type():
    service = AnalyticsService()
    response = service.track_event("invalid_event")
    assert response["success"] is False

def test_analytics_service_get_event_counts():
    service = AnalyticsService()
    service.track_event("click")
    service.track_event("click")
    service.track_event("purchase")
    counts = service.get_event_counts()
    assert counts["click"] == 2
    assert counts["purchase"] == 1

def test_analytics_service_get_user_events():
    service = AnalyticsService()
    service.track_event("login", user_id="user_999")
    events = service.get_user_events("user_999")
    assert len(events) == 1

def test_analytics_service_get_metric_summary():
    service = AnalyticsService()
    service.record_metric("metric1", 10)
    summary = service.get_metric_summary("metric1")
    assert summary["count"] == 1

def test_analytics_service_get_dashboard_data():
    service = AnalyticsService()
    service.track_event("error")
    dashboard_data = service.get_dashboard_data()
    assert dashboard_data["total_events"] == 1
