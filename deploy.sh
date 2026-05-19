#!/bin/bash
set -e
cd "$(dirname "$0")"

# Clone or update OpenWA
if [ -d "openwa" ]; then
  echo "Actualizando OpenWA..."
  git -C openwa pull
else
  echo "Clonando OpenWA (primera vez, puede tardar unos minutos)..."
  git clone https://github.com/rmyndharis/OpenWA.git openwa
fi

git pull
docker compose up -d --build
echo "Desplegado OK"
