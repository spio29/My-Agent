#!/usr/bin/env python3
"""Spio watchdog: self-heal + incident report via Telegram.

- Checks critical containers status/health.
- Attempts auto-restart when needed.
- Sends incident/recovery reports to Telegram chat IDs configured in connector account.
- Persists lightweight state to avoid spam.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STATE_PATH = Path("/opt/spio-agent/ops/no-code/.watchdog_state.json")
ENV_PATH = Path("/opt/spio-agent/.env")
LOG_TAG = "[spio-watchdog]"

# Keep alert frequency sane.
ALERT_COOLDOWN_SEC = 15 * 60

CONTAINERS = [
    "spio-redis",
    "spio-api",
    "spio-connector",
    "spio-dashboard",
    "spio-worker",
    "spio-scheduler",
]


@dataclass
class ContainerCheck:
    name: str
    status: str
    health: str
    ok: bool
    reason: str


def run_cmd(cmd: List[str], timeout: int = 20) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except Exception as exc:
        return 1, "", str(exc)


def read_env_value(key: str, default: str = "") -> str:
    value = os.getenv(key, "").strip()
    if value:
        return value
    if not ENV_PATH.exists():
        return default
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip() or default
    return default


def read_admin_token() -> str:
    token = read_env_value("SPIO_ADMIN_TOKEN", "")
    if token:
        return token
    raw = read_env_value("AUTH_API_KEYS", "")
    if not raw:
        return ""
    first = raw.split(",", 1)[0]
    return first.split(":", 1)[0].strip()


def read_operator_token() -> str:
    token = read_env_value("NEXT_PUBLIC_API_TOKEN", "")
    if token:
        return token
    raw = read_env_value("AUTH_API_KEYS", "")
    if not raw:
        return ""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for pair in parts:
        if ":" in pair:
            t, role = pair.split(":", 1)
            if role.strip().lower() == "operator":
                return t.strip()
    return ""


def load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def now_iso_wib() -> str:
    wib = timezone(timedelta(hours=7))
    return datetime.now(wib).isoformat(timespec="seconds")


def inspect_container(name: str) -> ContainerCheck:
    code, out, err = run_cmd([
        "docker",
        "inspect",
        "-f",
        "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
        name,
    ])
    if code != 0:
        return ContainerCheck(name=name, status="missing", health="unknown", ok=False, reason=err or "not found")

    parts = out.split("|", 1)
    status = parts[0].strip() if parts else "unknown"
    health = parts[1].strip() if len(parts) > 1 else "none"

    if status != "running":
        return ContainerCheck(name=name, status=status, health=health, ok=False, reason=f"status={status}")
    if health == "unhealthy":
        return ContainerCheck(name=name, status=status, health=health, ok=False, reason="health=unhealthy")

    return ContainerCheck(name=name, status=status, health=health, ok=True, reason="ok")


def restart_container(name: str) -> Tuple[bool, str]:
    code, out, err = run_cmd(["docker", "restart", name], timeout=60)
    if code != 0:
        return False, err or out or "restart failed"

    # give a short warm-up before re-check
    time.sleep(4)
    check = inspect_container(name)
    if check.ok:
        return True, "restarted and healthy"
    return False, f"restarted but still problematic ({check.reason})"


def api_get_json(path: str, token: str, timeout: int = 10) -> Any:
    req = urllib.request.Request(
        f"http://127.0.0.1:8000{path}",
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def check_api_health() -> Tuple[bool, str]:
    # /healthz should be public
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/healthz")
        with urllib.request.urlopen(req, timeout=6) as resp:
            if 200 <= resp.status < 300:
                return True, "api healthz ok"
            return False, f"api healthz status={resp.status}"
    except Exception as exc:
        return False, f"api healthz error={exc}"


def get_ops_snapshot(operator_token: str) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "enabled_jobs": None,
        "queue_depth": None,
        "queue_delayed": None,
        "recent_errors": 0,
    }
    if not operator_token:
        return snapshot

    try:
        jobs = api_get_json("/jobs?limit=1000", operator_token)
        if isinstance(jobs, list):
            snapshot["enabled_jobs"] = sum(1 for row in jobs if bool(row.get("enabled")))
    except Exception:
        pass

    try:
        queue = api_get_json("/queue", operator_token)
        if isinstance(queue, dict):
            snapshot["queue_depth"] = int(queue.get("depth") or 0)
            snapshot["queue_delayed"] = int(queue.get("delayed") or 0)
    except Exception:
        pass

    try:
        events = api_get_json("/events?limit=80", operator_token)
        if isinstance(events, list):
            err = 0
            for row in events:
                t = str(row.get("type") or "").lower()
                if any(k in t for k in ["failed", "error", "degraded"]):
                    err += 1
            snapshot["recent_errors"] = err
    except Exception:
        pass

    return snapshot


def get_telegram_target_from_redis() -> Tuple[str, List[str]]:
    # Read connector account data directly from Redis container.
    code, out, err = run_cmd(["docker", "exec", "spio-redis", "redis-cli", "--raw", "smembers", "connector:telegram:accounts"])
    if code != 0:
        return "", []

    account_ids = [line.strip() for line in out.splitlines() if line.strip()]
    for acc in account_ids:
        key = f"connector:telegram:account:{acc}"
        code2, raw, _ = run_cmd(["docker", "exec", "spio-redis", "redis-cli", "--raw", "get", key])
        if code2 != 0 or not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except Exception:
            continue

        enabled = bool(row.get("enabled", True))
        token = str(row.get("bot_token") or "").strip()
        chat_ids = [str(c).strip() for c in (row.get("allowed_chat_ids") or []) if str(c).strip()]
        if enabled and token and chat_ids:
            return token, chat_ids

    return "", []


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text[:3800]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=12) as _:
        return


def alert_fingerprint(lines: List[str]) -> str:
    raw = "\n".join(lines)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_incident_message(
    checks: List[ContainerCheck],
    restarts: List[str],
    api_ok: bool,
    api_note: str,
    snapshot: Dict[str, Any],
) -> str:
    lines = [
        "SPIO WATCHDOG ALERT",
        f"Waktu: {now_iso_wib()}",
        "",
    ]

    bad = [c for c in checks if not c.ok]
    if bad:
        lines.append("Service bermasalah:")
        for c in bad:
            lines.append(f"- {c.name}: {c.reason} (status={c.status}, health={c.health})")
        lines.append("")

    if restarts:
        lines.append("Aksi auto-heal:")
        for r in restarts:
            lines.append(f"- {r}")
        lines.append("")

    lines.append(f"API health: {'OK' if api_ok else 'FAIL'} ({api_note})")
    lines.append(
        "Snapshot: enabled_jobs={enabled_jobs}, queue_depth={queue_depth}, queue_delayed={queue_delayed}, recent_errors={recent_errors}".format(
            enabled_jobs=snapshot.get("enabled_jobs"),
            queue_depth=snapshot.get("queue_depth"),
            queue_delayed=snapshot.get("queue_delayed"),
            recent_errors=snapshot.get("recent_errors"),
        )
    )
    lines.append("")
    lines.append("Catatan: watchdog aktif, sistem tetap dijaga agar tidak mati total.")
    return "\n".join(lines)


def build_recovery_message(snapshot: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "SPIO WATCHDOG RECOVERY",
            f"Waktu: {now_iso_wib()}",
            "Semua service inti kembali normal.",
            "Snapshot: enabled_jobs={enabled_jobs}, queue_depth={queue_depth}, queue_delayed={queue_delayed}, recent_errors={recent_errors}".format(
                enabled_jobs=snapshot.get("enabled_jobs"),
                queue_depth=snapshot.get("queue_depth"),
                queue_delayed=snapshot.get("queue_delayed"),
                recent_errors=snapshot.get("recent_errors"),
            ),
        ]
    )


def main() -> int:
    state = load_state()
    now_ts = int(time.time())

    checks: List[ContainerCheck] = [inspect_container(name) for name in CONTAINERS]
    api_ok, api_note = check_api_health()

    restarts: List[str] = []
    for c in checks:
        if c.ok:
            continue
        ok, note = restart_container(c.name)
        restarts.append(f"{c.name}: {'OK' if ok else 'FAIL'} ({note})")

    # re-check after heal attempts
    checks = [inspect_container(name) for name in CONTAINERS]
    api_ok, api_note = check_api_health()

    has_issue = (not api_ok) or any(not c.ok for c in checks)

    operator_token = read_operator_token()
    snapshot = get_ops_snapshot(operator_token)

    lines_for_fp = []
    for c in checks:
        if not c.ok:
            lines_for_fp.append(f"{c.name}:{c.status}:{c.health}:{c.reason}")
    if not api_ok:
        lines_for_fp.append(f"api:{api_note}")
    for r in restarts:
        lines_for_fp.append(f"restart:{r}")

    fp = alert_fingerprint(lines_for_fp) if lines_for_fp else "ok"

    last_fp = str(state.get("last_fp") or "")
    last_alert_ts = int(state.get("last_alert_ts") or 0)
    was_issue = bool(state.get("was_issue", False))

    should_send_incident = False
    should_send_recovery = False
    had_autoheal = len(restarts) > 0

    # Send alert for unresolved issues OR successful auto-heal actions.
    if has_issue or had_autoheal:
        if fp != last_fp:
            should_send_incident = True
        elif now_ts - last_alert_ts >= ALERT_COOLDOWN_SEC:
            should_send_incident = True
    else:
        if was_issue:
            should_send_recovery = True

    bot_token, chat_ids = get_telegram_target_from_redis()
    sent_any = False

    if should_send_incident and bot_token and chat_ids:
        msg = build_incident_message(checks, restarts, api_ok, api_note, snapshot)
        for chat_id in chat_ids:
            try:
                send_telegram_message(bot_token, chat_id, msg)
                sent_any = True
            except Exception:
                continue

    if should_send_recovery and bot_token and chat_ids:
        msg = build_recovery_message(snapshot)
        for chat_id in chat_ids:
            try:
                send_telegram_message(bot_token, chat_id, msg)
                sent_any = True
            except Exception:
                continue

    state["was_issue"] = has_issue
    state["last_fp"] = fp
    if should_send_incident or should_send_recovery:
        state["last_alert_ts"] = now_ts
    state["last_run_ts"] = now_ts
    state["last_run_iso"] = now_iso_wib()
    state["last_sent"] = sent_any
    save_state(state)

    status_line = f"issue={has_issue} api_ok={api_ok} restarts={len(restarts)} sent={sent_any}"
    print(f"{LOG_TAG} {status_line}")
    if restarts:
        for r in restarts:
            print(f"{LOG_TAG} {r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
