#!/usr/bin/env bash
set -euo pipefail

# Build + push worker image FLUX untuk RunPod Serverless.
# Usage:
#   ./deploy_flux_worker.sh docker.io/USERNAME/spio-flux-worker:v1
# Optional env:
#   PLATFORM=linux/amd64

if [[ "${1:-}" == "" ]]; then
  echo "Usage: $0 <docker_image_tag>"
  echo "Example: $0 docker.io/sonny29/spio-flux-worker:v1"
  exit 1
fi

IMAGE_TAG="$1"
PLATFORM="${PLATFORM:-linux/amd64}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker tidak ditemukan. Install Docker dulu."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Build image: $IMAGE_TAG"
docker build --platform "$PLATFORM" -f Dockerfile.image -t "$IMAGE_TAG" .

echo "==> Push image: $IMAGE_TAG"
docker push "$IMAGE_TAG"

cat <<EOF

SUKSES build+push worker image FLUX.

Langkah lanjut di RunPod:
1) Serverless -> New Endpoint -> Import from Docker Registry
2) Container image: $IMAGE_TAG
3) GPU: A4000/A4500 (awal)
4) Active workers=0, Max workers=2, Idle timeout=15s
5) Env minimal:
   IMAGE_MODEL_ID=black-forest-labs/FLUX.1-schnell
   IMAGE_TORCH_DTYPE=float16
   OUTPUT_S3_BUCKET=...
   OUTPUT_S3_REGION=...
   OUTPUT_S3_ACCESS_KEY_ID=...
   OUTPUT_S3_SECRET_ACCESS_KEY=...

EOF
