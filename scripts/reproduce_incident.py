"""Reproduce the risk regression over HTTP using an isolated loopback server."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, ProxyHandler, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    run_id = uuid4().hex
    output = ROOT / "output" / ("incident-" + run_id)
    output.mkdir(parents=True)
    report_path = output / "http-results.json"
    report = {"run_id": run_id, "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "executor": "whoever invokes this script; archived snapshot records actual executor",
              "status": "running", "checks": [], "limits": [
                  "Local lab with fictional transactions, not production traffic",
                  "HTTP reproduction does not prove alert delivery or real fraud outcomes"]}
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        port = port_probe.getsockname()[1]
    base = "http://127.0.0.1:" + str(port)
    opener = build_opener(ProxyHandler({}))
    def request(method, path, body=None, request_id=None):
        headers = {"Content-Type": "application/json", "x-api-key": "demo-key"}
        if request_id:
            headers["x-request-id"] = request_id
        data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
        with opener.open(Request(base + path, data, headers, method=method), timeout=5) as response:
            return response.status, json.load(response)
    process = None
    server_log = (output / "server.log").open("w", encoding="utf-8")
    try:
        env = dict(os.environ, SUPPORT_LOG_PATH=str(output / "events.jsonl"))
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host",
                                    "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env,
                                   stdout=server_log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 30
        while True:
            if process.poll() is not None:
                raise RuntimeError("Lab server exited before readiness")
            try:
                request("GET", "/health")
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Lab server readiness timed out") from None
                time.sleep(0.2)
        transaction = {"event_id": "fictional-checkout", "user_id": "fictional-customer",
                       "amount": 180, "currency": "USD", "billing_country": "US",
                       "email_age_days": 400, "device": {"device_id": "fictional-device",
                       "ip_country": "US", "is_emulator": False, "velocity_1h": 1}}
        stages = [("baseline", "2026.10.1", "normal", "default", [(180, "approve", 0), (1200, "approve", 20)]),
                  ("regression", "2026.10.2", "rules_regression", None, [(180, "review", 45), (1200, "review", 45)]),
                  ("hotfix", "2026.10.3", "normal", "2026.10.3", [(180, "approve", 0), (1200, "review", 45)])]
        for stage, version, mode, pinned, cases in stages:
            request("POST", "/admin/incident-mode/" + mode)
            if pinned:
                request("POST", "/admin/rules-version/" + pinned)
            status, health = request("GET", "/health")
            assert status == 200 and health["rules_version"] == version
            for amount, decision, score in cases:
                request_id = run_id + "-" + stage + "-" + str(amount)
                status, result = request("POST", "/risk/decisions", dict(transaction, amount=amount), request_id)
                assert status == 200 and result["rules_version"] == version
                assert (result["decision"], result["risk_score"]) == (decision, score)
                _, logs = request("GET", "/admin/logs?" + urlencode({"request_id": request_id, "event_type": "risk_decision"}))
                assert len(logs["events"]) == 1
                assert logs["events"][0]["payload"]["decision"] == decision
                report["checks"].append({"stage": stage, "rules_version": version,
                    "amount": amount, "http_status": status, "health_http_status": 200,
                    "decision": decision, "score": score, "request_id": request_id,
                    "reason_codes": [r["code"] for r in result["reason_codes"]], "trace_verified": True})
                print(stage + " $" + str(amount) + ": " + decision + " (score " + str(score) + ")", flush=True)
        with opener.open(base + "/metrics", timeout=5) as response:
            metrics = response.read().decode()
        for version in ("2026.10.1", "2026.10.2", "2026.10.3"):
            assert 'rules_version="' + version + '"' in metrics
        (output / "metrics.txt").write_text(metrics)
        report["metrics_versions_verified"] = True
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["error_type"] = type(error).__name__
        raise
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        server_log.close()
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print("Fresh report: " + str(report_path), flush=True)


if __name__ == "__main__":
    main()
