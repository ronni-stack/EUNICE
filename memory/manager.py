# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE v0.9 — Unified Memory Manager (SQLite + ChromaDB, multi-user) with Validation"""
from typing import Optional
from memory.sqlite_store import SQLiteStore
from memory.vector_store import VectorStore
from core.fact_validator import FactValidator
from core.rbac import require_permission
from core.audit import get_audit_logger

DEFAULT_USER_ID = "ronny"

class MemoryManager:
    """Single interface for all memory operations with fact validation."""

    def __init__(self):
        self.sqlite = SQLiteStore()
        self.vector = VectorStore()
        self.validator = FactValidator()
        self._turn_counter = {}
        self.audit = get_audit_logger()

    def _get_org_id(self, user_id: str) -> str:
        return self.sqlite.get_user_org(user_id) or "default"

    def _require_permission(self, user_id: str, permission: str):
        """Raise PermissionError if the user lacks the requested permission."""
        try:
            require_permission(self.sqlite, user_id, permission)
        except PermissionError as exc:
            self.audit.log_permission_denied(
                user_id=user_id,
                permission=permission,
                resource="memory",
                org_id=self._get_org_id(user_id),
            )
            raise exc

    # --- User profile ---
    def ensure_user(self, user_id: str, name: str = None, org_id: str = "default",
                    department_id: str = "default", role_id: str = "user"):
        return self.sqlite.ensure_user(user_id, name, org_id, department_id, role_id)

    def get_user(self, user_id: str):
        return self.sqlite.get_user(user_id)

    def update_user(self, user_id: str, **fields):
        return self.sqlite.update_user(user_id, **fields)

    def get_user_tone(self, user_id: str) -> dict:
        return self.sqlite.get_user_tone(user_id)

    def update_user_tone(self, user_id: str, **tones):
        return self.sqlite.update_user_tone(user_id, **tones)

    def has_document(self, doc_hash: str, user_id: str = DEFAULT_USER_ID) -> bool:
        self._require_permission(user_id, "documents:read")
        org_id = self._get_org_id(user_id)
        result = self.sqlite.has_document(doc_hash, user_id, org_id)
        self.audit.log_memory_access("read", user_id, org_id, f"document:{doc_hash}", {"exists": result})
        return result

    def add_document_index(self, doc_hash: str, user_id: str, filename: str,
                           content_type: str, chunk_count: int):
        self._require_permission(user_id, "documents:write")
        org_id = self._get_org_id(user_id)
        self.sqlite.add_document_index(doc_hash, user_id, filename, content_type, chunk_count, org_id)
        self.audit.log_memory_access("write", user_id, org_id, f"document:{doc_hash}",
                                      {"filename": filename, "content_type": content_type, "chunk_count": chunk_count})

    def list_documents(self, user_id: str = DEFAULT_USER_ID) -> list:
        self._require_permission(user_id, "documents:read")
        org_id = self._get_org_id(user_id)
        docs = self.sqlite.list_documents(user_id, org_id)
        self.audit.log_memory_access("read", user_id, org_id, "documents", {"count": len(docs)})
        return docs

    def get_research_cache(self, query: str) -> Optional[str]:
        return self.sqlite.get_research_cache(query)

    def set_research_cache(self, query: str, results: str, ttl_hours: int = 24):
        return self.sqlite.set_research_cache(query, results, ttl_hours)

    def is_onboarded(self, user_id: str) -> bool:
        user = self.sqlite.get_user(user_id)
        if not user:
            return False
        return bool(user.get("onboarding_complete"))

    def get_profile_gaps(self, user_id: str):
        return self.sqlite.get_profile_gaps(user_id)

    def update_profile_gap(self, user_id: str, topic: str, **fields):
        return self.sqlite.update_profile_gap(user_id, topic, **fields)

    # --- Episodic (SQLite) ---
    def save_interaction(self, session: str, user_msg: str, assistant_msg: str, tools: list = None,
                         user_id: str = DEFAULT_USER_ID):
        self._require_permission(user_id, "memory:write")
        org_id = self._get_org_id(user_id)
        self.sqlite.save_message("user", user_msg, session, user_id, org_id)
        self.sqlite.save_message("assistant", assistant_msg, session, user_id, org_id)
        self.audit.log_memory_access("write", user_id, org_id, f"session:{session}",
                                      {"user_preview": user_msg[:80], "assistant_preview": assistant_msg[:80]})

    def get_recent_history(self, session: str, n: int = 20, user_id: str = DEFAULT_USER_ID) -> list:
        self._require_permission(user_id, "memory:read")
        org_id = self._get_org_id(user_id)
        history = self.sqlite.get_recent(limit=n, session=session, user_id=user_id, org_id=org_id)
        self.audit.log_memory_access("read", user_id, org_id, f"session:{session}", {"count": len(history), "limit": n})
        return history

    def get_session_history(self, session: str, user_id: str = DEFAULT_USER_ID) -> dict:
        self._require_permission(user_id, "memory:read")
        result = self.sqlite.get_session_history(session, user_id)
        self.audit.log_memory_access("read", user_id, self._get_org_id(user_id), f"session:{session}",
                                      {"messages": len(result.get("messages", []))})
        return result

    def get_all_sessions(self, user_id: str = DEFAULT_USER_ID) -> list:
        self._require_permission(user_id, "memory:read")
        sessions = self.sqlite.get_all_sessions(user_id)
        self.audit.log_memory_access("read", user_id, self._get_org_id(user_id), "sessions", {"count": len(sessions)})
        return sessions

    def delete_session(self, session: str, user_id: str = DEFAULT_USER_ID):
        self._require_permission(user_id, "memory:write")
        self.sqlite.delete_session(session, user_id)
        self.audit.log_memory_access("delete", user_id, self._get_org_id(user_id), f"session:{session}")

    def rename_session(self, session: str, new_name: str, user_id: str = DEFAULT_USER_ID):
        self._require_permission(user_id, "memory:write")
        self.sqlite.rename_session(session, new_name, user_id)
        self.audit.log_memory_access("rename", user_id, self._get_org_id(user_id), f"session:{session}",
                                      {"new_name": new_name})

    def get_facts(self, category: str = None, user_id: str = DEFAULT_USER_ID) -> dict:
        """RBAC-protected wrapper around SQLite get_facts."""
        self._require_permission(user_id, "memory:read")
        org_id = self._get_org_id(user_id)
        facts = self.sqlite.get_facts(category=category, user_id=user_id, org_id=org_id)
        self.audit.log_memory_access("read", user_id, org_id, "facts", {"category": category, "count": len(facts)})
        return facts

    # --- Reasoning (v0.10) ---
    def create_reasoning_run(self, run_id: str, user_id: str, session: str, trail_id: str, goal: str):
        self._require_permission(user_id, "reasoning:run")
        org_id = self._get_org_id(user_id)
        self.sqlite.create_reasoning_run(run_id, user_id, session, trail_id, goal, org_id)
        self.audit.log_reasoning_run(run_id, user_id, goal=goal, status="started", org_id=org_id, session=session)

    def save_reasoning_step(self, run_id: str, step_index: int, thought: str, action: str,
                            action_input: dict, observation: str):
        return self.sqlite.save_reasoning_step(run_id, step_index, thought, action, action_input, observation)

    def finish_reasoning_run(self, run_id: str, status: str, final_answer: str = ""):
        return self.sqlite.finish_reasoning_run(run_id, status, final_answer)

    def get_reasoning_run(self, run_id: str) -> dict:
        return self.sqlite.get_reasoning_run(run_id)

    # --- Semantic (ChromaDB) with Validation ---
    def store_fact(self, fact: str, category: str = "general", source: str = "explicit",
                   user_id: str = DEFAULT_USER_ID) -> bool:
        """
        Store a fact with validation.
        source: 'explicit' (user commanded) or 'extracted' (background extraction)
        """
        self._require_permission(user_id, "memory:write")
        org_id = self._get_org_id(user_id)

        # Generate key from fact
        key = fact.split(":")[0].strip().lower().replace(" ", "_")[:50]
        if not key:
            key = "fact_" + str(hash(fact) & 0xFFFFFFFF)

        # Get existing facts for validation (user/org-scoped)
        existing = self.sqlite.get_facts(user_id=user_id, org_id=org_id)

        # Validate
        should_store, confidence, reason = self.validator.validate_before_storage(key, fact, existing)

        if not should_store:
            print(f"[FACT REJECTED] user={user_id}, org={org_id}, source={source}, key={key}: {reason}")
            return False

        # Store in SQLite with confidence
        self.sqlite.save_fact(key, fact, category, confidence, user_id=user_id, source=source, org_id=org_id)
        self.audit.log_memory_access("write", user_id, org_id, f"fact:{key}",
                                      {"category": category, "source": source, "confidence": confidence})

        # Store in vector DB with user_id and org_id
        self.vector.store_document(
            doc_id=f"fact_{user_id}_{key}_{hash(fact) & 0xFFFF}",
            text=fact,
            metadata={"category": category, "confidence": confidence, "source": source, "user_id": user_id, "org_id": org_id}
        )

        print(f"[FACT STORED] user={user_id}, org={org_id}, source={source}, key={key}, confidence={confidence:.2f}")
        return True

    def store_relationship(self, user_id: str, entity: str, relationship_type: str,
                           entity_type: str = "general", confidence: float = 0.5):
        """Store a relationship in the social graph."""
        self.sqlite.save_relationship(user_id, entity, relationship_type, entity_type, confidence)

    def get_relationships(self, user_id: str, entity: str = None):
        return self.sqlite.get_relationships(user_id, entity)

    def retrieve(self, query: str, user_id: str = DEFAULT_USER_ID, n_results: int = 5) -> str:
        """Retrieve relevant facts and conversation context as natural language."""
        self._require_permission(user_id, "memory:read")
        org_id = self._get_org_id(user_id)

        # Search vector DB scoped by user and org
        facts = self.vector.search_documents(query, n_results=n_results, user_id=user_id, org_id=org_id)
        facts = self.validator.validate_retrieved_facts(facts)

        # Get structured facts from SQLite (user/org-scoped)
        structured = self.sqlite.get_facts(user_id=user_id, org_id=org_id)

        lines = []
        if facts:
            lines.append("Relevant memories:")
            for f in facts:
                lines.append(f"- {f['content']}")

        if structured:
            lines.append("Known facts:")
            for k, v in list(structured.items())[:5]:
                # Format as natural language, not raw key-value
                lines.append(f"- {v}")

        result = "\n".join(lines) if lines else ""
        self.audit.log_memory_access("read", user_id, org_id, "retrieve",
                                      {"query_preview": query[:80], "n_results": n_results,
                                       "facts_found": len(facts), "structured_found": len(structured)})
        return result

    def store_conversation_turn(self, session: str, role: str, content: str, user_id: str = DEFAULT_USER_ID):
        """Store turn in vector DB for long-term semantic recall."""
        self._require_permission(user_id, "memory:write")
        org_id = self._get_org_id(user_id)
        counter_key = f"{user_id}:{session}"
        turn_id = self._turn_counter.get(counter_key, 0)
        self._turn_counter[counter_key] = turn_id + 1
        self.vector.store_conversation_turn(session, role, content, turn_id, user_id=user_id, org_id=org_id)
        self.audit.log_memory_access("write", user_id, org_id, f"conversation_turn:{session}",
                                      {"role": role, "turn_id": turn_id, "content_preview": content[:80]})

    def is_explicit_memory_command(self, text: str) -> bool:
        """Check if user is explicitly asking to store a fact."""
        return self.validator.is_explicit_memory_command(text)
