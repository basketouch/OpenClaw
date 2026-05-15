#!/usr/bin/env bash
# OpenClaw — Script de configuración del VPS
# Uso: chmod +x scripts/setup-vps.sh && ./scripts/setup-vps.sh
set -euo pipefail

INSTALL_DIR="/opt/openclaw"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "======================================"
echo "  OpenClaw — Setup VPS"
echo "======================================"
echo ""

# ── Directorios ────────────────────────────────────────────────────────────
echo "[1/4] Creando estructura de directorios en $INSTALL_DIR..."
sudo mkdir -p "$INSTALL_DIR"/{data,workspace,logs}
sudo chown -R "$USER:$USER" "$INSTALL_DIR"
echo "      OK: $INSTALL_DIR/{data,workspace,logs}"

# ── Docker ────────────────────────────────────────────────────────────────
echo ""
echo "[2/4] Verificando Docker..."
if ! command -v docker &>/dev/null; then
  echo "      Instalando Docker..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"
  echo ""
  echo "  ⚠  Docker instalado. Cierra sesión y vuelve a entrar, luego ejecuta este script de nuevo."
  exit 0
fi

if ! docker compose version &>/dev/null 2>&1; then
  echo "  ERROR: Docker Compose v2 no encontrado."
  echo "  Instala el plugin: sudo apt-get install docker-compose-plugin"
  exit 1
fi

echo "      Docker: $(docker --version)"
echo "      Compose: $(docker compose version)"

# ── Caddy ─────────────────────────────────────────────────────────────────
echo ""
echo "[3/4] Verificando Caddy..."
if ! command -v caddy &>/dev/null; then
  echo "      Instalando Caddy..."
  sudo apt-get update -qq
  sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y caddy
  echo "      Caddy instalado: $(caddy version)"
else
  echo "      Caddy: $(caddy version)"
fi

# ── .env ──────────────────────────────────────────────────────────────────
echo ""
echo "[4/4] Configuración de entorno..."

if [ ! -f "$REPO_DIR/.env" ]; then
  cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
  SECRET=$(openssl rand -hex 32)
  sed -i "s/cambia-este-valor-ahora/$SECRET/" "$REPO_DIR/.env"
  echo "      Archivo .env creado."
  echo "      AUTH_SECRET generado automáticamente."
  echo ""
  echo "  ➜  Edita $REPO_DIR/.env y añade tu ANTHROPIC_API_KEY"
else
  echo "      .env ya existe, no se sobreescribe."
fi

# ── Resumen ───────────────────────────────────────────────────────────────
echo ""
echo "======================================"
echo "  Setup completado"
echo "======================================"
echo ""
echo "Próximos pasos:"
echo ""
echo "  1. Edita .env y añade tu API key:"
echo "     nano $REPO_DIR/.env"
echo ""
echo "  2. Edita Caddyfile con tu dominio:"
echo "     nano $REPO_DIR/Caddyfile"
echo "     sudo cp $REPO_DIR/Caddyfile /etc/caddy/Caddyfile"
echo "     sudo systemctl reload caddy"
echo ""
echo "  3. Lanza OpenClaw:"
echo "     cd $REPO_DIR && docker compose up -d"
echo ""
echo "  4. Verifica que funciona:"
echo "     curl http://localhost:8000/health"
echo ""
