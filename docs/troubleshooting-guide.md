# Troubleshooting Guide

Use this guide to connect a user-facing symptom to the evidence that should be checked before escalation.

| Symptom | Evidence to check | Likely cause | Next action |
| --- | --- | --- | --- |
| API returns 401 | Request headers and `x-api-key` value | Missing or invalid API key | Confirm caller configuration and retry with a valid key |
| API returns 422 | Request body and validation error | Required field missing or invalid data type | Correct payload and rerun the request |
| API returns 504 | `/health` incident mode, `verification_error` or `risk_error` events | Downstream provider timeout | Capture request ID, impact, and failure mode for escalation |
| API returns 502 | `verification_error` event with `provider_auth_error` | Upstream credential or configuration issue | Escalate to Engineering with request IDs; customer action is not needed |
| Legitimate users declined or sent to review | `risk_decision` events by request ID, `risk_decisions_total`, `risk_rules_info` | Rules change or a dominant reason code | Follow `docs/fraud-false-positive-runbook.md` and run `scripts/investigate_decisions.py` |
| Customer cannot find their request in logs | Their `x-request-id` value and `/admin/logs?request_id=` | Caller did not send a request ID, or used a different one | Ask for the `x-request-id` response header from their side |
| Webhook replay fails | Webhook payload, target URL, and response body | Endpoint unavailable or payload rejected | Confirm endpoint health and replay with a known-good payload |
| Health check passes but function fails | `/health`, request logs, and endpoint-specific response | Partial application or dependency issue | Escalate with reproduction steps and request IDs |

## Escalation Checklist

Before escalating, include:

- endpoint called
- request method
- timestamp
- request ID or correlation ID
- rules version and reason codes, for risk decisions
- relevant metric (error rate, approval rate) and when it changed
- sanitized payload
- response code
- response body
- reproduction steps
- expected result
- actual result

This keeps the handoff useful for engineering or vendor support teams.
