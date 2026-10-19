# API Support Lab

A small, fully functional support-engineering lab built to demonstrate API troubleshooting, webhook handling, incident reproduction, fraud decision investigation, and observability.

## What It Shows

- FastAPI service with health, verification, risk decision, webhook, metrics, and admin incident endpoints
- Rule-based fraud risk scoring with explainable reason codes and versioned rules
- Structured JSON logs with one request ID shared across the response header, handler, and every log event
- Prometheus metrics, alert rules, and alert unit tests, with a Docker Compose setup for Prometheus
- A false-positive investigation script that replays decisions against the previous rules version
- Simulated incident modes for reproducing common failures, including a bad rules release
- Automated tests and CI for support-critical API behavior
- Support documentation for escalation, incident handling, and fraud false positives

## Quick Start

### Local

Recommended Python version: 3.12. The pinned FastAPI and Pydantic stack is tested with Python 3.12. Very recent Python versions may require native package builds that are not needed for normal use.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

Run the tests:

```bash
pytest -q
```

### Docker

```bash
docker build -t api-support-lab .
docker run -p 8000:8000 api-support-lab
```

### Docker Compose with Prometheus

```bash
docker compose up --build
```

API at `http://localhost:8000/docs`, Prometheus at `http://localhost:9090`. See `docs/observability.md` for queries and alerts.

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

5. Score a checkout with the risk decision endpoint.

```bash
curl -X POST http://127.0.0.1:8000/risk/decisions \
  -H "Content-Type: application/json" \
  -H "x-api-key: demo-key" \
  -H "x-request-id: case-4821" \
  -d '{"event_id":"evt-1","user_id":"cust-1","amount":180,"currency":"USD","billing_country":"US","email_age_days":400,"device":{"device_id":"dev-1","ip_country":"US","is_emulator":false,"velocity_1h":1}}'
```

The response includes the decision, risk score, reason codes, and rules version.

6. Simulate a bad rules release, then send the same request again. The decision changes to `review` with reason code `HIGH_AMOUNT`.

```bash
curl -X POST http://127.0.0.1:8000/admin/incident-mode/rules_regression
```

7. Trace the request and check the metrics.

```bash
curl "http://127.0.0.1:8000/admin/logs?request_id=case-4821"
curl http://127.0.0.1:8000/metrics
```

## Fraud Scenario: Legitimate Customers Blocked

A customer reports that real users are being declined at checkout. The lab reproduces the incident end to end:

1. `scripts/simulate_traffic.py` sends four hours of fictional checkout traffic: two hours on rules `2026.10.1`, then two hours after release `2026.10.2`, which set the `HIGH_AMOUNT` limit to 100 instead of 1000. The output is `examples/decision_events.log`.
2. `scripts/investigate_decisions.py` reads the log, compares decision rates by rules version, finds the reason code driving the change, and re-scores every decision on the previous rules.
3. The result, `examples/false-positive-investigation.md`, shows the approval rate falling 58 points. It also reports the replay: 145 decisions would have been approved on the previous rules. It ends with a ready-to-send escalation note.

```bash
python scripts/simulate_traffic.py
python scripts/investigate_decisions.py
```

The matching runbook is `docs/fraud-false-positive-runbook.md`, and the `RiskApprovalRateDrop` alert in `monitoring/alert_rules.yml` is built to catch this before customers report it.

## Observability

- **Request IDs:** the caller's `x-request-id` is used if sent, otherwise one is generated. Either way it appears in the response header, the response body, and every log event for that request.
- **Logs:** JSON lines with an `http_request` access event (route, status, latency) plus endpoint events. `GET /admin/logs` filters by `request_id` and `event_type`. Set `SUPPORT_LOG_PATH` to change the log file.
- **Metrics:** `GET /metrics` exposes request counts, latency histograms, risk decisions by rules version, reason codes, and the active incident mode.
- **Alerts:** approval rate drop, reason code surge, 5xx rate, and decision latency, each unit tested with `promtool test rules`.

Details and example queries are in `docs/observability.md`.

## Support Scenarios Demonstrated

- Verify scope and reproduction steps
- Trace issues with request IDs
- Confirm health vs. functional failure
- Distinguish API timeout vs. validation failure vs. auth failure
- Capture a clean engineering escalation with logs and reproduction steps
- Explain a fraud decision from its reason codes and rules version
- Confirm a platform-wide false-positive spike with metrics and quantify it with a replay
- Tie an incident to a release by watching decisions by rules version

See `docs/troubleshooting-guide.md` for a support-focused symptom-to-action guide.

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
|-- README.md
|-- Dockerfile
|-- docker-compose.yml
|-- requirements.txt
|-- .github/workflows/tests.yml
|-- app/
|   |-- __init__.py
|   |-- main.py
|   |-- metrics.py
|   |-- models.py
|   |-- risk.py
|   `-- risk_rules.json
|-- docs/
|   |-- fraud-false-positive-runbook.md
|   |-- incident_runbook.md
|   |-- observability.md
|   |-- production_support_playbook.md
|   |-- sample_bug_report.md
|   `-- troubleshooting-guide.md
|-- examples/
|   |-- decision_events.log
|   `-- false-positive-investigation.md
|-- monitoring/
|   |-- alert_rules.yml
|   |-- alert_rules_test.yml
|   `-- prometheus.yml
|-- scripts/
|   |-- investigate_decisions.py
|   |-- replay_webhook.py
|   `-- simulate_traffic.py
|-- tests/
|   |-- conftest.py
|   |-- test_api.py
|   `-- test_risk_and_observability.py
`-- support_events.log
```

## Suggested GitHub Pin Description

Mock API and fraud decision lab for support engineering: incident reproduction, false-positive investigation, structured logs, Prometheus metrics, and alerts.
