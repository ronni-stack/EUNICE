# EUNICE Migration Guides

## v0.7 → v0.8: Multi-User + Autonomous Discovery

### What Changed
- The assistant is no longer hardcoded to a single user ("Ronny"). It now supports isolated user profiles via `device_id`.
- New database tables: `users`, `profile_gaps`, `relationships`.
- Existing tables (`messages`, `sessions`, `facts`, `trails`, `trail_nodes`, `trail_entities`) now have a `user_id` column.
- Old data without a `user_id` is automatically assigned to `user_id = "ronny"` so existing conversations keep working.
- New onboarding engine asks for your name naturally on first use.
- New background fact extractor learns facts and relationships from every exchange.
- Personality prompt is now generic and onboarding-aware.

### Migration Steps
1. **Backup** (already done by the v0.8 startup migration):
   ```bash
   cp data/eunice_memory.db data/eunice_memory_v7_backup_$(date +%Y%m%d_%H%M%S).db
   cp -r data/chroma data/chroma_v7_backup_$(date +%Y%m%d_%H%M%S)
   ```

2. **Start the server**:
   ```bash
   source venv/bin/activate
   python main.py
   ```
   The schema migration runs automatically on startup.

3. **Verify old data**:
   - Visit `http://localhost:8000/health` — version should be `0.8`.
   - Send a message without a `device_id` — your existing v0.7 history and facts should still be available under the default `ronny` user.

4. **Test a new user**:
   - Open the PWA in a new browser/incognito window.
   - The client generates a new `device_id`.
   - EUNICE should greet you and ask your name.

### Files Added/Changed in v0.8
- `core/onboarding.py` — autonomous onboarding engine
- `core/fact_extractor.py` — implicit fact/relationship extraction
- `memory/sqlite_store.py` — multi-user schema + migration
- `memory/trail_store.py` — user-scoped trails
- `memory/vector_store.py` — user-scoped ChromaDB
- `memory/manager.py` — user-aware memory facade
- `memory/trail_manager.py` — user-aware trail logic
- `core/auth.py` — device/user identity resolution
- `api/server.py` — onboarding integration, user scoping
- `client.html` — sends `X-EUNICE-Device-ID` header
- `config.py` — per-user notes path, version bump
- `personality.txt` / `prompts/system_prompt.txt` — generic prompt

---

## v0.6 Migration Guide (legacy)

This scaffold upgrades your working v0.5 monolith into a modular v0.6 architecture.
Your existing `client.html`, `personality.txt`, `data/eunice_memory.db`, and `tools/` are preserved.

### Files Added (v0.6)
```
config.py                    ← Central configuration
main.py                      ← New entry point

core/
  auth.py                    ← API key verification
  personality.py             ← Prompt management with date injection
  inference.py               ← Ollama streaming wrapper
  tool_router.py             ← Risk-tiered tool execution

memory/
  sqlite_store.py            ← Your existing DB, refactored
  vector_store.py            ← NEW: ChromaDB semantic search
  manager.py                 ← Unified interface

api/
  server.py                  ← FastAPI routes (API-compatible with client.html)

scripts/
  train_lora.py              ← Fine-tuning pipeline

data/
  chroma/                    ← NEW: Vector DB storage
  training/                  ← NEW: Fine-tuning datasets

tests/
  test_memory.py             ← Unit tests
```

### Migration Steps (v0.6)

#### 1. Backup
```bash
cp -r ~/EUNICE_MASTER ~/EUNICE_MASTER_backup_$(date +%Y%m%d)
```

#### 2. Clean redundant files
```bash
cd ~/EUNICE_MASTER
rm -f client_v04.html client_v05.html client_v05_fixed.html
rm -f eunice_core_v04.py eunice_core_v05.py
rm -f eunice_starter_kit.zip
```

#### 3. Extract this scaffold into your directory
```bash
# Copy all new files into EUNICE_MASTER
cp -r eunice_evolution_scaffold/* ~/EUNICE_MASTER/
```

#### 4. Install new dependencies
```bash
cd ~/EUNICE_MASTER
source venv/bin/activate
pip install chromadb sentence-transformers unsloth peft transformers datasets accelerate
```

#### 5. Initialize vector memory
```bash
python -c "from memory.manager import MemoryManager; m = MemoryManager(); m.store_fact('EUNICE v0.6 migration complete.', 'system')"
```

#### 6. Test the new server
```bash
python main.py
```
Open `http://<your-ip>:8000` in your phone browser. The PWA should work identically.

#### 7. Verify your old data is intact
- Conversations: Check `/history/default` — your old messages should appear.
- Facts: Check `/facts` — your old structured facts should appear.

#### 8. (Optional) Start fine-tuning dataset
Edit `data/training/eunice_dataset.jsonl` with real conversation examples, then run:
```bash
python scripts/train_lora.py
```

### API Compatibility (v0.6)
All endpoints from v0.5 are preserved:
- `GET /` → Serves client.html
- `GET /health` → Status check
- `GET /personality` / `POST /personality` → Prompt management
- `POST /chat` → Legacy non-streaming
- `POST /chat/stream` → Streaming (your client.html uses this)
- `GET /sessions` / `GET /history/{session}` / `DELETE /sessions/{session}`
- `GET /facts` / `DELETE /facts/{key}`

### Risk Tiers (v0.6)
Tools are now classified:
- **Low**: `network_scan`, `notes`, `get_weather` → Auto-execute
- **Medium**: `add_event` → Execute + log
- **High**: `run_code`, `get_balance` → Require confirmation (dev mode auto-approves)
- **Critical**: `transfer_funds` → Always deny until biometric flow built

Add future banking tools to `core/tool_router.py`.

### Troubleshooting
- **"Module not found"**: Ensure you are in the venv and ran `pip install -r requirements.txt`
- **"ChromaDB lock"**: Kill any lingering Python processes, then retry.
- **Client shows offline**: Check that Ollama is running (`ollama serve`) and `main.py` is on port 8000.
