# Job Studio UI

A modern, intuitive web interface for the Multi-Job Platform.

## Features

- **Overview Dashboard**: System health, queue status, job performance metrics
- **Job Management**: Create, edit, enable/disable, and manually trigger jobs
- **Run Monitoring**: View job execution history with detailed run information
- **Agent Monitoring**: Track worker and scheduler agent status
- **Connector Monitoring**: Monitor external service connections (Telegram, etc.)
- **Settings**: Configure API endpoints and refresh intervals

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for local development)

### Running with Docker

1. Start all services:
```bash
docker compose up --build
```

2. Access the UI at: [http://localhost:3000](http://localhost:3000)
3. Access the API docs at: [http://localhost:8000/docs](http://localhost:8000/docs)

### Running Locally (Development)

1. Install dependencies in the UI directory:
```bash
cd multi_job/ui
npm install
```

2. Start the development server:
```bash
npm run dev
```

3. The UI will be available at [http://localhost:3000](http://localhost:3000)

If `npm run dev` fails in restricted environments, use production mode:
```bash
npm run build
npm run serve
```
Then open [http://127.0.0.1:3000](http://127.0.0.1:3000)

### Running UI E2E (Playwright)

1. From the UI directory, run the helper script:
```bash
e2e-local.cmd
```

If you prefer PowerShell:
```powershell
.\e2e-local.ps1
```

Both scripts set `E2E_USE_SYSTEM_CHROME=1` so Playwright uses the system Chrome,
which avoids `spawn EPERM` errors in restricted Windows environments.

## Environment Variables

The UI uses the following environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8000` | Base URL for the FastAPI backend |

## Troubleshooting

### CORS Issues
If you see CORS errors, ensure your FastAPI backend has CORS middleware configured:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### npm audit Error (Registry / Cache)
If `npm audit --audit-level=high` fails due to registry errors or cache write issues, retry with a
local cache path:

```bash
cmd /c "set npm_config_cache=%cd%\.npm-cache&& npm audit --audit-level=high"
```

PowerShell:
```powershell
$env:npm_config_cache = "$pwd\.npm-cache"
npm audit --audit-level=high
```

If registry access is blocked, run the audit from a network with registry access or rely on CI.

### Port Conflicts
- UI runs on port 3000
- API runs on port 8000
- Redis runs on port 6379

If ports are in use, modify the `docker-compose.yml` file to use different ports.

### Backend Endpoints Not Found
The UI expects the following endpoints from the FastAPI backend:
- `GET /jobs`
- `POST /jobs`
- `PUT /jobs/{job_id}/enable`
- `PUT /jobs/{job_id}/disable`
- `POST /jobs/{job_id}/run`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /connectors`
- `GET /healthz`
- `GET /readyz`
- `GET /queue`

If any endpoints are missing, implement minimal stubs in your FastAPI app.

## UI Design Principles

- **Simple & Clear**: Minimal text, clear buttons, obvious status indicators
- **Real-time Updates**: Automatic polling every 5-10 seconds
- **Error Handling**: Clear error messages with retry options
- **Responsive**: Works on desktop and tablet screens
- **Accessible**: Proper contrast and keyboard navigation

## Technology Stack

- **Frontend**: Next.js 14 (App Router) + TypeScript
- **Styling**: TailwindCSS
- **Data Fetching**: TanStack Query
- **Charts**: Recharts
- **Icons**: Lucide React
- **Notifications**: Sonner

## License

MIT License
