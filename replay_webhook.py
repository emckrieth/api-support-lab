from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional
import json
from pathlib import Path
from .models import VerificationRequest, VerificationResponse

app = FastAPI(title="API Support Lab", version="1.0.0")
LOG_PATH = Path(__file__).resolve().parent.parent / "support_events.log"
STATE = {"incident_mode": "normal"}


def log_event(event_type: str, request_id: str, payload: dict) -> None:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "request_id": request_id,
        "payload": payload,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid4()))
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.get("/health")
def health():
    return {"status": "ok", "incident_mode": STATE["incident_mode"]}


@app.post("/verifications", response_model=VerificationResponse)
def create_verification(body: VerificationRequest, x_api_key: Optional[str] = Header(default=None), x_request_id: Optional[str] = Header(default=None)):
    request_id = x_request_id or str(uuid4())
    log_event("verification_request", request_id, body.model_dump())

    if x_api_key != "demo-key":
        log_event("verification_error", request_id, {"type": "auth_error"})
        raise HTTPException(status_code=401, detail="Invalid API key")

    mode = STATE["incident_mode"]
    if mode == "timeout":
        log_event("verification_error", request_id, {"type": "timeout", "message": "Downstream provider timeout"})
        raise HTTPException(status_code=504, detail="Downstream provider timeout")
    if mode == "auth_error":
        log_event("verification_error", request_id, {"type": "provider_auth_error"})
        raise HTTPException(status_code=502, detail="Provider authentication failure")
    if mode == "validation_error":
        log_event("verification_result", request_id, {"status": "failed", "reason": "document image quality too low"})
        return VerificationResponse(request_id=request_id, status="failed", reason="document image quality too low")

    status = "review" if body.country.upper() != "US" else "approved"
    reason = None if status == "approved" else "manual review required for non-US document"
    result = VerificationResponse(request_id=request_id, status=status, reason=reason)
    log_event("verification_result", request_id, result.model_dump())
    return result


@app.post("/admin/incident-mode/{mode}")
def set_incident_mode(mode: str):
    if mode not in {"normal", "timeout", "auth_error", "validation_error"}:
        raise HTTPException(status_code=400, detail="Unsupported mode")
    STATE["incident_mode"] = mode
    return {"incident_mode": mode}


@app.post("/webhooks/verification")
async def receive_webhook(request: Request):
    payload = await request.json()
    request_id = request.headers.get("x-request-id", str(uuid4()))
    log_event("webhook_received", request_id, payload)
    return JSONResponse({"received": True, "request_id": request_id})


@app.get("/admin/logs")
def read_recent_logs(limit: int = 20):
    if not LOG_PATH.exists():
        return {"events": []}
    lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line) for line in lines[-limit:] if line.strip()]
    return {"events": events}
