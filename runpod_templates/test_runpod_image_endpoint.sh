#!/usr/bin/env bash
set -euo pipefail

# Test endpoint image RunPod sampai selesai.
# Usage:
#   ./test_runpod_image_endpoint.sh <api_key> <endpoint_id>

if [[ "${1:-}" == "" || "${2:-}" == "" ]]; then
  echo "Usage: $0 <runpod_api_key> <endpoint_id>"
  exit 1
fi

API_KEY="$1"
ENDPOINT_ID="$2"
API_BASE="https://api.runpod.ai/v2"

post_payload='{
  "input": {
    "prompt": "ultra realistic Indonesian female influencer, natural skin texture, realistic pores, proportional full body, soft studio lighting, photorealistic",
    "negative_prompt": "deformed body, extra fingers, extra limbs, bad anatomy, plastic skin, blurry, lowres",
    "width": 768,
    "height": 1344,
    "steps": 6,
    "cfg_scale": 1.5,
    "seed": 12345
  }
}'

echo "==> Submit job to $ENDPOINT_ID"
RUN_RESP="$(curl -sS -X POST "$API_BASE/$ENDPOINT_ID/run" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "$post_payload")"

echo "$RUN_RESP"

JOB_ID="$(python3 - <<'PY' "$RUN_RESP"
import json, sys
raw = sys.argv[1]
try:
    data = json.loads(raw)
except Exception:
    print("")
    raise SystemExit(0)
print(data.get("id", ""))
PY
)"

if [[ -z "$JOB_ID" ]]; then
  echo "ERROR: Job ID tidak ditemukan. Cek response di atas."
  exit 1
fi

echo "==> Job ID: $JOB_ID"
echo "==> Poll status tiap 5 detik (maks 5 menit)..."

for _ in $(seq 1 60); do
  sleep 5
  STATUS_RESP="$(curl -sS -X GET "$API_BASE/$ENDPOINT_ID/status/$JOB_ID" \
    -H "Authorization: Bearer $API_KEY")"

  STATUS="$(python3 - <<'PY' "$STATUS_RESP"
import json, sys
try:
    data = json.loads(sys.argv[1])
except Exception:
    print("UNKNOWN")
    raise SystemExit(0)
print(data.get("status", "UNKNOWN"))
PY
)"

  echo "status=$STATUS"

  if [[ "$STATUS" == "COMPLETED" ]]; then
    echo "$STATUS_RESP"
    IMAGE_URL="$(python3 - <<'PY' "$STATUS_RESP"
import json, sys
try:
    data = json.loads(sys.argv[1])
except Exception:
    print("")
    raise SystemExit(0)
out = data.get("output", {}) if isinstance(data, dict) else {}
if isinstance(out, dict):
    print(out.get("image_url", ""))
else:
    print("")
PY
)"
    if [[ -n "$IMAGE_URL" ]]; then
      echo "SUKSES image_url=$IMAGE_URL"
    else
      echo "SUKSES tapi image_url kosong, cek field output endpoint."
    fi
    exit 0
  fi

  if [[ "$STATUS" == "FAILED" ]]; then
    echo "FAILED:"
    echo "$STATUS_RESP"
    exit 1
  fi
done

echo "TIMEOUT: job belum selesai dalam 5 menit."
exit 1
