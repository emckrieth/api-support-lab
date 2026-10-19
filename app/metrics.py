"""In-process metrics in the Prometheus text exposition format.

Kept dependency-free so the lab runs anywhere. In production this would be the
prometheus_client library or OpenTelemetry; the metric names and labels are what matter.
"""

from collections import defaultdict
from threading import Lock

LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)


class Metrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.requests = defaultdict(int)
            self.latency_buckets = defaultdict(lambda: [0] * len(LATENCY_BUCKETS))
            self.latency_sum = defaultdict(float)
            self.latency_count = defaultdict(int)
            self.decisions = defaultdict(int)
            self.reason_codes = defaultdict(int)
            self.verifications = defaultdict(int)

    def observe_request(self, route: str, method: str, status: int, seconds: float) -> None:
        with self._lock:
            self.requests[(route, method, str(status))] += 1
            buckets = self.latency_buckets[route]
            for index, bound in enumerate(LATENCY_BUCKETS):
                if seconds <= bound:
                    buckets[index] += 1
            self.latency_sum[route] += seconds
            self.latency_count[route] += 1

    def observe_decision(self, decision: str, rules_version: str, reason_codes: list[str]) -> None:
        with self._lock:
            self.decisions[(decision, rules_version)] += 1
            for code in reason_codes:
                self.reason_codes[(code, decision)] += 1

    def observe_verification(self, status: str) -> None:
        with self._lock:
            self.verifications[status] += 1

    def render(self, incident_mode: str, rules_version: str) -> str:
        lines: list[str] = []

        def block(name: str, kind: str, help_text: str) -> None:
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {kind}")

        with self._lock:
            block("http_requests_total", "counter", "HTTP requests by route, method, and status code.")
            for (route, method, status), count in sorted(self.requests.items()):
                lines.append(f'http_requests_total{{route="{route}",method="{method}",status="{status}"}} {count}')

            block("http_request_duration_seconds", "histogram", "Request latency by route.")
            for route in sorted(self.latency_buckets):
                for bound, count in zip(LATENCY_BUCKETS, self.latency_buckets[route]):
                    lines.append(f'http_request_duration_seconds_bucket{{route="{route}",le="{bound}"}} {count}')
                lines.append(f'http_request_duration_seconds_bucket{{route="{route}",le="+Inf"}} {self.latency_count[route]}')
                lines.append(f'http_request_duration_seconds_sum{{route="{route}"}} {self.latency_sum[route]:.6f}')
                lines.append(f'http_request_duration_seconds_count{{route="{route}"}} {self.latency_count[route]}')

            block("risk_decisions_total", "counter", "Risk decisions by outcome and rules version.")
            for (decision, version), count in sorted(self.decisions.items()):
                lines.append(f'risk_decisions_total{{decision="{decision}",rules_version="{version}"}} {count}')

            block("risk_reason_codes_total", "counter", "Reason codes attached to risk decisions.")
            for (code, decision), count in sorted(self.reason_codes.items()):
                lines.append(f'risk_reason_codes_total{{code="{code}",decision="{decision}"}} {count}')

            block("verification_results_total", "counter", "Verification results by status.")
            for status, count in sorted(self.verifications.items()):
                lines.append(f'verification_results_total{{status="{status}"}} {count}')

        block("app_incident_mode", "gauge", "Active simulated incident mode (1 = active).")
        lines.append(f'app_incident_mode{{mode="{incident_mode}"}} 1')
        block("risk_rules_info", "gauge", "Active risk rules version.")
        lines.append(f'risk_rules_info{{version="{rules_version}"}} 1')
        return "\n".join(lines) + "\n"


METRICS = Metrics()
