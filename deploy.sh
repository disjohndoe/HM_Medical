#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Pulling latest code ==="
git pull origin main

echo "=== Tagging current images for rollback ==="
docker compose images -q 2>/dev/null | xargs -r docker tag 2>/dev/null || true

echo "=== Cleaning stale containers ==="
docker container prune -f 2>/dev/null || true

echo "=== Building and restarting services (keep DB running) ==="
docker compose build
docker compose up -d --force-recreate --no-deps backend frontend caddy backup
docker compose up -d

echo "=== Waiting for services to become healthy ==="
TIMEOUT=120
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
  UNHEALTHY=$(docker compose ps --format json 2>/dev/null | grep -c '"unhealthy"' || true)
  STARTING=$(docker compose ps --format json 2>/dev/null | grep -c '"starting"' || true)
  if [ "$UNHEALTHY" -eq 0 ] && [ "$STARTING" -eq 0 ]; then
    echo "All services healthy"
    break
  fi
  sleep 5
  ELAPSED=$((ELAPSED + 5))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
  echo "WARNING: Some services did not become healthy within ${TIMEOUT}s"
  docker compose ps
  echo "Check logs with: docker compose logs"
  exit 1
fi

echo "=== Running database migrations ==="
docker compose exec -T backend alembic upgrade head

echo "=== Cleaning up old images ==="
docker image prune -f

echo "=== Deployment complete ==="
docker compose ps
