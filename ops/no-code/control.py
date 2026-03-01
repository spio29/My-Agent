#!/usr/bin/env python3
"""No-code command center for influencer operations.

Usage examples:
  ./control.sh status all
  ./control.sh on inf_001
  ./control.sh off all
  ./control.sh strategy inf_001 story
  ./control.sh cadence inf_001 fast
  ./control.sh schedule inf_001 --ig 08:30 --fb 09:00 --report 21:00
  ./control.sh tone inf_001 warm
  ./control.sh followup inf_001 hard
  ./control.sh channels inf_003 ig,fb
  ./control.sh chain all --start 09:00 --gap-min-sec 70 --gap-max-sec 130 --next-inf-gap-sec 80
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import random
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

def _resolve_manifest_default() -> str:
    candidates = [
        "/opt/spio-agent/ops/no-code/manifest.json",
        "/app/ops/no-code/manifest.json",
    ]
    for item in candidates:
        if pathlib.Path(item).exists():
            return item
    return candidates[0]


MANIFEST_DEFAULT = _resolve_manifest_default()
API_DEFAULT = "http://127.0.0.1:8000"
ENV_PATH = "/opt/spio-agent/.env"

CHANNEL_CODE_MAP = {
    "ig": "ig",
    "instagram": "ig",
    "fb": "fb",
    "facebook": "fb",
    "wa": "wa",
    "whatsapp": "wa",
}

POST_KIND_BY_CHANNEL = {
    "fb": "fb_post",
    "ig": "ig_post",
}

REPLY_KIND_BY_CHANNEL = {
    "fb": "fb_reply",
    "ig": "ig_reply",
    "wa": "wa_followup",
}


def _read_admin_token() -> str:
    env_token = os.getenv("SPIO_ADMIN_TOKEN", "").strip()
    if env_token:
        return env_token

    connector_token = os.getenv("CONNECTOR_API_TOKEN", "").strip()
    if connector_token:
        return connector_token

    next_token = os.getenv("NEXT_PUBLIC_API_TOKEN", "").strip()
    if next_token:
        return next_token

    env_file = pathlib.Path(ENV_PATH)
    if not env_file.exists():
        return ""

    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("AUTH_API_KEYS="):
            raw = line.split("=", 1)[1].strip()
            if not raw:
                return ""
            first = raw.split(",", 1)[0]
            return first.split(":", 1)[0].strip()
    return ""


def _request_json(method: str, base_url: str, path: str, token: str, payload: Dict[str, Any] | None = None) -> Any:
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(base_url + path, method=method.upper(), headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} {path}: {detail}") from exc


def _load_manifest(path: str) -> Dict[str, Any]:
    p = pathlib.Path(path)
    if not p.exists():
        raise RuntimeError(f"Manifest tidak ditemukan: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def _save_manifest(path: str, data: Dict[str, Any]) -> None:
    p = pathlib.Path(path)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _selected_influencers(manifest: Dict[str, Any], target: str) -> List[Dict[str, Any]]:
    rows = list(manifest.get("influencers") or [])
    if target == "all":
        return rows
    picked = [row for row in rows if str(row.get("id")) == target]
    if not picked:
        valid = ", ".join(str(r.get("id")) for r in rows)
        raise RuntimeError(f"Target '{target}' tidak ditemukan. Pilihan: all, {valid}")
    return picked


def _job_kind(job_id: str) -> str:
    if job_id.endswith("_ig_post"):
        return "ig_post"
    if job_id.endswith("_ig_reply"):
        return "ig_reply"
    if job_id.endswith("_fb_post"):
        return "fb_post"
    if job_id.endswith("_fb_reply"):
        return "fb_reply"
    if job_id.endswith("_wa_followup"):
        return "wa_followup"
    if job_id.endswith("_report"):
        return "report"
    return "unknown"


def _normalize_channels(value: str) -> List[str]:
    items = []
    for raw in str(value or "").split(","):
        key = CHANNEL_CODE_MAP.get(raw.strip().lower(), "")
        if key and key not in items:
            items.append(key)
    if not items:
        raise RuntimeError("Channels kosong/tidak valid. Contoh: ig,fb atau ig saja")
    return items


def _build_prompt(strategy: str, kind: str, account_id: str, inf_id: str) -> str:
    prefix = f"[MODE:{strategy}]"

    if strategy == "softsell":
        prompts = {
            "ig_post": f"{prefix} Susun konten Instagram akun {account_id} dengan gaya edukatif + storytelling ringan. Hindari hard-selling.",
            "fb_post": f"{prefix} Buat konten Facebook akun {account_id} yang membangun trust, pakai CTA halus ke DM/WhatsApp.",
            "ig_reply": f"{prefix} Balas komentar/DM Instagram {account_id} dengan empati, gali kebutuhan, lalu arahkan ke solusi secara natural.",
            "fb_reply": f"{prefix} Balas inbox/komentar Facebook {account_id} secara ramah, klasifikasikan lead dingin/hangat/panas.",
            "wa_followup": f"{prefix} Follow-up WhatsApp {account_id} fokus value first: jawaban jelas, ringkas, tanpa memaksa closing.",
            "report": f"{prefix} Laporan harian {inf_id}: trust signal, kualitas percakapan, lead hangat, dan peluang closing besok.",
        }
    elif strategy == "hardclose":
        prompts = {
            "ig_post": f"{prefix} Buat konten Instagram {account_id} dengan CTA tegas ke konsultasi/pembelian hari ini.",
            "fb_post": f"{prefix} Buat konten Facebook {account_id} berorientasi konversi, sorot manfaat + urgensi + CTA.",
            "ig_reply": f"{prefix} Balas DM/komentar Instagram {account_id} dengan alur cepat: qualify -> offer -> ajak closing.",
            "fb_reply": f"{prefix} Balas inbox Facebook {account_id} dengan format singkat, fokus menyelesaikan keraguan untuk closing.",
            "wa_followup": f"{prefix} Follow-up WhatsApp {account_id} untuk mendorong keputusan: ringkas, jelas, dan ajak finalisasi.",
            "report": f"{prefix} Laporan harian {inf_id}: jumlah offer, objection utama, close rate, dan target besok.",
        }
    elif strategy == "story":
        prompts = {
            "ig_post": f"{prefix} Buat konten Instagram {account_id} berformat cerita manusiawi (problem-real life-solution) agar natural influencer.",
            "fb_post": f"{prefix} Buat konten Facebook {account_id} bernarasi pengalaman nyata, hindari gaya iklan kaku.",
            "ig_reply": f"{prefix} Balas interaksi Instagram {account_id} dengan gaya personal, hangat, tidak robotik.",
            "fb_reply": f"{prefix} Balas interaksi Facebook {account_id} dengan nada manusiawi dan konteks percakapan.",
            "wa_followup": f"{prefix} Follow-up WhatsApp {account_id} seperti asisten manusia: sopan, bertahap, relevan konteks chat terakhir.",
            "report": f"{prefix} Laporan harian {inf_id}: engagement kualitas, topik yang resonan, dan ide cerita besok.",
        }
    elif strategy == "endorse":
        prompts = {
            "ig_post": f"{prefix} Konten Instagram {account_id} untuk memperkuat positioning agar menarik brand partner/endorse.",
            "fb_post": f"{prefix} Konten Facebook {account_id} untuk bukti kredibilitas dan social proof ke brand.",
            "ig_reply": f"{prefix} Balas DM Instagram {account_id} dengan prioritas peluang kolaborasi brand dan lead sponsor.",
            "fb_reply": f"{prefix} Balas inbox Facebook {account_id} dengan fokus negosiasi awal kerja sama brand.",
            "wa_followup": f"{prefix} Follow-up WhatsApp {account_id} untuk prospek brand: rate card, deliverables, timeline.",
            "report": f"{prefix} Laporan harian {inf_id}: peluang endorse, tahap negosiasi, dan next action deal.",
        }
    else:
        raise RuntimeError("Preset strategy tidak valid. Gunakan: softsell, hardclose, story, endorse")

    return prompts.get(kind, f"{prefix} Jalankan job {kind} untuk {account_id}.")


def _build_tone_prompt(kind: str, account_id: str, tone: str) -> str:
    if tone == "warm":
        if kind == "wa_followup":
            return f"[TONE:warm] Follow-up WhatsApp {account_id} dengan nada hangat, empatik, dan natural tanpa terkesan menjual keras."
        return f"[TONE:warm] Balas interaksi {account_id} dengan nada hangat, sopan, dan manusiawi."
    if tone == "formal":
        if kind == "wa_followup":
            return f"[TONE:formal] Follow-up WhatsApp {account_id} dengan bahasa profesional, rapi, dan jelas poinnya."
        return f"[TONE:formal] Balas interaksi {account_id} dengan gaya profesional, ringkas, dan jelas."
    if tone == "hard":
        if kind == "wa_followup":
            return f"[TONE:hard] Follow-up WhatsApp {account_id} tegas ke keputusan: identifikasi hambatan lalu dorong closing hari ini."
        return f"[TONE:hard] Balas interaksi {account_id} dengan fokus cepat ke aksi/keputusan."
    raise RuntimeError("Tone tidak valid. Gunakan: warm, formal, hard")


def _hhmm_to_total_seconds(hhmm: str) -> int:
    raw = (hhmm or "").strip()
    if ":" not in raw:
        raise RuntimeError(f"Format waktu harus HH:MM, dapat: {hhmm}")
    hh_s, mm_s = raw.split(":", 1)
    try:
        hh = int(hh_s)
        mm = int(mm_s)
    except ValueError as exc:
        raise RuntimeError(f"Format waktu harus HH:MM, dapat: {hhmm}") from exc

    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        raise RuntimeError(f"Jam/menit di luar range: {hhmm}")
    return hh * 3600 + mm * 60


def _seconds_to_cron(total_seconds: int) -> str:
    day_seconds = 24 * 3600
    s = total_seconds % day_seconds
    hh = s // 3600
    mm = (s % 3600) // 60
    return f"{mm} {hh} * * *"


def _build_upsert_payload(
    job_row: Dict[str, Any],
    *,
    prompt: Optional[str] = None,
    cron: Optional[str] = None,
    interval_sec: Optional[int] = None,
    dispatch_jitter_sec: Optional[int] = None,
    enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    inputs = dict(job_row.get("inputs") or {})
    schedule = dict(job_row.get("schedule") or {})
    retry_policy = dict(job_row.get("retry_policy") or {})

    existing_prompt = str(inputs.get("prompt") or "").strip()
    existing_cron = schedule.get("cron")
    existing_interval = schedule.get("interval_sec")

    final_prompt = prompt if prompt is not None else existing_prompt
    final_cron = cron if cron is not None else existing_cron
    final_interval = interval_sec if interval_sec is not None else existing_interval
    final_jitter = dispatch_jitter_sec if dispatch_jitter_sec is not None else int(inputs.get("dispatch_jitter_sec") or 0)

    payload: Dict[str, Any] = {
        "job_id": str(job_row.get("job_id") or "").strip(),
        "prompt": final_prompt,
        "enabled": bool(job_row.get("enabled", False)) if enabled is None else bool(enabled),
        "timezone": str(inputs.get("timezone") or "Asia/Jakarta"),
        "default_channel": str(inputs.get("default_channel") or "telegram"),
        "default_account_id": str(inputs.get("default_account_id") or "default"),
        "flow_group": str(inputs.get("flow_group") or "default"),
        "flow_max_active_runs": int(inputs.get("flow_max_active_runs") or 10),
        "require_approval_for_missing": bool(inputs.get("require_approval_for_missing", True)),
        "allow_overlap": bool(inputs.get("allow_overlap", False)),
        "pressure_priority": str(inputs.get("pressure_priority") or "normal"),
        "dispatch_jitter_sec": int(max(0, min(3600, final_jitter))),
        "failure_threshold": int(inputs.get("failure_threshold") or 3),
        "failure_cooldown_sec": int(inputs.get("failure_cooldown_sec") or 120),
        "failure_cooldown_max_sec": int(inputs.get("failure_cooldown_max_sec") or 3600),
        "failure_memory_enabled": bool(inputs.get("failure_memory_enabled", True)),
        "command_allow_prefixes": list(inputs.get("command_allow_prefixes") or []),
        "allow_sensitive_commands": bool(inputs.get("allow_sensitive_commands", False)),
        "timeout_ms": int(job_row.get("timeout_ms") or 90000),
        "max_retry": int(retry_policy.get("max_retry") or 1),
        "backoff_sec": list(retry_policy.get("backoff_sec") or [2, 5]),
    }

    if final_cron:
        payload["cron"] = str(final_cron)
    else:
        payload["interval_sec"] = int(final_interval or 900)

    return payload


def _get_jobs(base_url: str, token: str) -> Dict[str, Dict[str, Any]]:
    rows = _request_json("GET", base_url, "/automation/agent-workflows", token)
    return {str(r.get("job_id") or ""): r for r in rows}


def _get_accounts(base_url: str, token: str) -> Dict[str, Dict[str, Any]]:
    rows = _request_json("GET", base_url, "/integrations/accounts", token)
    return {f"{r.get('provider')}::{r.get('account_id')}": r for r in rows}


def cmd_status(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    jobs = _get_jobs(args.api_url, args.token)
    accounts = _get_accounts(args.api_url, args.token)

    print("=== COMMAND CENTER STATUS ===")
    for inf in _selected_influencers(manifest, args.target):
        inf_id = str(inf.get("id"))
        channels_active = list(inf.get("channels_active") or ["fb", "ig", "wa"])
        print(f"[{inf_id}] {inf.get('name')} ({inf.get('model')})")
        print(f"  channels_active={','.join(channels_active)}")

        accs = inf.get("accounts") or {}
        for code, provider, key_name, acc_key in [
            ("fb", "facebook_graph", "facebook_page_id", "facebook"),
            ("ig", "instagram_graph", "instagram_user_id", "instagram"),
            ("wa", "whatsapp_api", "phone_number_id", "whatsapp"),
        ]:
            acc_id = str(accs.get(acc_key) or "").strip()
            if not acc_id:
                print(f"  - account {code}: (kosong)")
                continue
            row = accounts.get(f"{provider}::{acc_id}")
            if not row:
                print(f"  - account {code}: {acc_id} -> MISSING")
                continue
            cfg = row.get("config") or {}
            has_id = bool(str(cfg.get(key_name) or "").strip())
            has_secret = bool(row.get("has_secret"))
            enabled = bool(row.get("enabled"))
            readiness = "READY" if has_id and has_secret and enabled else "NOT_READY"
            print(f"  - account {code}: {acc_id} -> {readiness} (enabled={enabled}, token={has_secret}, id={has_id})")

        for job_id in inf.get("jobs") or []:
            row = jobs.get(job_id)
            if not row:
                print(f"  - {job_id}: MISSING")
                continue
            kind = _job_kind(job_id)
            sched = row.get("schedule") or {}
            sched_text = sched.get("cron") or f"every {sched.get('interval_sec')}s"
            prompt = str((row.get("inputs") or {}).get("prompt") or "")
            mode = "-"
            if prompt.startswith("[MODE:") and "]" in prompt:
                mode = prompt.split("]", 1)[0].replace("[MODE:", "")
            tone = "-"
            if prompt.startswith("[TONE:") and "]" in prompt:
                tone = prompt.split("]", 1)[0].replace("[TONE:", "")
            jitter = int((row.get("inputs") or {}).get("dispatch_jitter_sec") or 0)
            print(f"  - {job_id}: enabled={row.get('enabled')} | {kind} | {sched_text} | mode={mode} tone={tone} jitter={jitter}s")
        print()
    return 0


def cmd_switch(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    action = args.action
    endpoint_suffix = "enable" if action == "on" else "disable"

    for inf in _selected_influencers(manifest, args.target):
        print(f"[{action.upper()}] {inf.get('id')} {inf.get('name')}")
        for job_id in inf.get("jobs") or []:
            try:
                _request_json("PUT", args.api_url, f"/jobs/{job_id}/{endpoint_suffix}", args.token, payload={})
                tag = "+" if action == "on" else "-"
                print(f"  {tag} {job_id}")
            except Exception as exc:
                print(f"  ! {job_id}: {exc}")
    return 0


def cmd_strategy(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    jobs = _get_jobs(args.api_url, args.token)

    total = 0
    for inf in _selected_influencers(manifest, args.target):
        inf_id = str(inf.get("id"))
        print(f"[STRATEGY] {inf_id} -> {args.preset}")
        for job_id in inf.get("jobs") or []:
            row = jobs.get(job_id)
            if not row:
                print(f"  ! missing {job_id}")
                continue
            kind = _job_kind(job_id)
            account_id = str((row.get("inputs") or {}).get("default_account_id") or "default")
            new_prompt = _build_prompt(args.preset, kind, account_id, inf_id)
            payload = _build_upsert_payload(row, prompt=new_prompt)
            _request_json("POST", args.api_url, "/automation/agent-workflow", args.token, payload=payload)
            print(f"  + updated prompt {job_id}")
            total += 1
    print(f"updated_jobs={total}")
    return 0


def cmd_tone(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    jobs = _get_jobs(args.api_url, args.token)
    total = 0

    for inf in _selected_influencers(manifest, args.target):
        print(f"[TONE] {inf.get('id')} -> {args.tone}")
        for job_id in inf.get("jobs") or []:
            row = jobs.get(job_id)
            if not row:
                continue
            kind = _job_kind(job_id)
            if kind not in {"ig_reply", "fb_reply", "wa_followup"}:
                continue
            account_id = str((row.get("inputs") or {}).get("default_account_id") or "default")
            new_prompt = _build_tone_prompt(kind, account_id, args.tone)
            payload = _build_upsert_payload(row, prompt=new_prompt)
            _request_json("POST", args.api_url, "/automation/agent-workflow", args.token, payload=payload)
            print(f"  + updated tone {job_id}")
            total += 1

    print(f"updated_jobs={total}")
    return 0


def cmd_followup(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    jobs = _get_jobs(args.api_url, args.token)
    mapping = {
        "lembut": "warm",
        "keras": "hard",
        "formal": "formal",
    }
    tone = mapping[args.mode]

    total = 0
    for inf in _selected_influencers(manifest, args.target):
        print(f"[FOLLOWUP] {inf.get('id')} -> {args.mode}")
        for job_id in inf.get("jobs") or []:
            row = jobs.get(job_id)
            if not row:
                continue
            kind = _job_kind(job_id)
            if kind != "wa_followup":
                continue
            account_id = str((row.get("inputs") or {}).get("default_account_id") or "default")
            new_prompt = _build_tone_prompt(kind, account_id, tone)
            payload = _build_upsert_payload(row, prompt=new_prompt)
            _request_json("POST", args.api_url, "/automation/agent-workflow", args.token, payload=payload)
            print(f"  + updated followup {job_id}")
            total += 1

    print(f"updated_jobs={total}")
    return 0


def cmd_cadence(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    jobs = _get_jobs(args.api_url, args.token)

    cadence_map = {
        "slow": {"ig_reply": 300, "fb_reply": 360, "wa_followup": 360},
        "normal": {"ig_reply": 120, "fb_reply": 180, "wa_followup": 150},
        "fast": {"ig_reply": 60, "fb_reply": 90, "wa_followup": 90},
    }
    target_intervals = cadence_map[args.mode]

    total = 0
    for inf in _selected_influencers(manifest, args.target):
        print(f"[CADENCE] {inf.get('id')} -> {args.mode}")
        for job_id in inf.get("jobs") or []:
            row = jobs.get(job_id)
            if not row:
                print(f"  ! missing {job_id}")
                continue
            kind = _job_kind(job_id)
            if kind not in target_intervals:
                continue
            payload = _build_upsert_payload(row, cron=None, interval_sec=target_intervals[kind])
            payload.pop("cron", None)
            payload["interval_sec"] = int(target_intervals[kind])
            _request_json("POST", args.api_url, "/automation/agent-workflow", args.token, payload=payload)
            print(f"  + {job_id} -> every {target_intervals[kind]}s")
            total += 1
    print(f"updated_jobs={total}")
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    jobs = _get_jobs(args.api_url, args.token)

    cron_ig = _seconds_to_cron(_hhmm_to_total_seconds(args.ig))
    cron_fb = _seconds_to_cron(_hhmm_to_total_seconds(args.fb))
    cron_report = _seconds_to_cron(_hhmm_to_total_seconds(args.report))

    total = 0
    for inf in _selected_influencers(manifest, args.target):
        print(f"[SCHEDULE] {inf.get('id')} -> IG {args.ig}, FB {args.fb}, REPORT {args.report}")
        for job_id in inf.get("jobs") or []:
            row = jobs.get(job_id)
            if not row:
                print(f"  ! missing {job_id}")
                continue
            kind = _job_kind(job_id)
            if kind == "ig_post":
                payload = _build_upsert_payload(row, cron=cron_ig, interval_sec=None)
                payload.pop("interval_sec", None)
            elif kind == "fb_post":
                payload = _build_upsert_payload(row, cron=cron_fb, interval_sec=None)
                payload.pop("interval_sec", None)
            elif kind == "report":
                payload = _build_upsert_payload(row, cron=cron_report, interval_sec=None)
                payload.pop("interval_sec", None)
            else:
                continue

            _request_json("POST", args.api_url, "/automation/agent-workflow", args.token, payload=payload)
            print(f"  + {job_id} -> {payload.get('cron')}")
            total += 1

    print(f"updated_jobs={total}")
    return 0


def cmd_channels(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    channels = _normalize_channels(args.channels)

    for inf in manifest.get("influencers") or []:
        if args.target != "all" and str(inf.get("id")) != args.target:
            continue
        inf["channels_active"] = channels
        print(f"[CHANNELS] {inf.get('id')} -> {','.join(channels)}")

    _save_manifest(args.manifest, manifest)
    print("manifest updated")
    return 0


def _resolve_post_job_for_channel(inf: Dict[str, Any], jobs_map: Dict[str, Dict[str, Any]], channel: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    expected_kind = POST_KIND_BY_CHANNEL.get(channel)
    if not expected_kind:
        return None
    for job_id in inf.get("jobs") or []:
        if _job_kind(job_id) == expected_kind:
            row = jobs_map.get(job_id)
            if row:
                return job_id, row
    return None


def cmd_chain(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    jobs_map = _get_jobs(args.api_url, args.token)

    if args.gap_min_sec < 0 or args.gap_max_sec < 0:
        raise RuntimeError("gap detik tidak boleh negatif")
    if args.gap_max_sec < args.gap_min_sec:
        raise RuntimeError("gap_max_sec harus >= gap_min_sec")

    rng = random.Random(args.seed)
    cursor_sec = _hhmm_to_total_seconds(args.start)
    total = 0

    # Catatan: scheduler sekarang basis menit (cron 5-field), jadi gap detik diaproksimasi ke menit + jitter.
    for inf in _selected_influencers(manifest, args.target):
        inf_id = str(inf.get("id"))
        channels = list(inf.get("channels_active") or ["fb", "ig", "wa"])
        post_order = [ch for ch in ["fb", "ig"] if ch in channels]

        if not post_order:
            print(f"[CHAIN] {inf_id} -> skip (tidak ada channel post aktif)")
            cursor_sec += int(args.next_inf_gap_sec)
            continue

        print(f"[CHAIN] {inf_id} start~{_seconds_to_cron(cursor_sec)} order={','.join(post_order)}")

        local_sec = cursor_sec
        for idx, ch in enumerate(post_order):
            found = _resolve_post_job_for_channel(inf, jobs_map, ch)
            if not found:
                print(f"  ! missing post job channel={ch}")
                continue

            job_id, row = found
            if idx > 0:
                local_sec += rng.randint(args.gap_min_sec, args.gap_max_sec)

            cron = _seconds_to_cron(local_sec)
            sec_part = local_sec % 60
            # dispatch_jitter dipakai kecil untuk efek tidak kaku. Bukan delay fix.
            jitter = min(59, max(0, sec_part))

            payload = _build_upsert_payload(row, cron=cron, interval_sec=None, dispatch_jitter_sec=jitter)
            payload.pop("interval_sec", None)
            _request_json("POST", args.api_url, "/automation/agent-workflow", args.token, payload=payload)
            print(f"  + {job_id} -> {cron} (jitter={jitter}s)")
            total += 1

        cursor_sec = local_sec + int(args.next_inf_gap_sec)

    print(f"updated_jobs={total}")
    print("note=chain uses minute cron + jitter approximation")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Spio No-Code Command Center")
    parser.add_argument("--manifest", default=os.getenv("MANIFEST_PATH", MANIFEST_DEFAULT), help="Path ke manifest JSON")
    parser.add_argument("--api-url", default=os.getenv("SPIO_API_URL", API_DEFAULT), help="Base URL API")
    parser.add_argument("--token", default=_read_admin_token(), help="Admin token (opsional, auto-detect dari .env)")

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="Lihat status jobs per influencer")
    p_status.add_argument("target", nargs="?", default="all", help="inf_001..inf_010 atau all")
    p_status.set_defaults(func=cmd_status)

    p_on = sub.add_parser("on", help="Aktifkan jobs influencer")
    p_on.add_argument("target", nargs="?", default="all", help="inf_001..inf_010 atau all")
    p_on.set_defaults(func=cmd_switch, action="on")

    p_off = sub.add_parser("off", help="Matikan jobs influencer")
    p_off.add_argument("target", nargs="?", default="all", help="inf_001..inf_010 atau all")
    p_off.set_defaults(func=cmd_switch, action="off")

    p_strategy = sub.add_parser("strategy", help="Ganti strategi copy/prompt")
    p_strategy.add_argument("target", help="inf_001..inf_010 atau all")
    p_strategy.add_argument("preset", choices=["softsell", "hardclose", "story", "endorse"], help="Preset strategi")
    p_strategy.set_defaults(func=cmd_strategy)

    p_tone = sub.add_parser("tone", help="Atur gaya balasan DM/WA")
    p_tone.add_argument("target", help="inf_001..inf_010 atau all")
    p_tone.add_argument("tone", choices=["warm", "formal", "hard"], help="Nada balasan")
    p_tone.set_defaults(func=cmd_tone)

    p_follow = sub.add_parser("followup", help="Mode follow-up WA")
    p_follow.add_argument("target", help="inf_001..inf_010 atau all")
    p_follow.add_argument("mode", choices=["lembut", "keras", "formal"], help="Mode follow-up")
    p_follow.set_defaults(func=cmd_followup)

    p_cadence = sub.add_parser("cadence", help="Atur kecepatan reply/follow-up")
    p_cadence.add_argument("target", help="inf_001..inf_010 atau all")
    p_cadence.add_argument("mode", choices=["slow", "normal", "fast"], help="Mode cadence")
    p_cadence.set_defaults(func=cmd_cadence)

    p_schedule = sub.add_parser("schedule", help="Atur jam posting/report")
    p_schedule.add_argument("target", help="inf_001..inf_010 atau all")
    p_schedule.add_argument("--ig", required=True, help="Jam IG post, format HH:MM")
    p_schedule.add_argument("--fb", required=True, help="Jam FB post, format HH:MM")
    p_schedule.add_argument("--report", required=True, help="Jam report, format HH:MM")
    p_schedule.set_defaults(func=cmd_schedule)

    p_channels = sub.add_parser("channels", help="Set channel aktif influencer")
    p_channels.add_argument("target", help="inf_001..inf_010 atau all")
    p_channels.add_argument("channels", help="Contoh: ig,fb atau ig atau fb,ig,wa")
    p_channels.set_defaults(func=cmd_channels)

    p_chain = sub.add_parser("chain", help="Susun urutan posting per influencer (berantai)")
    p_chain.add_argument("target", help="inf_001..inf_010 atau all")
    p_chain.add_argument("--start", required=True, help="Jam mulai influencer pertama (HH:MM)")
    p_chain.add_argument("--gap-min-sec", type=int, default=70, help="Gap minimal antar channel dalam influencer (detik)")
    p_chain.add_argument("--gap-max-sec", type=int, default=130, help="Gap maksimal antar channel dalam influencer (detik)")
    p_chain.add_argument("--next-inf-gap-sec", type=int, default=80, help="Gap setelah influencer selesai ke influencer berikutnya (detik)")
    p_chain.add_argument("--seed", type=int, default=None, help="Seed random opsional agar reproducible")
    p_chain.set_defaults(func=cmd_chain)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.token:
        print("Token admin tidak ditemukan. Isi SPIO_ADMIN_TOKEN atau AUTH_API_KEYS di /opt/spio-agent/.env", file=sys.stderr)
        return 2

    try:
        return int(args.func(args) or 0)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
