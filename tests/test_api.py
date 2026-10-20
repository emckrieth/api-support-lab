import json

from fastapi.testclient import TestClient

import app.main as api
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_verification_requires_api_key():
    response = client.post(
        "/verifications",
        json={"user_id": "u1", "document_type": "passport", "country": "US"},
    )
    assert response.status_code == 401


def test_verification_success():
    response = client.post(
        "/verifications",
        headers={"x-api-key": "demo-key"},
        json={"user_id": "u1", "document_type": "passport", "country": "US"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_webhook_acknowledges_and_logs_with_request_id():
    payload = {"verification_id": "verif-100", "status": "approved", "user_id": "u-100"}
    response = client.post("/webhooks/verification", json=payload, headers={"x-request-id": "hook-1"})
    assert response.status_code == 200
    assert response.json() == {"received": True, "request_id": "hook-1"}
    assert response.headers["x-request-id"] == "hook-1"
    events = [json.loads(line) for line in api.LOG_PATH.read_text(encoding="utf-8").splitlines()]
    webhook = next(e for e in events if e["event_type"] == "webhook_received")
    assert webhook["request_id"] == "hook-1"
    assert webhook["payload"] == payload
