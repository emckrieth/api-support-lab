from typing import Literal, Optional

from pydantic import BaseModel, Field


class VerificationRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    document_type: Literal["passport", "drivers_license", "id_card"]
    country: str = Field(..., min_length=2, max_length=2)


class VerificationResponse(BaseModel):
    request_id: str
    status: Literal["approved", "review", "failed"]
    reason: Optional[str] = None


IncidentMode = Literal["normal", "timeout", "auth_error", "validation_error", "rules_regression"]


class IncidentModeChange(BaseModel):
    mode: IncidentMode


class DeviceSignals(BaseModel):
    device_id: str = Field(..., min_length=1)
    ip_country: str = Field(..., min_length=2, max_length=2)
    is_emulator: bool = False
    velocity_1h: int = Field(0, ge=0, description="Attempts from this device in the last hour")


class RiskDecisionRequest(BaseModel):
    event_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    currency: str = Field(..., min_length=3, max_length=3)
    billing_country: str = Field(..., min_length=2, max_length=2)
    email_age_days: int = Field(..., ge=0)
    device: DeviceSignals


class ReasonCode(BaseModel):
    code: str
    description: str
    points: int


class RiskDecisionResponse(BaseModel):
    request_id: str
    event_id: str
    decision: Literal["approve", "review", "decline"]
    risk_score: int
    reason_codes: list[ReasonCode]
    rules_version: str
