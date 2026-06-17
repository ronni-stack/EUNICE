| Word              | Current reality                                                                               | Gap                                                                                      |
| ----------------- | --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| **Efficient**     | Runs locally on 3B–4B models (Llama 3.2 / Phi4), no cloud latency.                            | Not yet optimized for speed or resource footprint; no quantization or caching layers.    |
| **Unified**       | Single stack (FastAPI + SQLite + ChromaDB), one CLI entry point, unified memory + tool layer. | Cross-device identity is missing, so it's *not* unified across a user's devices.         |
| **Neural**        | Yes — local LLM via Ollama.                                                                   | Still a thin wrapper around the model; no custom fine-tuning or agentic reasoning loops. |
| **Intelligence**  | Has memory, profiling, and tool selection.                                                    | No dynamic tone adaptation, no document ingestion, no multi-step planning.               |
| **Communication** | Natural chat, onboarding, recall.                                                             | Only text; no voice, no multi-modal.                                                     |
| **Execution**     | Risk-tiered tool execution with confirmation gates.                                           | Limited tool set; no autonomous background execution across users.     
                  |
---

## Phase 1: Foundation (Cross-Device Identity + Document Ingestion)

These two change your data model and storage patterns. Do them first or everything else gets retrofitted badly.

### 1. Cross-Device Identity
**The problem:** A user on laptop + phone = two rows in `users`.  
**The fix:** Decouple *identity* from *device/session*.

**Architecture:**
```
users
  └── identity_id (UUID, the real "person")
  └── device_fingerprint (hash of device + optional name)
  └── paired_devices[] (list of identity_ids that are linked)
```

**Pairing flow (no central server, local-network only):**
1. Device A generates a 6-word pairing code (e.g., `apple-battery-west-lobby-zebra-02`) + a temporary ECDH public key.
2. Device B enters the code. Both resolve via mDNS or a short-lived UDP broadcast on LAN.
3. They exchange public keys, establish a shared secret, and sync their `identity_id` + encrypted user profile.
4. SQLite on both devices now use the same `identity_id`. Messages/sessions are tagged with `device_id` for provenance but queried by `identity_id`.

**Why this works for EUNICE:** You don't need a cloud auth server. Pairing is one-time and LAN-based. For remote sync later, you can layer WebDAV or Syncthing on top.

**Files to touch:**
- `memory/sqlite_store.py` — add `devices` table, migrate `users` to have `identity_id`
- `api/server.py` — add `/pair/init` and `/pair/confirm` endpoints
- `core/sync.py` — new module for conflict resolution (last-write-wins for profile, append-only for messages)

---

### 2. Document Ingestion (RAG Pipeline)
**Stack:** You already have ChromaDB and sentence-transformers. Don't add LangChain; keep it thin.

**Pipeline:**
```
Upload (PDF/TXT/MD) 
  → Extract text (pymupdf / markdown-it)
  → Chunk by semantic boundaries (paragraph > 512 tokens, overlap 64)
  → Embed via existing sentence-transformer
  → Store in ChromaDB with metadata: {source, user_id, chunk_index, doc_hash}
  → Index doc_hash in SQLite to prevent re-ingestion
```

**Retrieval hook:**
In `core/inference.py`, before calling Ollama:
1. Check if the user query looks like it needs documents (simple heuristic: "in my notes", "the pdf", or always retrieve top-3).
2. Query ChromaDB with `where={"user_id": identity_id}`.
3. Inject top-k chunks into the system prompt context window.

**Files to touch:**
- `core/ingestion.py` — new
- `api/server.py` — add `/docs/upload` endpoint
- `core/inference.py` — add retrieval context injection

---

## Phase 2: Intelligence (Agent Reasoning + Multi-Step Planning)

Now that identity and memory are solid, upgrade the brain.

### 3. Agentic Reasoning Loop (ReAct + Reflection)
**Current state:** Single-shot prompt to Ollama.  
**Target:** A loop that thinks, acts, observes, and reflects.

**Loop structure in `core/agent.py`:**
```python
class AgentLoop:
    def run(self, user_input, context):
        for step in range(max_steps):
            # 1. Reason: LLM generates thought + next action
            thought = self.llm.generate(prompt=build_react_prompt(history, tools))
            
            # 2. Act: Parse action (tool call or final_answer)
            action = parse_action(thought)
            
            if action.type == "final_answer":
                return action.content
            
            # 3. Observe: Execute tool, get result
            observation = self.tool_registry.execute(action)
            
            # 4. Reflect: Brief LLM call to summarize if observation was useful
            reflection = self.llm.generate(f"Was this useful? {observation}")
            
            history.append({"thought": thought, "action": action, "observation": observation, "reflection": reflection})
```

**Key insight for 3B models:** Don't ask the model to output raw JSON. Use a strict, few-shot prompt with delimiters:
```
Thought: I need to check the user's calendar.
Action: tool_check_calendar
Input: {"date": "today"}
Observation: [result goes here]
```

**Files to touch:**
- `core/agent.py` — new
- `core/inference.py` — refactor to use `AgentLoop` instead of direct Ollama call

---

### 4. Multi-Step Planning
This sits *above* the ReAct loop. If the user asks something complex ("Plan a trip to Tokyo within my budget and block my calendar"), the planner breaks it into sub-tasks.

**Implementation:**
- A lightweight `Planner` class in `core/planner.py`.
- First LLM call is *planning-only*: outputs a list of steps in strict markdown.
- Then the AgentLoop executes each step sequentially.
- If a step fails, the planner can replan.

**Prompt template:**
```
You are a planner. Break the following request into steps.
Each step must use one tool or provide a direct answer.
Request: {user_input}
Available tools: {tool_list}
Output format:
1. [TOOL: check_balance] Verify budget
2. [TOOL: search_calendar] Find free dates
3. [TOOL: create_event] Block calendar
```

---

## Phase 3: Personality (Dynamic Tone Adaptation)

This builds on your existing `profile_gaps` and `facts` tables.

### 5. Dynamic Tone Adaptation
**Current state:** Static system prompt.  
**Target:** System prompt is assembled dynamically from user profile.

**Tone vector:** Extract a 4-dimensional tone profile from user facts over time:
- Formality (casual ↔ formal)
- Verbosity (terse ↔ detailed)
- Humor (dry ↔ playful)
- Proactivity (reactive ↔ anticipatory)

**How to build it:**
1. In `core/fact_extractor.py`, add tone-specific extraction rules. e.g., if user says "just give me the short version", boost `terse`.
2. Store tone scores in `users` table as JSON.
3. In `core/inference.py`, assemble the system prompt:
```python
tone = get_user_tone(user_id)
system = f"""You are EUNICE. 
Tone: {tone.formality}, {tone.verbosity}, {tone.humor}, {tone.proactivity}.
User context: {profile_summary}
"""
```

**The magic:** This costs zero extra inference. It's just prompt engineering against data you already collect.

---

## Phase 4: Model (Custom Fine-Tuning)

This is the heaviest lift. Do it last, when the data pipeline is producing clean training data.

### 6. Custom Fine-Tuning (LoRA on Phi4/Llama 3.2 3B)
**Why:** A 3B model with LoRA can learn EUNICE's specific tone, tool formats, and user context better than prompt engineering alone.

**Data pipeline:**
1. Export high-quality conversations from SQLite where:
   - User gave positive feedback (or no correction)
   - Tool execution succeeded
   - Multi-turn coherence was good
2. Format as instruction-following JSON:
```json
{"system": "...", "conversations": [{"from": "human", "value": "..."}, {"from": "gpt", "value": "..."}]}
```

**Training:**
- Use `unsloth` or `axolotl` for QLoRA (fits on 8GB VRAM or even CPU with `bitsandbytes`).
- Train adapters for:
  - Tool calling format (so the model stops hallucinating JSON)
  - Tone matching
  - User-specific memory recall patterns

**Integration:**
- Ollama supports LoRA adapters via `MODFILE` or you can merge the adapter into the base model and create a custom Ollama model: `ollama create eunice-phi4-lora -f Modelfile`.

**Files to touch:**
- `scripts/export_training_data.py` — new
- `training/` — new directory for configs
- `eunice.sh` — add `train` command

---

## Suggested Execution Order

| Phase | Feature | Why this order |
|-------|---------|--------------|
| 1 | Cross-device identity | Foundation for "Unified" |
| 1 | Document ingestion | High impact, clear scope |
| 2 | Agent reasoning loop | Unlocks multi-step planning |
| 2 | Multi-step planning | Depends on agent loop |
| 3 | Dynamic tone adaptation | Easy win, builds on profiling |
| 4 | Custom fine-tuning | Needs clean data from 1-3 |

---

in addition, I want the base architecture of eunice to have the following abilities: 
1. coding, dynamic, efficient, any language, just like you, kimi
2. Research/access the internet, filter results, analyse, give feedback etc,
3. file handling, locally and online
4. calendar, reminders, auto cron jobs, based on memory.

from here we can add more tools.