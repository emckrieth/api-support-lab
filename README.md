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
?   ??? sample_bug_report.md
??? scripts/
?   ??? replay_webhook.py
??? tests/
?   ??? test_api.py
??? support_events.log
```

## Suggested GitHub Pin Description

Mock API and webhook troubleshooting lab for support engineering, incident reproduction, and diagnostics.
