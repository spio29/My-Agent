# Multi-Job Platform

![CI](https://github.com/amoyzaskia33-max/multi-job/actions/workflows/ci.yml/badge.svg)

A scalable job processing platform built with Python and Redis.

## Dokumentasi Utama

- Buku panduan sistem end-to-end: [docs/BUKU_PANDUAN_SISTEM.md](docs/BUKU_PANDUAN_SISTEM.md)
- Checklist operasional harian: [docs/CHECKLIST_OPERASIONAL_HARIAN.md](docs/CHECKLIST_OPERASIONAL_HARIAN.md)
- Template insiden/postmortem: [docs/TEMPLATE_INSIDEN_POSTMORTEM.md](docs/TEMPLATE_INSIDEN_POSTMORTEM.md)
- FAQ operasional: [docs/FAQ_OPERASIONAL.md](docs/FAQ_OPERASIONAL.md)
- Skill registry & CLI: [docs/skill-registry.md](docs/skill-registry.md)

## Deployment & Production

- Panduan deployment VPS lengkap: [DEPLOYMENT_VPS.md](docs/DEPLOYMENT_VPS.md)
- Checklist pre-deployment: [CHECKLIST_DEPLOYMENT.md](docs/CHECKLIST_DEPLOYMENT.md)
- Setup script otomatis: [scripts/setup-vps.sh](scripts/setup-vps.sh)
- Quick deploy script: [scripts/deploy.sh](scripts/deploy.sh)
- Production docker-compose: [docker-compose.prod.yml](docker-compose.prod.yml)

## CLI Integration

Poetry exposes `poetry run spio-skill` sebagai entry point supaya skill registry bisa dioperasikan dari terminal:

```bash
poetry run spio-skill install ./skills/content-brief.yaml
poetry run spio-skill list
poetry run spio-skill describe skill_content_brief
poetry run spio-skill delete skill_content_brief
```

`spio-skill` adalah alias ke `scripts/spio_skill.py`, jadi perintah yang sama bisa dijalankan via `python scripts/spio_skill.py ...` jika tidak menggunakan Poetry.

## Release Automation

GitHub Actions akan membuat release otomatis setiap kali tag `v*.*.*` (semver) dipush:

1. Workflow `ci.yml` tetap berjalan untuk `pytest` backend + Playwright e2e.
2. Workflow `release.yml` membangun artefak (backend ZIP, produksi Next.js UI) dan membuat GitHub Release dengan file tersebut.
3. Tag baru juga memudahkan milestone & changelog, jadi cukup `git tag -a v1.0.0 -m "Release v1.0.0"` lalu push.

## Architecture

The platform consists of four main services:

1. **API Service** - FastAPI for CRUD operations, health checks, and metrics
2. **Scheduler Service** - Manages scheduled jobs (interval/cron)
3. **Worker Service** - Executes jobs from the queue
4. **Connector Service** - Manages external connections (webhook, Telegram, email, voice, Slack, SMS) and approval-aware triggers

## Key Features

- **Job Scheduling**: Interval-based and cron scheduling
- **Retry Logic**: Configurable retry policies with exponential backoff
- **Tool System**: Reusable tools (HTTP, KV, Messaging, Files, Metrics)
- **Observability**: Structured logging, metrics, and health endpoints
- **Redis-Based Queue**: Uses Redis Streams for job queuing and ZSET for delayed jobs

## Project Structure

```
multi_job/
├── app/
│   ├── core/               # Core components
│   │   ├── config.py       # Configuration
│   │   ├── redis_client.py # Redis client
│   │   ├── models.py       # Pydantic models
│   │   ├── queue.py        # Queue system (Streams + ZSET)
│   │   ├── runner.py       # Job execution pipeline
│   │   ├── registry.py     # Job type -> handler mapping
│   │   ├── observability.py # Logger + metrics + tracing
│   │   ├── policies.py     # Tool allowlist/denylist
│   │   ├── tools/          # Tool implementations
│   │   └── connectors/     # Connector implementations
│   ├── jobs/
│   │   ├── specs/          # Job specifications (JSON/YAML)
│   │   └── handlers/       # Job logic handlers
│   └── services/
│       ├── api/            # API service (FastAPI)
│       ├── worker/         # Worker service
│       ├── scheduler/      # Scheduler service
│       └── connector/      # Connector service
├── tests/                  # Test files
├── docker-compose.yml      # Docker configuration
├── pyproject.toml          # Dependency management
└── README.md               # This file
```

## Getting Started

### Node.js Version (UI/E2E)
- Recommended: **Node.js 22 LTS** (v22.22.0 tested on VPS).
- Minimum supported: >=20.19.0 (required by modern eslint toolchain).


1. Start Redis:
   ```bash
   docker-compose up -d redis
   ```

2. Install dependencies:
   ```bash
   pip install -e .
   ```

3. Run services:
   - API: `python -m uvicorn app.services.api.main:app --host 127.0.0.1 --port 8000`
   - Worker: `python -m app.services.worker.main`
   - Scheduler: `python -m app.services.scheduler.main`
   - Connector: `python -m app.services.connector.main`

4. Run Next.js frontend:
   ```bash
   cd ui
   npm install
   npm run build
   npm run serve
   ```
   UI URL: `http://127.0.0.1:3000`

Quick Windows launcher:
```bat
scripts\testing\start-local.cmd
```
This opens 5 windows (API, worker, scheduler, connector, UI).  
To stop:
```bat
scripts\testing\stop-local.cmd
```

Alternative launcher with health check + PID/log tracking (recommended):
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\testing\start-local.ps1
```
Check status:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\testing\status-local.ps1
```
Stop all:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\testing\stop-local.ps1
```
Logs are stored in:
```text
.\runtime-logs
```

## UI E2E (Playwright)

From the UI directory, run:
```bash
e2e-local.cmd
```

Or via PowerShell:
```powershell
.\e2e-local.ps1
```

Both scripts set `E2E_USE_SYSTEM_CHROME=1` so Playwright uses the system Chrome,
which helps avoid `spawn EPERM` errors in restricted Windows environments.

## API Endpoints

- `GET /healthz` - Health check
- `GET /readyz` - Readiness check
- `GET /metrics` - Prometheus metrics
- `POST /planner/plan` - Convert prompt into structured job plan
- `POST /planner/plan-ai` - Prompt planner with smolagents (auto fallback to rule-based)
- `POST /planner/execute` - Prompt to plan + create/update jobs + enqueue runs in one call
- `POST /jobs` - Create new job
- `GET /jobs/{job_id}` - Get job specification
- `GET /jobs/{job_id}/versions` - List saved job spec versions
- `POST /jobs/{job_id}/rollback/{version_id}` - Roll back job spec to selected version
- `PUT /jobs/{job_id}/enable` - Enable job
- `PUT /jobs/{job_id}/disable` - Disable job
- `GET /jobs/{job_id}/runs` - Get recent runs for a job
- `GET /jobs/{job_id}/memory` - Get failure memory (consecutive failures + cooldown)
- `GET /jobs` - List all jobs
- `GET /connector/telegram/accounts` - List Telegram connector accounts
- `GET /connector/telegram/accounts/{account_id}` - Get Telegram connector account detail
- `PUT /connector/telegram/accounts/{account_id}` - Create/update Telegram connector account
- `DELETE /connector/telegram/accounts/{account_id}` - Delete Telegram connector account
- `GET /integrations/mcp/servers` - List MCP server configs
- `GET /integrations/mcp/servers/{server_id}` - Get MCP server config detail
- `PUT /integrations/mcp/servers/{server_id}` - Create/update MCP server config
- `DELETE /integrations/mcp/servers/{server_id}` - Delete MCP server config
- `GET /integrations/accounts` - List generic integration accounts (optional `?provider=...`)
- `GET /integrations/accounts/{provider}/{account_id}` - Get integration account detail
- `PUT /integrations/accounts/{provider}/{account_id}` - Create/update integration account
- `DELETE /integrations/accounts/{provider}/{account_id}` - Delete integration account
- `GET /integrations/catalog` - List connector templates (providers + MCP)
- `POST /integrations/catalog/bootstrap` - Add connector templates to dashboard storage
- `GET /automation/agent-workflows` - List recurring `agent.workflow` jobs
- `POST /automation/agent-workflow` - Create/update recurring `agent.workflow` job
- `GET /approvals` - List approval queue (`pending/approved/rejected`)
- `POST /approvals/{approval_id}/approve` - Approve approval request
- `POST /approvals/{approval_id}/reject` - Reject approval request
- `GET /runs` - List all runs
- `GET /runs/{run_id}` - Get run detail
- `GET /audit/logs` - List audit actions (`method/outcome/actor_role/path_contains`)
- `GET /events` - Get timeline events (supports SSE mode)

Planner request example:
```json
{
  "prompt": "Pantau telegram akun bot_a01 tiap 30 detik dan buat laporan harian jam 07:00",
  "timezone": "Asia/Jakarta"
}
```

Planner AI request example:
```json
{
  "prompt": "Pantau whatsapp akun ops_01 tiap 45 detik dan buat laporan harian jam 08:00",
  "timezone": "Asia/Jakarta",
  "model_id": "openai/gpt-4o-mini",
  "force_rule_based": false
}
```

Optional setup for planner AI (`/planner/plan-ai`):
```bash
pip install smolagents litellm
```
Set environment variables:
```bash
set OPENAI_API_KEY=your_key_here
set PLANNER_AI_MODEL=openai/gpt-4o-mini
```

Optional setup for Auth + RBAC (API):
```bash
set AUTH_ENABLED=true
set AUTH_API_KEYS=viewer_token:viewer,operator_token:operator,admin_token:admin
set AUTH_TOKEN_HEADER=Authorization
set AUTH_TOKEN_SCHEME=Bearer
```
Notes:
- Public endpoints without auth: `/healthz`, `/readyz`, `/metrics`.
- Read-only endpoints require `viewer` (or higher).
- Write endpoints require `operator` (or higher).
- Security-sensitive writes (`/approvals/*/approve|reject`, integrations writes, bootstrap catalog, delete agent memory) require `admin`.
- Use `GET /auth/me` to check active role seen by API.

Optional setup for UI auth header forwarding:
```bash
set NEXT_PUBLIC_API_AUTH_HEADER=Authorization
set NEXT_PUBLIC_API_AUTH_SCHEME=Bearer
set NEXT_PUBLIC_API_TOKEN=viewer_token
```
UI can also store token at runtime via `localStorage` key `spio_api_token`.

One-call execute example:
```json
{
  "prompt": "Pantau telegram akun bot_a01 tiap 30 detik dan buat laporan harian jam 07:00",
  "use_ai": true,
  "force_rule_based": true,
  "run_immediately": true,
  "wait_seconds": 2
}
```

One-call execute helper script (PowerShell):
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\testing\planner-execute.ps1 `
  -Prompt "Pantau telegram akun bot_a01 tiap 30 detik dan buat laporan harian jam 07:00" `
  -UseAi `
  -ForceRuleBased `
  -WaitSeconds 2
```

Telegram connector account example:
```json
{
  "bot_token": "123456789:AA...",
  "allowed_chat_ids": ["123456789", "-1001122334455"],
  "enabled": true,
  "use_ai": true,
  "force_rule_based": false,
  "run_immediately": true,
  "wait_seconds": 2,
  "timezone": "Asia/Jakarta",
  "default_channel": "telegram",
  "default_account_id": "bot_a01"
}
```

MCP server config example:
```json
{
  "enabled": true,
  "transport": "stdio",
  "description": "MCP GitHub server",
  "command": "npx @modelcontextprotocol/server-github",
  "args": [],
  "url": "",
  "headers": {},
  "env": {
    "GITHUB_TOKEN": "ghp_xxx"
  },
  "auth_token": "",
  "timeout_sec": 20
}
```

Generic integration account example:
```json
{
  "enabled": true,
  "secret": "sk-xxx",
  "config": {
    "base_url": "https://api.openai.com/v1",
    "workspace": "ops-main"
  }
}
```

Catalog bootstrap example:
```json
{
  "provider_ids": ["openai", "github", "notion", "shopee"],
  "mcp_template_ids": ["mcp_github", "mcp_filesystem"],
  "account_id": "default",
  "overwrite": false
}
```

Telegram command bridge flow:
1. Save Telegram account from Dashboard `Setelan`.
2. (Optional) Save MCP server and integration accounts from the same `Setelan` page.
3. Keep connector service running (`python -m app.services.connector.main`).
4. Send command to bot chat, for example:
   - `/ai pantau telegram akun bot_a01 tiap 30 detik dan buat laporan harian jam 07:00`
   - `/ai sinkron issue github terbaru ke notion`
5. Connector will execute planner 1-call and reply execution summary to the same chat.

Agent workflow notes:
- If prompt does not match monitor/report/backup intent, planner will fallback to `agent.workflow`.
- `agent.workflow` reads enabled integration accounts + MCP servers from dashboard storage.
- Provider auth token is taken from integration account secret (`/integrations/accounts/...`).
- OpenAI planner key is resolved from:
  1) `openai/default` (or selected account in job input), then
  2) `OPENAI_API_KEY` environment variable.
- Use `Template Konektor Cepat` in Dashboard `Setelan` to auto-create provider/MCP templates
  (OpenAI, GitHub, Notion, Linear, Shopee, Tokopedia, Lazada, etc.).

Safe 100+ jobs load simulation:
```bash
python .\scripts\testing\simulate_safe_load.py --jobs 100 --interval-sec 30 --work-ms 8000 --jitter-sec 25 --duration-sec 90 --cleanup
```
What this does:
1. Creates 100 recurring synthetic jobs (`simulation.heavy`) without external API dependency.
2. Monitors runs, queue depth, and overlap guard every few seconds.
3. Prints recommended worker count and final safety summary.
4. Disables simulation jobs at the end (`--cleanup`).

Failure memory and anti-loop safeguards:
1. Scheduler skips dispatch when approval for that job is still pending.
2. Scheduler skips dispatch while job is in failure cooldown window.
3. Failure memory is tracked per job (`consecutive_failures`, `cooldown_until`, `last_error`).
4. Configure from job inputs (optional):
   - `failure_threshold` (default `3`)
   - `failure_cooldown_sec` (default `120`)
   - `failure_cooldown_max_sec` (default `3600`)
   - `failure_memory_enabled` (default `true`)

Extreme pressure safeguards:
1. Worker runs multi-slot concurrency via `WORKER_CONCURRENCY` (default `5`).
2. Scheduler caps new dispatch per tick via `SCHEDULER_MAX_DISPATCH_PER_TICK` (default `80`).
3. Scheduler enters pressure mode when queue depth reaches `SCHEDULER_PRESSURE_DEPTH_HIGH` (default `300`).
4. Pressure mode is released when queue depth drops to `SCHEDULER_PRESSURE_DEPTH_LOW` (default `180`).
5. During pressure mode, only jobs with `inputs.pressure_priority = "critical"` are dispatched.
6. Configure per `agent.workflow` job using input `pressure_priority` (`critical|normal|low`).

Flow isolation safeguards (agar jalur agen tidak saling ganggu):
1. Set `flow_group` untuk mengelompokkan job dalam satu jalur kerja (contoh: `konten_harian`, `riset_produk`).
2. Set `flow_max_active_runs` untuk membatasi run aktif per jalur flow.
3. Scheduler akan skip dispatch jika jalur flow sudah penuh (event: `scheduler.dispatch_skipped_flow_limit`).
4. Cocok untuk skenario banyak job campur: tiap tim/jalur punya kuota sendiri.

## Job Specification Example

```json
{
  "job_id": "monitor-telegram-a01",
  "type": "monitor.channel",
  "schedule": { "interval_sec": 30 },
  "timeout_ms": 15000,
  "retry_policy": { "max_retry": 5, "backoff_sec": [1,2,5,10,30] },
  "inputs": { "channel": "telegram", "account_id": "bot_a01" }
}
```

Example `agent.workflow` with isolated flow lane:

```json
{
  "job_id": "campaign_konten_harian",
  "type": "agent.workflow",
  "schedule": { "interval_sec": 300 },
  "timeout_ms": 90000,
  "retry_policy": { "max_retry": 1, "backoff_sec": [2, 5] },
  "inputs": {
    "prompt": "Siapkan konten compliance harian dan kirim ke approval queue",
    "flow_group": "konten_harian",
    "flow_max_active_runs": 8,
    "pressure_priority": "normal",
    "allow_overlap": false
  }
}
```

## Starter Job Types

- `monitor.channel` - Check connector health and emit metrics
- `report.daily` - Generate daily summary report
- `backup.export` - Export job registry and run history
- `agent.workflow` - Plan and execute provider/MCP HTTP steps from a natural-language prompt
- `simulation.heavy` - Synthetic heavy-workload job for safe stress/load simulation

## Tool System

Each job can use predefined tools:
- `http`: Make HTTP requests
- `kv`: Key-value storage in Redis
- `messaging`: Send messages (Telegram, WhatsApp)
- `files`: Read/write files
- `metrics`: Emit metrics and logs

Tool access is controlled by policies per job type.

## Observability

- Structured JSON logs with job_id, run_id, trace_id
- Prometheus metrics endpoint
- Health endpoints for monitoring
- Redis-based heartbeat monitoring

## Integrasi Sistem dan Referensi Kompetitif

### Latar belakang pesaing
- **OpenClaw** menerapkan `exec approvals`, allowlist per-agent, dan policy tool yang dijalankan di gateway/node host untuk mencegah perintah keluar tanpa verification human—semua request `system.run` dapat diblokir atau digantikan fallback `deny` jika UI tidak tersedia, sehingga operator bisa menahan perintah berbahaya sebelum menyentuh host.citeturn0search1turn0search0
- **OpenClaw** juga telah menjadi contoh betapa marketplace skill yang terbuka bisa disusupi malware dan prompt injection; bahkan Microsoft memperingatkan bahwa runtime ini tidak tepat dijalankan di workstation standar karena akses credential penuh, sehingga isolasi dan monitoring ketat menjadi keharusan demi mencegah data leakage.citeturn0news12turn0news13turn0news14
- **SuperAGI** menekankan orkestrasi multi-agen paralel, concurrent execution, dan monitoring per-agent (runs, token consumption, utilization), plus dashboard GUI, tool/plugin extensibility, dan shared memory/feedback loop sehingga agent terus belajar serta menyeimbangkan resources secara dinamis.citeturn1search1turn1search2turn1search3turn1search4turn1search5

### Bagaimana Multi-Job menggabungkan kekuatan tersebut
- CLI `spio-skill` + dashboard skill registry sudah menjalankan metadata skill (command prefix, channel, default inputs, tags, approval, sensitive) sehingga operator dapat mengatur agent blueprint seperti skill OpenClaw/SuperAGI, lengkap dengan filter channel/pengalaman dan statistik operasional yang baru ditambahkan. (lihat `docs/skill-registry.md`, ui/skills).
- Fitur observability + retry policy + safety guardrails (pressure mode, failure memory, flow lanes) menjaga job/agent tetap terkendali tanpa harus memberi agent akses shell/domain tak terbatas, sambil tetap menyelesaikan job scheduling serta integration connectors untuk Telegram, Slack, SMS, WhatsApp, dan MCP service lain.
- Release automation & CI sudah didefinisikan: `ci.yml` menjalankan Pytest backend + Playwright e2e; `release.yml` otomatis membuat artefak backend dan Next.js UI saat tag `v*.*.*` di-push sehingga `CD` tersinkronkan dengan `CI`. (lihat bagian `Release Automation` di README).
- Dengan menautkan referensi ini (docs baru `docs/feature-integration-openclaw-superagi.md`), tim dapat melihat apa saja kemampuan yang kami samakan/perbaiki dari OpenClaw/SuperAGI dan mana yang dapat ditambah (sandbox policy, CICD keamanan, observability, channel analytics, experience registry).
