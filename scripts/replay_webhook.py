import json
from uuid import uuid4

import httpx


WEBHOOK_URL = "http://127.0.0.1:8000/webhooks/verification"

payload = {
    "verification_id": "verif-100",
    "status": "approved",
    "user_id": "u-100",
}
headers = {
    "content-type": "application/json",
    "x-request-id": str(uuid4()),
}

response = httpx.post(WEBHOOK_URL, data=json.dumps(payload), headers=headers, timeout=10)
print(response.status_code)
print(response.json())
