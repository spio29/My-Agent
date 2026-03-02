import base64
import io
import os
import random
import tempfile
import uuid
from typing import Any, Dict, List, Optional

import boto3
import imageio.v2 as imageio
import numpy as np
import runpod
import torch
from diffusers import StableVideoDiffusionPipeline
from PIL import Image, ImageOps

VIDEO_PIPE = None
S3_CLIENT = None


def _to_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        num = int(value)
    except Exception:
        return default
    return max(min_value, min(max_value, num))


def _to_float(value: Any, default: float, min_value: float, max_value: float) -> float:
    try:
        num = float(value)
    except Exception:
        return default
    return max(min_value, min(max_value, num))


def _decode_data_uri_to_image(data_uri: str) -> Optional[Image.Image]:
    if not data_uri or not isinstance(data_uri, str):
        return None
    if not data_uri.startswith("data:"):
        return None
    try:
        encoded = data_uri.split(",", 1)[1]
        binary = base64.b64decode(encoded)
        return Image.open(io.BytesIO(binary)).convert("RGB")
    except Exception:
        return None


def _fit_anchor(anchor: Image.Image) -> Image.Image:
    # Template default SVD paling stabil di 1024x576.
    return ImageOps.fit(anchor.convert("RGB"), (1024, 576), method=Image.Resampling.LANCZOS)


def _get_s3_client():
    global S3_CLIENT
    if S3_CLIENT is not None:
        return S3_CLIENT
    S3_CLIENT = boto3.client(
        "s3",
        region_name=os.getenv("OUTPUT_S3_REGION", "ap-southeast-1"),
        aws_access_key_id=os.getenv("OUTPUT_S3_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("OUTPUT_S3_SECRET_ACCESS_KEY"),
    )
    return S3_CLIENT


def _upload_video_bytes(video_bytes: bytes) -> str:
    bucket = os.getenv("OUTPUT_S3_BUCKET", "").strip()
    if not bucket:
        raise ValueError("OUTPUT_S3_BUCKET belum diisi.")
    prefix = os.getenv("OUTPUT_PREFIX_VIDEO", "spio/videos").strip("/") or "spio/videos"
    key = f"{prefix}/{uuid.uuid4().hex}.mp4"
    client = _get_s3_client()
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=video_bytes,
        ContentType="video/mp4",
        CacheControl="public, max-age=31536000",
    )
    public_base = os.getenv("OUTPUT_S3_PUBLIC_BASE_URL", "").strip()
    if public_base:
        return f"{public_base.rstrip('/')}/{key}"
    region = os.getenv("OUTPUT_S3_REGION", "ap-southeast-1")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"


def _get_video_pipe():
    global VIDEO_PIPE
    if VIDEO_PIPE is not None:
        return VIDEO_PIPE
    model_id = os.getenv("VIDEO_MODEL_ID", "stabilityai/stable-video-diffusion-img2vid-xt").strip()
    pipe = StableVideoDiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float16,
        variant="fp16",
    )
    pipe = pipe.to("cuda")
    pipe.enable_attention_slicing()
    VIDEO_PIPE = pipe
    return VIDEO_PIPE


def _frames_to_mp4(frames: List[Image.Image], fps: int) -> bytes:
    arrays = [np.array(frame.convert("RGB")) for frame in frames]
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = tmp.name
        imageio.mimsave(tmp_path, arrays, fps=fps)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def handler(job: Dict[str, Any]) -> Dict[str, Any]:
    data = (job or {}).get("input", {}) or {}
    prompt = str(data.get("prompt", "")).strip()
    if not prompt:
        return {"error": "prompt wajib diisi"}

    i2v_key = os.getenv("VIDEO_I2V_KEY", "image").strip() or "image"
    anchor_data_uri = str(data.get(i2v_key, "")).strip()
    if not anchor_data_uri:
        return {"error": f"{i2v_key} (anchor image) wajib diisi"}

    anchor = _decode_data_uri_to_image(anchor_data_uri)
    if anchor is None:
        return {"error": "anchor image tidak valid (harus data URI base64)"}

    # Key ini diterima untuk kompatibilitas payload UI. Integrasi body lock lanjutan tergantung model.
    _ = _decode_data_uri_to_image(str(data.get("body_image", "")))

    negative_prompt = str(data.get("negative_prompt", "")).strip()
    fps = _to_int(data.get("fps", 12), 12, 6, 30)
    duration = _to_int(data.get("duration", 5), 5, 2, 12)
    target_frames = max(8, min(96, fps * duration))
    seed = _to_int(data.get("seed", random.randint(1000, 999999)), random.randint(1000, 999999), 1, 2147483647)
    motion_bucket_id = _to_int(data.get("motion_bucket_id", 127), 127, 1, 255)
    noise_aug_strength = _to_float(data.get("noise_aug_strength", 0.02), 0.02, 0.0, 1.0)

    anchor = _fit_anchor(anchor)
    pipe = _get_video_pipe()
    generator = torch.Generator(device="cuda").manual_seed(seed)

    result = pipe(
        image=anchor,
        prompt=prompt,
        negative_prompt=negative_prompt if negative_prompt else None,
        generator=generator,
        num_frames=target_frames,
        decode_chunk_size=8,
        motion_bucket_id=motion_bucket_id,
        noise_aug_strength=noise_aug_strength,
    )
    frames = result.frames[0]
    if len(frames) > target_frames:
        frames = frames[:target_frames]

    mp4_bytes = _frames_to_mp4(frames, fps=fps)
    video_url = _upload_video_bytes(mp4_bytes)

    return {
        "video_url": video_url,
        "videos": [video_url],
        "seed": seed,
        "fps": fps,
        "duration": duration,
        "frames": len(frames),
    }


runpod.serverless.start({"handler": handler})

