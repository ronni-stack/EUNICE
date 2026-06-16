"""EUNICE v0.8 — Memory Tests (multi-user)"""
import pytest
import memory.sqlite_store
import memory.vector_store
import memory.trail_store
from memory.manager import MemoryManager

@pytest.fixture
def mm(tmp_path):
    # Patch module-level paths so each test gets an isolated DB.
    # These are imported at module load time, so updating config.* alone is not enough.
    db_path = tmp_path / "test.db"
    chroma_path = tmp_path / "chroma"
    memory.sqlite_store.DB_PATH = db_path
    memory.vector_store.CHROMA_PATH = chroma_path
    memory.trail_store.DB_PATH = db_path
    return MemoryManager()


def test_store_and_retrieve_fact(mm):
    user_id = "test_user_1"
    mm.ensure_user(user_id)
    mm.store_fact("Prefers tea over coffee.", "preferences", user_id=user_id)
    result = mm.retrieve("what do they drink", user_id=user_id)
    assert "tea" in result.lower() or "coffee" in result.lower()


def test_session_history(mm):
    user_id = "test_user_2"
    mm.save_interaction("sess-1", "Hello", "Hi there", [], user_id=user_id)
    history = mm.get_recent_history("sess-1", n=2, user_id=user_id)
    assert len(history) == 2
    assert history[0]["role"] == "user"


def test_user_isolation(mm):
    user_a = "user_a"
    user_b = "user_b"
    mm.ensure_user(user_a)
    mm.ensure_user(user_b)

    mm.store_fact("Lives in Nairobi.", "location", user_id=user_a)
    mm.store_fact("Lives in Berlin.", "location", user_id=user_b)

    facts_a = mm.sqlite.get_facts(category="location", user_id=user_a)
    facts_b = mm.sqlite.get_facts(category="location", user_id=user_b)

    assert any("Nairobi" in v for v in facts_a.values())
    assert any("Berlin" in v for v in facts_b.values())
    assert not any("Berlin" in v for v in facts_a.values())
    assert not any("Nairobi" in v for v in facts_b.values())


def test_profile_gaps_initialized(mm):
    user_id = "new_user"
    mm.ensure_user(user_id)
    gaps = mm.get_profile_gaps(user_id)
    topics = {g["topic"] for g in gaps}
    assert "name" in topics
    assert "work" in topics


def test_relationship_storage(mm):
    user_id = "user_rel"
    mm.ensure_user(user_id)
    mm.store_relationship(user_id, "Claire", "sister", entity_type="person", confidence=0.8)
    rels = mm.get_relationships(user_id, entity="Claire")
    assert len(rels) >= 1
    assert any(r["relationship_type"] == "sister" for r in rels)
