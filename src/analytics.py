"""
Analytics & Metrics Module
=============================
Event tracking, metric aggregation, time-series bucketing, and trend analysis.

Classes:
    - Event: Analytics event domain model
    - MetricCollector: Collects and stores metrics
    - TimeSeriesBucket: Time-series data bucketing (hourly, daily, weekly)
    - TrendAnalyzer: Growth rate and anomaly detection
    - AnalyticsService: Orchestrates analytics operations
"""

import uuid
import statistics
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Optional


# -----------------------------
# DOMAIN MODELS
# -----------------------------

class Event:
    VALID_TYPES = {"page_view", "click", "purchase", "signup", "login", "error", "custom"}

    def __init__(self, event_type: str, user_id: str = None, properties: dict = None):
        if event_type not in self.VALID_TYPES:
            raise ValueError(f"Invalid event type: {event_type}. Must be one of {self.VALID_TYPES}")

        self.event_id = str(uuid.uuid4())
        self.event_type = event_type
        self.user_id = user_id
        self.properties = properties or {}
        self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "user_id": self.user_id,
            "properties": self.properties,
            "timestamp": self.timestamp.isoformat(),
        }


# -----------------------------
# METRIC COLLECTOR
# -----------------------------

class MetricCollector:
    """Collects numeric metrics and computes aggregations."""

    def __init__(self):
        self.metrics = defaultdict(list)  # metric_name -> [(timestamp, value)]

    def record(self, name: str, value: float, timestamp: datetime = None):
        if not isinstance(value, (int, float)):
            raise TypeError("Metric value must be numeric")
        ts = timestamp or datetime.now(timezone.utc)
        self.metrics[name].append((ts, value))

    def get_count(self, name: str) -> int:
        return len(self.metrics.get(name, []))

    def get_sum(self, name: str) -> float:
        values = [v for _, v in self.metrics.get(name, [])]
        return round(sum(values), 4) if values else 0

    def get_average(self, name: str) -> Optional[float]:
        values = [v for _, v in self.metrics.get(name, [])]
        if not values:
            return None
        return round(statistics.mean(values), 4)

    def get_min(self, name: str) -> Optional[float]:
        values = [v for _, v in self.metrics.get(name, [])]
        return min(values) if values else None

    def get_max(self, name: str) -> Optional[float]:
        values = [v for _, v in self.metrics.get(name, [])]
        return max(values) if values else None

    def get_percentile(self, name: str, percentile: float) -> Optional[float]:
        if not 0 <= percentile <= 100:
            raise ValueError("Percentile must be between 0 and 100")
        values = sorted([v for _, v in self.metrics.get(name, [])])
        if not values:
            return None
        if len(values) == 1:
            return values[0]
        # Linear interpolation
        index = (percentile / 100) * (len(values) - 1)
        lower = int(index)
        upper = min(lower + 1, len(values) - 1)
        fraction = index - lower
        return round(values[lower] + fraction * (values[upper] - values[lower]), 4)

    def get_stddev(self, name: str) -> Optional[float]:
        values = [v for _, v in self.metrics.get(name, [])]
        if len(values) < 2:
            return None
        return round(statistics.stdev(values), 4)

    def get_summary(self, name: str) -> dict:
        values = [v for _, v in self.metrics.get(name, [])]
        if not values:
            return {"count": 0, "sum": 0, "avg": None, "min": None, "max": None, "stddev": None}
        return {
            "count": len(values),
            "sum": round(sum(values), 4),
            "avg": self.get_average(name),
            "min": self.get_min(name),
            "max": self.get_max(name),
            "stddev": self.get_stddev(name),
            "p50": self.get_percentile(name, 50),
            "p95": self.get_percentile(name, 95),
            "p99": self.get_percentile(name, 99),
        }

    def list_metrics(self) -> list:
        return list(self.metrics.keys())

    def clear(self, name: str = None):
        if name:
            self.metrics.pop(name, None)
        else:
            self.metrics.clear()


# -----------------------------
# TIME SERIES BUCKETING
# -----------------------------

class TimeSeriesBucket:
    """Buckets time-series data into intervals for visualization."""

    VALID_INTERVALS = {"minute", "hour", "day", "week"}

    def __init__(self, interval: str = "hour"):
        if interval not in self.VALID_INTERVALS:
            raise ValueError(f"Invalid interval: {interval}. Must be one of {self.VALID_INTERVALS}")
        self.interval = interval

    def _get_bucket_key(self, timestamp: datetime) -> str:
        if self.interval == "minute":
            return timestamp.strftime("%Y-%m-%d %H:%M")
        elif self.interval == "hour":
            return timestamp.strftime("%Y-%m-%d %H:00")
        elif self.interval == "day":
            return timestamp.strftime("%Y-%m-%d")
        elif self.interval == "week":
            start_of_week = timestamp - timedelta(days=timestamp.weekday())
            return start_of_week.strftime("%Y-%m-%d")

    def bucket_events(self, events: list) -> dict:
        buckets = defaultdict(int)
        for event in events:
            key = self._get_bucket_key(event.timestamp)
            buckets[key] += 1
        return dict(sorted(buckets.items()))

    def bucket_values(self, data_points: list) -> dict:
        """Bucket (timestamp, value) pairs and aggregate with sum."""
        buckets = defaultdict(list)
        for timestamp, value in data_points:
            key = self._get_bucket_key(timestamp)
            buckets[key].append(value)

        result = {}
        for key in sorted(buckets.keys()):
            values = buckets[key]
            result[key] = {
                "count": len(values),
                "sum": round(sum(values), 4),
                "avg": round(statistics.mean(values), 4),
                "min": min(values),
                "max": max(values),
            }
        return result


# -----------------------------
# TREND ANALYZER
# -----------------------------

class TrendAnalyzer:
    """Analyzes trends in time-series data."""

    @staticmethod
    def growth_rate(values: list) -> Optional[float]:
        if len(values) < 2:
            return None
        if values[0] == 0:
            return None
        return round((values[-1] - values[0]) / abs(values[0]) * 100, 2)

    @staticmethod
    def moving_average(values: list, window: int = 3) -> list:
        if window <= 0:
            raise ValueError("Window must be positive")
        if len(values) < window:
            return []
        result = []
        for i in range(len(values) - window + 1):
            avg = round(statistics.mean(values[i:i + window]), 4)
            result.append(avg)
        return result

    @staticmethod
    def detect_anomalies(values: list, threshold: float = 2.0) -> list:
        if len(values) < 3:
            return []
        mean = statistics.mean(values)
        stddev = statistics.stdev(values)
        if stddev == 0:
            return []

        anomalies = []
        for i, value in enumerate(values):
            z_score = (value - mean) / stddev
            if abs(z_score) > threshold:
                anomalies.append({
                    "index": i,
                    "value": value,
                    "z_score": round(z_score, 4),
                    "type": "spike" if z_score > 0 else "dip"
                })
        return anomalies

    @staticmethod
    def is_trending_up(values: list, min_samples: int = 3) -> Optional[bool]:
        if len(values) < min_samples:
            return None
        increases = sum(1 for i in range(1, len(values)) if values[i] > values[i - 1])
        return increases > len(values) / 2


# -----------------------------
# ANALYTICS SERVICE
# -----------------------------

class AnalyticsService:
    """Orchestrates analytics operations."""

    def __init__(self):
        self.events = []
        self.metric_collector = MetricCollector()
        self.trend_analyzer = TrendAnalyzer()

    def track_event(self, event_type: str, user_id: str = None, properties: dict = None) -> dict:
        try:
            event = Event(event_type, user_id, properties)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        self.events.append(event)
        return {"success": True, "event": event.to_dict()}

    def record_metric(self, name: str, value: float) -> dict:
        try:
            self.metric_collector.record(name, value)
        except TypeError as e:
            return {"success": False, "error": str(e)}
        return {"success": True, "metric": name, "value": value}

    def get_event_counts(self, group_by_type: bool = True) -> dict:
        if not group_by_type:
            return {"total": len(self.events)}
        counts = defaultdict(int)
        for event in self.events:
            counts[event.event_type] += 1
        return dict(counts)

    def get_user_events(self, user_id: str) -> list:
        return [e.to_dict() for e in self.events if e.user_id == user_id]

    def get_events_in_range(self, start: datetime, end: datetime) -> list:
        return [e.to_dict() for e in self.events if start <= e.timestamp <= end]

    def get_metric_summary(self, name: str) -> dict:
        return self.metric_collector.get_summary(name)

    def get_time_series(self, event_type: str = None, interval: str = "hour") -> dict:
        filtered_events = self.events
        if event_type:
            filtered_events = [e for e in self.events if e.event_type == event_type]
        bucket = TimeSeriesBucket(interval)
        return bucket.bucket_events(filtered_events)

    def detect_metric_anomalies(self, name: str, threshold: float = 2.0) -> list:
        values = [v for _, v in self.metric_collector.metrics.get(name, [])]
        return self.trend_analyzer.detect_anomalies(values, threshold)

    def get_dashboard_data(self) -> dict:
        return {
            "total_events": len(self.events),
            "event_counts": self.get_event_counts(),
            "unique_users": len(set(e.user_id for e in self.events if e.user_id)),
            "metrics": {name: self.metric_collector.get_summary(name) for name in self.metric_collector.list_metrics()},
        }
