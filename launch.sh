#!/bin/bash
# EUNICE Launcher — v0.7
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "ERROR: venv/ not found. Run setup.sh first."
    exit 1
fi

source venv/bin/activate

# Detect actual model from config
MODEL=$(grep "MODEL_NAME" config.py 2>/dev/null | head -1 | sed 's/.*=//;s/"//g;s/ //g' || echo "unknown")

if ! curl -s http://localhost:11434 > /dev/null 2>&1; then
    echo "WARNING: Ollama is not running. Start it first with: ollama serve"
fi

echo "╔══════════════════════════════════════════╗"
echo "║     EUNICE v0.7 Launching...             ║"
echo "║     Model: $MODEL                        ║"
echo "║     API: http://0.0.0.0:8000             ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Press Ctrl+C to stop."
echo ""

python3 main.py
