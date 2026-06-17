"""EUNICE v0.9 — Multi-User Identity + Autonomous Discovery
Associative memory, proactive retrieval, background daemon integration, onboarding,
identity/device model, and session-token auth.
"""
import os
import json
import re
import asyncio
import logging
import httpx
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from config import BASE_DIR, DATA_DIR, VERSION, MODEL_NAME, MEMORY_LIMIT
from core.auth import verify_token, get_current_user, get_auth_context, AuthContext
from core.identity import IdentityManager
from core.personality import load_personality, save_personality
from core.inference import stream_chat, generate_non_stream
from core.tool_router import ToolRouter
from core.background_daemon import BackgroundDaemon
from core.onboarding import OnboardingEngine
from core.fact_extractor import FactExtractor
from core.tone import format_tone_instruction
from core.ingestion import IngestionPipeline
from core.research import ResearchAssistant
from memory.manager import MemoryManager
from memory.trail_manager import TrailManager

app = FastAPI(title=f"EUNICE v{VERSION}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = asyncio.get_event_loop().time()
    method = request.method
    path = request.url.path
    user_agent = request.headers.get("user-agent", "-")
    logger.info(f"[REQUEST] {method} {path} UA={user_agent}")
    try:
        response = await call_next(request)
        elapsed = (asyncio.get_event_loop().time() - start) * 1000
        logger.info(f"[RESPONSE] {method} {path} status={response.status_code} time={elapsed:.1f}ms")
        return response
    except Exception as e:
        elapsed = (asyncio.get_event_loop().time() - start) * 1000
        logger.exception(f"[RESPONSE ERROR] {method} {path} time={elapsed:.1f}ms error={e}")
        raise

memory = MemoryManager()
tools = ToolRouter()
trails = TrailManager()
daemon = BackgroundDaemon(check_interval=900)
fact_extractor = FactExtractor(memory)
ingestion = IngestionPipeline(memory)
research = ResearchAssistant(memory)
identity_manager = IdentityManager()
logger = logging.getLogger("eunice.api")

# Start background daemon on startup
@app.on_event("startup")
async def startup():
    # Initialize databases
    from memory.trail_store import TrailStore
    TrailStore()  # Ensures tables exist

    # Start daemon in background
    asyncio.create_task(daemon.start())

    print("╔══════════════════════════════════════════╗")
    print(f"║     EUNICE v{VERSION} Core Online              ║")
    print(f"║     Model: {MODEL_NAME:<22}        ║")
    print(f"║     Memory: SQLite + ChromaDB            ║")
    print(f"║     Trails: ASSOCIATIVE MEMORY           ║")
    print(f"║     Background Daemon: ACTIVE            ║")
    print(f"║     Proactive Retrieval: ENABLED         ║")
    print(f"║     Tool Confirmation: ENABLED           ║")
    print(f"║     Multi-User: ENABLED                  ║")
    print("╚══════════════════════════════════════════╝")
    print(f"Open: http://<this-ip>:8000")


async def _resolve_user_id(request: Request, body: dict = None) -> str:
    """Resolve identity_id from JWT, device header, or JSON body."""
    # 1. Check Authorization header for JWT session token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        identity = identity_manager.verify_session_token(token)
        if identity:
            return identity.identity_id

    # 2. Try device header
    device_id = request.headers.get("X-EUNICE-Device-ID") or request.headers.get("X-EUNICE-User-ID")
    if device_id:
        identity = identity_manager.get_identity_by_device(device_id.strip())
        if identity:
            return identity.identity_id

    # 3. Try provided body or read from request
    try:
        if body is None:
            body = await request.json()
        device_id = body.get("device_id") or body.get("user_id")
        if device_id:
            identity = identity_manager.get_identity_by_device(device_id.strip())
            if identity:
                return identity.identity_id
    except Exception:
        pass

    return "ronny"


def _get_user_name(user_id: str) -> str:
    """Return the user's preferred name or a generic fallback."""
    user = memory.get_user(user_id)
    if user:
        return user.get("preferred_name") or user.get("name") or "the user"
    return "the user"


# --- Dynamic Denial Prompt ---
DENIAL_PROMPT = """You are EUNICE, a personal assistant. The user asked a question about 
something that should be in your shared memory, but you found nothing relevant in the database.

Respond naturally and in character. You may:
- Admit you don't know or don't remember
- Ask the user to tell you (so you can store it)
- Make a dry, self-deprecating observation
- Keep it warm and concise

You must NOT:
- Invent facts about the user
- Guess, assume, or hallucinate memories
- Reference specific details you cannot verify
- Use robotic phrases like "I don't have that in my records"

Keep it under 2 sentences. Speak like a capable colleague who forgot something."""

def is_memory_question(text: str) -> bool:
    text_lower = text.lower().strip()
    patterns = [
        r"what(\'s| is) my (favorite|favourite)",
        r"what did i (say|tell|mention)",
        r"do you remember",
        r"have we (spoken|talked|discussed)",
        r"what do you know about me",
        r"what was my",
        r"did i (say|tell|mention)",
        r"when did i",
        r"where am i from",
        r"what(\'s| is) my",
        r"tell me (about|what) we",
        r"recall our",
        r"what about",
        r"how about",
    ]
    return any(re.search(p, text_lower) for p in patterns)

def _looks_like_document_query(text: str) -> bool:
    """Heuristic: does the query seem to ask about uploaded documents?"""
    lower = text.lower()
    triggers = [
        "document", "pdf", "file", "my notes", "in my", "according to",
        "from the", "the report", "the paper", "the article", "mentions",
        "says that", "stated that", "summarize", "what does it say"
    ]
    return any(t in lower for t in triggers)


def _retrieve_document_context(user_msg: str, user_id: str, max_chunks: int = 3) -> str:
    """Retrieve relevant document chunks and format them for the prompt."""
    chunks = ingestion.retrieve_relevant_chunks(user_msg, user_id, n_results=max_chunks)
    if not chunks:
        return ""
    lines = []
    for i, chunk in enumerate(chunks[:max_chunks], 1):
        source = chunk.get("filename", "document")
        lines.append(f"[Excerpt {i} from {source}]\n{chunk['content']}")
    return "\n\n".join(lines)


def facts_are_relevant(facts_text: str, query: str) -> bool:
    if not facts_text or facts_text.strip() == "":
        return False
    query_lower = query.lower()
    facts_lower = facts_text.lower()
    query_words = set(re.findall(r'\b\w{4,}\b', query_lower))
    facts_words = set(re.findall(r'\b\w{4,}\b', facts_lower))
    overlap = query_words & facts_words

    specific_topics = {
        "sister": ["sister", "sibling", "family"],
        "brother": ["brother", "sibling", "family"],
        "mother": ["mother", "mom", "parent", "family"],
        "father": ["father", "dad", "parent", "family"],
        "car": ["car", "vehicle", "auto", "driving", "tesla"],
        "job": ["job", "work", "career", "employer", "office"],
        "house": ["house", "home", "apartment", "live", "address"],
    }
    for topic, keywords in specific_topics.items():
        if any(k in query_lower for k in keywords):
            if not any(k in facts_lower for k in keywords):
                return False
    return len(overlap) > 0 or len(query_words) == 0

def sanitize_response(text: str) -> str:
    text = re.sub(r"\[Fact updated.*?\]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[Checking database.*?\]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[Retracting.*?\]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[.*?\]\s*", "", text)
    return text.strip()

async def generate_dynamic_denial(user_msg: str) -> str:
    messages = [
        {"role": "system", "content": DENIAL_PROMPT},
        {"role": "user", "content": f'The user asked: "{user_msg}"'}
    ]
    denial = await generate_non_stream(messages=messages)
    denial = sanitize_response(denial)
    if denial and len(denial) > 10:
        return denial
    return "I'm drawing a blank on that one. What am I missing?"

# --- Single System Message Builder with Trail Context ---
def build_system_message(personality: str, intent: str, user_msg: str,
                         facts: dict, trail_context: str = "", tools: list = None,
                         user_name: str = "the user", tone: dict = None,
                         doc_context: str = "") -> str:
    """Build ONE system message with identity, personality, voice, context, and rules."""

    # 1. IDENTITY (always first)
    identity = "You are EUNICE. Your name is EUNICE. You are a personal assistant. You never deny having a name or identity. This is who you are — not information the user provided."

    # 2. TONE ADAPTATION
    if tone:
        parts.append(format_tone_instruction(tone))

    # 3. VOICE EXAMPLES (concrete samples of how EUNICE speaks)
    voice_examples = f"""
How EUNICE speaks:
- "Hey {user_name}. What's up?"
- "You drive a Tesla Model 3. Want me to check if service is due?"
- "I'm drawing a blank on that one. What am I missing?"
- "I can't print photos, but I can find them and make a digital album. Your move."
- "Morning. You have a 9am call and traffic is already garbage. Leave by 8:15?"

How EUNICE does NOT speak:
- "I understand that you're asking about..."
- "Based on the information provided..."
- "It seems like we're starting with..."
- "If there's anything else you'd like to know..."
- "I'm an AI assistant designed to help..."
"""

    parts = [identity, personality, voice_examples]

    # 4. DOCUMENT CONTEXT (RAG)
    if doc_context:
        parts.append("Relevant document excerpts:\n" + doc_context)
        parts.append("Rule for documents: Base your answer on the excerpts above when the question relates to them. Do not invent details not present in the excerpts.")

    # 5. TRAIL CONTEXT
    if trail_context:
        parts.append(trail_context)
        parts.append("Rule for facts: Only use what the user explicitly told you. If they didn't mention something, admit you don't know. Never invent.")

    # 6. RELEVANT FACTS
    if intent == "fact_recall" and facts:
        relevant = []
        query_words = set(user_msg.lower().split())
        for k, v in facts.items():
            fact_words = set(v.lower().split())
            if query_words & fact_words:
                relevant.append(v)
        if relevant:
            parts.append("Known facts:\n" + "\n".join([f"- {f}" for f in relevant[:3]]))

    # 7. TOOLS
    elif intent == "tool_use" and tools:
        tool_text = "Available tools:\n" + "\n".join([f"- {t['name']}: {t['description']}" for t in tools])
        tool_text += "\nTo use a tool, respond with JSON: {\"tool\": \"name\", \"params\": {}}"
        parts.append(tool_text)

    # 8. GENERAL CHAT
    elif intent == "general_chat" and facts:
        recent = list(facts.values())[:2]
        if recent:
            parts.append("Recent context:\n" + "\n".join([f"- {f}" for f in recent]))

    # 9. ANTI-GENERIC RULES
    parts.append("Rule: Never start with 'It seems like...' or 'I understand that...' Just answer directly.")
    parts.append("Rule: Never end with 'If there's anything else...' or 'Feel free to ask!' Just stop when you're done.")
    parts.append(f"Rule: Speak to {user_name} like you've worked together for years. No introductions, no explanations.")
    parts.append("Rule: Keep responses under 3 sentences unless asked for detail.")

    return "\n\n".join(parts)


# --- Static Files ---
@app.get("/", response_class=HTMLResponse)
async def root():
    client_path = BASE_DIR / "client.html"
    if client_path.exists():
        return client_path.read_text(encoding="utf-8")
    return "<h1>EUNICE is running, but client.html is missing.</h1>"

@app.get("/personality")
async def get_personality(token: str = Depends(verify_token)):
    return {"personality": load_personality()}

@app.post("/personality")
async def post_personality(request: Request, token: str = Depends(verify_token)):
    body = await request.json()
    new_personality = body.get("personality", "").strip()
    if not new_personality:
        raise HTTPException(status_code=400, detail="Personality cannot be empty")
    save_personality(new_personality)
    return {"status": "saved", "personality": new_personality}


# --- Identity & Access (v0.9) ---
@app.post("/identity/create")
async def identity_create(request: Request, token: str = Depends(verify_token)):
    body = await request.json()
    display_name = body.get("display_name", "").strip()
    passphrase = body.get("passphrase", "").strip()
    device_id = body.get("device_id", "").strip()
    device_name = body.get("device_name", "").strip() or device_id
    device_type = body.get("device_type", "unknown").strip()

    if not display_name:
        raise HTTPException(status_code=400, detail="display_name is required")
    if not passphrase:
        raise HTTPException(status_code=400, detail="passphrase is required")
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id is required")

    existing_device = identity_manager.get_identity_by_device(device_id)
    if existing_device:
        raise HTTPException(status_code=409, detail="Device already linked to an identity")

    info = identity_manager.create_identity(
        display_name=display_name,
        passphrase=passphrase,
        device_id=device_id,
        device_name=device_name,
        device_type=device_type,
    )
    session_token = identity_manager.create_session_token(info.identity_id, device_id)
    return {
        "identity_id": info.identity_id,
        "device_id": info.device_id,
        "display_name": info.display_name,
        "is_admin": info.is_admin,
        "token": session_token,
    }


@app.post("/identity/claim")
async def identity_claim(request: Request, token: str = Depends(verify_token)):
    body = await request.json()
    identity_id = body.get("identity_id", "").strip()
    passphrase = body.get("passphrase", "").strip()
    device_id = body.get("device_id", "").strip()
    device_name = body.get("device_name", "").strip() or device_id
    device_type = body.get("device_type", "unknown").strip()

    if not identity_id or not passphrase or not device_id:
        raise HTTPException(status_code=400, detail="identity_id, passphrase, and device_id are required")

    info = identity_manager.claim_identity(
        identity_id=identity_id,
        passphrase=passphrase,
        device_id=device_id,
        device_name=device_name,
        device_type=device_type,
    )
    if not info:
        raise HTTPException(status_code=401, detail="Invalid identity or passphrase")

    session_token = identity_manager.create_session_token(info.identity_id, device_id)
    return {
        "identity_id": info.identity_id,
        "device_id": info.device_id,
        "display_name": info.display_name,
        "is_admin": info.is_admin,
        "token": session_token,
    }


@app.post("/identity/switch")
async def identity_switch(request: Request, token: str = Depends(verify_token)):
    body = await request.json()
    device_id = body.get("device_id", "").strip()
    identity_id = body.get("identity_id", "").strip()
    passphrase = body.get("passphrase", "").strip()

    if not device_id or not identity_id or not passphrase:
        raise HTTPException(status_code=400, detail="device_id, identity_id, and passphrase are required")

    info = identity_manager.switch_device_identity(device_id, identity_id, passphrase)
    if not info:
        raise HTTPException(status_code=401, detail="Invalid identity or passphrase")

    session_token = identity_manager.create_session_token(info.identity_id, device_id)
    return {
        "identity_id": info.identity_id,
        "device_id": info.device_id,
        "display_name": info.display_name,
        "is_admin": info.is_admin,
        "token": session_token,
    }


@app.post("/identity/logout")
async def identity_logout(request: Request, auth: AuthContext = Depends(get_auth_context)):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
    if token:
        identity_manager.revoke_session_token(token)
    return {"logged_out": True}


@app.get("/identity/me")
async def identity_me(auth: AuthContext = Depends(get_auth_context)):
    identity = identity_manager.store.get_identity(auth.identity_id)
    return {
        "identity_id": auth.identity_id,
        "device_id": auth.device_id,
        "display_name": auth.display_name,
        "is_admin": auth.is_admin,
        "auth_method": auth.auth_method,
        "profile": identity,
    }


@app.get("/devices")
async def list_devices(auth: AuthContext = Depends(get_auth_context)):
    return {"devices": identity_manager.list_devices(auth.identity_id)}


# --- Onboarding Helper ---
async def _handle_onboarding(user_id: str, user_msg: str, session: str) -> str:
    """Process an onboarding exchange and return the next response."""
    engine = OnboardingEngine(user_id, memory=memory)

    # First message ever
    if engine.is_first_interaction() and not user_msg:
        return engine.get_greeting()

    # Allow explicit memory commands even during onboarding
    user_msg_lower = user_msg.lower()
    if memory.is_explicit_memory_command(user_msg):
        fact_text = user_msg
        for trigger in ["remember that", "remember i", "remember my", "save this", "store this", "note that", "don't forget", "add to my"]:
            if trigger in user_msg_lower:
                parts = user_msg_lower.split(trigger, 1)
                if len(parts) > 1:
                    fact_text = user_msg[len(trigger):].strip()
                break
        if fact_text and fact_text != user_msg:
            memory.sqlite.save_fact("user_stated", fact_text, "explicit", 1.0, user_id=user_id, source="explicit")
            memory.vector.store_document(
                doc_id=f"fact_explicit_{user_id}_{hash(fact_text) & 0xFFFF}",
                text=fact_text,
                metadata={"category": "explicit", "source": "explicit", "user_id": user_id}
            )
            reply = "Got it. I'll remember that. By the way, what should I call you?"
            memory.save_interaction(session, user_msg, reply, user_id=user_id)
            return reply

    # Extract a simple response from user
    probe = engine.process_message(user_msg, "")

    # Build a warm reply
    user_name = _get_user_name(user_id)
    if user_name and user_name != "the user":
        reply = f"Nice to meet you, {user_name}. I'm EUNICE."
    else:
        reply = "Got it. I'm EUNICE, by the way."

    if probe:
        reply += " " + probe
    else:
        reply += " What can I help you with?"

    memory.save_interaction(session, user_msg, reply, user_id=user_id)

    # Mark onboarding complete once we have a name
    if engine._is_name_known():
        memory.update_user(user_id, onboarding_complete=True)

    return reply


# --- Legacy Non-Streaming Chat ---
@app.post("/chat")
async def chat(request: Request, background_tasks: BackgroundTasks, token: str = Depends(verify_token)):
    body = await request.json()
    user_msg = body.get("message", "").strip()
    session = body.get("session", "default").strip()
    user_id = await _resolve_user_id(request, body)

    if not user_msg:
        return {"reply": "[No message received]"}

    # Ensure user exists
    memory.ensure_user(user_id)
    user_name = _get_user_name(user_id)

    # Onboarding: short-circuit if not complete
    if not memory.is_onboarded(user_id):
        reply = await _handle_onboarding(user_id, user_msg, session)
        return {"reply": reply}

    # 1. Explicit confirmation
    confirm_match = re.match(r'^confirm\s+(\w+)', user_msg.lower())
    if confirm_match:
        tool_name = confirm_match.group(1)
        result = await tools.execute(tool_name, {"confirmed": True, "user_id": user_id})
        return {"reply": f"[Executed {tool_name}]: {result}"}

    # 2. Hardcoded intent routing
    user_msg_lower = user_msg.lower()

    if any(word in user_msg_lower for word in ["balance", "account", "how much money", "bank"]):
        result = await tools.execute("get_balance", {"user_id": user_id})
        if result.startswith("[PENDING:"):
            return {"reply": f"I need your approval for that. {result}"}
        try:
            summary = await generate_non_stream(prompt=f"The user asked about their balance. Here's the raw data: {result}. Summarize it briefly.")
            return {"reply": summary or result}
        except Exception:
            return {"reply": result}

    if any(word in user_msg_lower for word in ["scan network", "network scan", "who is on my wifi", "devices on network"]):
        result = await tools.execute("network_scan", {"user_id": user_id})
        if result.startswith("[PENDING:"):
            return {"reply": f"I need your approval for that. {result}"}
        try:
            summary = await generate_non_stream(prompt=f"The user asked to scan the network. Here's the raw result: {result}. Summarize it briefly.")
            return {"reply": summary or result}
        except Exception:
            return {"reply": result}

    if any(word in user_msg_lower for word in ["take a note", "save note", "write down", "remember this", "note that"]):
        content = user_msg
        for trigger in ["take a note", "save note", "write down", "remember this", "note that"]:
            if trigger in user_msg_lower:
                parts = user_msg_lower.split(trigger, 1)
                if len(parts) > 1:
                    content = user_msg[len(trigger):].strip()
                break
        result = await tools.execute("notes", {"action": "append", "content": content, "tag": "note", "user_id": user_id})
        return {"reply": f"Got it. {result}"}

    if any(word in user_msg_lower for word in ["check for updates", "update yourself", "any updates", "new version"]):
        result = await tools.execute("self_update", {"action": "check", "user_id": user_id})
        return {"reply": result}

    if any(word in user_msg_lower for word in ["transfer", "send money", "wire", "pay", "send $"]):
        result = await tools.execute("transfer_funds", {"user_id": user_id})
        return {"reply": result}

    # 3. Explicit memory command
    if memory.is_explicit_memory_command(user_msg):
        fact_text = user_msg
        for trigger in ["remember that", "remember i", "remember my", "save this", "store this", "note that", "don't forget", "add to my"]:
            if trigger in user_msg_lower:
                parts = user_msg_lower.split(trigger, 1)
                if len(parts) > 1:
                    fact_text = user_msg[len(trigger):].strip()
                break
        if fact_text:
            memory.sqlite.save_fact("user_stated", fact_text, "explicit", 1.0, user_id=user_id, source="explicit")
            memory.vector.store_document(
                doc_id=f"fact_explicit_{user_id}_{hash(fact_text) & 0xFFFF}",
                text=fact_text,
                metadata={"category": "explicit", "source": "explicit", "user_id": user_id}
            )
            return {"reply": "Got it. I'll remember that."}
        return {"reply": "I couldn't understand what to remember. Try: Remember that [fact]"}

    # 4. Memory gate (skip if trail context already loaded)
    trail_context = ""
    if is_memory_question(user_msg) and not trail_context:
        facts = memory.retrieve(user_msg, user_id=user_id)
        if not facts or facts.strip() == "" or not facts_are_relevant(facts, user_msg):
            denial = await generate_dynamic_denial(user_msg)
            memory.save_interaction(session, user_msg, denial, [], user_id=user_id)
            return {"reply": denial}
        clean_facts = sanitize_response(facts)
        memory.save_interaction(session, user_msg, clean_facts, [], user_id=user_id)
        return {"reply": clean_facts}

    # 5. === TRAIL DETECTION & ACTIVATION (THE NEW CORE) ===
    trail_id = trails.detect_or_create_trail(user_msg, session, user_id=user_id)
    trails.activate_trail(trail_id, trigger_type="user_mention", user_id=user_id)

    # Get trail context for prompt
    trail_context = trails.get_trail_context_for_prompt(trail_id, user_id=user_id, user_name=user_name, max_nodes=3)

    # Check for proactive nudges from daemon
    nudge = daemon.generate_proactive_nudge(user_msg, user_id=user_id)

    # 6. NORMAL CHAT with trail context
    memory.save_interaction(session, user_msg, "", [], user_id=user_id)
    history = memory.get_recent_history(session, MEMORY_LIMIT, user_id=user_id)
    all_facts = memory.sqlite.get_facts(user_id=user_id)
    available_tools = tools.get_available_tools()

    intent = "general_chat"
    if any(k in user_msg_lower for k in ["what", "remember", "do you know", "tell me about"]):
        intent = "fact_recall"
    elif any(k in user_msg_lower for k in ["scan", "balance", "note", "transfer", "update"]):
        intent = "tool_use"

    personality = load_personality(user_name=user_name)
    tone = memory.get_user_tone(user_id)
    doc_context = _retrieve_document_context(user_msg, user_id) if _looks_like_document_query(user_msg) else ""
    system_content = build_system_message(
        personality, intent, user_msg, all_facts, trail_context, available_tools,
        user_name=user_name, tone=tone, doc_context=doc_context
    )

    messages = [{"role": "system", "content": system_content}]
    for msg in history[-5:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_msg})

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 256}
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post("http://localhost:11434/api/chat", json=payload)
            resp.raise_for_status()
            raw = resp.json()["message"]["content"].strip()
            raw = sanitize_response(raw)

            # Append to trail
            trails.append_to_trail(trail_id, raw, role="assistant", user_id=user_id, source_type="chat")

            # Append nudge if exists
            if nudge:
                raw += f"\n\n{nudge}"

            memory.save_interaction(session, user_msg, raw, [], user_id=user_id)
            background_tasks.add_task(fact_extractor.extract, user_msg, raw, user_id)
            return {"reply": raw}
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.exception(f"[SERVER ERROR] user={user_id} session={session} {error_detail}")
        return {"reply": f"[ERROR: {type(e).__name__}: {str(e)}]"}


# --- Streaming Chat ---
@app.post("/chat/stream")
async def chat_stream(request: Request, background_tasks: BackgroundTasks, token: str = Depends(verify_token)):
    body = await request.json()
    user_msg = body.get("message", "").strip()
    session = body.get("session", "default").strip()
    user_id = await _resolve_user_id(request, body)

    logger.info(f"[CHAT] user={user_id} session={session} msg={user_msg!r}")

    if not user_msg:
        logger.warning("[CHAT] Empty message received")
        return StreamingResponse(
            iter([f'data: {json.dumps({"error": "No message received"})}\n\n']),
            media_type="text/event-stream"
        )

    # Ensure user exists
    memory.ensure_user(user_id)

    # Onboarding: short-circuit if not complete
    if not memory.is_onboarded(user_id):
        logger.info(f"[CHAT] user={user_id} onboarding mode")
        reply = await _handle_onboarding(user_id, user_msg, session)
        logger.info(f"[CHAT] user={user_id} onboarding reply={reply!r}")
        return StreamingResponse(
            iter([
                f'data: {json.dumps({"token": reply, "done": False})}\n\n',
                f'data: {json.dumps({"done": True, "full": reply})}\n\n'
            ]),
            media_type="text/event-stream"
        )

    user_name = _get_user_name(user_id)

    confirm_match = re.match(r'^confirm\s+(\w+)', user_msg.lower())
    if confirm_match:
        tool_name = confirm_match.group(1)
        result = await tools.execute(tool_name, {"confirmed": True, "user_id": user_id})
        response = f"[Executed {tool_name}]: {result}" if not result.startswith("[PENDING:") else result
        return StreamingResponse(
            iter([
                f'data: {json.dumps({"token": response, "done": False})}\n\n',
                f'data: {json.dumps({"done": True, "full": response})}\n\n'
            ]),
            media_type="text/event-stream"
        )

    user_msg_lower = user_msg.lower()

    if any(word in user_msg_lower for word in ["balance", "account", "how much money", "bank"]):
        logger.info(f"[CHAT] user={user_id} intent=tool_balance")
        result = await tools.execute("get_balance", {"user_id": user_id})
        logger.info(f"[CHAT] user={user_id} balance_result={result[:120]!r}")
        if result.startswith("[PENDING:"):
            response = f"I need your approval for that. {result}"
        else:
            try:
                summary = await generate_non_stream(prompt=f"The user asked about their balance. Here's the raw data: {result}. Summarize it briefly and naturally.")
                response = summary or result
            except Exception:
                response = result

        return StreamingResponse(
            iter([
                f'data: {json.dumps({"token": response, "done": False})}\n\n',
                f'data: {json.dumps({"done": True, "full": response})}\n\n'
            ]),
            media_type="text/event-stream"
        )

    if any(word in user_msg_lower for word in ["scan network", "network scan", "who is on my wifi", "devices on network"]):
        result = await tools.execute("network_scan", {"user_id": user_id})
        if result.startswith("[PENDING:"):
            response = f"I need your approval for that. {result}"
        else:
            try:
                summary = await generate_non_stream(prompt=f"The user asked to scan the network. Here's the raw result: {result}. Summarize it briefly.")
                response = summary or result
            except Exception:
                response = result
        return StreamingResponse(
            iter([
                f'data: {json.dumps({"token": response, "done": False})}\n\n',
                f'data: {json.dumps({"done": True, "full": response})}\n\n'
            ]),
            media_type="text/event-stream"
        )

    if any(word in user_msg_lower for word in ["take a note", "save note", "write down", "remember this", "note that"]):
        content = user_msg
        for trigger in ["take a note", "save note", "write down", "remember this", "note that"]:
            if trigger in user_msg_lower:
                parts = user_msg_lower.split(trigger, 1)
                if len(parts) > 1:
                    content = user_msg[len(trigger):].strip()
                break
        result = await tools.execute("notes", {"action": "append", "content": content, "tag": "note", "user_id": user_id})
        response = f"Got it. {result}"
        return StreamingResponse(
            iter([
                f'data: {json.dumps({"token": response, "done": False})}\n\n',
                f'data: {json.dumps({"done": True, "full": response})}\n\n'
            ]),
            media_type="text/event-stream"
        )

    if any(word in user_msg_lower for word in ["check for updates", "update yourself", "any updates", "new version"]):
        result = await tools.execute("self_update", {"action": "check", "user_id": user_id})
        response = result
        return StreamingResponse(
            iter([
                f'data: {json.dumps({"token": response, "done": False})}\n\n',
                f'data: {json.dumps({"done": True, "full": response})}\n\n'
            ]),
            media_type="text/event-stream"
        )

    if any(word in user_msg_lower for word in ["transfer", "send money", "wire", "pay", "send $"]):
        result = await tools.execute("transfer_funds", {"user_id": user_id})
        response = result
        return StreamingResponse(
            iter([
                f'data: {json.dumps({"token": response, "done": False})}\n\n',
                f'data: {json.dumps({"done": True, "full": response})}\n\n'
            ]),
            media_type="text/event-stream"
        )

    if memory.is_explicit_memory_command(user_msg):
        fact_text = user_msg
        for trigger in ["remember that", "remember i", "remember my", "save this", "store this", "note that", "don't forget", "add to my"]:
            if trigger in user_msg_lower:
                parts = user_msg_lower.split(trigger, 1)
                if len(parts) > 1:
                    fact_text = user_msg[len(trigger):].strip()
                break
        if fact_text:
            memory.sqlite.save_fact("user_stated", fact_text, "explicit", 1.0, user_id=user_id, source="explicit")
            memory.vector.store_document(
                doc_id=f"fact_explicit_{user_id}_{hash(fact_text) & 0xFFFF}",
                text=fact_text,
                metadata={"category": "explicit", "source": "explicit", "user_id": user_id}
            )
            response = "Got it. I'll remember that."
        else:
            response = "I couldn't understand what to remember. Try: Remember that [fact]"
        return StreamingResponse(
            iter([
                f'data: {json.dumps({"token": response, "done": False})}\n\n',
                f'data: {json.dumps({"done": True, "full": response})}\n\n'
            ]),
            media_type="text/event-stream"
        )

    if is_memory_question(user_msg):
        logger.info(f"[CHAT] user={user_id} intent=memory_question")
        facts = memory.retrieve(user_msg, user_id=user_id)
        logger.debug(f"[CHAT] user={user_id} retrieved_facts={facts[:200]!r}")
        if not facts or facts.strip() == "" or not facts_are_relevant(facts, user_msg):
            denial = await generate_dynamic_denial(user_msg)
            logger.info(f"[CHAT] user={user_id} memory_denial={denial!r}")
            memory.save_interaction(session, user_msg, denial, [], user_id=user_id)
            memory.store_conversation_turn(session, "user", user_msg, user_id=user_id)
            memory.store_conversation_turn(session, "assistant", denial, user_id=user_id)
            return StreamingResponse(
                iter([
                    f'data: {json.dumps({"token": denial, "done": False})}\n\n',
                    f'data: {json.dumps({"done": True, "full": denial})}\n\n'
                ]),
                media_type="text/event-stream"
            )
        clean_facts = sanitize_response(facts)
        memory.save_interaction(session, user_msg, clean_facts, [], user_id=user_id)
        memory.store_conversation_turn(session, "user", user_msg, user_id=user_id)
        memory.store_conversation_turn(session, "assistant", clean_facts, user_id=user_id)
        return StreamingResponse(
            iter([
                f'data: {json.dumps({"token": clean_facts, "done": False})}\n\n',
                f'data: {json.dumps({"done": True, "full": clean_facts})}\n\n'
            ]),
            media_type="text/event-stream"
        )

    # === TRAIL DETECTION & ACTIVATION ===
    trail_id = trails.detect_or_create_trail(user_msg, session, user_id=user_id)
    trails.activate_trail(trail_id, trigger_type="user_mention", user_id=user_id)
    trail_context = trails.get_trail_context_for_prompt(trail_id, user_id=user_id, user_name=user_name, max_nodes=3)
    nudge = daemon.generate_proactive_nudge(user_msg, user_id=user_id)

    intent = "general_chat"
    if any(k in user_msg_lower for k in ["what", "remember", "do you know", "tell me about"]):
        intent = "fact_recall"
    elif any(k in user_msg_lower for k in ["scan", "balance", "note", "transfer", "update"]):
        intent = "tool_use"

    logger.info(f"[CHAT] user={user_id} intent={intent} trail={trail_id}")

    memory.save_interaction(session, user_msg, "", [], user_id=user_id)
    history = memory.get_recent_history(session, MEMORY_LIMIT, user_id=user_id)
    all_facts = memory.sqlite.get_facts(user_id=user_id)
    available_tools = tools.get_available_tools()

    personality = load_personality(user_name=user_name)
    tone = memory.get_user_tone(user_id)
    doc_context = _retrieve_document_context(user_msg, user_id) if _looks_like_document_query(user_msg) else ""
    system_content = build_system_message(
        personality, intent, user_msg, all_facts, trail_context, available_tools,
        user_name=user_name, tone=tone, doc_context=doc_context
    )

    messages = [{"role": "system", "content": system_content}]
    for msg in history[-5:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_msg})

    logger.debug(f"[CHAT] user={user_id} system_prompt_len={len(system_content)} history_len={len(history)}")

    async def event_generator():
        full_reply = ""
        tool_name = None
        tool_params = {}

        try:
            logger.info(f"[INFERENCE] user={user_id} sending {len(messages)} messages to model={MODEL_NAME}")
            async for chunk in stream_chat(messages, available_tools):
                data = json.loads(chunk)
                if "error" in data:
                    logger.error(f"[INFERENCE] user={user_id} stream_error={data}")
                    yield f'data: {json.dumps(data)}\n\n'
                    return
                if "tool_call" in data:
                    tool_name = data["tool"]
                    tool_params = data.get("params", {})
                    logger.info(f"[CHAT] user={user_id} llm_tool_call={tool_name} params={tool_params}")
                    yield f'data: {json.dumps({"token": f"\n[Using tool: {tool_name}...]\n"})}\n\n'
                    continue
                if "token" in data:
                    full_reply += data["token"]
                    yield f'data: {json.dumps(data)}\n\n'
                if data.get("done"):
                    break

            if tool_name:
                tool_params["user_id"] = user_id
                tool_result = await tools.execute(tool_name, tool_params)
                logger.info(f"[CHAT] user={user_id} tool={tool_name} result={tool_result[:120]!r}")
                if tool_result.startswith("[PENDING:"):
                    full_reply = f"I need your approval for that. Say 'confirm {tool_name}' to proceed."
                    yield f'data: {json.dumps({"token": full_reply})}\n\n'
                else:
                    yield f'data: {json.dumps({"token": f"[Result: {tool_result}]\n"})}\n\n'
                    followup_messages = messages + [
                        {"role": "assistant", "content": f"Used {tool_name}: {tool_result}"},
                        {"role": "user", "content": "Summarize that briefly."}
                    ]
                    followup = ""
                    async for chunk in stream_chat(followup_messages, []):
                        data = json.loads(chunk)
                        if "token" in data:
                            followup += data["token"]
                            yield f'data: {json.dumps(data)}\n\n'
                        if data.get("done"):
                            break
                    full_reply = followup

            full_reply = sanitize_response(full_reply)
            logger.info(f"[CHAT] user={user_id} final_reply={full_reply[:200]!r}")

            # Append to trail
            trails.append_to_trail(trail_id, full_reply, role="assistant", user_id=user_id, source_type="chat")

            # Append nudge if exists
            if nudge:
                full_reply += f"\n\n{nudge}"

            memory.save_interaction(session, user_msg, full_reply, [], user_id=user_id)
            memory.store_conversation_turn(session, "user", user_msg, user_id=user_id)
            memory.store_conversation_turn(session, "assistant", full_reply, user_id=user_id)
            yield f'data: {json.dumps({"done": True, "full": full_reply})}\n\n'

            background_tasks.add_task(fact_extractor.extract, user_msg, full_reply, user_id)
            logger.info(f"[LEARN] user={user_id} queued background fact extraction")

        except Exception as e:
            error_msg = str(e) or f"Stream crashed: {type(e).__name__}"
            logger.exception(f"[STREAM ERROR] user={user_id} {error_msg}")
            yield f'data: {json.dumps({"error": f"Stream failed: {error_msg}"})}\n\n'

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- Background Daemon Endpoints ---
@app.get("/daemon/status")
async def daemon_status(token: str = Depends(verify_token)):
    return daemon.get_daemon_status()

@app.get("/daemon/alerts")
async def daemon_alerts(token: str = Depends(verify_token)):
    return {"alerts": daemon.get_all_alerts()}

@app.delete("/daemon/alerts/{trail_id}")
async def clear_alert(trail_id: str, token: str = Depends(verify_token)):
    daemon.clear_alert(trail_id)
    return {"cleared": True}

@app.get("/trails")
async def list_trails(request: Request, token: str = Depends(verify_token)):
    user_id = await _resolve_user_id(request)
    active = trails.get_active_trails(user_id=user_id)
    dormant = trails.get_dormant_trails(user_id=user_id)
    return {
        "active": [{"id": t['id'], "name": t['name'], "last_accessed": t['last_accessed']} for t in active],
        "dormant": [{"id": t['id'], "name": t['name'], "deadline": t.get('deadline')} for t in dormant]
    }

@app.get("/trails/{trail_id}")
async def get_trail(trail_id: str, request: Request, token: str = Depends(verify_token)):
    user_id = await _resolve_user_id(request)
    trail = trails.store.get_trail(trail_id, user_id=user_id)
    if not trail:
        raise HTTPException(status_code=404, detail="Trail not found")
    nodes = trails.follow_trail(trail_id, n=10, user_id=user_id)
    user_name = _get_user_name(user_id)
    return {
        "trail": trail,
        "nodes": nodes,
        "context": trails.get_trail_context_for_prompt(trail_id, user_id=user_id, user_name=user_name, max_nodes=5)
    }

@app.post("/trails/{trail_id}/deadline")
async def set_trail_deadline(trail_id: str, request: Request, token: str = Depends(verify_token)):
    user_id = await _resolve_user_id(request)
    body = await request.json()
    deadline = body.get("deadline")
    if not deadline:
        raise HTTPException(status_code=400, detail="deadline required")
    trails.store.update_trail_deadline(trail_id, deadline, user_id=user_id)
    return {"trail_id": trail_id, "deadline": deadline}

@app.post("/trails/{trail_id}/status")
async def set_trail_status(trail_id: str, request: Request, token: str = Depends(verify_token)):
    user_id = await _resolve_user_id(request)
    body = await request.json()
    status = body.get("status")
    if status not in ["active", "dormant", "archived"]:
        raise HTTPException(status_code=400, detail="status must be active, dormant, or archived")
    trails.store.set_trail_status(trail_id, status, user_id=user_id)
    return {"trail_id": trail_id, "status": status}


# --- Document Ingestion ---
@app.post("/docs/upload")
async def upload_document(
    request: Request,
    filename: str,
    token: str = Depends(verify_token)
):
    """Upload a PDF, TXT, or MD document for RAG retrieval."""
    user_id = await _resolve_user_id(request)
    body = await request.body()

    if not body:
        raise HTTPException(status_code=400, detail="Empty file body")

    allowed_extensions = {".pdf", ".txt", ".md"}
    ext = Path(filename).suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Allowed: {allowed_extensions}"
        )

    try:
        result = await ingestion.ingest(filename, body, user_id)
        logger.info(f"[INGEST] user={user_id} filename={filename} result={result['status']} chunks={result.get('chunks', 0)}")
        return result
    except Exception as e:
        logger.exception(f"[INGEST ERROR] user={user_id} filename={filename} error={e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")


@app.get("/docs")
async def list_documents(request: Request, token: str = Depends(verify_token)):
    """List uploaded documents for the current user."""
    user_id = await _resolve_user_id(request)
    return {"documents": memory.list_documents(user_id)}


@app.post("/research")
async def research_endpoint(request: Request, token: str = Depends(verify_token)):
    """Research a query on the web and return a summarized answer with sources."""
    body = await request.json()
    query = body.get("query", "").strip()
    max_results = min(int(body.get("max_results", 5)), 10)
    fetch_full = bool(body.get("fetch_full", True))

    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    try:
        result = await research.research(query, max_results=max_results, fetch_full=fetch_full)
        return result
    except Exception as e:
        logger.exception(f"[RESEARCH ERROR] query={query!r} error={e}")
        raise HTTPException(status_code=500, detail=f"Research failed: {e}")


# --- File Manager ---
@app.get("/files")
async def list_files(request: Request, path: str = "", token: str = Depends(verify_token)):
    """List files in the user's sandboxed workspace."""
    from core.file_manager import FileManager
    user_id = await _resolve_user_id(request)
    try:
        fm = FileManager(user_id)
        return {"entries": fm.list(path)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/files/read")
async def read_file(request: Request, path: str, token: str = Depends(verify_token)):
    """Read a file from the user's sandboxed workspace."""
    from core.file_manager import FileManager
    user_id = await _resolve_user_id(request)
    try:
        fm = FileManager(user_id)
        return {"content": fm.read(path)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/files/write")
async def write_file(request: Request, token: str = Depends(verify_token)):
    """Write or append to a file in the user's sandboxed workspace."""
    from core.file_manager import FileManager
    user_id = await _resolve_user_id(request)
    body = await request.json()
    path = body.get("path", "")
    content = body.get("content", "")
    mode = body.get("mode", "write")  # write | append

    try:
        fm = FileManager(user_id)
        result = fm.write(path, content, mode=mode)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/files")
async def delete_file(request: Request, path: str, token: str = Depends(verify_token)):
    """Delete a file or directory in the user's sandboxed workspace."""
    from core.file_manager import FileManager
    user_id = await _resolve_user_id(request)
    try:
        fm = FileManager(user_id)
        return fm.delete(path, confirmed=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Health & Sessions ---
@app.get("/health")
async def health():
    vector_stats = memory.vector.get_stats() if hasattr(memory, 'vector') else {"status": "unknown"}
    daemon_stat = daemon.get_daemon_status()
    return {
        "status": "awake",
        "version": VERSION,
        "model": MODEL_NAME,
        "facts_stored": len(memory.sqlite.get_facts(user_id="ronny")),
        "semantic_memory": vector_stats,
        "trails": {
            "active": len(trails.get_active_trails(user_id="ronny")),
            "dormant": len(trails.get_dormant_trails(user_id="ronny"))
        },
        "daemon": daemon_stat,
        "tools_available": [t["name"] for t in tools.get_available_tools()]
    }

@app.get("/sessions")
async def list_sessions(request: Request, token: str = Depends(verify_token)):
    user_id = await _resolve_user_id(request)
    return {"sessions": memory.get_all_sessions(user_id=user_id)}

@app.get("/history/{session}")
async def get_history(session: str, request: Request, token: str = Depends(verify_token)):
    user_id = await _resolve_user_id(request)
    return memory.get_session_history(session, user_id=user_id)

@app.delete("/sessions/{session}")
async def delete_session(session: str, request: Request, token: str = Depends(verify_token)):
    user_id = await _resolve_user_id(request)
    memory.delete_session(session, user_id=user_id)
    return {"deleted": True}

@app.get("/facts")
async def list_facts(request: Request, category: str = None, token: str = Depends(verify_token)):
    user_id = await _resolve_user_id(request)
    return {"facts": memory.sqlite.get_facts(category, user_id=user_id)}

@app.delete("/facts/{key}")
async def delete_fact(key: str, request: Request, token: str = Depends(verify_token)):
    user_id = await _resolve_user_id(request)
    deleted = memory.sqlite.delete_fact(key, user_id=user_id)
    return {"deleted": deleted}


# --- Background Fact Extraction (GATED) ---
async def extract_facts_background(user_msg: str, assistant_reply: str, user_id: str = "ronny"):
    """Legacy background extraction wrapper. New code uses FactExtractor directly."""
    await fact_extractor.extract(user_msg, assistant_reply, user_id)
