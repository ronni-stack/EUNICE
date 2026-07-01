# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.
"""EUNICE v0.9 — Centralized Configuration (multi-user + identity)"""
import os
import secrets
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
TOOLS_DIR = BASE_DIR / "tools"
BACKUP_DIR = BASE_DIR / "backups"
NOTES_DIR = DATA_DIR / "notes"
FILES_DIR = DATA_DIR / "files"
NOTES_DIR.mkdir(parents=True, exist_ok=True)
FILES_DIR.mkdir(parents=True, exist_ok=True)

# Inference
OLLAMA_URL = os.getenv("EUNICE_OLLAMA_URL", "http://localhost:11434")
LOCALAI_URL = os.getenv("EUNICE_LOCALAI_URL", "http://localhost:8080")
LOCALAI_API_KEY = os.getenv("EUNICE_LOCALAI_API_KEY", "dummy")
#MODEL_NAME = os.getenv("EUNICE_MODEL", "llama3.2:3b")
#MODEL_NAME = os.getenv("EUNICE_MODEL", "phi4")
MODEL_NAME = os.getenv("EUNICE_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT = float(os.getenv("EUNICE_OLLAMA_TIMEOUT", "300.0"))
MEMORY_LIMIT = int(os.getenv("EUNICE_MEMORY_LIMIT", "20"))

# Backend selection: "ollama" or "localai"
INFERENCE_BACKEND = os.getenv("EUNICE_INFERENCE_BACKEND", "ollama")

# Approved models with metadata. Add models here as they become available.
APPROVED_MODELS = {
    "llama3.2:3b": {
        "family": "llama",
        "params": "3b",
        "vram_gb": 4,
        "tiers": ["routing", "light_chat"],
        "context_length": 4096,
    },
    "llama3.1:8b": {
        "family": "llama",
        "params": "8b",
        "vram_gb": 8,
        "tiers": ["chat", "tool_use", "coding"],
        "context_length": 8192,
    },
    "llama3.1:70b": {
        "family": "llama",
        "params": "70b",
        "vram_gb": 48,
        "tiers": ["legal", "finance", "deep_reasoning"],
        "context_length": 8192,
    },
    "qwen2.5:14b": {
        "family": "qwen",
        "params": "14b",
        "vram_gb": 10,
        "tiers": ["chat", "tool_use", "coding", "deep_reasoning"],
        "context_length": 8192,
    },
}

# Map task tiers to ideal models. The router will fall back to whatever is available.
MODEL_TIER_MAP = {
    "routing": "llama3.2:3b",
    "light_chat": "llama3.2:3b",
    "chat": "llama3.1:8b",
    "tool_use": "llama3.1:8b",
    "coding": "qwen2.5:14b",
    "legal": "llama3.1:70b",
    "finance": "llama3.1:70b",
    "deep_reasoning": "llama3.1:70b",
}

# Model governance policy
MODEL_POLICY = {
    "default_model": MODEL_NAME,
    "approved_models_only": True,
    "fallback_on_missing": True,
    "max_context": 4096,
}

# Auth
API_KEY = os.getenv("EUNICE_API_KEY", "eunice-local-dev-key-2026")

# JWT secret: prefer env, then persisted file, then generate once
_JWT_SECRET_FILE = DATA_DIR / ".jwt_secret"
if os.getenv("EUNICE_JWT_SECRET"):
    JWT_SECRET = os.getenv("EUNICE_JWT_SECRET")
elif _JWT_SECRET_FILE.exists():
    JWT_SECRET = _JWT_SECRET_FILE.read_text().strip()
else:
    JWT_SECRET = secrets.token_urlsafe(32)
    _JWT_SECRET_FILE.write_text(JWT_SECRET)

JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.getenv("EUNICE_JWT_EXPIRATION_HOURS", "168"))

# Memory
DB_PATH = DATA_DIR / "eunice_memory.db"
CHROMA_PATH = DATA_DIR / "chroma"
PERSONALITY_PATH = BASE_DIR / "personality.txt"
NOTES_PATH = NOTES_DIR / "{user_id}.md"

def get_notes_path(user_id: str = "ronny") -> Path:
    """Return per-user notes file path."""
    return NOTES_DIR / f"{user_id}.md"

# Embedding (for vector memory)
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Banking
BANKING_PATH = DATA_DIR / "banking.json"
BANK_API_KEY = os.getenv("BANK_API_KEY", "")
BANK_API_URL = os.getenv("BANK_API_URL", "")

# Fine-tuning
LORA_OUTPUT_DIR = BASE_DIR / "eunice_lora_adapter"
TRAINING_DATA_DIR = DATA_DIR / "training"

# Risk Tiers (UPDATED with banking + self-update)
RISK_LOW = {"network_scan", "notes", "get_weather", "get_time", "search_memory"}
RISK_MEDIUM = {"add_event", "send_email_draft", "self_update"}
RISK_HIGH = {"run_code", "get_balance"}
RISK_CRITICAL = {"transfer_funds", "delete_file", "share_data"}

VERSION = "0.10"
