# Panduan Operasional Pabrik AI (VPS 2)

Chairman, dokumen ini berisi instruksi teknis mendalam untuk mengaktifkan **Pusat Produksi Konten** Anda di VPS kedua.

## 1. Persiapan Lingkungan (Pre-Flight)
Pastikan VPS 2 Anda memiliki spesifikasi berikut:
*   **OS**: Ubuntu 22.04 LTS (Murni/Fresh Install).
*   **Storage**: Minimal 100GB SSD (Model AI berukuran besar).
*   **RAM**: Minimal 16GB. Jika tanpa GPU, disarankan 32GB agar proses "Swap" lancar.
*   **Port**: Pastikan Port `8080` terbuka di Firewall/Security Group VPS Anda.

## 2. Instalasi Otomatis (The Command)
Jalankan perintah ini satu-per-satu di terminal VPS 2:

```bash
# 1. Update & Clean
sudo apt update && sudo apt upgrade -y

# 2. Instal Docker & Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 3. Jalankan Pabrik AI (Optimasi RAM 16GB)
# Menggunakan model terkompresi (pruned) yang hanya butuh ~4GB RAM.
docker run -d --name ai-factory \
  --restart always \
  -p 8080:80 \
  -e MODEL_NAME="runwayml/stable-diffusion-v1-5" \
  -e FACTORY_SECRET="factory-secret-123" \
  -e HF_HUB_OFFLINE=0 \
  -v ai-models:/root/.cache/huggingface \
  kserve/huggingface-server:latest
```

## 3. Cara Memantau Download (Crucial)
Karena ukuran model sangat besar (15GB+), Anda harus memantau prosesnya agar tahu kapan "Pabrik" siap digunakan. Gunakan perintah ini di VPS 2:

```bash
docker logs -f ai-factory
```
**Apa yang harus dilihat?**
*   Jika muncul tulisan `Downloading model...`, artinya proses sedang berjalan. Tunggu saja.
*   Jika muncul tulisan `Uvicorn running on http://0.0.0.0:80`, artinya **Pabrik Telah Aktif** dan siap menerima pesanan dari VPS 1.

## 4. Menghubungkan ke Gedung Pusat (VPS 1)
Setelah VPS 2 siap (sudah muncul status running di log), buka file `.env` di **VPS 1** dan masukkan:

```env
AI_NODE_URL=http://IP_VPS_2_ANDA:8080
AI_NODE_SECRET=factory-secret-123
```

## 5. Troubleshooting (Jika Gagal)
*   **Out of Memory**: Jika proses berhenti tiba-tiba, tambahkan "Swap File" di Ubuntu (tanyakan ke saya jika butuh caranya).
*   **Koneksi Lambat**: Proses download bisa memakan waktu 10-30 menit tergantung kecepatan internet VPS Anda ke server HuggingFace.
*   **Ganti Model**: Jika ingin model yang lebih ringan (untuk RAM kecil), ganti `MODEL_NAME` menjadi `"runwayml/stable-diffusion-v1-5"`.

---
*Laporan ini disusun secara otomatis oleh CEO Spio Holding untuk Chairman.*
