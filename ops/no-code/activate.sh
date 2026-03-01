#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-all}"
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_PATH="${MANIFEST_PATH:-$BASE_DIR/manifest.json}"
API_URL="${SPIO_API_URL:-http://127.0.0.1:8000}"
TOKEN="${SPIO_ADMIN_TOKEN:-$(grep '^AUTH_API_KEYS=' /opt/spio-agent/.env | cut -d= -f2 | cut -d, -f1 | cut -d: -f1)}"

python3 - "$MANIFEST_PATH" "$API_URL" "$TOKEN" "$TARGET" <<'PY'
import json
import sys
import urllib.request

manifest_path, api_url, token, target = sys.argv[1:5]
manifest = json.load(open(manifest_path, "r", encoding="utf-8"))
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def put(path: str):
    req = urllib.request.Request(api_url + path, headers=headers, data=b"{}", method="PUT")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())

selected = []
for inf in manifest.get("influencers", []):
    if target == "all" or inf.get("id") == target:
        selected.append(inf)

if not selected:
    valid = [i.get("id") for i in manifest.get("influencers", [])]
    raise SystemExit(f"Target tidak ditemukan: {target}. Pilihan: all, " + ", ".join(valid))

for inf in selected:
    print(f"[ON] {inf.get('id')} {inf.get('name')}")
    for job_id in inf.get("jobs", []):
        try:
            put(f"/jobs/{job_id}/enable")
            print(f"  + enabled {job_id}")
        except Exception as exc:
            print(f"  ! failed  {job_id}: {exc}")
PY
