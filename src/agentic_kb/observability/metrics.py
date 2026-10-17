"""Prometheus metrics collector and OpenTelemetry-ready metrics registry.

Provides lightweight, dependency-free Prometheus exposition format (/metrics)
tracking HTTP requests, LLM token consumption, SQL validation failures,
and database query latencies.
"""

import time
from collections import defaultdict
from threading import Lock
from typing import Dict, List, Optional, Tuple


class MetricsCollector:
    """Thread-safe Prometheus metrics registry and collector."""

    def __init__(self):
        self._lock = Lock()

        # Counters: (name, label_tuple) -> count
        self._counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = defaultdict(float)

        # Histograms: (name, label_tuple) -> list of sample observations
        self._histograms: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], List[float]] = defaultdict(list)

        # Gauge values: (name, label_tuple) -> current value
        self._gauges: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}

    def inc_counter(self, name: str, amount: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric."""
        label_key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._counters[(name, label_key)] += amount

    def record_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record an observation in a histogram."""
        label_key = tuple(sorted((labels or {}).items()))
        with self._lock:
            # Keep up to 1000 latest samples for memory safety
            samples = self._histograms[(name, label_key)]
            if len(samples) > 1000:
                samples.pop(0)
            samples.append(value)

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge value."""
        label_key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._gauges[(name, label_key)] = value

    def to_prometheus_text(self) -> str:
        """Export all recorded metrics in the standard Prometheus text format."""
        lines: List[str] = []

        with self._lock:
            # Export Counters
            counter_groups: Dict[str, List[Tuple[Tuple[Tuple[str, str], ...], float]]] = defaultdict(list)
            for (name, label_key), val in self._counters.items():
                counter_groups[name].append((label_key, val))

            for name, items in sorted(counter_groups.items()):
                lines.append(f"# TYPE {name} counter")
                for label_key, val in items:
                    labels_str = ",".join(f'{k}="{v}"' for k, v in label_key)
                    label_part = f"{{{labels_str}}}" if labels_str else ""
                    lines.append(f"{name}{label_part} {val}")

            # Export Gauges
            gauge_groups: Dict[str, List[Tuple[Tuple[Tuple[str, str], ...], float]]] = defaultdict(list)
            for (name, label_key), val in self._gauges.items():
                gauge_groups[name].append((label_key, val))

            for name, items in sorted(gauge_groups.items()):
                lines.append(f"# TYPE {name} gauge")
                for label_key, val in items:
                    labels_str = ",".join(f'{k}="{v}"' for k, v in label_key)
                    label_part = f"{{{labels_str}}}" if labels_str else ""
                    lines.append(f"{name}{label_part} {val}")

            # Export Histograms (Count, Sum, and Buckets)
            histogram_groups: Dict[str, List[Tuple[Tuple[Tuple[str, str], ...], List[float]]]] = defaultdict(list)
            for (name, label_key), samples in self._histograms.items():
                histogram_groups[name].append((label_key, samples))

            for name, items in sorted(histogram_groups.items()):
                lines.append(f"# TYPE {name} histogram")
                for label_key, samples in items:
                    labels_dict = dict(label_key)
                    count = len(samples)
                    total_sum = sum(samples)

                    # Standard latency buckets in seconds
                    buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
                    for le in buckets:
                        b_count = sum(1 for s in samples if s <= le)
                        b_labels = dict(labels_dict)
                        b_labels["le"] = str(le)
                        b_str = ",".join(f'{k}="{v}"' for k, v in sorted(b_labels.items()))
                        lines.append(f"{name}_bucket{{{b_str}}} {b_count}")

                    # +Inf bucket
                    inf_labels = dict(labels_dict)
                    inf_labels["le"] = "+Inf"
                    inf_str = ",".join(f'{k}="{v}"' for k, v in sorted(inf_labels.items()))
                    lines.append(f"{name}_bucket{{{inf_str}}} {count}")

                    # Sum and Count
                    labels_str = ",".join(f'{k}="{v}"' for k, v in label_key)
                    label_part = f"{{{labels_str}}}" if labels_str else ""
                    lines.append(f"{name}_sum{label_part} {total_sum:.6f}")
                    lines.append(f"{name}_count{label_part} {count}")

        return "\n".join(lines) + "\n"


# Global singleton metrics collector
metrics_collector = MetricsCollector()


class MetricsTimer:
    """Context manager to measure and record execution time into a histogram."""

    def __init__(self, metric_name: str, labels: Optional[Dict[str, str]] = None):
        self.metric_name = metric_name
        self.labels = labels or {}
        self.start_time: float = 0.0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.perf_counter() - self.start_time
        metrics_collector.record_histogram(self.metric_name, duration, self.labels)
