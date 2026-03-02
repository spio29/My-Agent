# RunPod Handler Template (Kompatibel SPIO Studio V2)

Folder ini berisi template worker RunPod custom:

1. `image_handler_template.py`
2. `video_handler_template.py`
3. `requirements_image.txt`
4. `requirements_video.txt`

Tujuan:
- Input schema cocok dengan payload dari `scripts/runpod_nocode_studio.py`.
- Output mengembalikan URL (`image_url` / `video_url`) supaya terbaca langsung oleh UI.

## 1) Env wajib

Set environment variable di RunPod worker:

1. `OUTPUT_S3_BUCKET`
2. `OUTPUT_S3_REGION` (contoh: `ap-southeast-1`)
3. `OUTPUT_S3_ACCESS_KEY_ID`
4. `OUTPUT_S3_SECRET_ACCESS_KEY`

Opsional:

1. `OUTPUT_S3_PUBLIC_BASE_URL` (kalau pakai Cloudflare R2 custom domain/CDN)
2. `OUTPUT_PREFIX_IMAGE` (default: `spio/images`)
3. `OUTPUT_PREFIX_VIDEO` (default: `spio/videos`)

Model env opsional:

1. `IMAGE_MODEL_ID` default `black-forest-labs/FLUX.1-schnell`
2. `IMAGE_TORCH_DTYPE` default `float16` (opsi: `bfloat16`)
3. `VIDEO_MODEL_ID` default `stabilityai/stable-video-diffusion-img2vid-xt`

## 2) Contract input dari UI

### Image
- `prompt`, `negative_prompt`, `width`, `height`, `steps`, `cfg_scale`, `sampler_name`, `seed`
- opsional: `ip_adapter_image`, `body_image`, `body_lock_strength`

### Video
- `prompt`, `negative_prompt`, `width`, `height`, `duration`, `fps`, `seed`
- anchor image key default: `image` (bisa diubah dari UI)
- opsional: `body_image`, `body_lock_strength`

## 3) Contract output ke UI

### Image
```json
{
  "image_url": "https://.../result.png",
  "images": ["https://.../result.png"],
  "seed": 12345
}
```

### Video
```json
{
  "video_url": "https://.../result.mp4",
  "videos": ["https://.../result.mp4"],
  "seed": 12345
}
```

## 4) Catatan penting

1. Template image/video ini fokus `siap konek` dengan UI.
2. `ip_adapter_image` dan `body_image` sudah diterima, tapi integrasi lock lanjutan tergantung model/pipeline yang kamu pakai.
3. Template video default pakai SVD dan menyesuaikan anchor ke 1024x576 agar stabil.
4. Untuk vertical native (9:16) kualitas tinggi, nanti bisa diganti model video lain tanpa ubah contract input-output.

## 5) Quick start FLUX (Serverless self-host)

Di VPS:

```bash
cd /opt/spio-agent/runpod_templates
chmod +x deploy_flux_worker.sh test_runpod_image_endpoint.sh
./deploy_flux_worker.sh docker.io/USERNAME/spio-flux-worker:v1
```

Lalu di dashboard RunPod:

1. Serverless -> New Endpoint -> Import from Docker Registry.
2. Image: `docker.io/USERNAME/spio-flux-worker:v1`
3. GPU awal: `A4000/A4500`
4. Scaling hemat:
   - `Active workers = 0`
   - `Max workers = 2`
   - `Idle timeout = 15s`
5. Isi env dari file contoh `runpod_flux_env.example`.

Test endpoint dari VPS:

```bash
./test_runpod_image_endpoint.sh rpa_xxx endpoint_id_kamu
```

Jika output ada `image_url`, endpoint siap dipakai di UI (`RunPod API Key` + `Image Endpoint ID`).
