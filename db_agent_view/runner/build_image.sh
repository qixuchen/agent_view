#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_TAG="${BEAVER_C0_AGENT_IMAGE:-beaver-c0-agent:local}"

docker build --tag "${IMAGE_TAG}" "${SCRIPT_DIR}"
docker image inspect --format='{{index .RepoDigests 0}} {{.Id}}' "${IMAGE_TAG}"
docker run --rm --entrypoint /bin/bash "${IMAGE_TAG}" -lc \
  'openclaw --version && mysql --version'
