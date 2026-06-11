# Production Support Playbook

## Purpose

This playbook summarizes how I would approach a production API incident in a support engineering role.

## 1. Confirm Impact

- Identify affected endpoint, customer segment, and approximate start time.
- Check whether the issue affects all requests or only specific payloads/users.
- Prioritize based on severity, customer impact, and regulatory or business risk.

## 2. Reproduce Safely

- Reproduce with a known request body and correlation ID.
- Avoid changing production data unless an approved support process exists.
- Capture request path, response code, timestamp, and relevant headers.

## 3. Investigate Signals

- Check `/health` or equivalent service health endpoints.
- Review structured logs by request ID.
- Compare error patterns across recent requests.
- Separate application errors from downstream dependency, authentication, and validation failures.

## 4. Escalate Clearly

Include:

- impact summary
- reproduction steps
- request ID or correlation ID
- timestamp and endpoint
- observed vs. expected behavior
- relevant logs or query results
- suspected failure domain

## 5. Validate Resolution

- Re-run the original reproduction path.
- Confirm logs show expected behavior.
- Run automated tests where available.
- Document the outcome for future incidents.

## Production Skills Represented

- Application support triage
- Incident management
- Root cause investigation
- Vendor or engineering escalation
- Change validation
- Clear technical communication
