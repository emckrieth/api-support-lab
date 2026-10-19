"""Rule-based risk scoring for the lab's /risk/decisions endpoint.

Rules live in risk_rules.json so a support engineer can read exactly why a decision
was made and diff two rule versions when decisions change.
"""

import json
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).resolve().parent / "risk_rules.json"


def load_rules(path: Path = RULES_PATH) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def field_value(event: dict, field: str) -> Any:
    value: Any = event
    for part in field.split("."):
        value = value[part]
    return value


def signal_fires(event: dict, signal: dict) -> bool:
    observed = field_value(event, signal["field"])
    op = signal["op"]
    if op == "gt":
        return observed > signal["value"]
    if op == "lt":
        return observed < signal["value"]
    if op == "eq":
        return observed == signal["value"]
    if op == "ne_field":
        return str(observed).upper() != str(field_value(event, signal["value"])).upper()
    raise ValueError(f"Unsupported rule operator: {op}")


def score_event(event: dict, ruleset: dict) -> dict:
    fired = [signal for signal in ruleset["signals"] if signal_fires(event, signal)]
    score = min(100, sum(signal["points"] for signal in fired))
    thresholds = ruleset["thresholds"]
    if score >= thresholds["decline"]:
        decision = "decline"
    elif score >= thresholds["review"]:
        decision = "review"
    else:
        decision = "approve"
    reasons = sorted(
        ({"code": s["code"], "description": s["description"], "points": s["points"]} for s in fired),
        key=lambda reason: reason["points"],
        reverse=True,
    )
    return {"decision": decision, "risk_score": score, "reason_codes": reasons}
