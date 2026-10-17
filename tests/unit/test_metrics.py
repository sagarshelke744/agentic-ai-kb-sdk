"""Unit tests for Prometheus metrics registry and exposition format."""

import time
from agentic_kb.observability.metrics import MetricsCollector, MetricsTimer


def test_metrics_collector_counter():
    collector = MetricsCollector()
    collector.inc_counter("test_requests_total", amount=1.0, labels={"status": "200", "method": "POST"})
    collector.inc_counter("test_requests_total", amount=2.0, labels={"status": "200", "method": "POST"})
    collector.inc_counter("test_requests_total", amount=1.0, labels={"status": "500", "method": "GET"})

    text = collector.to_prometheus_text()
    assert "# TYPE test_requests_total counter" in text
    assert 'test_requests_total{method="POST",status="200"} 3.0' in text
    assert 'test_requests_total{method="GET",status="500"} 1.0' in text


def test_metrics_collector_gauge():
    collector = MetricsCollector()
    collector.set_gauge("active_connections", 5.0, labels={"pool": "main"})
    text = collector.to_prometheus_text()
    assert "# TYPE active_connections gauge" in text
    assert 'active_connections{pool="main"} 5.0' in text

    collector.set_gauge("active_connections", 2.0, labels={"pool": "main"})
    text_updated = collector.to_prometheus_text()
    assert 'active_connections{pool="main"} 2.0' in text_updated


def test_metrics_collector_histogram_and_timer():
    collector = MetricsCollector()
    collector.record_histogram("db_latency_seconds", 0.05, labels={"db": "postgres"})
    collector.record_histogram("db_latency_seconds", 0.15, labels={"db": "postgres"})

    text = collector.to_prometheus_text()
    assert "# TYPE db_latency_seconds histogram" in text
    assert 'db_latency_seconds_count{db="postgres"} 2' in text
    assert 'db_latency_seconds_sum{db="postgres"} 0.200000' in text
    assert 'db_latency_seconds_bucket{db="postgres",le="0.05"} 1' in text
    assert 'db_latency_seconds_bucket{db="postgres",le="+Inf"} 2' in text


def test_metrics_timer_context():
    with MetricsTimer("test_timer_duration_seconds", labels={"scope": "unit_test"}):
        time.sleep(0.01)
