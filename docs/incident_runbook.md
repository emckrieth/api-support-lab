# Incident Runbook

## Goal

Use this checklist to reproduce, scope, and communicate API verification issues clearly.

## Triage Steps

1. Confirm whether `/health` is returning `ok`.
2. Reproduce the customer request with the same request body and headers.
3. Capture the `x-request-id` returned by the API.
4. Check `/admin/logs` for related request and error events.
5. Toggle incident modes only in the local lab environment to reproduce expected failure patterns.

## Common Failure Modes

| Mode | Expected API Behavior | Support Interpretation |
| --- | --- | --- |
| `normal` | Verification succeeds or moves to review | Service is functioning |
| `timeout` | `504 Downstream provider timeout` | Provider or network dependency issue |
| `auth_error` | `502 Provider authentication failure` | Upstream credential/config issue |
| `validation_error` | Failed verification response | User input or document quality issue |

## Escalation Notes

Include the request ID, timestamp, endpoint, response code, payload shape, and the relevant log event when escalating to engineering.
