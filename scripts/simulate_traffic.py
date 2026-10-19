"""Generate the sample decision log used by the false-positive investigation.

Sends fictional checkout traffic through the API in-process: two hours on the
baseline rules, then two hours after a bad rules release (incident mode
`rules_regression`). Timestamps come from a fixed clock and traffic from a fixed
seed, so the output is the same on every run.

Usage: python scripts/simulate_traffic.py [--output examples/decision_events.log]
"""

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import app.main as api  # noqa: E402
from app.metrics import METRICS  # noqa: E402

SEED = 20261014
START = datetime(2026, 10, 14, 13, 0, tzinfo=timezone.utc)
STEP = timedelta(seconds=30)
EVENTS_PER_PHASE = 240
COUNTRIES = ["US", "US", "US", "US", "CA", "GB", "DE", "MX"]


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class FakeTimer:
    """Stands in for perf_counter so every simulated request takes 6 ms and the log is reproducible."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> float:
        self.calls += 1
        return self.calls * 0.006


def build_event(rng: random.Random, index: int) -> dict:
    billing = rng.choice(COUNTRIES)
    mismatch = rng.random() < 0.08
    amount = round(min(4000, rng.lognormvariate(4.9, 0.8)), 2)
    return {
        "event_id": f"evt-{100000 + index}",
        "user_id": f"cust-{rng.randint(1000, 1999)}",
        "amount": amount,
        "currency": "USD",
        "billing_country": billing,
        "email_age_days": rng.randint(0, 6) if rng.random() < 0.12 else rng.randint(30, 2000),
        "device": {
            "device_id": f"dev-{rng.randint(10000, 99999)}",
            "ip_country": rng.choice([c for c in COUNTRIES if c != billing]) if mismatch else billing,
            "is_emulator": rng.random() < 0.02,
            "velocity_1h": rng.randint(6, 12) if rng.random() < 0.04 else rng.randint(0, 3),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=ROOT / "examples" / "decision_events.log")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("", encoding="utf-8")
    clock = Clock()
    api.LOG_PATH = args.output
    api.utcnow = clock
    api.perf_counter = FakeTimer()
    METRICS.reset()

    rng = random.Random(SEED)
    client = TestClient(api.app)
    headers = {"x-api-key": "demo-key"}
    index = 0
    for mode in ("normal", "rules_regression"):
        client.post("/admin/incident-mode/" + mode, headers={"x-request-id": f"admin-{mode}"})
        for _ in range(EVENTS_PER_PHASE):
            headers["x-request-id"] = f"req-{index:05d}"
            response = client.post("/risk/decisions", json=build_event(rng, index), headers=headers)
            response.raise_for_status()
            clock.now += STEP
            index += 1
    client.post("/admin/incident-mode/normal", headers={"x-request-id": "admin-reset"})
    print(f"Wrote {index} decisions to {args.output}")


if __name__ == "__main__":
    main()
