#!/usr/bin/env bash
set -euo pipefail

echo "======================================================"
echo "    SNIPER TRADING BOT — VPS SETUP & OPTIMIZATION     "
echo "======================================================"

# Helper para ejecutar con sudo si no es root
run_sudo() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

# 1. Configurar SWAP de 2 GB (Failsafe para VPS con 1 GB RAM / e2-micro de Google Cloud)
if [ ! -f /swapfile ]; then
    echo "[+] Configurando 2 GB de memoria SWAP..."
    run_sudo fallocate -l 2G /swapfile || run_sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    run_sudo chmod 600 /swapfile
    run_sudo mkswap /swapfile
    run_sudo swapon /swapfile
    if ! grep -q '/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' | run_sudo tee -a /etc/fstab
    fi
    echo "[OK] Memoria SWAP de 2 GB creada y activada permanentemente."
else
    echo "[i] /swapfile ya existe. Verificando estado activo..."
    if ! swapon --show | grep -q '/swapfile'; then
        run_sudo swapon /swapfile || true
    fi
    echo "[OK] SWAP verificado y activo."
fi

# 2. Instalar paquetes de sistema indispensables si apt está disponible
if command -v apt-get >/dev/null 2>&1; then
    echo "[+] Actualizando repositorios e instalando paquetes base..."
    run_sudo apt-get update -qq || true
    run_sudo apt-get install -y -qq python3 python3-pip python3-venv git curl build-essential tmux >/dev/null 2>&1 || true
fi

# 3. Determinar directorio de trabajo del proyecto
if [ -f "main.py" ] && [ -f "requirements.lock" ]; then
    PROJECT_ROOT="$(pwd)"
elif [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/../main.py" ]; then
    PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
else
    PROJECT_ROOT="$HOME/Pbot-V5ARCH-DEV-clean"
    if [ ! -d "$PROJECT_ROOT" ]; then
        echo "[+] Clonando repositorio en $PROJECT_ROOT..."
        git clone https://github.com/Rukawua26/Pbot-V5ARCH-DEV-clean.git "$PROJECT_ROOT"
    fi
fi

cd "$PROJECT_ROOT"
echo "[+] Directorio del proyecto: $PROJECT_ROOT"

# 4. Preparar entorno virtual .venv
if [ ! -d ".venv" ]; then
    echo "[+] Creando entorno virtual Python en .venv..."
    python3 -m venv .venv
fi

echo "[+] Actualizando pip, setuptools, wheel e instalando dependencias..."
./.venv/bin/python -m pip install --upgrade pip setuptools wheel -q
if [ -f "requirements.lock" ]; then
    echo "[+] Instalando paquetes bloqueados desde requirements.lock..."
    ./.venv/bin/python -m pip install -r requirements.lock -q
fi

# 5. Generar archivo .env inicial si no existe
if [ ! -f ".env" ]; then
    echo "[+] Creando archivo .env inicial (Modo PAPER seguro)..."
    cat << 'EOF' > .env
MODE=PAPER
ALLOW_REAL_TRADING=false
BINANCE_API_KEY=
BINANCE_API_SECRET=
DASHBOARD_PORT=3000
EOF
    echo "[OK] Archivo .env generado en $PROJECT_ROOT/.env."
fi

# 6. Validar integridad sintáctica
echo "[+] Verificando integridad del código Python..."
./.venv/bin/python -m compileall -q main.py core

echo "======================================================"
echo "    [LISTO] INSTALACIÓN Y OPTIMIZACIÓN COMPLETADAS    "
echo "======================================================"
echo "Para iniciar el bot:"
echo "  cd $PROJECT_ROOT"
echo "  ./.venv/bin/python main.py"
echo ""
echo "Para mantenerlo corriendo 24/7 en segundo plano con tmux:"
echo "  tmux new -s bot './.venv/bin/python main.py'"
echo "======================================================"
