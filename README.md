# EUNICE v0.9 — Personal AI Assistant (Multi-User Identity + Autonomous Discovery)

EUNICE is a locally-hosted AI assistant with persistent associative memory, risk-tiered tool execution, autonomous user profiling, document understanding, internet research, and coding assistance.

## What's New in v0.9

- **Identity & device model**: People and devices are separate. One identity can be used on multiple devices; one device can switch between identities.
- **Session-token auth**: Log in with a passphrase to get a JWT session token, or continue using the static API key.
- **Dynamic tone adaptation**: EUNICE learns and mirrors your formality, verbosity, humor, and proactivity over time.
- **Document ingestion (RAG)**: Upload PDF, TXT, or MD files; EUNICE retrieves relevant excerpts during chat.
- **Internet research**: Ask EUNICE to search the web, fetch pages, and summarize with citations.
- **File manager**: Sandboxed read/write/append/list/delete for files in your per-user workspace.
- **Coding assistant**: Generate, edit, analyze, and run Python code in a sandboxed workspace.
- **Multi-user foundation**: Each device/browser gets an isolated user profile by default.
- **Autonomous onboarding**: EUNICE learns your name, work, location, and preferences through natural chat.
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

### 2. Start EUNICE Server

```bash
cd ~/EUNICE_MASTER
./eunice.sh launch
```

This automatically starts Ollama if it isn't already running, then launches the FastAPI server.
If `venv/` is missing, `launch` will run `setup` first.

### 3. Open the Client

On your phone or laptop browser:

```
http://<this-machine-ip>:8000
```

Find the IP by running `hostname -I` on the server machine.

The first time you open the client, you'll see a login screen:

- **Create Identity** — set a display name + passphrase for a new profile.
- **Claim Identity** — enter an existing identity ID + passphrase to link another device.

The static API key (set in `config.py` or `EUNICE_API_KEY`) still works for backward compatibility.

## CLI Commands

| Command | Description |
|---|---|
| `./eunice.sh setup` | Install dependencies, Ollama, models, and create venv |
| `./eunice.sh launch` | Start the EUNICE server (auto-runs setup if needed) |
| `./eunice.sh test` | Run pytest + smoke tests against a running server |
| `./eunice.sh backup` | Create a timestamped backup of data and code |
| `./eunice.sh help` | Show help |

Legacy scripts (`launch.sh`, `setup.sh`, `test_eunice_full.sh`, `backup.sh`) still work as wrappers around `./eunice.sh`.

## API Endpoints

### Chat
- `POST /chat/stream` — main streaming chat endpoint
- `POST /chat` — non-streaming chat

### Identity & Access
- `POST /identity/create` — create a new identity + first device
- `POST /identity/claim` — link a new device to an existing identity
- `POST /identity/switch` — switch a device to a different identity
- `POST /identity/logout` — revoke session token
- `GET /identity/me` — current identity info
- `GET /devices` — list devices for current identity

### Memory
- `GET /sessions`
- `GET /history/{session}`
- `DELETE /sessions/{session}`
- `GET /facts`
- `DELETE /facts/{key}`

### Documents & Research
- `POST /docs/upload?filename=...` — upload PDF/TXT/MD for RAG
- `GET /docs` — list uploaded documents
- `POST /research` — web search + summarize with citations

### Files
- `GET /files?path=...` — list files in user workspace
- `GET /files/read?path=...` — read a file
- `POST /files/write` — write or append to a file
- `DELETE /files?path=...` — delete a file/directory

### Coding
- `POST /coder` — generate, edit, analyze, or run code

### Other
- `GET /health` — server status
- `GET /trails`, `GET /trails/{id}` — associative memory trails
- `GET /daemon/status`, `GET /daemon/alerts` — background daemon

## Model Notes

- Default: `phi4` (4B params, ~2.3GB download, best quality for 8GB)
- Fallback: `llama3.2:3b` (faster, slightly less eloquent)
- To switch models, edit `MODEL_NAME` in `config.py`

## Capabilities

### Dynamic Tone Adaptation
EUNICE tracks four tone dimensions per identity:
- **Formality** (casual ↔ formal)
- **Verbosity** (terse ↔ detailed)
- **Humor** (dry ↔ playful)
- **Proactivity** (reactive ↔ anticipatory)

Tone is updated incrementally from your messages. No UI needed — it just works.

### Document Ingestion (RAG)
Upload documents and ask questions about them:

```bash
curl -X POST "http://localhost:8000/docs/upload?filename=report.pdf" \
  -H "Authorization: Bearer $API_KEY" \
  -H "X-EUNICE-Device-ID: my-device" \
  --data-binary @report.pdf
```

Then chat: *"What does the report say about revenue?"*

### Internet Research
```bash
curl -X POST http://localhost:8000/research \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "latest Mars rover news", "max_results": 5}'
```

Returns a summarized answer with `[Source N]` citations and source URLs.

### File Manager
Files are sandboxed to `data/files/{identity_id}/`. Supported operations via tool or API: read, write, append, list, mkdir, delete, search.

### Coding Assistant
Generate or edit code, then run it in a sandboxed subprocess:

```bash
curl -X POST http://localhost:8000/coder \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "generate",
    "request": "write a function that returns fibonacci numbers",
    "filename": "fib.py",
    "language": "python"
  }'
```

Then run it:

```bash
curl -X POST http://localhost:8000/coder \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"action": "run", "filename": "fib.py"}'
```

Dangerous patterns (network, shell, eval) are blocked before execution.

## Files

| File | Purpose |
|------|---------|
| `eunice.sh` | Unified CLI for setup, launch, test, and backup |
| `main.py` | Entry point (starts FastAPI server) |
| `api/server.py` | FastAPI routes, chat, identity, tools, files, coder, research |
| `core/` | Auth, inference, tool router, onboarding, fact extractor, tone, ingestion, research, coder |
| `memory/` | SQLite + ChromaDB memory, trails, user profiles, documents, research cache |
| `tools/` | Executable tool scripts (notes, balance, file_manager, coder, etc.) |
| `client.html` | Phone/chat interface with identity login |
| `personality.txt` | System prompt / identity |
| `data/eunice_memory.db` | SQLite conversation memory |
| `data/chroma/` | Vector semantic memory |
| `data/files/` | Per-user file workspace |
| `data/eunice.log` | Runtime logs |

## Data Layout

```
data/
├── eunice_memory.db      # SQLite: users, messages, sessions, facts, identities, devices, documents
├── chroma/               # ChromaDB vector memory
├── files/                # Per-user file workspaces
├── notes/                # Per-user notes
└── eunice.log            # Runtime logs
```

## Backup

```bash
./eunice.sh backup
```

Backups save to `~/eunice_backups/`.

## Logs

Runtime logs are written to `data/eunice.log` and printed to stdout:

```bash
tail -f data/eunice.log
```

Useful grep patterns:
- `[REQUEST]` / `[RESPONSE]` — all HTTP traffic
- `[CHAT]` — chat messages, intents, tool calls
- `[INFERENCE]` / `[OLLAMA]` — model requests and responses
- `[SERVER ERROR]` / `[STREAM ERROR]` — errors
- `[INGEST]` — document ingestion
- `[RESEARCH]` — web research

## Troubleshooting

- **Slow replies**: Switch to `llama3.2:3b` in `config.py`.
- **Phone cannot connect**: Ensure both devices are on the same Wi-Fi. Check firewall with `sudo ufw allow 8000`.
- **"Wrong API key"**: Set the same key in `config.py` (or `EUNICE_API_KEY` env var) and in the client Settings.
- **Cross-device identity**: Use the login screen to create an identity on one device, then use **Claim Identity** on the other device with the same identity ID + passphrase.

## Roadmap

- Phase 2 identity hardening: conflict resolution, per-identity tool permissions, guest mode.
- Google OAuth provider (optional cloud identity).
- Agentic reasoning loop (ReAct) + multi-step planning.
- Calendar/reminders integration.
- Custom LoRA fine-tuning.
