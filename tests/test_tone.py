"""EUNICE v0.9 — Dynamic Tone Adaptation Tests"""
import pytest
import memory.sqlite_store
import config as config_module
from core.tone import analyze_message, tone_label, format_tone_instruction
from memory.manager import MemoryManager

config_module.JWT_SECRET = "test-secret-32-bytes-long-1234567890"


@pytest.fixture
def mm(tmp_path):
    db_path = tmp_path / "test_tone.db"
    chroma_path = tmp_path / "chroma"
    memory.sqlite_store.DB_PATH = db_path
    memory.vector_store.CHROMA_PATH = chroma_path
    return MemoryManager()


def test_casual_message_decreases_formality():
    deltas = analyze_message("hey dude, sup? lol")
    assert deltas["tone_formality"] < 0


def test_formal_message_increases_formality():
    deltas = analyze_message("Could you please assist me with this matter? Thank you kindly.")
    assert deltas["tone_formality"] > 0


def test_short_message_decreases_verbosity():
    deltas = analyze_message("just the short version")
    assert deltas["tone_verbosity"] < 0


def test_long_message_increases_verbosity():
    deltas = analyze_message("Please explain this in great detail and walk me through every step thoroughly.")
    assert deltas["tone_verbosity"] > 0


def test_humor_signals():
    deltas = analyze_message("that's hilarious haha")
    assert deltas["tone_humor"] > 0


def test_proactivity_signals():
    deltas = analyze_message("remind me to call mom and schedule a meeting")
    assert deltas["tone_proactivity"] > 0


def test_tone_label_ranges():
    assert tone_label(0.1) == "low"
    assert tone_label(0.5) == "medium"
    assert tone_label(0.9) == "high"


def test_format_tone_instruction_contains_labels():
    tone = {"formality": 0.2, "verbosity": 0.8, "humor": 0.5, "proactivity": 0.3}
    instruction = format_tone_instruction(tone)
    assert "casual" in instruction.lower() or "low" in instruction.lower()
    assert "detailed" in instruction.lower() or "high" in instruction.lower()


def test_user_tone_stored_and_updated(mm):
    user_id = "tone_user"
    mm.ensure_user(user_id)
    tone = mm.get_user_tone(user_id)
    assert tone["formality"] == 0.5

    mm.update_user_tone(user_id, tone_formality=0.7, tone_verbosity=0.3)
    tone = mm.get_user_tone(user_id)
    assert tone["formality"] == 0.7
    assert tone["verbosity"] == 0.3


def test_user_tone_clamped(mm):
    user_id = "tone_user2"
    mm.ensure_user(user_id)
    mm.update_user_tone(user_id, tone_formality=1.5, tone_humor=-0.2)
    tone = mm.get_user_tone(user_id)
    assert tone["formality"] == 1.0
    assert tone["humor"] == 0.0
