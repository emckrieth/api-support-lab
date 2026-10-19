from datetime import datetime, timezone
import json
import os
from pathlib import Path
from time import perf_counter
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from .metrics import METRICS
from .models import (
    RiskDecisionRequest,
    RiskDecisionResponse,
    VerificationRequest,
    VerificationResponse,
)
from .risk import load_rules, score_event

app = FastAPI(title="API Support Lab", version="1.1.0")
DEFAULT_LOG_PATH = Path(__file__).resolve().parent.parent / "support_events.log"
LOG_PATH = Path(os.environ.get("SUPPORT_LOG_PATH", DEFAULT_LOG_PATH))
STATE = {"incident_mode": "normal"}
INCIDENT_MODES = {"normal", "timeout", "auth_error", "validation_error", "rules_regression"}
RULES = load_rules()
# Scrapes and log reads would drown out customer traffic in the access log.
UNLOGGED_PATHS = {"/metrics", "/admin/logs"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def log_event(event_type: str, request_id: str, payload: dict) -> None:
    event = {
        "timestamp": utcnow().isoformat(),
        "event_type": event_type,
        "request_id": request_id,
        "payload": payload,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def active_rules_version() -> str:
    if STATE["incident_mode"] == "rules_regression":
        return RULES["regression_version"]
    return RULES["active_version"]


@app.middleware("http")
async def request_context(request: Request, call_next):
    # One request ID per request, shared by the handler, the logs, and the response header.
    request_id = request.headers.get("x-request-id") or str(uuid4())
    request.state.request_id = request_id
    started = perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["x-request-id"] = request_id
        return response
    finally:
        elapsed = perf_counter() - started
        route = getattr(request.scope.get("route"), "path", "unmatched")
        METRICS.observe_request(route, request.method, status, elapsed)
        if request.url.path not in UNLOGGED_PATHS:
            log_event(
                "http_request",
                request_id,
                {"method": request.method, "route": route, "status": status, "latency_ms": round(elapsed * 1000, 2)},
            )


@app.get("/health")
def health():
    return {"status": "ok", "incident_mode": STATE["incident_mode"], "rules_version": active_rules_version()}


@app.post("/verifications", response_model=VerificationResponse)
def create_verification(
    body: VerificationRequest,
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
):
    request_id = request.state.request_id
    log_event("verification_request", request_id, body.model_dump())

    if x_api_key != "demo-key":
        log_event("verification_error", request_id, {"type": "auth_error"})
        raise HTTPException(status_code=401, detail="Invalid API key")

    mode = STATE["incident_mode"]
    if mode == "timeout":
        log_event(
            "verification_error",
            request_id,
            {"type": "timeout", "message": "Downstream provider timeout"},
        )
        raise HTTPException(status_code=504, detail="Downstream provider timeout")
    if mode == "auth_error":
        log_event("verification_error", request_id, {"type": "provider_auth_error"})
        raise HTTPException(status_code=502, detail="Provider authentication failure")
    if mode == "validation_error":
        log_event(
            "verification_result",
            request_id,
            {"status": "failed", "reason": "document image quality too low"},
        )
        METRICS.observe_verification("failed")
        return VerificationResponse(
            request_id=request_id,
            status="failed",
            reason="document image quality too low",
        )

    status = "review" if body.country.upper() != "US" else "approved"
    reason = None if status == "approved" else "manual review required for non-US document"
    result = VerificationResponse(request_id=request_id, status=status, reason=reason)
    log_event("verification_result", request_id, result.model_dump())
    METRICS.observe_verification(status)
    return result


@app.post("/risk/decisions", response_model=RiskDecisionResponse)
def create_risk_decision(
    body: RiskDecisionRequest,
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
):
    request_id = request.state.request_id
    if x_api_key != "demo-key":
        log_event("risk_error", request_id, {"type": "auth_error", "event_id": body.event_id})
        raise HTTPException(status_code=401, detail="Invalid API key")
    if STATE["incident_mode"] == "timeout":
        log_event(
            "risk_error",
            request_id,
            {"type": "timeout", "message": "Device intelligence provider timeout", "event_id": body.event_id},
        )
        raise HTTPException(status_code=504, detail="Device intelligence provider timeout")

    version = active_rules_version()
    result = score_event(body.model_dump(), RULES["versions"][version])
    codes = [reason["code"] for reason in result["reason_codes"]]
    log_event(
        "risk_decision",
        request_id,
        {
            "event_id": body.event_id,
            "user_id": body.user_id,
            "decision": result["decision"],
            "risk_score": result["risk_score"],
            "reason_codes": codes,
            "rules_version": version,
            # The full scoring input lets support replay a decision against another rules version.
            "input": body.model_dump(),
        },
    )
    METRICS.observe_decision(result["decision"], version, codes)
    return RiskDecisionResponse(request_id=request_id, event_id=body.event_id, rules_version=version, **result)


@app.post("/admin/incident-mode/{mode}")
def set_incident_mode(mode: str):
    if mode not in INCIDENT_MODES:
        raise HTTPException(status_code=400, detail="Unsupported mode")
    STATE["incident_mode"] = mode
    return {"incident_mode": mode, "rules_version": active_rules_version()}


@app.post("/webhooks/verification")
async def receive_webhook(request: Request):
    payload = await request.json()
    request_id = request.state.request_id
    log_event("webhook_received", request_id, payload)
    return JSONResponse({"received": True, "request_id": request_id})


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    return METRICS.render(STATE["incident_mode"], active_rules_version())


@app.get("/admin/logs")
def read_recent_logs(limit: int = 20, request_id: Optional[str] = None, event_type: Optional[str] = None):
    if not LOG_PATH.exists():
        return {"events": []}
    lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line) for line in lines if line.strip()]
    if request_id:
        events = [event for event in events if event["request_id"] == request_id]
    if event_type:
        events = [event for event in events if event["event_type"] == event_type]
    return {"events": events[-limit:]}
