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

## Quick Start

### Terminal 1 — Start the Brain (Ollama)
```bash
ollama serve
```

### Terminal 2 — Start EUNICE Server
```bash
cd ~/EUNICE_MASTER
source venv/bin/activate
python main.py
```

### Phone Access
Open your phone browser and type:
```
http://<old-laptop-ip>:8000
```
Find the IP by running `hostname -I` on the old laptop.

The PWA will generate a stable `device_id` and send it with every request so EUNICE can keep your profile separate from other users.

## Model Notes
- Default: `phi4` (4B params, ~2.3GB download, best quality for 8GB)
- Fallback: `llama3.2:3b` (faster, slightly less eloquent)
- To switch models, edit `MODEL_NAME` in `config.py`

## Files
| File | Purpose |
|------|---------|
| `main.py` | Entry point (starts FastAPI server) |
| `api/server.py` | FastAPI routes, chat, sessions, facts |
| `core/` | Auth, inference, tool router, onboarding, fact extractor |
| `memory/` | SQLite + ChromaDB memory, trails, user profiles |
| `client.html` | Phone chat interface with voice input |
| `personality.txt` | System prompt / identity |
| `data/eunice_memory.db` | SQLite conversation memory |
| `data/chroma/` | Vector semantic memory |
| `backup.sh` | One-click backup script |

## Backup
```bash
./backup.sh
```
Backups save to `~/eunice_backups/` (or as configured in `backup.sh`).

## Troubleshooting
- **"Ollama is not running"**: Start Terminal 1 first.
- **Slow replies**: Switch to `llama3.2:3b` in `config.py`.
- **Phone cannot connect**: Ensure both devices are on the same Wi-Fi. Check firewall with `sudo ufw allow 8000`.
- **"Wrong API key"**: Set the same key in `config.py` (or `EUNICE_API_KEY` env var) and in the client Settings.
