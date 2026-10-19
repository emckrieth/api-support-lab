# Observability

The lab exposes the three signals a support engineer uses to debug an API: request IDs that tie everything together, structured logs, and metrics with alerts.

## Request IDs

Every request gets one ID, shared by the handler, every log event, and the `x-request-id` response header. If the caller sends `x-request-id`, that value is used, so a customer's own correlation ID can be searched directly.

```bash
curl "http://127.0.0.1:8000/admin/logs?request_id=case-4821"
```

## Structured Logs

Events are JSON lines in `support_events.log`. Set `SUPPORT_LOG_PATH` to write somewhere else; the tests do this so they never modify the committed log.

| Event type | Written when | Key payload fields |
| --- | --- | --- |
| `http_request` | Every request except `/metrics` and `/admin/logs` | `method`, `route` (template, e.g. `/admin/incident-mode/{mode}`), `status`, `latency_ms` |
| `verification_request` / `verification_result` / `verification_error` | `POST /verifications` | request body, `status`, `reason`, error `type` |
| `risk_decision` | `POST /risk/decisions` succeeds | `event_id`, `decision`, `risk_score`, `reason_codes`, `rules_version`, full `input` |
| `risk_error` | Risk request fails auth or times out | `type`, `event_id` |
| `webhook_received` | `POST /webhooks/verification` | webhook payload |

`GET /admin/logs` filters by `request_id` and `event_type` and returns the most recent `limit` events.

The `risk_decision` event keeps the full scoring input so a decision can be replayed against another rules version (see `scripts/investigate_decisions.py`). In production, that input would be retained under the data handling policy and masked where required.

## Metrics

`GET /metrics` returns the Prometheus text format.

| Metric | Type | Labels | Use |
| --- | --- | --- | --- |
| `http_requests_total` | counter | `route`, `method`, `status` | Error rate by endpoint |
| `http_request_duration_seconds` | histogram | `route` | Latency percentiles |
| `risk_decisions_total` | counter | `decision`, `rules_version` | Approval rate, impact of a rules release |
| `risk_reason_codes_total` | counter | `code`, `decision` | Which signal is driving decisions |
| `verification_results_total` | counter | `status` | Verification outcomes |
| `app_incident_mode` | gauge | `mode` | Which lab scenario is active |
| `risk_rules_info` | gauge | `version` | Active rules version |

Routes are labeled by template, not raw path, so `/admin/incident-mode/timeout` and `/admin/incident-mode/normal` share one series. Unknown paths are labeled `unmatched`.

### Useful queries

```promql
# Approval rate over the last 15 minutes
sum(rate(risk_decisions_total{decision="approve"}[15m])) / sum(rate(risk_decisions_total[15m]))

# Decisions by rules version: shows the moment a release took effect
sum by (rules_version, decision) (rate(risk_decisions_total[5m]))

# Share of decisions each reason code fires on
sum by (code) (rate(risk_reason_codes_total[15m])) / scalar(sum(rate(risk_decisions_total[15m])))

# 5xx rate by route
sum by (route) (rate(http_requests_total{status=~"5.."}[5m])) / sum by (route) (rate(http_requests_total[5m]))

# p95 latency for risk decisions
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{route="/risk/decisions"}[5m])))
```

## Alerts

Defined in `monitoring/alert_rules.yml` and unit tested in `monitoring/alert_rules_test.yml`.

| Alert | Fires when | Severity | First step |
| --- | --- | --- | --- |
| `RiskApprovalRateDrop` | Approvals under 80% for 10 minutes | page | `docs/fraud-false-positive-runbook.md` |
| `RiskReasonCodeSurge` | One reason code on more than 40% of decisions for 10 minutes | ticket | Compare rules versions; check for a data change |
| `ApiHigh5xxRate` | More than 5% of requests return 5xx for 5 minutes | page | `docs/incident_runbook.md` |
| `RiskDecisionLatencyHigh` | p95 on `/risk/decisions` above 500 ms for 10 minutes | ticket | Check downstream provider latency |

The thresholds fit the sample traffic, which approves about 96% of decisions. A real deployment would set them from each customer's historical baseline.

## Running Prometheus

```bash
docker compose up --build
```

- API: http://localhost:8000/docs
- Prometheus: http://localhost:9090 (try the queries above, or open Alerts)

Validate the configuration without Docker using Prometheus's `promtool`:

```bash
promtool check rules monitoring/alert_rules.yml
promtool test rules monitoring/alert_rules_test.yml
```

## Production equivalents

The lab keeps everything dependency-free and local. In production the same ideas map to:

- **Metrics:** `prometheus_client` or OpenTelemetry metrics, scraped by Prometheus or a managed service
- **Logs:** JSON logs shipped to a log platform and searched by `request_id`
- **Traces:** OpenTelemetry spans carrying the same request ID across services and downstream providers
- **Dashboards:** an approval-rate panel annotated with rules releases is the single most useful view for this scenario
