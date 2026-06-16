"""EUNICE v0.8 — Centralized Configuration (multi-user)"""
import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data"
TOOLS_DIR = BASE_DIR / "tools"
BACKUP_DIR = BASE_DIR / "backups"
NOTES_DIR = DATA_DIR / "notes"
NOTES_DIR.mkdir(parents=True, exist_ok=True)

# Inference
OLLAMA_URL = os.getenv("EUNICE_OLLAMA_URL", "http://localhost:11434")
#MODEL_NAME = os.getenv("EUNICE_MODEL", "llama3.2:3b")
MODEL_NAME = os.getenv("EUNICE_MODEL", "phi4")
MEMORY_LIMIT = int(os.getenv("EUNICE_MEMORY_LIMIT", "20"))

# Auth
API_KEY = os.getenv("EUNICE_API_KEY", "eunice-local-dev-key-2026")

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

VERSION = "0.8"
