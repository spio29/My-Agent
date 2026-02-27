# Planner Model Benchmark Gate

Script ini dipakai untuk menilai kandidat model AI planner (misalnya hasil hunting Hugging Face) dengan prompt set tetap.

## File
- Script: `scripts/testing/benchmark_planner_models.py`
- Prompt set default: `scripts/testing/planner_benchmark_prompts.json`

## Tujuan
- Ukur latency (`p50`, `p95`)
- Ukur stabilitas (timeout rate)
- Ukur ketergantungan fallback ke rule-based
- Ukur kualitas dasar (expected job types terpenuhi)

## Contoh Pakai

```bash
python3 scripts/testing/benchmark_planner_models.py \
  --api-base http://127.0.0.1:8000 \
  --auth-token "<OPERATOR_TOKEN>" \
  --ai-provider ollama \
  --ai-account-id default \
  --models "qwen2.5:0.5b,spio:latest"
```

## Output
- Ringkasan per model di stdout
- JSON report lengkap di `/tmp/planner_model_benchmark_<timestamp>.json`

## Gate Default
- `min_pass_rate=0.90`
- `max_timeout_rate=0.05`
- `max_fallback_rate=0.30`
- `min_ai_source_rate=0.70`
- `max_p95_latency_sec=12.0`

Semua nilai bisa diubah lewat argumen CLI.

## Catatan
Endpoint yang dipakai adalah `/planner/plan-ai`, jadi benchmark **tidak membuat job eksekusi**.
