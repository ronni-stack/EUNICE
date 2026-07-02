# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE v0.8 — ChromaDB Semantic Memory (multi-user)
Fixes: Embedding model download failures, silent crashes, empty collections, user scoping.
"""
import chromadb
import warnings
import os
from typing import Optional
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from config import CHROMA_PATH, EMBEDDING_MODEL
from core.crypto import encrypt_optional, decrypt_optional

DEFAULT_USER_ID = "ronny"

class VectorStore:
    """Vector-based semantic search over conversations and documents, scoped by user_id."""

    def __init__(self):
        os.makedirs(CHROMA_PATH, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        self.embed_fn = None
        self.conversations = None
        self.documents = None
        self._key_resolver = None
        self._init_embeddings()

    def set_key_resolver(self, resolver):
        """Inject a callback(org_id) -> Optional[bytes] for per-org encryption keys."""
        self._key_resolver = resolver

    def _get_org_key(self, org_id: str) -> Optional[bytes]:
        if self._key_resolver is None:
            return None
        try:
            return self._key_resolver(org_id)
        except Exception:
            return None

    def _init_embeddings(self):
        """Initialize embedding function with fallback handling."""
        try:
            print(f"[VECTOR] Loading embedding model: {EMBEDDING_MODEL}...")
            self.embed_fn = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
            print(f"[VECTOR] ✓ Embedding model loaded successfully")

            self.conversations = self.client.get_or_create_collection(
                name="conversations", embedding_function=self.embed_fn
            )
            self.documents = self.client.get_or_create_collection(
                name="documents", embedding_function=self.embed_fn
            )

            # Verify collections are working
            test_count = self.conversations.count()
            print(f"[VECTOR] ✓ Collections ready. Existing conversation memories: {test_count}")

        except Exception as e:
            warnings.warn(f"[VECTOR] ⚠ Failed to load embeddings: {e}")
            print(f"[VECTOR] ⚠ Semantic memory DISABLED. Run: python scripts/download_embeddings.py")
            self.embed_fn = None
            self.conversations = None
            self.documents = None

    def store_conversation_turn(self, session_id: str, role: str, content: str, turn_id: int,
                                user_id: str = DEFAULT_USER_ID, org_id: str = "default"):
        """Store a conversation turn for semantic retrieval."""
        if not self.conversations:
            print(f"[VECTOR] ⚠ Skip: embeddings not available")
            return False

        try:
            doc_id = f"{user_id}_{session_id}_{turn_id}"
            self.conversations.add(
                documents=[content],
                metadatas=[{"user_id": user_id, "org_id": org_id, "session": session_id, "role": role}],
                ids=[doc_id]
            )
            return True
        except Exception as e:
            print(f"[VECTOR] ⚠ Failed to store turn: {e}")
            return False

    def store_document(self, doc_id: str, text: str, metadata: dict = None):
        """Store external documents (PDFs, notes, facts, etc.)."""
        if not self.documents:
            return False
        try:
            metadata = metadata or {}
            if "user_id" not in metadata:
                metadata["user_id"] = DEFAULT_USER_ID
            org_id = metadata.get("org_id", "default")
            key = self._get_org_key(org_id)
            stored_text = encrypt_optional(text, key)
            self.documents.add(
                documents=[stored_text],
                metadatas=[metadata],
                ids=[doc_id]
            )
            return True
        except Exception as e:
            print(f"[VECTOR] ⚠ Failed to store document: {e}")
            return False

    def search_conversations(self, query: str, n_results: int = 5, user_id: str = DEFAULT_USER_ID) -> list:
        """Find relevant past conversation turns for this user."""
        if not self.conversations:
            return []
        try:
            results = self.conversations.query(
                query_texts=[query],
                n_results=n_results,
                where={"user_id": user_id}
            )
            docs = results["documents"][0] if results["documents"] else []
            metas = results["metadatas"][0] if results["metadatas"] else []
            distances = results["distances"][0] if results["distances"] else []
            return [
                {"content": d, "meta": m, "distance": dist}
                for d, m, dist in zip(docs, metas, distances)
            ]
        except Exception as e:
            print(f"[VECTOR] ⚠ Search failed: {e}")
            return []

    def search_documents(self, query: str, n_results: int = 5, user_id: str = DEFAULT_USER_ID,
                         org_id: str = "default") -> list:
        """Find relevant documents for this user within their org."""
        if not self.documents:
            return []
        try:
            results = self.documents.query(
                query_texts=[query],
                n_results=n_results,
                where={"$and": [{"user_id": user_id}, {"org_id": org_id}]}
            )
            docs = results["documents"][0] if results["documents"] else []
            metas = results["metadatas"][0] if results["metadatas"] else []
            key = self._get_org_key(org_id)
            return [{"content": decrypt_optional(d, key), "meta": m} for d, m in zip(docs, metas)]
        except Exception as e:
            print(f"[VECTOR] ⚠ Document search failed: {e}")
            return []

    def get_stats(self) -> dict:
        """Return collection statistics."""
        if not self.conversations:
            return {"status": "disabled", "conversations": 0, "documents": 0}
        return {
            "status": "active",
            "conversations": self.conversations.count(),
            "documents": self.documents.count() if self.documents else 0
        }
