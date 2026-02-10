#!/usr/bin/env bash
set -euo pipefail

# Docker build helper for this repository.
# Usage:
#   ./docker_build.sh
#   ./docker_build.sh -n facjxzdt/animescore -t v1.0.0
#   ./docker_build.sh -n facjxzdt/animescore -t latest -p

IMAGE_NAME="animescore"
IMAGE_TAG="latest"
DOCKERFILE="Dockerfile"
CONTEXT="."
PUSH_IMAGE="false"
NO_CACHE="false"

print_help() {
  cat <<'EOF'
Usage: ./docker_build.sh [options]

Options:
  -n, --name <name>        Docker image name (default: animescore)
  -t, --tag <tag>          Docker image tag (default: latest)
  -f, --file <dockerfile>  Dockerfile path (default: Dockerfile)
  -c, --context <path>     Build context path (default: .)
  -p, --push               Push image after build
      --no-cache           Build image with --no-cache
  -h, --help               Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--name)
      IMAGE_NAME="$2"
      shift 2
      ;;
    -t|--tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    -f|--file)
      DOCKERFILE="$2"
      shift 2
      ;;
    -c|--context)
      CONTEXT="$2"
      shift 2
      ;;
    -p|--push)
      PUSH_IMAGE="true"
      shift
      ;;
    --no-cache)
      NO_CACHE="true"
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      print_help
      exit 1
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker command not found."
  exit 1
fi

if [[ ! -f "$DOCKERFILE" ]]; then
  echo "Error: Dockerfile not found: $DOCKERFILE"
  exit 1
fi

IMAGE_REF="${IMAGE_NAME}:${IMAGE_TAG}"
BUILD_ARGS=(-f "$DOCKERFILE" -t "$IMAGE_REF")
if [[ "$NO_CACHE" == "true" ]]; then
  BUILD_ARGS+=(--no-cache)
fi
BUILD_ARGS+=("$CONTEXT")

echo "[INFO] Building image: $IMAGE_REF"
docker build "${BUILD_ARGS[@]}"
echo "[INFO] Build complete: $IMAGE_REF"

if [[ "$PUSH_IMAGE" == "true" ]]; then
  echo "[INFO] Pushing image: $IMAGE_REF"
  docker push "$IMAGE_REF"
  echo "[INFO] Push complete: $IMAGE_REF"
fi
