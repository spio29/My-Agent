# Panduan Deployment ke VPS

Panduan lengkap untuk deploy Multi-Job Platform ke VPS production.

## Prasyarat VPS

### Spesifikasi Minimum
- **OS**: Ubuntu 22.04 LTS (recommended) atau Ubuntu 20.04 LTS
- **CPU**: 2 cores (4 cores recommended)
- **RAM**: 4GB (8GB+ recommended untuk production)
- **Storage**: 50GB SSD minimum
- **Port yang perlu dibuka**: 8000 (API), 3000 (UI), 6379 (Redis - optional, internal saja)

### Port Firewall
```bash
# Di VPS, buka port berikut
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 8000/tcp  # API
sudo ufw allow 3000/tcp  # UI Dashboard
sudo ufw enable
```

---

## Metode 1: Deployment dengan Docker Compose (RECOMMENDED)

### Step 1: Update & Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose (jika belum include)
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verifikasi
docker --version
docker-compose --version

# Tambahkan user ke docker group (optional, agar tidak perlu sudo)
sudo usermod -aG docker $USER
```

### Step 2: Clone/Upload Project

```bash
# Buat direktori aplikasi
sudo mkdir -p /opt/spio-agent
sudo chown $USER:$USER /opt/spio-agent

# Clone dari Git (jika ada repository)
cd /opt/spio-agent
git clone <repository-url> .

# ATAU upload manual via SCP/SFTP
# Dari Windows (PowerShell):
# scp -r C:\Users\user\Desktop\spio_agent\multi_job\* user@VPS_IP:/opt/spio-agent/
```

### Step 3: Buat File Environment

```bash
cd /opt/spio-agent

# Buat file .env
cat > .env << 'EOF'
# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Worker Configuration
WORKER_CONCURRENCY=5

# Scheduler Configuration
SCHEDULER_MAX_DISPATCH_PER_TICK=80
SCHEDULER_PRESSURE_DEPTH_HIGH=300
SCHEDULER_PRESSURE_DEPTH_LOW=180

# AI Configuration (Optional)
LOCAL_AI_URL=http://host.docker.internal:11434/v1
PLANNER_AI_MODEL=llama3

# VPS 2 - AI Factory (Optional)
AI_NODE_URL=
AI_NODE_SECRET=factory-secret-123

# Telegram Notification (Optional)
TELEGRAM_NOTIF_TOKEN=
TELEGRAM_NOTIF_CHAT_ID=

# Auth & RBAC (Optional)
AUTH_ENABLED=false
AUTH_API_KEYS=admin_token:admin
AUTH_TOKEN_HEADER=Authorization
AUTH_TOKEN_SCHEME=Bearer
EOF
```

### Step 4: Start Services dengan Docker Compose

```bash
cd /opt/spio-agent

# Build dan start semua services
docker-compose up -d --build

# Cek status
docker-compose ps

# Lihat logs
docker-compose logs -f
```

### Step 5: Verifikasi Deployment

```bash
# Test API health
curl http://localhost:8000/healthz

# Test API dari external (ganti VPS_IP dengan IP VPS Anda)
curl http://VPS_IP:8000/healthz

# Test UI
curl http://localhost:3000
```

**Akses Dashboard:**
- API: `http://VPS_IP:8000`
- UI Dashboard: `http://VPS_IP:3000`

---

## Metode 2: Manual Deployment (Tanpa Docker)

### Step 1: Install Dependencies System

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11, Node.js, dan Redis
sudo apt install -y python3.11 python3.11-venv python3-pip redis-server nginx git curl

# Install Node.js 20.x
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"
```

### Step 2: Setup Redis

```bash
# Start Redis
sudo systemctl start redis
sudo systemctl enable redis

# Verifikasi Redis
redis-cli ping
# Output: PONG
```

### Step 3: Setup Application

```bash
# Buat direktori
sudo mkdir -p /opt/spio-agent
sudo chown $USER:$USER /opt/spio-agent
cd /opt/spio-agent

# Clone/upload project (sama seperti Step 2 Metode 1)

# Setup Python venv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Setup UI
cd ui
npm install
npm run build
cd ..
```

### Step 4: Buat Systemd Services

```bash
# Buat service file untuk API
sudo cat > /etc/systemd/system/spio-api.service << 'EOF'
[Unit]
Description=SPIO Agent API Service
After=network.target redis.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/spio-agent
Environment="PATH=/opt/spio-agent/.venv/bin"
Environment="REDIS_HOST=localhost"
Environment="REDIS_PORT=6379"
Environment="API_HOST=0.0.0.0"
Environment="API_PORT=8000"
ExecStart=/opt/spio-agent/.venv/bin/uvicorn app.services.api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Buat service file untuk Worker
sudo cat > /etc/systemd/system/spio-worker.service << 'EOF'
[Unit]
Description=SPIO Agent Worker Service
After=network.target redis.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/spio-agent
Environment="PATH=/opt/spio-agent/.venv/bin"
Environment="REDIS_HOST=localhost"
Environment="REDIS_PORT=6379"
Environment="WORKER_CONCURRENCY=5"
ExecStart=/opt/spio-agent/.venv/bin/python -m app.services.worker.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Buat service file untuk Scheduler
sudo cat > /etc/systemd/system/spio-scheduler.service << 'EOF'
[Unit]
Description=SPIO Agent Scheduler Service
After=network.target redis.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/spio-agent
Environment="PATH=/opt/spio-agent/.venv/bin"
Environment="REDIS_HOST=localhost"
Environment="REDIS_PORT=6379"
ExecStart=/opt/spio-agent/.venv/bin/python -m app.services.scheduler.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Buat service file untuk Connector
sudo cat > /etc/systemd/system/spio-connector.service << 'EOF'
[Unit]
Description=SPIO Agent Connector Service
After=network.target redis.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/spio-agent
Environment="PATH=/opt/spio-agent/.venv/bin"
Environment="REDIS_HOST=localhost"
Environment="REDIS_PORT=6379"
ExecStart=/opt/spio-agent/.venv/bin/python -m app.services.connector.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Buat service file untuk UI
sudo cat > /etc/systemd/system/spio-ui.service << 'EOF'
[Unit]
Description=SPIO Dashboard UI Service
After=network.target spio-api.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/spio-agent/ui
Environment="PATH=/opt/spio-agent/.venv/bin"
Environment="NEXT_PUBLIC_API_BASE=http://localhost:8000"
ExecStart=/usr/bin/npm run serve
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

### Step 5: Enable & Start Services

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable semua services
sudo systemctl enable spio-api spio-worker spio-scheduler spio-connector spio-ui

# Start semua services
sudo systemctl start spio-api spio-worker spio-scheduler spio-connector spio-ui

# Cek status
sudo systemctl status spio-api
sudo systemctl status spio-worker
sudo systemctl status spio-scheduler
sudo systemctl status spio-connector
sudo systemctl status spio-ui
```

### Step 6: Setup Nginx Reverse Proxy (Optional)

```bash
# Install Nginx
sudo apt install -y nginx

# Buat konfigurasi Nginx
sudo cat > /etc/nginx/sites-available/spio-agent << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    # API
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # UI Dashboard
    location / {
        proxy_pass http://127.0.0.1:3000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/spio-agent /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## Monitoring & Maintenance

### Cek Logs

**Docker:**
```bash
docker-compose logs -f api
docker-compose logs -f worker
docker-compose logs -f scheduler
docker-compose logs -f connector
docker-compose logs -f ui
```

**Systemd:**
```bash
sudo journalctl -u spio-api -f
sudo journalctl -u spio-worker -f
sudo journalctl -u spio-scheduler -f
sudo journalctl -u spio-connector -f
sudo journalctl -u spio-ui -f
```

### Restart Services

**Docker:**
```bash
docker-compose restart
```

**Systemd:**
```bash
sudo systemctl restart spio-api spio-worker spio-scheduler spio-connector spio-ui
```

### Update Deployment

**Docker:**
```bash
cd /opt/spio-agent
git pull
docker-compose up -d --build
```

**Systemd:**
```bash
cd /opt/spio-agent
git pull
source .venv/bin/activate
pip install -e .
cd ui && npm install && npm run build
sudo systemctl restart spio-api spio-worker spio-scheduler spio-connector spio-ui
```

---

## Troubleshooting

### API tidak merespons
```bash
# Cek logs
docker-compose logs api
# atau
sudo journalctl -u spio-api -f

# Cek apakah port terbuka
sudo netstat -tlnp | grep 8000
```

### Redis connection error
```bash
# Cek Redis status
sudo systemctl status redis
# atau
docker-compose ps redis

# Test koneksi
redis-cli ping
```

### UI tidak bisa akses API
```bash
# Pastikan NEXT_PUBLIC_API_BASE sudah benar
# Untuk Docker: http://localhost:8000
# Untuk direct access: http://VPS_IP:8000
```

### Out of memory
```bash
# Tambahkan swap file
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## Security Best Practices

1. **Gunakan Firewall**
   ```bash
   sudo ufw allow 22/tcp
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw enable
   ```

2. **Setup SSL dengan Let's Encrypt**
   ```bash
   sudo apt install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d your-domain.com
   ```

3. **Gunakan Environment Variables untuk secrets**
   - Jangan commit `.env` ke Git
   - Gunakan Docker secrets atau Vault untuk production

4. **Enable Auth & RBAC**
   ```bash
   # Di .env
   AUTH_ENABLED=true
   AUTH_API_KEYS=admin_token:admin,operator_token:operator,viewer_token:viewer
   ```

5. **Regular Backups**
   ```bash
   # Backup Redis data
   docker exec spio-redis redis-cli BGSAVE
   # Backup volume
   docker run --rm -v spio-agent_redis-data:/data -v $(pwd):/backup ubuntu tar czf /backup/redis-backup-$(date +%Y%m%d).tar.gz /data
   ```

---

## Quick Reference

| Service | Port | Health Check |
|---------|------|--------------|
| API | 8000 | `GET /healthz` |
| UI | 3000 | `GET /` |
| Redis | 6379 | `redis-cli ping` |

**Commands:**
- Start: `docker-compose up -d`
- Stop: `docker-compose down`
- Restart: `docker-compose restart`
- Logs: `docker-compose logs -f`
- Status: `docker-compose ps`
