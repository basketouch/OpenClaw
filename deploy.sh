#!/bin/bash
set -e
cd "$(dirname "$0")"

git pull
docker compose build openclaw
docker compose up -d --no-deps openclaw
echo "Desplegado OK"
