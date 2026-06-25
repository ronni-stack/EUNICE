# EUNICE

> Your local, private AI with persistent memory, risk-tiered tools, and autonomous user profiling.

EUNICE is a locally-hosted AI assistant that runs entirely on your hardware. It remembers your context across conversations, learns your preferences over time, and can research, code, manage files, and ingest documents — without sending your data to the cloud.

---

## Quick Start

### One-line install

```bash
curl -fsSL https://raw.githubusercontent.com/ronni-stack/EUNICE/main/install.sh | bash
```

### Or manually

```bash
git clone https://github.com/ronni-stack/EUNICE.git ~/EUNICE_MASTER
cd ~/EUNICE_MASTER
pip install -r requirements.txt
./eunice.sh launch
```

Then open `http://<this-machine-ip>:8000` in your browser.

Find your IP with: `hostname -I`

---

## Requirements

| Spec | Minimum | Recommended |
|------|---------|-------------|
| **RAM** | 8 GB | 16 GB |
| **Storage** | 10 GB free | 20 GB free (NVMe) |
| **OS** | Ubuntu 22.04+ / Debian | Any modern Linux |
| **CPU** | Any x86_64 | Intel i7 / AMD Ryzen |
| **GPU** | Optional | NVIDIA with 8GB+ VRAM |

**Note:** EUNICE runs on CPU. A GPU accelerates inference but is not required.

---

## What Makes EUNICE Different

| Feature | EUNICE | ChatGPT / Claude |
|---------|--------|------------------|
| **Data privacy** | 100% local. Your data never leaves your machine. | Cloud-only; data processed externally |
| **Persistent memory** | Associative trails + SQLite + ChromaDB across all sessions | Per-conversation context window |
| **Autonomous profiling** | Learns your name, work, tone, and preferences through chat | No persistent user model |
| **Risk-tiered tools** | Low-risk auto-executes; critical requires confirmation | No local tool execution |
| **Document ingestion** | Upload PDF/TXT/MD; RAG retrieval injected into context | File upload (cloud) |
| **Internet research** | Built-in web search + citation | Built-in |
| **Coding assistant** | Generate, edit, analyze, and run Python locally | Cloud execution |
| **Cross-device identity** | One identity, multiple devices, local pairing | Account-based (cloud) |

---

## Features

### Persistent Associative Memory
EUNICE stores facts, relationships, and conversation trails in SQLite and ChromaDB. It recalls context across sessions without stuffing the entire history into the prompt.

### Autonomous Onboarding
No forms. EUNICE learns your name, work, location, and preferences naturally through conversation.

### Dynamic Tone Adaptation
Tracks four dimensions per identity:
- **Formality** (casual ↔ formal)
- **Verbosity** (terse ↔ detailed)
- **Humor** (dry ↔ playful)
- **Proactivity** (reactive ↔ anticipatory)

### Document Ingestion (RAG)
Upload PDF, TXT, or MD files. EUNICE chunks, embeds, and retrieves relevant excerpts during chat.

```bash
curl -X POST "http://localhost:8000/docs/upload?filename=report.pdf" \
  -H "Authorization: Bearer $API_KEY" \
  -H "X-EUNICE-Device-ID: my-device" \
  --data-binary @report.pdf
```

### Internet Research
Search the web, fetch pages, and summarize with citations.

```bash
curl -X POST http://localhost:8000/research \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "latest Mars rover news", "max_results": 5}'
```

### Coding Assistant
Generate, edit, analyze, and run Python code in a sandboxed workspace.

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

### File Manager
Sandboxed read/write/append/list/delete in `data/files/{identity_id}/`.

### Risk-Tiered Tool Execution
| Tier | Tools | Behavior |
|------|-------|----------|
| **Low** | `network_scan`, `notes`, `get_weather` | Auto-execute |
| **Medium** | `add_event`, `self_update` | Execute + log |
| **High** | `run_code`, `get_balance` | Requires confirmation |
| **Critical** | `transfer_funds`, `delete_file` | Always deny until biometric flow |

### Intent Routing (v0.9.1)
Structured intent classification replaces blunt keyword matching. EUNICE now understands:
- **"Write code that..."** → `generate`
- **"This code is wrong, fix it"** → `fix`
- **"Explain this code"** → `analyze`
- **"Run this code"** → `run`

---

## CLI Commands

EUNICE uses a single unified CLI: `./eunice.sh`.

| Command | Description |
|---------|-------------|
| `./eunice.sh setup` | Install deps, Ollama, Python venv, and models |
| `./eunice.sh launch` | Start the EUNICE server (auto-runs setup if needed) |
| `./eunice.sh test` | Run pytest + smoke tests against a running server |
| `./eunice.sh backup` | Create a timestamped backup of data and code |
| `./eunice.sh help` | Show help |

---

## Architecture

```
EUNICE/
├── eunice.sh           # Unified CLI
├── main.py             # FastAPI entry point
├── config.py           # Central configuration
├── client.html         # PWA frontend
├── manifest.json       # PWA manifest
├── sw.js               # Service worker (offline)
├── personality.txt     # System prompt
├── api/
│   └── server.py       # FastAPI routes, chat, identity, tools
├── core/
│   ├── __init__.py
│   ├── auth.py         # API key + JWT verification
│   ├── identity.py     # Identity & device management
│   ├── inference.py    # Ollama streaming wrapper
│   ├── personality.py  # Prompt management
│   ├── tool_router.py  # Risk-tiered tool execution
│   ├── onboarding.py   # Progressive profiling engine
│   ├── fact_extractor.py # Implicit fact extraction
│   ├── tone.py         # Dynamic tone adaptation
│   ├── ingestion.py    # Document RAG pipeline
│   ├── research.py     # Web search + summarization
│   ├── coder.py        # Code generation & sandbox execution
│   ├── file_manager.py # Sandboxed file operations
│   ├── intent.py       # Structured intent classification
│   └── background_daemon.py # Proactive alerts & maintenance
├── memory/
│   ├── __init__.py
│   ├── manager.py      # Unified memory facade
│   ├── sqlite_store.py # SQLite: messages, sessions, facts, identities
│   ├── vector_store.py # ChromaDB semantic search
│   ├── trail_manager.py # Associative memory trails
│   └── trail_store.py  # Trail persistence
├── tools/              # Executable tool scripts
├── docs/               # Migration guides & architecture docs
└── tests/              # Pytest suite
```

### Data Layout

```
data/
├── eunice_memory.db    # SQLite: users, messages, sessions, facts, identities
├── chroma/             # ChromaDB vector memory
├── files/              # Per-user file workspaces
├── notes/              # Per-user notes
└── eunice.log          # Runtime logs
```

---

## API Endpoints

### Chat
- `POST /chat/stream` — Streaming chat (SSE)
- `POST /chat` — Non-streaming chat

### Identity & Access
- `POST /identity/create` — Create identity + first device
- `POST /identity/claim` — Link device to existing identity
- `POST /identity/switch` — Switch device to another identity
- `POST /identity/logout` — Revoke session token
- `GET /identity/me` — Current identity info
- `GET /devices` — List devices for current identity

### Memory
- `GET /sessions` — List sessions
- `GET /history/{session}` — Get session history
- `DELETE /sessions/{session}` — Delete session
- `GET /facts` — List stored facts
- `DELETE /facts/{key}` — Delete a fact

### Documents & Research
- `POST /docs/upload?filename=...` — Upload PDF/TXT/MD for RAG
- `GET /docs` — List uploaded documents
- `POST /research` — Web search + summarize with citations

### Files
- `GET /files?path=...` — List files in workspace
- `GET /files/read?path=...` — Read a file
- `POST /files/write` — Write or append to a file
- `DELETE /files?path=...` — Delete a file/directory

### Coding
- `POST /coder` — Generate, edit, analyze, or run code

### Other
- `GET /health` — Server status
- `GET /trails`, `GET /trails/{id}` — Associative memory trails
- `GET /daemon/status`, `GET /daemon/alerts` — Background daemon

---

## Configuration

Edit `config.py` or set environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `EUNICE_MODEL` | `phi4-mini:latest` | Ollama model to use |
| `EUNICE_OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `EUNICE_OLLAMA_TIMEOUT` | `300.0` | Request timeout (seconds) |
| `EUNICE_API_KEY` | `eunice-local-dev-key-2026` | Static API key |
| `EUNICE_MEMORY_LIMIT` | `20` | Recent messages to include |

---

## Model Notes

- **Default:** `phi4-mini:latest` (~3.8B params, ~2.5GB, best for 8GB RAM)
- **Alternative:** `llama3.2:3b` (faster, slightly less capable)
- **Premium:** `phi4` (14B, ~10GB, requires 16GB+ RAM)

To switch models, edit `MODEL_NAME` in `config.py` or set `EUNICE_MODEL`.

---

## Logs

```bash
tail -f data/eunice.log
```

Useful grep patterns:
- `[REQUEST]` / `[RESPONSE]` — HTTP traffic
- `[CHAT]` — Chat messages, intents, tool calls
- `[INFERENCE]` / `[OLLAMA]` — Model requests/responses
- `[SERVER ERROR]` / `[STREAM ERROR]` — Errors
- `[INGEST]` — Document ingestion
- `[RESEARCH]` — Web research

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Slow replies** | Switch to `phi4-mini` or `llama3.2:3b` in `config.py`. Reduce `EUNICE_OLLAMA_TIMEOUT`. |
| **Phone cannot connect** | Ensure both devices are on the same Wi-Fi. Run `sudo ufw allow 8000`. |
| **"Wrong API key"** | Set the same key in `config.py` (or `EUNICE_API_KEY` env var) and in the client Settings. |
| **Ollama timeout** | Increase `EUNICE_OLLAMA_TIMEOUT` in `config.py`. First request loads the model into RAM. |
| **Cross-device identity** | Create an identity on one device, then use **Claim Identity** on the other with the same ID + passphrase. |

---

## Roadmap

- [ ] Phase 2 identity hardening: conflict resolution, per-identity tool permissions, guest mode
- [ ] Google OAuth provider (optional cloud identity)
- [ ] Agentic reasoning loop (ReAct) + multi-step planning
- [ ] Calendar / reminders integration
- [ ] Custom LoRA fine-tuning pipeline
- [ ] Docker support
- [ ] Mobile app (iOS/Android)

---

## License

AGPL-3.0. See [LICENSE](LICENSE).

---

## Contributing

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the system design.

Open an issue or PR. EUNICE is built for the community.
