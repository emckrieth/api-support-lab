"""Investigate a change in risk decisions from the structured event log.

Answers the questions a support engineer gets when a customer reports
"legitimate users are being declined":

- Did the approval rate actually change, and when?
- Did it line up with a rules version change?
- Which reason code is driving the new reviews and declines?
- How many decisions would have been approved under the previous rules?
- With --verify-fix, does a proposed rules version restore those decisions?

Usage:
    python scripts/investigate_decisions.py [--log examples/decision_events.log]
        [--output examples/false-positive-investigation.md]
        [--verify-fix 2026.10.3 --fix-output examples/hotfix-verification.md]
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.risk import load_rules, score_event  # noqa: E402

# A review is still a blocked checkout for the customer, so the verdict uses the approval rate.
APPROVAL_DROP_POINTS = 10


def load_decisions(path: Path) -> list[dict]:
    decisions = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            event = json.loads(line)
            if event["event_type"] == "risk_decision":
                decisions.append({**event["payload"], "timestamp": event["timestamp"], "request_id": event["request_id"]})
    return decisions


def pct(part: int, whole: int) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


def summarize(decisions: list[dict]) -> dict:
    total = len(decisions)
    outcomes = Counter(d["decision"] for d in decisions)
    fired = Counter(code for d in decisions for code in d["reason_codes"])
    decline_codes = Counter(code for d in decisions if d["decision"] == "decline" for code in d["reason_codes"])
    return {
        "rules_version": decisions[0]["rules_version"],
        "first_seen": decisions[0]["timestamp"],
        "last_seen": decisions[-1]["timestamp"],
        "decisions": total,
        "approve_rate": pct(outcomes["approve"], total),
        "review_rate": pct(outcomes["review"], total),
        "decline_rate": pct(outcomes["decline"], total),
        "code_fire_rate": {code: pct(count, total) for code, count in fired.items()},
        "top_decline_codes": decline_codes.most_common(3),
    }


def group_by_version(decisions: list[dict]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    for decision in decisions:
        if groups and groups[-1][0]["rules_version"] == decision["rules_version"]:
            groups[-1].append(decision)
        else:
            groups.append([decision])
    return groups


def replay(decisions: list[dict], version: str, rules: dict) -> list[dict]:
    """Re-score each decision's logged input against another rules version."""
    ruleset = rules["versions"][version]
    return [{**d, "replayed": score_event(d["input"], ruleset)} for d in decisions]


def investigate(decisions: list[dict], rules: dict) -> dict:
    groups = group_by_version(decisions)
    summaries = [summarize(group) for group in groups]
    result = {"summaries": summaries, "finding": None}
    if len(groups) < 2:
        return result

    before, after = summaries[-2], summaries[-1]
    approval_change = round(after["approve_rate"] - before["approve_rate"], 1)
    codes = set(before["code_fire_rate"]) | set(after["code_fire_rate"])
    driver = max(codes, key=lambda code: after["code_fire_rate"].get(code, 0) - before["code_fire_rate"].get(code, 0))
    replayed = replay(groups[-1], before["rules_version"], rules)
    flipped = [d for d in replayed if d["decision"] != "approve" and d["replayed"]["decision"] == "approve"]
    old_rule = next(s for s in rules["versions"][before["rules_version"]]["signals"] if s["code"] == driver)
    new_rule = next(s for s in rules["versions"][after["rules_version"]]["signals"] if s["code"] == driver)
    result["finding"] = {
        "approval_drop": approval_change <= -APPROVAL_DROP_POINTS,
        "approval_rate_change": approval_change,
        "review_rate_change": round(after["review_rate"] - before["review_rate"], 1),
        "decline_rate_change": round(after["decline_rate"] - before["decline_rate"], 1),
        "changed_at": after["first_seen"],
        "previous_version": before["rules_version"],
        "new_version": after["rules_version"],
        "driver_code": driver,
        "driver_fire_rate_before": before["code_fire_rate"].get(driver, 0.0),
        "driver_fire_rate_after": after["code_fire_rate"].get(driver, 0.0),
        "rule_before": old_rule,
        "rule_after": new_rule,
        "impacted": len(flipped),
        "impacted_declines": sum(1 for d in flipped if d["decision"] == "decline"),
        "impacted_reviews": sum(1 for d in flipped if d["decision"] == "review"),
        "impacted_median_amount": round(median(d["input"]["amount"] for d in flipped), 2) if flipped else None,
        "impacted_customers": len({d["user_id"] for d in flipped}),
        "samples": [
            {"request_id": d["request_id"], "event_id": d["event_id"], "amount": d["input"]["amount"],
             "decision": d["decision"], "score": d["risk_score"], "previous_score": d["replayed"]["risk_score"]}
            for d in flipped[:5]
        ],
    }
    return result


def describe_rule(rule: dict) -> str:
    return f"`{rule['field']} {rule['op']} {rule['value']}` for {rule['points']} points"


def render_markdown(result: dict) -> str:
    lines = ["# Risk Decision Investigation", "", "Generated by `scripts/investigate_decisions.py` from the structured event log.", ""]
    lines += [
        "## Decisions by rules version",
        "",
        "| Rules version | First seen (UTC) | Decisions | Approve | Review | Decline | Top decline reasons |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for s in result["summaries"]:
        reasons = ", ".join(f"{code} ({count})" for code, count in s["top_decline_codes"]) or "none"
        lines.append(
            f"| {s['rules_version']} | {s['first_seen'][:16].replace('T', ' ')} | {s['decisions']} | "
            f"{s['approve_rate']}% | {s['review_rate']}% | {s['decline_rate']}% | {reasons} |"
        )

    finding = result["finding"]
    if not finding:
        lines += ["", "Only one rules version in this log, so there is nothing to compare."]
        return "\n".join(lines) + "\n"

    verdict = "Approval drop confirmed." if finding["approval_drop"] else "No significant change in approvals."
    lines += [
        "",
        "## Finding",
        "",
        f"**{verdict}** When rules `{finding['new_version']}` replaced `{finding['previous_version']}` at "
        f"{finding['changed_at'][:16].replace('T', ' ')} UTC, the approval rate changed by {finding['approval_rate_change']:+g} points "
        f"(review {finding['review_rate_change']:+g}, decline {finding['decline_rate_change']:+g}).",
        "",
        f"- Driver: `{finding['driver_code']}` fired on {finding['driver_fire_rate_before']}% of decisions before "
        f"and {finding['driver_fire_rate_after']}% after.",
        f"- Rule change: {describe_rule(finding['rule_before'])} became {describe_rule(finding['rule_after'])}.",
        f"- Replay: {finding['impacted']} decisions under `{finding['new_version']}` would have been approved under "
        f"`{finding['previous_version']}` ({finding['impacted_declines']} declines, {finding['impacted_reviews']} sent to review), "
        f"across {finding['impacted_customers']} customers. Median amount: ${finding['impacted_median_amount']:,.2f}.",
        "",
        "## Sample affected requests",
        "",
        "| Request ID | Event ID | Amount | Decision | Score | Score on previous rules |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for sample in finding["samples"]:
        lines.append(
            f"| {sample['request_id']} | {sample['event_id']} | ${sample['amount']:,.2f} | {sample['decision']} | "
            f"{sample['score']} | {sample['previous_score']} |"
        )
    lines += [
        "",
        "## Escalation note for Engineering",
        "",
        "```text",
        f"Impact: approval rate {finding['approval_rate_change']:+g} pts since {finding['changed_at'][:16].replace('T', ' ')} UTC; "
        f"{finding['impacted']} decisions would have approved on the previous rules.",
        f"Suspected cause: rules {finding['new_version']} changed {finding['driver_code']} "
        f"(limit {finding['rule_before']['value']} -> {finding['rule_after']['value']}, "
        f"points {finding['rule_before']['points']} -> {finding['rule_after']['points']}).",
        "Evidence: risk_decisions_total by rules_version, risk_reason_codes_total, replay output above, sample request IDs.",
        f"Ask: confirm the intended limit; roll back to {finding['previous_version']} or hotfix; "
        "advise whether affected customers should retry.",
        "```",
    ]
    return "\n".join(lines) + "\n"


def verify_fix(decisions: list[dict], rules: dict, fix_version: str) -> dict:
    """Replay the incident traffic on a proposed fix and compare it with the previous rules."""
    groups = group_by_version(decisions)
    if len(groups) < 2:
        raise ValueError("Need decisions from at least two rules versions to verify a fix")
    incident, previous_version = groups[-1], groups[-2][0]["rules_version"]
    on_previous = replay(incident, previous_version, rules)
    on_fix = replay(incident, fix_version, rules)
    impacted = [i for i, d in enumerate(on_previous) if d["decision"] != "approve" and d["replayed"]["decision"] == "approve"]
    still_blocked = [i for i in impacted if on_fix[i]["replayed"]["decision"] != "approve"]
    changed = [
        {"request_id": d["request_id"], "amount": d["input"]["amount"],
         "previous": p["replayed"]["decision"], "fix": d["replayed"]["decision"]}
        for d, p in zip(on_fix, on_previous) if d["replayed"]["decision"] != p["replayed"]["decision"]
    ]

    def rate(replayed: list[dict], outcome: str) -> float:
        return pct(sum(1 for d in replayed if d["replayed"]["decision"] == outcome), len(replayed))

    return {
        "fix_version": fix_version,
        "incident_version": incident[0]["rules_version"],
        "previous_version": previous_version,
        "decisions": len(incident),
        "approve_rate": {
            "incident": pct(sum(1 for d in incident if d["decision"] == "approve"), len(incident)),
            "previous": rate(on_previous, "approve"),
            "fix": rate(on_fix, "approve"),
        },
        "impacted": len(impacted),
        "recovered": len(impacted) - len(still_blocked),
        "still_blocked": [incident[i]["request_id"] for i in still_blocked],
        "changed_vs_previous": changed[:5],
        "changed_count": len(changed),
    }


def render_fix_markdown(check: dict) -> str:
    rates = check["approve_rate"]
    passed = not check["still_blocked"]
    lines = [
        "# Hotfix Verification",
        "",
        "Generated by `scripts/investigate_decisions.py --verify-fix` from the structured event log.",
        "",
        f"Replays the {check['decisions']} decisions made on `{check['incident_version']}` against the hotfix "
        f"`{check['fix_version']}` and the previous rules `{check['previous_version']}`.",
        "",
        f"**{'Fix verified.' if passed else 'Fix incomplete.'}** "
        f"{check['recovered']} of {check['impacted']} wrongly blocked decisions are approved on `{check['fix_version']}`.",
        "",
        "| Rules | Approval rate on incident traffic |",
        "| --- | --- |",
        f"| `{check['incident_version']}` (as decided) | {rates['incident']}% |",
        f"| `{check['previous_version']}` (replay) | {rates['previous']}% |",
        f"| `{check['fix_version']}` (replay) | {rates['fix']}% |",
        "",
    ]
    if check["still_blocked"]:
        lines += ["Still blocked: " + ", ".join(check["still_blocked"][:10]), ""]
    lines += [f"## Differences from `{check['previous_version']}`", ""]
    if not check["changed_count"]:
        lines.append(
            "No decisions in this traffic differ from the previous rules. The hotfix keeps the intended weight increase, "
            "which only changes outcomes for purchases over the HIGH_AMOUNT limit: they now go to review instead of "
            "being approved. This traffic has no purchases over the limit."
        )
    else:
        lines += [
            f"{check['changed_count']} decisions differ from the previous rules. These should all come from the intended "
            "weight increase for amounts over the limit; confirm each one is expected.",
            "",
            "| Request ID | Amount | Previous rules | Hotfix |",
            "| --- | --- | --- | --- |",
        ]
        for row in check["changed_vs_previous"]:
            lines.append(f"| {row['request_id']} | ${row['amount']:,.2f} | {row['previous']} | {row['fix']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Investigate a change in risk decisions.")
    parser.add_argument("--log", type=Path, default=ROOT / "examples" / "decision_events.log")
    parser.add_argument("--output", type=Path, default=ROOT / "examples" / "false-positive-investigation.md")
    parser.add_argument("--verify-fix", metavar="VERSION", help="Replay the incident traffic on this rules version")
    parser.add_argument("--fix-output", type=Path, default=ROOT / "examples" / "hotfix-verification.md")
    args = parser.parse_args()

    rules = load_rules()
    decisions = load_decisions(args.log)
    result = investigate(decisions, rules)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_markdown(result), encoding="utf-8")
    finding = result["finding"]
    if finding:
        print(f"Approval rate change: {finding['approval_rate_change']:+g} pts ({finding['previous_version']} -> {finding['new_version']})")
        print(f"Driver: {finding['driver_code']}; {finding['impacted']} decisions would have approved on the previous rules")
    print(f"Wrote {args.output}")
    if args.verify_fix:
        check = verify_fix(decisions, rules, args.verify_fix)
        args.fix_output.write_text(render_fix_markdown(check), encoding="utf-8")
        print(f"Fix {args.verify_fix}: {check['recovered']} of {check['impacted']} wrongly blocked decisions recovered")
        print(f"Wrote {args.fix_output}")


if __name__ == "__main__":
    main()
