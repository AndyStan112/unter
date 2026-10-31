#!/bin/bash
set -euo pipefail
# Run from the repository root after a successful CI release.
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/unter-uv-cache}" uv run --project services/python python scripts/sync-secrets.py
ssh -F /dev/null -o BatchMode=yes andy@ssh.windogs.win \
 'KUBECONFIG=/home/andy/.kube/cube-studio.yaml /usr/local/bin/kubectl apply -f -' < deploy/flux/sync.yaml
# Flux handles subsequent deployments. Caddy routing is a separate, reviewed step.
