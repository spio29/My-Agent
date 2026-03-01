# Spio No-Code Framework (IG/FB/WA)

Tujuan: Anda tidak perlu menyentuh coding. Cukup isi token/ID, lalu kontrol operasi influencer dengan perintah sederhana.

## 1) Yang sudah disiapkan
- Influencer scaffold: `inf_001` sampai `inf_010`
- Akun integrasi placeholder:
  - instagram_graph: `ig_001..ig_010`
  - facebook_graph: `fb_001..fb_010`
  - whatsapp_api: `wa_001..wa_010`
- Template job siap pakai (6 job per influencer):
  - `tmpl_inf_xxx_ig_reply`
  - `tmpl_inf_xxx_ig_post`
  - `tmpl_inf_xxx_fb_reply`
  - `tmpl_inf_xxx_fb_post`
  - `tmpl_inf_xxx_wa_followup`
  - `tmpl_inf_xxx_report`
- Semua job default aman: OFF.

## 2) Isi kredensial via dashboard
Buka: `http://213.163.193.6:3001/settings`

Isi masing-masing akun:
- Instagram (`instagram_graph`):
  - secret = token
  - config `instagram_user_id`
- Facebook (`facebook_graph`):
  - secret = token
  - config `facebook_page_id`
- WhatsApp (`whatsapp_api`):
  - secret = token
  - config `phone_number_id`

## 3) Command Mudah (disarankan)
```bash
cd /opt/spio-agent/ops/no-code

./easy.sh status all
./easy.sh nyala inf_001
./easy.sh mati all

./easy.sh strategi inf_001 natural
./easy.sh nada inf_001 warm
./easy.sh followup inf_001 keras
./easy.sh ritme inf_001 cepat

./easy.sh jadwal inf_001 09:00 09:30 21:00
./easy.sh kanal inf_001 ig,fb
./easy.sh rantai all 09:00 70 130 80
./easy.sh paket inf_001 normal 09:00
```

## 4) Makna perintah
- `strategi`:
  - `natural` = storytelling natural manusia
  - `lembut` = soft sell
  - `closing` = dorong konversi
  - `endorse` = fokus deal brand
- `nada` untuk DM/komentar:
  - `warm` | `formal` | `tegas`
- `followup` khusus WA:
  - `lembut` | `keras` | `formal`
- `ritme` balas DM/WA:
  - `lambat` | `normal` | `cepat`
- `kanal` channel aktif per influencer:
  - contoh `ig` saja, `ig,fb`, atau `ig,fb,wa`
- `rantai` = posting berurutan per influencer (bukan barengan)
- `paket` = set strategi+nada+followup+ritme+rantai sekali jalan:
  - `santai` (lebih natural, jeda longgar)
  - `normal` (seimbang)
  - `agresif` (closing cepat, jeda pendek)

## 5) Catatan penting soal jeda detik
Scheduler job saat ini berbasis cron menit. Jadi jeda seperti 70 detik diterapkan sebagai **aproksimasi menit + jitter detik**.

## 6) Alur paling simpel
```bash
cd /opt/spio-agent/ops/no-code
./easy.sh status inf_001
./easy.sh kanal inf_001 ig,fb
./easy.sh strategi inf_001 natural
./easy.sh followup inf_001 lembut
./easy.sh rantai inf_001 09:00 70 130 80
./easy.sh nyala inf_001
```

Stop cepat:
```bash
./easy.sh mati all
```

## 7) Ketahanan sistem (auto-heal + laporan)
Watchdog aktif untuk mencegah sistem mati total:
- Cek service inti: redis, api, connector, dashboard, worker, scheduler.
- Jika ada yang down/unhealthy: watchdog auto-restart.
- Kirim laporan insiden/recovery ke Telegram operator (jika bot token + chat id sudah aktif).

Jalankan manual:
- cd /opt/spio-agent/ops/no-code
- ./watchdog.sh

Cek log:
- tail -f /var/log/spio-watchdog.log

Jadwal otomatis:
- Cron setiap 2 menit dengan lock file (/tmp/spio-watchdog.lock).

