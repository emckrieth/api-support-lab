# Runbook: Legitimate Customers Are Being Blocked

Use this when a customer reports that real users are being declined or sent to manual review by `POST /risk/decisions`. In a fraud platform this is one of the most common and most urgent enterprise tickets: every false positive is a lost sale and a frustrated end user.

## 1. Scope the report (first reply, within SLA)

Ask for, or pull from the ticket:

- 3-5 example `request_id` or `event_id` values, with timestamps (UTC)
- When they first noticed it, and whether anything changed on their side (new checkout flow, new market, SDK upgrade)
- Rough impact: share of checkouts affected, revenue at risk
- Whether they want affected users to retry or to be approved manually

Set priority from impact, not tone. A broad drop in approvals is P1 or P2. A handful of users with risky signals is P3.

## 2. Is it one customer or the platform?

| Check | Where | What it tells you |
| --- | --- | --- |
| Approval rate across all traffic | `risk_decisions_total` by `decision` | Platform-wide drop means a rules or data change, not this customer's users |
| Active rules version | `/health`, `risk_rules_info` | A version that changed near the start time is the first suspect |
| Reason code mix | `risk_reason_codes_total` by `code` | One code suddenly dominating points to a rule or data change, not a fraud wave |
| Incident mode (lab only) | `/health`, `app_incident_mode` | Confirms which scenario the lab is simulating |

If approvals dropped across every customer at the same moment, treat it as an incident and follow `docs/incident_runbook.md` alongside this runbook.

## 3. Read the decisions

For each example request:

```bash
curl "http://127.0.0.1:8000/admin/logs?request_id=<request_id>"
```

The `risk_decision` event shows the decision, score, reason codes, rules version, and the full scoring input. Look for:

- **Reason codes that do not fit the input.** For example, `HIGH_AMOUNT` on a $150 purchase.
- **The same code on every example.** That is a rule problem.
- **Genuinely risky signals**, such as an emulator, a velocity burst, or a mismatched country. That is the model working; explain the reason codes to the customer and suggest rule tuning or an allowlist.

## 4. Quantify impact with a replay

```bash
python scripts/investigate_decisions.py --log <decision log> --output investigation.md
```

The script groups decisions by rules version, compares approval, review, and decline rates, finds the reason code whose firing rate changed most, and re-scores every decision on the previous rules. The replay answers the question the customer and Engineering both ask: *how many of these would have been approved before the change?*

See `examples/false-positive-investigation.md` for output from the sample incident, where a rules release changed the `HIGH_AMOUNT` limit from 1000 to 100.

## 5. Escalate

Escalate to Engineering on-call when the cause is a rules or data change. Use the escalation note the script generates, and include:

- Impact: approval rate change, start time, affected customers and decisions
- Suspected cause: rules version and the specific rule diff
- Evidence: metric queries, replay counts, 3-5 request IDs
- Ask: roll back or hotfix, and guidance on whether affected users should retry

Support does not change production rules. Support brings the evidence that makes a rollback decision fast.

## 6. Communicate

First update to the customer:

```text
We've confirmed an increase in declines and reviews starting <time> UTC that affects ordinary
purchases. Engineering is investigating a recent rules change. Next update by <time>.
In the meantime, you can manually approve orders in review; we'll confirm whether declined
users should retry once the fix is in place.
```

After the fix, confirm approval rates are back to baseline on the metrics before closing. Then send the customer the list of affected `event_id` values from the replay so they can follow up with their users.

## 7. Prevent the next one

- Add a regression test for the rule that changed
- Ask for a rules release check that replays recent traffic and blocks a release if approvals move more than an agreed amount
- Confirm the `RiskApprovalRateDrop` alert fired. If support heard about this from a customer before the alert fired, tune the alert.
