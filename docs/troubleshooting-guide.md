# Troubleshooting Guide

Use this guide to connect a user-facing symptom to the evidence that should be checked before escalation.

| Symptom | Evidence to check | Likely cause | Next action |
| --- | --- | --- | --- |
| API returns 401 | Request headers and `x-api-key` value | Missing or invalid API key | Confirm caller configuration and retry with a valid key |
| API returns 422 | Request body and validation error | Required field missing or invalid data type | Correct payload and rerun the request |
| API returns 503 | Incident mode and logs | Simulated downstream dependency failure | Capture request ID, impact, and failure mode for escalation |
| Webhook replay fails | Webhook payload, target URL, and response body | Endpoint unavailable or payload rejected | Confirm endpoint health and replay with a known-good payload |
| Health check passes but function fails | `/health`, request logs, and endpoint-specific response | Partial application or dependency issue | Escalate with reproduction steps and request IDs |

## Escalation Checklist

Before escalating, include:

- endpoint called
- request method
- timestamp
- request ID or correlation ID
- sanitized payload
- response code
- response body
- reproduction steps
- expected result
- actual result

This keeps the handoff useful for engineering or vendor support teams.
