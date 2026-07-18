#!/usr/bin/env bash
# Production deploy / update script. Run from the project root on the server:
#   ./deploy.sh
# It pulls the latest code, rebuilds the frontend and backend, applies database
# migrations, and (re)starts the stack. Safe to re-run for every update.
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE="docker compose -f docker-compose.prod.yml"

echo "==> [0/5] Backing up the database (pre-deploy safety net)"
mkdir -p backups
if $COMPOSE ps --status running db 2>/dev/null | grep -q db; then
  $COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
    | gzip > "backups/pre_deploy_$(date +%F_%H%M%S).sql.gz"
  # keep only the 7 most recent backups
  ls -1t backups/pre_deploy_*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm --
  echo "    Backup saved to backups/ (7 most recent kept)"
else
  echo "    db container not running — skipping backup (first deploy)"
fi

echo "==> [1/5] Pulling latest code"
git pull --ff-only

echo "==> [2/5] Building the frontend (static SPA -> frontend/dist)"
docker run --rm \
  -v "$PWD/frontend:/app" -w /app \
  -e VITE_API_BASE_URL="" \
  -e NODE_OPTIONS="--max-old-space-size=1536" \
  node:20-alpine sh -c "npm ci && npm run build"

echo "==> [3/5] Building images"
$COMPOSE build

echo "==> [4/5] Applying database migrations"
$COMPOSE up -d db
$COMPOSE run --rm backend alembic upgrade head

echo "==> [5/5] Starting all services"
$COMPOSE up -d

# The Caddyfile lives in a directory mount (caddy/prod), so edits are always
# visible in the container — but Caddy doesn't re-read its config on its own and
# `up -d` won't recreate caddy for a content-only change, so force-recreate it to
# load the new Caddyfile.
echo "==> Recreating Caddy so Caddyfile changes take effect"
$COMPOSE up -d --force-recreate caddy

echo
echo "==> Done. Service status:"
$COMPOSE ps
