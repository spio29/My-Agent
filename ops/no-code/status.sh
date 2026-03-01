#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_PATH="${MANIFEST_PATH:-$BASE_DIR/manifest.json}"
API_URL="${SPIO_API_URL:-http://127.0.0.1:8000}"
TOKEN="${SPIO_ADMIN_TOKEN:-$(grep '^AUTH_API_KEYS=' /opt/spio-agent/.env | cut -d= -f2 | cut -d, -f1 | cut -d: -f1)}"

python3 - "$MANIFEST_PATH" "$API_URL" "$TOKEN" <<'PY'
import json
import sys
import urllib.request

manifest_path, api_url, token = sys.argv[1], sys.argv[2], sys.argv[3]
manifest = json.load(open(manifest_path, "r", encoding="utf-8"))
headers = {"Authorization": f"Bearer {token}"}

def get(path: str):
    req = urllib.request.Request(api_url + path, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())

accounts = get("/integrations/accounts")
jobs = get("/automation/agent-workflows")

acc_map = {(a.get("provider"), a.get("account_id")): a for a in accounts}
job_map = {j.get("job_id"): j for j in jobs}

print("=== NO-CODE FRAMEWORK STATUS ===")
print(f"Framework: {manifest.get('framework')} | Version: {manifest.get('version')}")
print()

provider_by_channel = {
    "instagram": "instagram_graph",
    "facebook": "facebook_graph",
    "whatsapp": "whatsapp_api",
}

for inf in manifest.get("influencers", []):
    inf_id = inf.get("id")
    print(f"[{inf_id}] {inf.get('name')} ({inf.get('model')})")

    for ch, acc_id in (inf.get("accounts") or {}).items():
        provider = provider_by_channel.get(ch, "")
        row = acc_map.get((provider, acc_id))
        if not row:
            print(f"  - {ch:<10} {acc_id:<10} -> MISSING")
            continue
        cfg = row.get("config") or {}
        id_key = "instagram_user_id" if provider == "instagram_graph" else ("facebook_page_id" if provider == "facebook_graph" else "phone_number_id")
        has_id = bool(str(cfg.get(id_key) or "").strip())
        has_secret = bool(row.get("has_secret"))
        enabled = bool(row.get("enabled"))
        readiness = "READY" if has_id and has_secret and enabled else "NOT_READY"
        print(f"  - {ch:<10} {acc_id:<10} -> {readiness} (enabled={enabled}, token={has_secret}, id={has_id})")

    enabled_jobs = 0
    missing_jobs = 0
    for job_id in inf.get("jobs", []):
        row = job_map.get(job_id)
        if not row:
            missing_jobs += 1
            continue
        if row.get("enabled"):
            enabled_jobs += 1

    total_jobs = len(inf.get("jobs", []))
    print(f"  - jobs       total={total_jobs} enabled={enabled_jobs} missing={missing_jobs}")
    print()

print("Tip: aktifkan per influencer dengan ./activate.sh inf_001")
PY
