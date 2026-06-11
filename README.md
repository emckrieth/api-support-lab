# API Support Lab

A small, fully functional support-engineering lab built to demonstrate API troubleshooting, webhook handling, incident reproduction, and structured diagnostics.

## What It Shows

- FastAPI service with health, verification, webhook, and admin incident endpoints
- Structured request logging with correlation IDs
- Simulated incident modes for reproducing common failures
- Basic automated tests for support-critical API behavior
- Example support documentation for escalation and incident handling

## Quick Start

### Local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

### Docker

```bash
docker build -t api-support-lab .
docker run -p 8000:8000 api-support-lab
```

## Example Flow

1. Check service health.

```bash
curl http://127.0.0.1:8000/health
```

2. Create a verification request.

```bash
curl -X POST http://127.0.0.1:8000/verifications \
  -H "Content-Type: application/json" \
  -H "x-api-key: demo-key" \
  -d '{"user_id":"u-100","document_type":"passport","country":"US"}'
```

3. Trigger a simulated downstream incident.

```bash
curl -X POST http://127.0.0.1:8000/admin/incident-mode/timeout
```

4. Re-run the verification request and inspect the error response and logs.

```bash
curl http://127.0.0.1:8000/admin/logs
```

## Support Scenarios Demonstrated

- Verify scope and reproduction steps
- Trace issues with request IDs
- Confirm health vs. functional failure
- Distinguish API timeout vs. validation failure vs. auth failure
- Capture a clean engineering escalation with logs and reproduction steps

## How This Maps to Production Support

This lab is designed around the same workflow used in production application support:

- triage an incident by impact, symptoms, and reproducibility
- use health checks, logs, and request IDs to narrow the failure path
- separate authentication, validation, timeout, and downstream dependency issues
- document a concise escalation with evidence for engineering or vendor partners
- validate expected behavior with repeatable test cases before and after a change

The project intentionally uses a small API so the support workflow is easy to inspect. In a real environment, the same approach would apply to larger systems running on Linux virtual machines, cloud infrastructure, and managed databases.

## ITIL-Style Support Practices Reflected

- **Incident management:** reproduce and classify user-facing failures quickly.
- **Problem management:** compare repeated error signatures to identify recurring root causes.
- **Change validation:** use tests and controlled incident modes to confirm behavior after fixes.
- **Knowledge management:** keep runbooks and bug reports clear enough for handoff.

## Project Structure

```text
api-support-lab/
??? README.md
??? Dockerfile
??? requirements.txt
??? app/
?   ??? __init__.py
?   ??? main.py
?   ??? models.py
??? docs/
?   ??? incident_runbook.md
?   ??? production_support_playbook.md
?   ??? sample_bug_report.md
??? scripts/
?   ??? replay_webhook.py
??? tests/
?   ??? test_api.py
??? support_events.log
```

## Suggested GitHub Pin Description

Mock API and webhook troubleshooting lab for support engineering, incident reproduction, and diagnostics.
