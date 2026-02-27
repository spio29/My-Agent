import argparse
import json
import math
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple
from urllib import error, request


def _http_json(api_base: str, path: str, method: str = "GET", payload: Dict[str, Any] = None) -> Tuple[int, Any]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = request.Request(
        url=f"{api_base.rstrip('/')}{path}",
        method=method.upper(),
        headers=headers,
        data=data,
    )
    try:
        with request.urlopen(req, timeout=20) as response:
            body = response.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            return response.status, parsed
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body) if body else {"detail": body}
        except Exception:
            parsed = {"detail": body}
        return exc.code, parsed


def _buat_job_spec(job_id: str, interval_sec: int, work_ms: int, jitter_sec: int) -> Dict[str, Any]:
    timeout_ms = max(5000, work_ms + 5000)
    return {
        "job_id": job_id,
        "type": "simulation.heavy",
        "schedule": {"interval_sec": interval_sec},
        "timeout_ms": timeout_ms,
        "retry_policy": {"max_retry": 0, "backoff_sec": [1]},
        "inputs": {
            "work_ms": work_ms,
            "payload_kb": 0,
            "allow_overlap": False,
            "dispatch_jitter_sec": max(0, jitter_sec),
            "source": "safe_load_simulation",
        },
    }


def _ringkas_snapshot(rows_runs: List[Dict[str, Any]], prefix: str) -> Dict[str, Any]:
    rows = [row for row in rows_runs if str(row.get("job_id", "")).startswith(prefix)]
    status = Counter(str(row.get("status", "unknown")) for row in rows)
    aktif_per_job = defaultdict(int)
    for row in rows:
        row_status = str(row.get("status", ""))
        if row_status in {"queued", "running"}:
            aktif_per_job[str(row.get("job_id", ""))] += 1

    overlap_jobs = {job_id: count for job_id, count in aktif_per_job.items() if count > 1}
    return {
        "total_runs": len(rows),
        "status": dict(status),
        "active_jobs": len(aktif_per_job),
        "overlap_jobs": overlap_jobs,
    }


def main():
    parser = argparse.ArgumentParser(description="Safe load simulation for 100+ scheduled jobs.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000", help="Base URL API")
    parser.add_argument("--jobs", type=int, default=100, help="Total jobs to create")
    parser.add_argument("--interval-sec", type=int, default=30, help="Interval per job (seconds)")
    parser.add_argument("--work-ms", type=int, default=8000, help="Synthetic work duration per run (ms)")
    parser.add_argument("--jitter-sec", type=int, default=25, help="Dispatch jitter per job (seconds)")
    parser.add_argument("--duration-sec", type=int, default=90, help="Monitoring duration (seconds)")
    parser.add_argument("--tick-sec", type=int, default=10, help="Snapshot period (seconds)")
    parser.add_argument("--prefix", default="simsafe", help="Job ID prefix")
    parser.add_argument("--cleanup", action="store_true", help="Disable simulation jobs at the end")
    args = parser.parse_args()

    if args.jobs <= 0:
        raise SystemExit("--jobs harus > 0")
    if args.interval_sec < 10:
        raise SystemExit("--interval-sec minimal 10")
    if args.duration_sec < args.tick_sec:
        raise SystemExit("--duration-sec harus >= --tick-sec")

    api_base = args.api_base.rstrip("/")
    ids_job = [f"{args.prefix}-{i:03d}" for i in range(args.jobs)]

    print(f"[SIM] API             : {api_base}")
    print(f"[SIM] Jobs            : {args.jobs}")
    print(f"[SIM] Interval        : {args.interval_sec}s")
    print(f"[SIM] Work per run    : {args.work_ms}ms")
    print(f"[SIM] Dispatch jitter : {args.jitter_sec}s")
    print(f"[SIM] Duration        : {args.duration_sec}s")
    print("")

    # Create/update all jobs
    ok_count = 0
    fail_count = 0
    for job_id in ids_job:
        status, body = _http_json(
            api_base,
            "/jobs",
            method="POST",
            payload=_buat_job_spec(job_id, args.interval_sec, args.work_ms, args.jitter_sec),
        )
        if status in {200, 201}:
            ok_count += 1
        else:
            # If job already exists, overwrite via disable+create fallback is not required for simulation.
            fail_count += 1
            print(f"[SIM][WARN] Gagal create {job_id}: status={status} body={body}")

    print(f"[SIM] Create success  : {ok_count}")
    print(f"[SIM] Create failed   : {fail_count}")

    teoretis_rps = args.jobs / float(args.interval_sec)
    kapasitas_per_worker_rps = 1000.0 / float(max(1, args.work_ms))
    minimum_worker = max(1, int(math.ceil((teoretis_rps / kapasitas_per_worker_rps) * 1.3)))
    print(f"[SIM] Throughput target ~ {teoretis_rps:.2f} run/s")
    print(f"[SIM] Rekomendasi worker minimal (safe 30% headroom): {minimum_worker}")
    print("")

    # Monitoring loop
    snapshot = []
    loops = max(1, args.duration_sec // args.tick_sec)
    for i in range(1, loops + 1):
        time.sleep(args.tick_sec)
        _, runs = _http_json(api_base, "/runs?limit=500")
        _, queue = _http_json(api_base, "/queue")
        ringkas = _ringkas_snapshot(runs if isinstance(runs, list) else [], args.prefix)
        ringkas["queue_depth"] = int((queue or {}).get("depth", 0))
        ringkas["queue_delayed"] = int((queue or {}).get("delayed", 0))
        ringkas["t"] = i * args.tick_sec
        snapshot.append(ringkas)

        overlap_count = len(ringkas["overlap_jobs"])
        print(
            f"[SIM][t={ringkas['t']:>3}s] "
            f"runs={ringkas['total_runs']:<4} "
            f"queued={ringkas['status'].get('queued', 0):<3} "
            f"running={ringkas['status'].get('running', 0):<3} "
            f"success={ringkas['status'].get('success', 0):<3} "
            f"failed={ringkas['status'].get('failed', 0):<3} "
            f"q_depth={ringkas['queue_depth']:<4} "
            f"overlap_jobs={overlap_count}"
        )

    max_queue = max((row["queue_depth"] for row in snapshot), default=0)
    max_overlap_jobs = max((len(row["overlap_jobs"]) for row in snapshot), default=0)
    total_runs_akhir = snapshot[-1]["total_runs"] if snapshot else 0

    print("")
    print("[SIM] Ringkasan akhir")
    print(f"[SIM] Total runs terpantau : {total_runs_akhir}")
    print(f"[SIM] Max queue depth      : {max_queue}")
    print(f"[SIM] Max overlap jobs     : {max_overlap_jobs}")
    if max_overlap_jobs == 0:
        print("[SIM] Guard overlap        : OK (tidak ada job overlap)")
    else:
        print("[SIM] Guard overlap        : WARNING (ada job overlap)")

    if args.cleanup:
        disabled = 0
        for job_id in ids_job:
            status, _ = _http_json(api_base, f"/jobs/{job_id}/disable", method="PUT")
            if status == 200:
                disabled += 1
        print(f"[SIM] Cleanup disabled jobs: {disabled}/{len(ids_job)}")


if __name__ == "__main__":
    main()
