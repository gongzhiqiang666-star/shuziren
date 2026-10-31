#!/usr/bin/env sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
command -v docker >/dev/null 2>&1 || { echo 'Please install Docker with Compose first.' >&2; exit 1; }
docker compose version >/dev/null
if [ ! -e .env ]; then
  umask 077
  command -v od >/dev/null 2>&1 || { echo 'od is required to generate local credentials.' >&2; exit 1; }
  app_secret=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
  database_secret=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
  temp_env=$(mktemp .env.setup.XXXXXX)
  trap 'rm -f "$temp_env"' EXIT HUP INT TERM
  sed -e "s/^APP_TOKEN=$/APP_TOKEN=$app_secret/" -e "s/^POSTGRES_PASSWORD=$/POSTGRES_PASSWORD=$database_secret/" .env.example > "$temp_env"
  # A hard link avoids replacing a file another setup process just created.
  if ! ln "$temp_env" .env 2>/dev/null; then
    echo '.env was created by another process; preserving it.'
  fi
  rm -f "$temp_env"
  trap - EXIT HUP INT TERM
fi
docker compose config --quiet
docker compose up --build -d --wait --wait-timeout 180
echo 'Workspace: http://127.0.0.1:8765 (or APP_PORT in .env)'
echo 'The workspace access token is APP_TOKEN in .env. Keep this file private.'
echo 'This starts the workspace and PostgreSQL. Configure TTS and LiveTalking separately.'
