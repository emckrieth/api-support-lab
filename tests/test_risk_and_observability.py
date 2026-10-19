import json
import shutil
import sys
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as api
from app.risk import load_rules, score_event

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from investigate_decisions import investigate, load_decisions, render_markdown  # noqa: E402

client = TestClient(api.app)
HEADERS = {"x-api-key": "demo-key"}
RULES = load_rules()


def risk_event(**overrides):
    event = {
        "event_id": "evt-1",
        "user_id": "cust-1",
        "amount": 150.0,
        "currency": "USD",
        "billing_country": "US",
        "email_age_days": 400,
        "device": {"device_id": "dev-1", "ip_country": "US", "is_emulator": False, "velocity_1h": 1},
    }
    device = overrides.pop("device", {})
    event.update(overrides)
    event["device"].update(device)
    return event


def logged_events():
    return [json.loads(line) for line in api.LOG_PATH.read_text(encoding="utf-8").splitlines()]


class TestRiskRules:
    baseline = RULES["versions"]["2026.10.1"]
    regression = RULES["versions"]["2026.10.2"]

    def test_ordinary_purchase_is_approved(self):
        result = score_event(risk_event(), self.baseline)
        assert result == {"decision": "approve", "risk_score": 0, "reason_codes": []}

    def test_stacked_signals_decline_with_reasons_ordered_by_points(self):
        event = risk_event(device={"is_emulator": True, "velocity_1h": 9, "ip_country": "GB"})
        result = score_event(event, self.baseline)
        assert result["decision"] == "decline"
        assert result["risk_score"] == 85
        assert [reason["code"] for reason in result["reason_codes"]] == ["EMULATOR", "COUNTRY_MISMATCH", "HIGH_VELOCITY"]

    def test_country_comparison_ignores_case(self):
        result = score_event(risk_event(billing_country="us"), self.baseline)
        assert result["reason_codes"] == []

    def test_regression_rules_flag_ordinary_amounts(self):
        assert score_event(risk_event(), self.regression)["decision"] == "review"
        assert score_event(risk_event(email_age_days=2), self.regression)["decision"] == "review"
        assert score_event(risk_event(device={"ip_country": "CA"}), self.regression)["decision"] == "decline"


class TestRiskEndpoint:
    def test_requires_api_key(self):
        response = client.post("/risk/decisions", json=risk_event())
        assert response.status_code == 401

    def test_returns_decision_with_reason_codes_and_rules_version(self):
        response = client.post("/risk/decisions", json=risk_event(email_age_days=3), headers=HEADERS)
        body = response.json()
        assert response.status_code == 200
        assert body["decision"] == "approve"
        assert body["reason_codes"][0]["code"] == "NEW_EMAIL"
        assert body["rules_version"] == "2026.10.1"

    def test_rejects_invalid_payload(self):
        response = client.post("/risk/decisions", json=risk_event(amount=-5), headers=HEADERS)
        assert response.status_code == 422

    def test_rules_regression_mode_switches_version(self):
        assert client.post("/admin/incident-mode/rules_regression").json()["rules_version"] == "2026.10.2"
        assert client.get("/health").json()["rules_version"] == "2026.10.2"
        body = client.post("/risk/decisions", json=risk_event(), headers=HEADERS).json()
        assert body["decision"] == "review"
        assert body["rules_version"] == "2026.10.2"

    def test_timeout_mode_returns_504_and_logs_error(self):
        client.post("/admin/incident-mode/timeout")
        response = client.post("/risk/decisions", json=risk_event(), headers=HEADERS)
        assert response.status_code == 504
        errors = [e for e in logged_events() if e["event_type"] == "risk_error"]
        assert errors[0]["payload"]["type"] == "timeout"

    def test_decision_log_keeps_input_for_replay(self):
        client.post("/risk/decisions", json=risk_event(), headers=HEADERS)
        decision = next(e for e in logged_events() if e["event_type"] == "risk_decision")
        assert decision["payload"]["input"]["amount"] == 150.0
        assert decision["payload"]["rules_version"] == "2026.10.1"

    def test_unknown_incident_mode_is_rejected(self):
        assert client.post("/admin/incident-mode/chaos").status_code == 400


class TestObservability:
    def test_generated_request_id_matches_header_body_and_logs(self):
        response = client.post("/risk/decisions", json=risk_event(), headers=HEADERS)
        request_id = response.headers["x-request-id"]
        assert response.json()["request_id"] == request_id
        assert {e["request_id"] for e in logged_events()} == {request_id}

    def test_caller_request_id_is_propagated(self):
        response = client.post(
            "/verifications",
            json={"user_id": "u1", "document_type": "passport", "country": "US"},
            headers={**HEADERS, "x-request-id": "case-4821"},
        )
        assert response.headers["x-request-id"] == "case-4821"
        assert response.json()["request_id"] == "case-4821"

    def test_access_log_records_route_status_and_latency(self):
        client.post("/risk/decisions", json=risk_event(), headers={"x-request-id": "no-key"})
        access = next(e for e in logged_events() if e["event_type"] == "http_request")
        assert access["payload"]["route"] == "/risk/decisions"
        assert access["payload"]["status"] == 401
        assert access["payload"]["latency_ms"] >= 0

    def test_metrics_endpoint_exposes_decisions_and_templated_routes(self):
        client.post("/risk/decisions", json=risk_event(), headers=HEADERS)
        client.post("/admin/incident-mode/rules_regression")
        client.post("/risk/decisions", json=risk_event(), headers=HEADERS)
        response = client.get("/metrics")
        text = response.text
        assert response.headers["content-type"].startswith("text/plain")
        assert 'risk_decisions_total{decision="approve",rules_version="2026.10.1"} 1' in text
        assert 'risk_decisions_total{decision="review",rules_version="2026.10.2"} 1' in text
        assert 'risk_reason_codes_total{code="HIGH_AMOUNT",decision="review"} 1' in text
        assert 'route="/admin/incident-mode/{mode}"' in text
        assert 'risk_rules_info{version="2026.10.2"} 1' in text

    def test_metrics_and_log_reads_are_not_access_logged(self):
        client.get("/metrics")
        client.get("/admin/logs")
        assert not api.LOG_PATH.exists()

    def test_admin_logs_filter_by_request_id_and_event_type(self):
        client.post("/risk/decisions", json=risk_event(), headers={**HEADERS, "x-request-id": "find-me"})
        client.post("/risk/decisions", json=risk_event(), headers={**HEADERS, "x-request-id": "other"})
        events = client.get("/admin/logs", params={"request_id": "find-me", "event_type": "risk_decision"}).json()["events"]
        assert len(events) == 1
        assert events[0]["request_id"] == "find-me"


class TestInvestigation:
    def test_sample_log_finds_rules_regression(self):
        result = investigate(load_decisions(ROOT / "examples" / "decision_events.log"), RULES)
        finding = result["finding"]
        assert finding["approval_drop"] is True
        assert finding["driver_code"] == "HIGH_AMOUNT"
        assert (finding["previous_version"], finding["new_version"]) == ("2026.10.1", "2026.10.2")
        assert finding["impacted"] > 0
        assert "Approval drop confirmed" in render_markdown(result)

    def test_single_version_has_no_finding(self, tmp_path):
        client.post("/risk/decisions", json=risk_event(), headers=HEADERS)
        shutil.copy(api.LOG_PATH, tmp_path / "single.log")
        result = investigate(load_decisions(tmp_path / "single.log"), RULES)
        assert result["finding"] is None
        assert "nothing to compare" in render_markdown(result)
