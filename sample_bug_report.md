from pydantic import BaseModel, Field
from typing import Literal, Optional

class VerificationRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    document_type: Literal['passport', 'drivers_license', 'id_card']
    country: str = Field(..., min_length=2, max_length=2)

class VerificationResponse(BaseModel):
    request_id: str
    status: Literal['approved', 'review', 'failed']
    reason: Optional[str] = None

class IncidentModeChange(BaseModel):
    mode: Literal['normal', 'timeout', 'auth_error', 'validation_error']
