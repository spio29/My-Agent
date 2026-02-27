#!/usr/bin/env python3
"""Benchmark gate for planner AI model candidates.

This script benchmarks `/planner/plan-ai` using a fixed prompt set, then
computes latency + quality metrics per model and determines pass/fail against
configurable thresholds.
"""

import argparse
import json
import math
import socket
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, request


DEFAULT_PROMPTS_FILE = Path(__file__).with_name("planner_benchmark_prompts.json")


@dataclass
class CaseResult:
    case_id: str
    model: str
    latency_sec: float
    http_status: Optional[int]
    timed_out: bool
    planner_source: str
    fallback_used: bool
    expected_job_types: List[str]
    actual_job_types: List[str]
    passed: bool
    error: str
    warnings: List[str]


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(math.ceil((p / 100.0) * len(ordered)) - 1)))
    return ordered[idx]


def _load_prompts(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Prompt file must be a JSON array")

    cleaned: List[Dict[str, Any]] = []
    for idx, row in enumerate(data, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Prompt item #{idx} must be an object")
        case_id = str(row.get("id") or f"case-{idx:02d}").strip()
        prompt = str(row.get("prompt") or "").strip()
        expected = row.get("expected_job_types") or []
        if not prompt:
            raise ValueError(f"Prompt item '{case_id}' is empty")
        if not isinstance(expected, list):
            raise ValueError(f"Prompt item '{case_id}': expected_job_types must be list")
        cleaned.append(
            {
                "id": case_id,
                "prompt": prompt,
                "expected_job_types": [str(x).strip() for x in expected if str(x).strip()],
                "timezone": str(row.get("timezone") or "Asia/Jakarta"),
                "default_channel": str(row.get("default_channel") or "telegram"),
                "default_account_id": str(row.get("default_account_id") or "bot_a01"),
                "max_steps": int(row.get("max_steps") or 1),
            }
        )
    return cleaned


def _http_json(
    base_url: str,
    path: str,
    payload: Dict[str, Any],
    token: str,
    timeout_sec: int,
) -> Tuple[Optional[int], Any, str, bool]:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(
        url=f"{base_url.rstrip('/')}{path}",
        method="POST",
        headers=headers,
        data=body,
    )

    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return int(resp.status), parsed, "", False
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"detail": raw}
        return int(exc.code), parsed, str(parsed.get("detail") or raw or "http_error"), False
    except (TimeoutError, socket.timeout):
        return None, None, "request_timeout", True
    except Exception as exc:
        return None, None, str(exc), False


def _extract_job_types(payload: Dict[str, Any]) -> List[str]:
    rows = payload.get("jobs")
    if not isinstance(rows, list):
        return []
    output: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        spec = row.get("job_spec")
        if not isinstance(spec, dict):
            continue
        job_type = str(spec.get("type") or "").strip()
        if job_type:
            output.append(job_type)
    return output


def _run_case(
    case: Dict[str, Any],
    model: str,
    args: argparse.Namespace,
    token: str,
) -> CaseResult:
    payload = {
        "prompt": case["prompt"],
        "timezone": case["timezone"],
        "default_channel": case["default_channel"],
        "default_account_id": case["default_account_id"],
        "ai_provider": args.ai_provider,
        "ai_account_id": args.ai_account_id,
        "model_id": model,
        "max_steps": int(case.get("max_steps") or args.max_steps),
        "force_rule_based": False,
    }

    start = time.perf_counter()
    status, data, err, timed_out = _http_json(
        base_url=args.api_base,
        path="/planner/plan-ai",
        payload=payload,
        token=token,
        timeout_sec=args.request_timeout_sec,
    )
    latency = round(time.perf_counter() - start, 3)

    planner_source = ""
    warnings: List[str] = []
    actual_types: List[str] = []
    fallback_used = True

    if isinstance(data, dict):
        planner_source = str(data.get("planner_source") or "")
        warnings = [str(x) for x in (data.get("warnings") or []) if str(x).strip()]
        actual_types = _extract_job_types(data)
        fallback_used = planner_source != "smolagents"

    expected_types = case["expected_job_types"]
    missing_expected = [x for x in expected_types if x not in actual_types]

    passed = (
        (status == 200)
        and (not timed_out)
        and bool(actual_types)
        and (not missing_expected)
    )

    if missing_expected:
        err = (err + "; " if err else "") + f"missing_expected={','.join(missing_expected)}"

    return CaseResult(
        case_id=case["id"],
        model=model,
        latency_sec=latency,
        http_status=status,
        timed_out=timed_out,
        planner_source=planner_source,
        fallback_used=fallback_used,
        expected_job_types=list(expected_types),
        actual_job_types=actual_types,
        passed=passed,
        error=err,
        warnings=warnings,
    )


def _summarize(model: str, rows: List[CaseResult], args: argparse.Namespace) -> Dict[str, Any]:
    total = len(rows)
    timeouts = sum(1 for r in rows if r.timed_out)
    fallback = sum(1 for r in rows if r.fallback_used)
    passed = sum(1 for r in rows if r.passed)
    ai_source = sum(1 for r in rows if r.planner_source == "smolagents")
    latencies = [r.latency_sec for r in rows]

    pass_rate = (passed / total) if total else 0.0
    timeout_rate = (timeouts / total) if total else 0.0
    fallback_rate = (fallback / total) if total else 0.0
    ai_source_rate = (ai_source / total) if total else 0.0

    p50 = _percentile(latencies, 50)
    p95 = _percentile(latencies, 95)

    reasons: List[str] = []
    if pass_rate < args.min_pass_rate:
        reasons.append(f"pass_rate<{args.min_pass_rate}")
    if timeout_rate > args.max_timeout_rate:
        reasons.append(f"timeout_rate>{args.max_timeout_rate}")
    if fallback_rate > args.max_fallback_rate:
        reasons.append(f"fallback_rate>{args.max_fallback_rate}")
    if ai_source_rate < args.min_ai_source_rate:
        reasons.append(f"ai_source_rate<{args.min_ai_source_rate}")
    if p95 > args.max_p95_latency_sec:
        reasons.append(f"p95>{args.max_p95_latency_sec}s")

    gate_pass = not reasons

    return {
        "model": model,
        "total_cases": total,
        "passed_cases": passed,
        "pass_rate": round(pass_rate, 4),
        "timeout_count": timeouts,
        "timeout_rate": round(timeout_rate, 4),
        "fallback_count": fallback,
        "fallback_rate": round(fallback_rate, 4),
        "ai_source_count": ai_source,
        "ai_source_rate": round(ai_source_rate, 4),
        "latency_p50_sec": round(p50, 3),
        "latency_p95_sec": round(p95, 3),
        "gate_pass": gate_pass,
        "gate_fail_reasons": reasons,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark gate for planner AI model candidates")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--auth-token", default="")
    parser.add_argument("--models", required=True, help="Comma-separated models, e.g. qwen2.5:0.5b,spio:latest")
    parser.add_argument("--ai-provider", default="ollama")
    parser.add_argument("--ai-account-id", default="default")
    parser.add_argument("--prompts-file", default=str(DEFAULT_PROMPTS_FILE))
    parser.add_argument("--output", default="")
    parser.add_argument("--request-timeout-sec", type=int, default=70)
    parser.add_argument("--pause-sec", type=float, default=0.2)
    parser.add_argument("--max-steps", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)

    # Gate thresholds
    parser.add_argument("--min-pass-rate", type=float, default=0.90)
    parser.add_argument("--max-timeout-rate", type=float, default=0.05)
    parser.add_argument("--max-fallback-rate", type=float, default=0.30)
    parser.add_argument("--min-ai-source-rate", type=float, default=0.70)
    parser.add_argument("--max-p95-latency-sec", type=float, default=12.0)

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    token = args.auth_token.strip()
    if not token:
        raise SystemExit("Missing auth token. Pass --auth-token or set SPIO_API_TOKEN env and reuse here.")

    prompts_path = Path(args.prompts_file)
    if not prompts_path.exists():
        raise SystemExit(f"Prompt file not found: {prompts_path}")

    cases = _load_prompts(prompts_path)
    if args.limit and args.limit > 0:
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("No cases loaded.")

    models = [x.strip() for x in args.models.split(",") if x.strip()]
    if not models:
        raise SystemExit("No models parsed from --models")

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    all_results: List[CaseResult] = []
    summaries: List[Dict[str, Any]] = []

    print(f"[BENCH] API: {args.api_base}")
    print(f"[BENCH] Cases: {len(cases)}")
    print(f"[BENCH] Models: {', '.join(models)}")
    print("")

    for model in models:
        rows: List[CaseResult] = []
        print(f"[BENCH] Model: {model}")
        for idx, case in enumerate(cases, start=1):
            row = _run_case(case=case, model=model, args=args, token=token)
            rows.append(row)
            all_results.append(row)
            status_tag = "PASS" if row.passed else "FAIL"
            print(
                f"  - [{status_tag}] {idx:02d}/{len(cases)} {row.case_id} "
                f"lat={row.latency_sec:.2f}s src={row.planner_source or '-'} "
                f"types={','.join(row.actual_job_types) or '-'} err={row.error or '-'}"
            )
            if args.pause_sec > 0:
                time.sleep(args.pause_sec)

        summary = _summarize(model=model, rows=rows, args=args)
        summaries.append(summary)
        print(
            "  => "
            f"pass_rate={summary['pass_rate']:.2%}, "
            f"timeout_rate={summary['timeout_rate']:.2%}, "
            f"fallback_rate={summary['fallback_rate']:.2%}, "
            f"ai_source_rate={summary['ai_source_rate']:.2%}, "
            f"p95={summary['latency_p95_sec']:.2f}s, "
            f"gate={'PASS' if summary['gate_pass'] else 'FAIL'}"
        )
        if summary["gate_fail_reasons"]:
            print(f"     reasons: {', '.join(summary['gate_fail_reasons'])}")
        print("")

    report = {
        "started_at": started_at,
        "api_base": args.api_base,
        "provider": args.ai_provider,
        "account_id": args.ai_account_id,
        "models": models,
        "prompts_file": str(prompts_path),
        "thresholds": {
            "min_pass_rate": args.min_pass_rate,
            "max_timeout_rate": args.max_timeout_rate,
            "max_fallback_rate": args.max_fallback_rate,
            "min_ai_source_rate": args.min_ai_source_rate,
            "max_p95_latency_sec": args.max_p95_latency_sec,
        },
        "summaries": summaries,
        "results": [asdict(x) for x in all_results],
    }

    output_path = args.output.strip()
    if not output_path:
        ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        output_path = str(Path("/tmp") / f"planner_model_benchmark_{ts}.json")
    Path(output_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[BENCH] Report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
