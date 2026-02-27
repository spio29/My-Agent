# Job Studio Sederhana UI

UI super mudah untuk orang awam yang tidak paham backend. Konsep: **Job = Resep**, **Run = Eksekusi**, **Worker = Tenaga**.

## Fitur Utama

- **Beranda**: Status sistem, antrian, koneksi, tenaga, dan aktivitas terbaru
- **Resep Tugas**: Daftar resep dengan tombol "Jalankan Sekarang", "Aktifkan/Nonaktifkan"
- **Buat Resep**: Mode sederhana (form) dan mode lanjutan (JSON)
- **Hasil Eksekusi**: Riwayat eksekusi dengan detail hasil dan error

## Cara Menjalankan

### Dengan Docker (rekomendasi)

1. Pastikan semua layanan sudah berjalan:
```bash
cd multi_job
docker compose up --build
```

2. Akses UI sederhana di: [http://localhost:5174](http://localhost:5174)

### Secara Lokal (development)

1. Instal dependensi:
```bash
cd multi_job/ui-simple
npm install
```

2. Jalankan development server:
```bash
npm run dev
```

3. Akses di: [http://localhost:5174](http://localhost:5174)

## Environment Variables

| Variabel | Default | Deskripsi |
|----------|---------|-----------|
| `VITE_API_BASE` | `http://localhost:8000` | Base URL untuk FastAPI backend |

## Troubleshooting

### Masalah CORS
Jika muncul error CORS, pastikan FastAPI backend Anda memiliki middleware CORS:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Port Konflik
- UI Sederhana: port 5174
- UI Admin: port 3000  
- API: port 8000
- Redis: port 6379

Jika port sudah digunakan, ubah di `docker-compose.yml`.

### Endpoint Backend Tidak Ditemukan
UI ini mengharapkan endpoint berikut dari FastAPI:
- `GET /healthz`
- `GET /readyz`
- `GET /queue`
- `GET /connectors`
- `GET /jobs`
- `POST /jobs`
- `PUT /jobs/{job_id}/enable`
- `PUT /jobs/{job_id}/disable`
- `POST /jobs/{job_id}/run`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /events` (untuk SSE)

Jika endpoint belum ada, buat stub minimal di FastAPI Anda.

## Desain UX

- **Bahasa Indonesia sederhana**
- **1 layar = 1 keputusan** (tidak ada menu dalam menu)
- **Tombol utama besar**: "Jalankan Sekarang", "Simpan"
- **Semua error punya tombol "Coba lagi"**
- **Tidak menampilkan token/secret apapun**

## Teknologi

- **Frontend**: React + TypeScript + Vite
- **Styling**: TailwindCSS
- **Data Fetching**: TanStack Query
- **Routing**: React Router
- **Realtime**: SSE dengan fallback polling

## Lisensi

MIT License