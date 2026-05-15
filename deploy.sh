#!/bin/bash
set -e
cd "$(dirname "$0")"
git pull
docker compose up -d --build
echo "Desplegado OK"
