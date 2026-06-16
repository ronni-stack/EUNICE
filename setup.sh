#!/bin/bash
set -e

echo "========================================="
echo "  EUNICE v0.7 — Automated Setup"
echo "========================================="

RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
RAM_GB=$((RAM_KB / 1024 / 1024))
echo "Detected RAM: ${RAM_GB}GB"

if [ "$RAM_GB" -lt 8 ]; then
    echo "WARNING: Less than 8GB RAM. Phi 4 will be slow. Consider llama3.2:3b for faster responses."
fi

echo ""
echo "[1/5] Installing system packages..."
sudo apt update -qq
sudo apt install -y -qq curl python3 python3-venv python3-pip python3-aiofiles

echo "[2/5] Installing Ollama..."
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
else
    echo "Ollama already installed."
fi

echo "[3/5] Pulling models..."
ollama pull phi4 || echo "Phi 4 pull failed."
ollama pull llama3.2:3b || echo "Llama 3.2 pull failed."

echo "[4/5] Creating Python virtual environment..."
cd "$(dirname "$0")"
python3 -m venv venv
source venv/bin/activate

pip install --quiet \
    fastapi uvicorn httpx aiofiles \
    chromadb sentence-transformers \
    pydantic pydantic-settings \
    sqlalchemy alembic \
    rich typer \
    pytest pytest-asyncio

echo "[5/5] Creating directories..."
mkdir -p data backups
chmod +x backup.sh launch.sh

echo ""
echo "========================================="
echo "  Setup Complete!"
echo "========================================="
echo ""
echo "To start EUNICE:"
echo "  Terminal 1: ollama serve"
echo "  Terminal 2: ./launch.sh"
echo ""
echo "Then open: http://\$(hostname -I | awk '{print \$1}'):8000"
echo ""
