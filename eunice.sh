#!/bin/bash
# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.
# # EUNICE v0.9 — Unified CLI
# Usage: ./eunice.sh [setup|launch|test|backup|help]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Source .env if present
[ -f .env ] && source .env

# Detect configuration using Python for reliable parsing
MODEL=$(python3 -c "import config; print(config.MODEL_NAME)" 2>/dev/null || echo "phi4")
API_KEY=$(python3 -c "import config; print(config.API_KEY)" 2>/dev/null || echo "unknown")
BASE="http://localhost:8000"

show_help() {
    echo "EUNICE v0.9 Unified CLI"
    echo ""
    echo "Usage: ./eunice.sh <command>"
    echo ""
    echo "Commands:"
    echo "  setup    Install system deps, Ollama, Python venv, and models"
    echo "  launch   Start the EUNICE server (runs setup first if venv is missing)"
    echo "  test     Run smoke tests against a running server"
    echo "  backup   Create a timestamped backup of data and config"
    echo "  help     Show this help message"
    echo ""
    echo "Typical workflow:"
    echo "  ./eunice.sh launch"
    echo ""
    echo "Then open: http://\$(hostname -I | awk '{print \$1}'):8000"
    echo ""
    echo "Logs: tail -f data/eunice.log"
}

cmd_setup() {
    echo "========================================="
    echo "  EUNICE v0.9 — Setup"
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

    echo ""
    echo "[2/5] Installing Ollama..."
    if ! command -v ollama &> /dev/null; then
        curl -fsSL https://ollama.com/install.sh | sh
    else
        echo "Ollama already installed."
    fi

    echo ""
    echo "[3/5] Pulling models..."
    ollama pull phi4 || echo "Phi 4 pull failed."
    ollama pull llama3.2:3b || echo "Llama 3.2 pull failed."

    echo ""
    echo "[4/5] Creating Python virtual environment..."
    python3 -m venv venv
    source venv/bin/activate

    pip install --quiet \
        fastapi uvicorn httpx aiofiles \
        chromadb sentence-transformers \
        pydantic pydantic-settings \
        sqlalchemy alembic \
        rich typer \
        pytest pytest-asyncio \
        bcrypt pyjwt \
        pymupdf \
        ddgs beautifulsoup4 \
        python-multipart

    echo ""
    echo "[5/5] Creating directories..."
    mkdir -p data backups

    echo ""
    echo "========================================="
    echo "  Setup Complete!"
    echo "========================================="
}

cmd_launch() {
    # Auto-run setup if venv is missing
    if [ ! -d "venv" ]; then
        echo "venv/ not found. Running setup first..."
        cmd_setup
    fi

    source venv/bin/activate

    STARTED_OLLAMA=false
    if ! curl -s http://localhost:11434 > /dev/null 2>&1; then
        if command -v ollama &> /dev/null; then
            echo "Starting Ollama in the background..."
            ollama serve > /tmp/ollama_eunice.log 2>&1 &
            OLLAMA_PID=$!
            STARTED_OLLAMA=true

            # Wait for Ollama to become ready
            for i in {1..30}; do
                if curl -s http://localhost:11434 > /dev/null 2>&1; then
                    echo "Ollama is ready."
                    break
                fi
                sleep 1
            done

            if ! curl -s http://localhost:11434 > /dev/null 2>&1; then
                echo "ERROR: Ollama failed to start. Check /tmp/ollama_eunice.log"
                exit 1
            fi
        else
            echo "ERROR: Ollama is not installed and not running. Run ./eunice.sh setup first."
            exit 1
        fi
    else
        echo "Ollama is already running."
    fi

    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║     EUNICE v0.9 Launching...             ║"
    echo "║     Model: $MODEL                        ║"
    echo "║     API: http://0.0.0.0:8000             ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""
    echo "Press Ctrl+C to stop."
    echo ""

    # Trap Ctrl+C so we can shut down Ollama if we started it
    cleanup() {
        echo ""
        echo "Shutting down EUNICE..."
        if [ "$STARTED_OLLAMA" = true ]; then
            echo "Stopping Ollama (PID $OLLAMA_PID)..."
            kill $OLLAMA_PID 2>/dev/null || true
            wait $OLLAMA_PID 2>/dev/null || true
        fi
    }
    trap cleanup INT TERM

    python3 main.py

    cleanup
}

cmd_test() {
    source venv/bin/activate

    echo "Running pytest..."
    python3 -m pytest tests/test_memory.py -v
    echo ""

    if ! curl -s $BASE/health > /dev/null 2>&1; then
        echo "ERROR: EUNICE server is not running. Start it first with: ./eunice.sh launch"
        exit 1
    fi

    echo "=== 1. HEALTH ==="
    curl -s $BASE/health | python3 -m json.tool

    echo ""
    echo "=== 2. ONBOARDING + NAME EXTRACTION ==="
    curl -s -X POST $BASE/chat/stream \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -H "X-EUNICE-Device-ID: test-device" \
        -d '{"message":"I am Alex","session":"test"}'
    echo ""

    echo ""
    echo "=== 3. MEMORY RECALL ==="
    curl -s -X POST $BASE/chat/stream \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -H "X-EUNICE-Device-ID: test-device" \
        -d '{"message":"what is my name","session":"test"}'
    echo ""

    echo ""
    echo "=== 4. EXPLICIT MEMORY ==="
    curl -s -X POST $BASE/chat/stream \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -H "X-EUNICE-Device-ID: test-device" \
        -d '{"message":"remember that my car is a Tesla Model 3","session":"test"}'
    echo ""

    echo ""
    echo "=== 5. BALANCE (should ask confirm) ==="
    curl -s -X POST $BASE/chat/stream \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -H "X-EUNICE-Device-ID: test-device" \
        -d '{"message":"what is my balance","session":"test"}'
    echo ""

    echo ""
    echo "=== 6. CONFIRM BALANCE ==="
    curl -s -X POST $BASE/chat/stream \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -H "X-EUNICE-Device-ID: test-device" \
        -d '{"message":"confirm get_balance","session":"test"}'
    echo ""

    echo ""
    echo "=== 7. TRANSFER (should deny) ==="
    curl -s -X POST $BASE/chat/stream \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -H "X-EUNICE-Device-ID: test-device" \
        -d '{"message":"transfer $100 to Bob","session":"test"}'
    echo ""

    echo ""
    echo "=== 8. TRAILS ==="
    curl -s -H "Authorization: Bearer $API_KEY" -H "X-EUNICE-Device-ID: test-device" $BASE/trails | python3 -m json.tool

    echo ""
    echo "=== 9. DAEMON STATUS ==="
    curl -s -H "Authorization: Bearer $API_KEY" $BASE/daemon/status | python3 -m json.tool

    echo ""
    echo "=== 10. USER ISOLATION ==="
    curl -s -X POST $BASE/chat/stream \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -H "X-EUNICE-Device-ID: other-device" \
        -d '{"message":"what is my name","session":"test"}'
    echo ""

    echo ""
    echo "=== TEST COMPLETE ==="
    echo "Note: test-device data was created. Run backup to preserve or delete manually."
}

cmd_backup() {
    BACKUP_DIR="$HOME/eunice_backups"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)

    mkdir -p "$BACKUP_DIR"

    echo "Creating backup: eunice_backup_$TIMESTAMP.tar.gz"

    tar -czf "$BACKUP_DIR/eunice_backup_$TIMESTAMP.tar.gz" \
        -C "$SCRIPT_DIR" \
        data \
        personality.txt \
        config.py \
        main.py \
        client.html \
        sw.js \
        manifest.json \
        core \
        memory \
        api \
        tools \
        scripts \
        tests \
        prompts \
        2>/dev/null

    echo "Backup saved to: $BACKUP_DIR/eunice_backup_$TIMESTAMP.tar.gz"
    echo "Size: $(du -h "$BACKUP_DIR/eunice_backup_$TIMESTAMP.tar.gz" | cut -f1)"
    echo "To restore: cd ~/EUNICE_MASTER && tar -xzf $BACKUP_DIR/eunice_backup_$TIMESTAMP.tar.gz"
}

# Main command dispatcher
case "${1:-help}" in
    setup)
        cmd_setup
        ;;
    launch|start|run)
        cmd_launch
        ;;
    test)
        cmd_test
        ;;
    backup)
        cmd_backup
        ;;
    help|--help|-h|"")
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
