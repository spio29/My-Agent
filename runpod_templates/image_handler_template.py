import base64
import io
import os
import random
import uuid
from typing import Any, Dict, Optional

import boto3
import runpod
import torch
from diffusers import AutoPipelineForText2Image, FluxPipeline
from PIL import Image

IMAGE_PIPE = None
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


def _decode_data_uri(data_uri: str) -> Optional[Image.Image]:
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


def _upload_image_bytes(image_bytes: bytes) -> str:
    bucket = os.getenv("OUTPUT_S3_BUCKET", "").strip()
    if not bucket:
        raise ValueError("OUTPUT_S3_BUCKET belum diisi.")
    prefix = os.getenv("OUTPUT_PREFIX_IMAGE", "spio/images").strip("/") or "spio/images"
    key = f"{prefix}/{uuid.uuid4().hex}.png"
    client = _get_s3_client()
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=image_bytes,
        ContentType="image/png",
        CacheControl="public, max-age=31536000",
    )
    public_base = os.getenv("OUTPUT_S3_PUBLIC_BASE_URL", "").strip()
    if public_base:
        return f"{public_base.rstrip('/')}/{key}"
    region = os.getenv("OUTPUT_S3_REGION", "ap-southeast-1")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{key}"


def _get_image_pipe():
    global IMAGE_PIPE
    if IMAGE_PIPE is not None:
        return IMAGE_PIPE
    model_id = os.getenv("IMAGE_MODEL_ID", "black-forest-labs/FLUX.1-schnell").strip()
    use_flux = "flux" in model_id.lower()
    dtype_name = (os.getenv("IMAGE_TORCH_DTYPE", "float16") or "float16").strip().lower()
    torch_dtype = torch.bfloat16 if dtype_name in ("bf16", "bfloat16") else torch.float16
    if use_flux:
        pipe = FluxPipeline.from_pretrained(
            model_id,
            torch_dtype=torch_dtype,
        )
    else:
        pipe = AutoPipelineForText2Image.from_pretrained(
            model_id,
            torch_dtype=torch_dtype,
            variant="fp16",
        )
    pipe = pipe.to("cuda")
    pipe.enable_attention_slicing()
    IMAGE_PIPE = pipe
    return IMAGE_PIPE


def handler(job: Dict[str, Any]) -> Dict[str, Any]:
    data = (job or {}).get("input", {}) or {}
    prompt = str(data.get("prompt", "")).strip()
    if not prompt:
        return {"error": "prompt wajib diisi"}

    negative_prompt = str(data.get("negative_prompt", "")).strip()
    width = _to_int(data.get("width", 1024), 1024, 256, 1536)
    height = _to_int(data.get("height", 1024), 1024, 256, 1536)
    steps = _to_int(data.get("steps", 4), 4, 1, 60)
    cfg_scale = _to_float(data.get("cfg_scale", 1.0), 1.0, 1.0, 15.0)
    seed = _to_int(data.get("seed", random.randint(1000, 999999)), random.randint(1000, 999999), 1, 2147483647)

    # Keys ini sudah diterima supaya cocok dengan payload UI.
    # Integrasi advanced face/body lock (IP-Adapter/ControlNet) bisa ditambah sesuai model.
    _ = _decode_data_uri(str(data.get("ip_adapter_image", "")))
    _ = _decode_data_uri(str(data.get("body_image", "")))

    pipe = _get_image_pipe()
    generator = torch.Generator(device="cuda").manual_seed(seed)

    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt if negative_prompt else None,
        width=width,
        height=height,
        num_inference_steps=steps,
        guidance_scale=cfg_scale,
        generator=generator,
    )
    image = result.images[0]
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    image_url = _upload_image_bytes(buf.getvalue())

    return {
        "image_url": image_url,
        "images": [image_url],
        "seed": seed,
        "width": width,
        "height": height,
    }


runpod.serverless.start({"handler": handler})
