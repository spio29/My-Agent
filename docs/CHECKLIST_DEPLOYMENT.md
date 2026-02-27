# SPIO Agent - Pre-Deployment Checklist

Checklist ini wajib diperiksa SEBELUM deploy ke VPS production.

## 🔧 Persiapan Infrastructure

- [ ] VPS sudah running (Ubuntu 22.04 LTS recommended)
- [ ] Spesifikasi minimum: 2 CPU cores, 4GB RAM, 50GB SSD
- [ ] Port firewall sudah dibuka: 22 (SSH), 8000 (API), 3000 (UI)
- [ ] Domain/subdomain sudah pointing ke IP VPS (jika menggunakan domain)
- [ ] Backup strategy sudah disiapkan

## 📦 Setup Environment

- [ ] Script `setup-vps.sh` sudah dijalankan
- [ ] Docker dan Docker Compose terinstall
- [ ] Redis sudah running dan merespons (`redis-cli ping` → PONG)
- [ ] Node.js 20.x terinstall
- [ ] Poetry terinstall
- [ ] User sudah ditambahkan ke docker group

## 🔐 Security

- [ ] File `.env` sudah dibuat dari `.env.example`
- [ ] Password/secret di `.env` sudah diganti dengan nilai yang kuat
- [ ] `AUTH_ENABLED=true` untuk production
- [ ] API keys sudah dibuat dengan role yang sesuai
- [ ] Firewall UFW sudah enabled
- [ ] SSL certificate sudah setup (Let's Encrypt) jika menggunakan domain
- [ ] `.env` tidak ter-commit ke Git (sudah ada di `.gitignore`)

## 📝 Konfigurasi Application

### Redis
- [ ] `REDIS_HOST=redis` (untuk Docker) atau `localhost` (manual)
- [ ] `REDIS_PORT=6379`
- [ ] `REDIS_PASSWORD` diisi jika Redis menggunakan password

### API
- [ ] `API_HOST=0.0.0.0`
- [ ] `API_PORT=8000`

### Worker
- [ ] `WORKER_CONCURRENCY=5` (sesuaikan dengan CPU cores)

### Scheduler
- [ ] `SCHEDULER_MAX_DISPATCH_PER_TICK=80`
- [ ] `SCHEDULER_PRESSURE_DEPTH_HIGH=300`
- [ ] `SCHEDULER_PRESSURE_DEPTH_LOW=180`

### AI (Optional)
- [ ] `LOCAL_AI_URL` diisi jika menggunakan local AI (Ollama, dll)
- [ ] `PLANNER_AI_MODEL` diisi dengan model yang sesuai
- [ ] `AI_NODE_URL` diisi jika menggunakan VPS 2 untuk AI Factory
- [ ] `AI_NODE_SECRET` sesuai dengan yang di VPS 2

### Telegram (Optional)
- [ ] `TELEGRAM_NOTIF_TOKEN` diisi dengan bot token
- [ ] `TELEGRAM_NOTIF_CHAT_ID` diisi dengan chat ID tujuan

### Auth & RBAC
- [ ] `AUTH_ENABLED=true`
- [ ] `AUTH_API_KEYS` sudah diisi dengan token yang aman
- [ ] Format: `token_admin:admin,token_operator:operator,token_viewer:viewer`

## 🚀 Deployment

### Docker Compose Method
- [ ] File `docker-compose.prod.yml` sudah ada
- [ ] `.env` file sudah ada di direktori yang sama dengan docker-compose
- [ ] `docker-compose -f docker-compose.prod.yml up -d --build` berhasil
- [ ] Semua container running: `docker-compose ps`
- [ ] Tidak ada error di logs: `docker-compose logs`

### Manual Deployment (Systemd)
- [ ] Semua service files sudah dibuat di `/etc/systemd/system/`
- [ ] `systemctl daemon-reload` sudah dijalankan
- [ ] Semua services enabled dan started
- [ ] `systemctl status spio-api` → active (running)
- [ ] `systemctl status spio-worker` → active (running)
- [ ] `systemctl status spio-scheduler` → active (running)
- [ ] `systemctl status spio-connector` → active (running)
- [ ] `systemctl status spio-ui` → active (running)

## ✅ Verification

### Health Checks
- [ ] API health: `curl http://localhost:8000/healthz` → OK
- [ ] API ready: `curl http://localhost:8000/readyz` → OK
- [ ] UI accessible: `curl http://localhost:3000` → HTML response
- [ ] Redis connection: `redis-cli ping` → PONG

### External Access
- [ ] API accessible dari external: `curl http://VPS_IP:8000/healthz`
- [ ] UI accessible dari browser: `http://VPS_IP:3000`
- [ ] SSL working (jika menggunakan domain): `https://your-domain.com`

### Functional Tests
- [ ] Create job via API/UI berhasil
- [ ] Job dijalankan oleh worker
- [ ] Scheduler membuat runs sesuai schedule
- [ ] Connector bisa mengirim notifikasi (jika dikonfigurasi)
- [ ] Logs tercatat dengan benar

## 📊 Monitoring Setup

- [ ] Log aggregation sudah setup (opsional: ELK, Loki, dll)
- [ ] Metrics endpoint `/metrics` bisa diakses
- [ ] Alerting sudah dikonfigurasi (opsional)
- [ ] Log rotation sudah aktif

## 💾 Backup Strategy

- [ ] Redis data backup script sudah dibuat
- [ ] Backup scheduled dengan cron
- [ ] Backup disimpan di lokasi terpisah
- [ ] Restore procedure sudah ditest

## 🔄 Update Procedure

- [ ] Update procedure sudah dipahami:
  ```bash
  cd /opt/spio-agent
  git pull
  docker-compose -f docker-compose.prod.yml up -d --build
  ```
- [ ] Rollback procedure sudah disiapkan

## 📝 Documentation

- [ ] `DEPLOYMENT_VPS.md` sudah dibaca dan dipahami
- [ ] IP VPS, credentials, dan konfigurasi penting sudah dicatat
- [ ] Contact person untuk emergency sudah ditentukan

---

## Quick Test Commands

```bash
# Cek semua containers
docker-compose ps

# Cek logs API
docker-compose logs api

# Cek logs Worker
docker-compose logs worker

# Test API
curl http://localhost:8000/healthz
curl http://localhost:8000/jobs

# Test Redis
redis-cli ping
redis-cli INFO memory

# Cek resource usage
docker stats --no-stream

# Cek disk usage
df -h
```

---

## Troubleshooting Common Issues

| Issue | Possible Cause | Solution |
|-------|----------------|----------|
| Container exit code 137 | Out of memory | Tambah swap atau upgrade RAM |
| API tidak merespons | Redis tidak connect | Cek `REDIS_HOST` dan Redis status |
| UI blank/error | API tidak accessible | Cek `NEXT_PUBLIC_API_BASE` |
| Worker tidak jalan | Queue kosong atau error | Cek logs worker, cek Redis queue |
| Scheduler tidak dispatch | Job disabled atau cooldown | Cek job status dan failure memory |

---

**Setelah semua checklist di atas terpenuhi, sistem siap untuk production!**
