# EUNICE v0.8 — Personal AI Assistant (Multi-User + Autonomous Discovery)

EUNICE is a locally-hosted AI assistant with persistent associative memory, risk-tiered tool execution, and autonomous user profiling.

## What's New in v0.8

- **Multi-user foundation**: Each device/browser gets an isolated user profile.
- **Autonomous onboarding**: EUNICE learns your name, work, location, and preferences through natural chat — no scripted questionnaire.
- **Confidence-based memory**: Facts are stored with confidence scores, source tags, and reinforcement counts.
- **Relationship graph**: People, places, and things are linked to you with typed relationships.
- **Implicit learning**: Every exchange is background-processed for extractable facts.
- **Generic personality**: Works for any user, not hardcoded to a single person.

## Hardware
- Old laptop (8GB RAM) running Ubuntu from external SSD
- Phone connects via home Wi-Fi
- Main laptop (16GB) remains free for your work
- Raspberry Pi 5 (8GB) for a standalone device

## Quick Start

EUNICE uses a single unified CLI script: `./eunice.sh`.

### 1. Setup (one time)
```bash
cd ~/EUNICE_MASTER
./eunice.sh setup
```
This installs system packages, Ollama, Python dependencies, and pulls the AI models.

### 2. Start the Brain (Ollama)
```bash
ollama serve
```

### 3. Start EUNICE Server
```bash
cd ~/EUNICE_MASTER
./eunice.sh launch
```
If `venv/` is missing, `launch` will automatically run `setup` first.

### 4. Open the Client
On your phone or laptop browser:
```
http://<this-machine-ip>:8000
```
Find the IP by running `hostname -I` on the server machine.

## CLI Commands

| Command | Description |
|---|---|
| `./eunice.sh setup` | Install dependencies, Ollama, models, and create venv |
| `./eunice.sh launch` | Start the EUNICE server (auto-runs setup if needed) |
| `./eunice.sh test` | Run pytest + smoke tests against a running server |
| `./eunice.sh backup` | Create a timestamped backup of data and code |
| `./eunice.sh help` | Show help |

Legacy scripts (`launch.sh`, `setup.sh`, `test_eunice_full.sh`, `backup.sh`) still work as wrappers around `./eunice.sh`.

## Model Notes
- Default: `phi4` (4B params, ~2.3GB download, best quality for 8GB)
- Fallback: `llama3.2:3b` (faster, slightly less eloquent)
- To switch models, edit `MODEL_NAME` in `config.py`

## Files
| File | Purpose |
|------|---------|
| `eunice.sh` | Unified CLI for setup, launch, test, and backup |
| `main.py` | Entry point (starts FastAPI server) |
| `api/server.py` | FastAPI routes, chat, sessions, facts |
| `core/` | Auth, inference, tool router, onboarding, fact extractor |
| `memory/` | SQLite + ChromaDB memory, trails, user profiles |
| `client.html` | Phone chat interface with voice input |
| `personality.txt` | System prompt / identity |
| `data/eunice_memory.db` | SQLite conversation memory |
| `data/chroma/` | Vector semantic memory |

## Backup
```bash
./eunice.sh backup
```
Backups save to `~/eunice_backups/`.

## Troubleshooting
- **"Ollama is not running"**: Start Terminal 1 first with `ollama serve`.
- **Slow replies**: Switch to `llama3.2:3b` in `config.py`.
- **Phone cannot connect**: Ensure both devices are on the same Wi-Fi. Check firewall with `sudo ufw allow 8000`.
- **"Wrong API key"**: Set the same key in `config.py` (or `EUNICE_API_KEY` env var) and in the client Settings.
- **Cross-device memory**: Currently each device gets its own profile. Copy `eunice_device_id` from browser localStorage to sync, or wait for the upcoming account/pairing layer.
