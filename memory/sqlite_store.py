# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE v0.9 — SQLite Episodic Memory (multi-user + identity)"""
import sqlite3
import json
from datetime import datetime
from typing import Optional
from config import DB_PATH

DEFAULT_USER_ID = "ronny"

class SQLiteStore:
    """Manages conversation history, structured facts, and user profiles in SQLite."""

    def __init__(self):
        self.db_path = DB_PATH
        self._init_db()

    def _column_exists(self, conn, table: str, column: str) -> bool:
        c = conn.cursor()
        c.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in c.fetchall())

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()

            # Users table
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    preferred_name TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_active TEXT DEFAULT CURRENT_TIMESTAMP,
                    rapport_level REAL DEFAULT 0,
                    communication_style TEXT,
                    onboarding_complete BOOLEAN DEFAULT FALSE,
                    tone_formality REAL DEFAULT 0.5,
                    tone_verbosity REAL DEFAULT 0.5,
                    tone_humor REAL DEFAULT 0.5,
                    tone_proactivity REAL DEFAULT 0.5
                )
            """)

            # Migrate tone columns if missing
            for col in ["tone_formality", "tone_verbosity", "tone_humor", "tone_proactivity"]:
                if not self._column_exists(conn, "users", col):
                    c.execute(f"ALTER TABLE users ADD COLUMN {col} REAL DEFAULT 0.5")

            # Profile gaps table
            c.execute("""
                CREATE TABLE IF NOT EXISTS profile_gaps (
                    user_id TEXT,
                    topic TEXT,
                    known BOOLEAN DEFAULT FALSE,
                    priority REAL,
                    confidence REAL DEFAULT 0,
                    last_probed TEXT,
                    probe_count INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, topic),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            # Relationships table (social graph)
            c.execute("""
                CREATE TABLE IF NOT EXISTS relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    entity TEXT,
                    entity_type TEXT DEFAULT 'general',
                    relationship_type TEXT,
                    confidence REAL DEFAULT 0.5,
                    first_mentioned TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            # Messages table
            c.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT DEFAULT 'ronny',
                    session TEXT DEFAULT 'default',
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            if not self._column_exists(conn, "messages", "user_id"):
                c.execute("ALTER TABLE messages ADD COLUMN user_id TEXT DEFAULT 'ronny'")

            # Sessions table (migrate to composite PK on user_id + id)
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
            sessions_exists = c.fetchone()
            if sessions_exists:
                # Legacy table exists: create new, migrate, drop old, rename
                c.execute("""
                    CREATE TABLE IF NOT EXISTS sessions_new (
                        user_id TEXT DEFAULT 'ronny',
                        id TEXT DEFAULT 'default',
                        title TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        last_active TEXT DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, id)
                    )
                """)
                if not self._column_exists(conn, "sessions", "user_id"):
                    c.execute("""
                        INSERT OR IGNORE INTO sessions_new (user_id, id, title, created_at, last_active)
                        SELECT 'ronny', id, title, created_at, last_active FROM sessions
                    """)
                else:
                    c.execute("""
                        INSERT OR IGNORE INTO sessions_new (user_id, id, title, created_at, last_active)
                        SELECT user_id, id, title, created_at, last_active FROM sessions
                    """)
                c.execute("DROP TABLE sessions")
                c.execute("ALTER TABLE sessions_new RENAME TO sessions")
            else:
                # Fresh DB: create final table directly
                c.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        user_id TEXT DEFAULT 'ronny',
                        id TEXT DEFAULT 'default',
                        title TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        last_active TEXT DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, id)
                    )
                """)

            # Facts table: migrate to (user_id, key) uniqueness
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='facts'")
            facts_exists = c.fetchone()
            if facts_exists:
                c.execute("""
                    CREATE TABLE IF NOT EXISTS facts_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT DEFAULT 'ronny',
                        key TEXT NOT NULL,
                        value TEXT,
                        category TEXT DEFAULT 'general',
                        confidence REAL DEFAULT 1.0,
                        source TEXT DEFAULT 'explicit',
                        reinforcement_count INTEGER DEFAULT 1,
                        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, key)
                    )
                """)
                if not self._column_exists(conn, "facts", "user_id"):
                    c.execute("""
                        INSERT OR IGNORE INTO facts_new (user_id, key, value, category, confidence, source, reinforcement_count, timestamp)
                        SELECT 'ronny', key, value, category, confidence, 'explicit', 1, timestamp FROM facts
                    """)
                else:
                    c.execute("""
                        INSERT OR IGNORE INTO facts_new (user_id, key, value, category, confidence, source, reinforcement_count, timestamp)
                        SELECT user_id, key, value, category, confidence, 'explicit', 1, timestamp FROM facts
                    """)
                c.execute("DROP TABLE facts")
                c.execute("ALTER TABLE facts_new RENAME TO facts")
            else:
                c.execute("""
                    CREATE TABLE IF NOT EXISTS facts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT DEFAULT 'ronny',
                        key TEXT NOT NULL,
                        value TEXT,
                        category TEXT DEFAULT 'general',
                        confidence REAL DEFAULT 1.0,
                        source TEXT DEFAULT 'explicit',
                        reinforcement_count INTEGER DEFAULT 1,
                        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, key)
                    )
                """)

            # --- Research cache (v0.9) ---
            c.execute("""
                CREATE TABLE IF NOT EXISTS research_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    results TEXT,
                    expires_at TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(query)
                )
            """)

            # --- Documents index (v0.9) ---
            c.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_hash TEXT UNIQUE,
                    user_id TEXT,
                    filename TEXT,
                    content_type TEXT,
                    chunk_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

            # --- Identity & device tables (v0.9) ---
            c.execute("""
                CREATE TABLE IF NOT EXISTS identities (
                    id TEXT PRIMARY KEY,
                    provider TEXT DEFAULT 'local',
                    provider_user_id TEXT UNIQUE,
                    display_name TEXT,
                    email TEXT,
                    avatar_url TEXT,
                    passphrase_hash TEXT,
                    is_admin BOOLEAN DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id TEXT PRIMARY KEY,
                    identity_id TEXT NOT NULL,
                    name TEXT,
                    device_type TEXT,
                    trusted BOOLEAN DEFAULT 1,
                    last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_ip TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (identity_id) REFERENCES identities(id) ON DELETE CASCADE
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS identity_tokens (
                    jti TEXT PRIMARY KEY,
                    identity_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked BOOLEAN DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (identity_id) REFERENCES identities(id) ON DELETE CASCADE
                )
            """)

            # --- Reasoning runs & steps (v0.10) ---
            c.execute("""
                CREATE TABLE IF NOT EXISTS reasoning_runs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    session TEXT,
                    trail_id TEXT,
                    goal TEXT,
                    status TEXT DEFAULT 'running',
                    final_answer TEXT,
                    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS reasoning_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    step_index INTEGER,
                    thought TEXT,
                    action TEXT,
                    action_input TEXT,
                    observation TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES reasoning_runs(id) ON DELETE CASCADE
                )
            """)

            # Migration: existing users rows represent both identity and device in v0.8
            c.execute("SELECT COUNT(*) FROM identities")
            if c.fetchone()[0] == 0:
                c.execute("SELECT id, name, created_at, last_active FROM users")
                for row in c.fetchall():
                    user_id, name, created_at, last_active = row
                    display_name = name or user_id
                    c.execute("""
                        INSERT OR IGNORE INTO identities (id, display_name, created_at, updated_at)
                        VALUES (?, ?, ?, ?)
                    """, (user_id, display_name, created_at, last_active))
                    c.execute("""
                        INSERT OR IGNORE INTO devices (id, identity_id, name, device_type, trusted, created_at, last_seen)
                        VALUES (?, ?, ?, ?, 1, ?, ?)
                    """, (user_id, user_id, display_name, "unknown", created_at, last_active))

            conn.commit()

    # --- Identities & Devices (v0.9) ---
    def create_identity(self, identity_id: str, display_name: str, passphrase_hash: str,
                        is_admin: bool = False, created_at: str = None, updated_at: str = None):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO identities (id, display_name, passphrase_hash, is_admin, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (identity_id, display_name, passphrase_hash, int(is_admin), created_at, updated_at))
            conn.commit()

    def get_identity(self, identity_id: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM identities WHERE id = ?", (identity_id,))
            row = c.fetchone()
            return self._row_to_dict(c, row) if row else None

    def update_identity(self, identity_id: str, **fields):
        allowed = {"display_name", "email", "avatar_url", "passphrase_hash", "is_admin", "updated_at"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            c.execute(f"UPDATE identities SET {set_clause} WHERE id = ?", (*updates.values(), identity_id))
            conn.commit()

    def create_device(self, device_id: str, identity_id: str, name: str = None,
                      device_type: str = "unknown", trusted: bool = True,
                      created_at: str = None, last_seen: str = None, last_ip: str = None):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO devices (id, identity_id, name, device_type, trusted, created_at, last_seen, last_ip)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (device_id, identity_id, name, device_type, int(trusted), created_at, last_seen, last_ip))
            conn.commit()

    def get_device(self, device_id: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM devices WHERE id = ?", (device_id,))
            row = c.fetchone()
            return self._row_to_dict(c, row) if row else None

    def update_device(self, device_id: str, **fields):
        allowed = {"name", "device_type", "trusted", "last_seen", "last_ip"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            c.execute(f"UPDATE devices SET {set_clause} WHERE id = ?", (*updates.values(), device_id))
            conn.commit()

    def list_devices(self, identity_id: str) -> list:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM devices WHERE identity_id = ? ORDER BY last_seen DESC", (identity_id,))
            return [self._row_to_dict(c, r) for r in c.fetchall()]

    def create_token(self, jti: str, identity_id: str, device_id: str, expires_at: str, created_at: str = None):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO identity_tokens (jti, identity_id, device_id, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (jti, identity_id, device_id, expires_at, created_at))
            conn.commit()

    def revoke_token(self, jti: str):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("UPDATE identity_tokens SET revoked = 1 WHERE jti = ?", (jti,))
            conn.commit()

    def is_token_revoked(self, jti: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT revoked FROM identity_tokens WHERE jti = ?", (jti,))
            row = c.fetchone()
            return row is None or bool(row[0])

    # --- Research cache ---
    def get_research_cache(self, query: str) -> Optional[str]:
        """Return cached research results if not expired."""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT results FROM research_cache WHERE query = ? AND expires_at > datetime('now')",
                (query,)
            )
            row = c.fetchone()
            return row[0] if row else None

    def set_research_cache(self, query: str, results: str, ttl_hours: int = 24):
        """Cache research results with TTL."""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO research_cache (query, results, expires_at)
                VALUES (?, ?, datetime('now', '+{} hours'))
                ON CONFLICT(query) DO UPDATE SET
                    results=excluded.results,
                    expires_at=excluded.expires_at,
                    created_at=datetime('now')
            """.format(ttl_hours), (query, results))
            conn.commit()

    # --- Documents index ---
    def has_document(self, doc_hash: str, user_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT 1 FROM documents WHERE doc_hash = ? AND user_id = ?", (doc_hash, user_id))
            return c.fetchone() is not None

    def add_document_index(self, doc_hash: str, user_id: str, filename: str,
                           content_type: str, chunk_count: int):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO documents (doc_hash, user_id, filename, content_type, chunk_count)
                VALUES (?, ?, ?, ?, ?)
            """, (doc_hash, user_id, filename, content_type, chunk_count))
            conn.commit()

    def list_documents(self, user_id: str) -> list:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT doc_hash, filename, content_type, chunk_count, created_at FROM documents WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )
            return [self._row_to_dict(c, r) for r in c.fetchall()]

    # --- Users ---
    def ensure_user(self, user_id: str, name: str = None):
        """Create user record if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM users WHERE id = ?", (user_id,))
            if not c.fetchone():
                c.execute(
                    "INSERT INTO users (id, name, created_at, last_active) VALUES (?, ?, datetime('now'), datetime('now'))",
                    (user_id, name)
                )
                # Initialize default profile gaps
                default_gaps = [
                    ("name", 1.0),
                    ("work", 0.7),
                    ("location", 0.6),
                    ("preferences", 0.6),
                    ("family", 0.5),
                ]
                c.executemany(
                    "INSERT INTO profile_gaps (user_id, topic, priority) VALUES (?, ?, ?)",
                    [(user_id, topic, priority) for topic, priority in default_gaps]
                )
            else:
                c.execute("UPDATE users SET last_active = datetime('now') WHERE id = ?", (user_id,))
            conn.commit()

    def get_user(self, user_id: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = c.fetchone()
            if row:
                return self._row_to_dict(c, row)
            return None

    def update_user(self, user_id: str, **fields):
        allowed = {"name", "preferred_name", "rapport_level", "communication_style", "onboarding_complete", "last_active"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            c.execute(f"UPDATE users SET {set_clause} WHERE id = ?", (*updates.values(), user_id))
            conn.commit()

    def get_user_tone(self, user_id: str) -> dict:
        """Return the user's tone profile (0-1 scale)."""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT tone_formality, tone_verbosity, tone_humor, tone_proactivity FROM users WHERE id = ?",
                (user_id,)
            )
            row = c.fetchone()
            if row:
                return {
                    "formality": row[0] if row[0] is not None else 0.5,
                    "verbosity": row[1] if row[1] is not None else 0.5,
                    "humor": row[2] if row[2] is not None else 0.5,
                    "proactivity": row[3] if row[3] is not None else 0.5,
                }
            return {"formality": 0.5, "verbosity": 0.5, "humor": 0.5, "proactivity": 0.5}

    def update_user_tone(self, user_id: str, **tones):
        """Update tone scores. Values are clamped to [0, 1]."""
        allowed = {"tone_formality", "tone_verbosity", "tone_humor", "tone_proactivity"}
        updates = {}
        for k, v in tones.items():
            if k in allowed and v is not None:
                updates[k] = max(0.0, min(1.0, float(v)))
        if not updates:
            return
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            c.execute(f"UPDATE users SET {set_clause} WHERE id = ?", (*updates.values(), user_id))
            conn.commit()

    # --- Profile gaps ---
    def get_profile_gaps(self, user_id: str) -> list:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT topic, known, priority, confidence, last_probed, probe_count FROM profile_gaps WHERE user_id = ? ORDER BY priority DESC",
                (user_id,)
            )
            return [self._row_to_dict(c, r) for r in c.fetchall()]

    def update_profile_gap(self, user_id: str, topic: str, **fields):
        allowed = {"known", "priority", "confidence", "last_probed", "probe_count"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            c.execute(f"UPDATE profile_gaps SET {set_clause} WHERE user_id = ? AND topic = ?", (*updates.values(), user_id, topic))
            conn.commit()

    # --- Relationships ---
    def save_relationship(self, user_id: str, entity: str, relationship_type: str,
                          entity_type: str = "general", confidence: float = 0.5):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO relationships (user_id, entity, entity_type, relationship_type, confidence, first_mentioned)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT DO NOTHING
            """, (user_id, entity, entity_type, relationship_type, confidence))
            # If already exists, update confidence upward slightly
            c.execute("""
                UPDATE relationships SET confidence = min(1.0, confidence + 0.1)
                WHERE user_id = ? AND entity = ? AND relationship_type = ?
            """, (user_id, entity, relationship_type))
            conn.commit()

    def get_relationships(self, user_id: str, entity: str = None) -> list:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            if entity:
                c.execute(
                    "SELECT * FROM relationships WHERE user_id = ? AND entity = ? COLLATE NOCASE ORDER BY confidence DESC",
                    (user_id, entity)
                )
            else:
                c.execute(
                    "SELECT * FROM relationships WHERE user_id = ? ORDER BY confidence DESC",
                    (user_id,)
                )
            return [self._row_to_dict(c, r) for r in c.fetchall()]

    # --- Messages ---
    def save_message(self, role: str, content: str, session: str = "default", user_id: str = DEFAULT_USER_ID):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            # Upsert session scoped by user
            c.execute("SELECT id, title FROM sessions WHERE id = ? AND user_id = ?", (session, user_id))
            row = c.fetchone()
            if not row:
                title = content[:40] + "..." if len(content) > 40 and role == "user" else (content if role == "user" else session)
                c.execute(
                    "INSERT INTO sessions (id, user_id, title, last_active) VALUES (?, ?, ?, datetime('now'))",
                    (session, user_id, title)
                )
            elif row[1] is None and role == "user":
                title = content[:40] + "..." if len(content) > 40 else content
                c.execute(
                    "UPDATE sessions SET title = ?, last_active = datetime('now') WHERE id = ? AND user_id = ?",
                    (title, session, user_id)
                )
            else:
                c.execute(
                    "UPDATE sessions SET last_active = datetime('now') WHERE id = ? AND user_id = ?",
                    (session, user_id)
                )

            c.execute(
                "INSERT INTO messages (user_id, session, role, content) VALUES (?, ?, ?, ?)",
                (user_id, session, role, content)
            )
            conn.commit()

    def get_recent(self, limit: int = 20, session: str = "default", user_id: str = DEFAULT_USER_ID) -> list:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT role, content FROM messages WHERE user_id = ? AND session = ? ORDER BY id DESC LIMIT ?",
                (user_id, session, limit)
            )
            rows = c.fetchall()
            return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    def get_session_history(self, session: str, user_id: str = DEFAULT_USER_ID) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT role, content, timestamp FROM messages WHERE user_id = ? AND session = ? ORDER BY id ASC",
                (user_id, session)
            )
            rows = c.fetchall()
            c.execute("SELECT title FROM sessions WHERE id = ? AND user_id = ?", (session, user_id))
            title_row = c.fetchone()
            return {
                "session": session,
                "title": title_row[0] if title_row else session,
                "messages": [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]
            }

    def get_all_sessions(self, user_id: str = DEFAULT_USER_ID) -> list:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT id, title, created_at, last_active FROM sessions WHERE user_id = ? ORDER BY last_active DESC",
                (user_id,)
            )
            rows = c.fetchall()
            return [{"id": r[0], "title": r[1] or r[0], "created": r[2], "last_active": r[3]} for r in rows]

    def delete_session(self, session: str, user_id: str = DEFAULT_USER_ID):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM messages WHERE user_id = ? AND session = ?", (user_id, session))
            c.execute("DELETE FROM sessions WHERE user_id = ? AND id = ?", (user_id, session))
            conn.commit()

    def rename_session(self, session: str, new_name: str, user_id: str = DEFAULT_USER_ID):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE sessions SET title = ? WHERE user_id = ? AND id = ?",
                (new_name, user_id, session)
            )
            conn.commit()
            return c.rowcount > 0

    # --- Reasoning runs & steps (v0.10) ---
    def create_reasoning_run(self, run_id: str, user_id: str, session: str, trail_id: str, goal: str):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO reasoning_runs (id, user_id, session, trail_id, goal) VALUES (?, ?, ?, ?, ?)",
                (run_id, user_id, session, trail_id, goal)
            )
            conn.commit()

    def save_reasoning_step(self, run_id: str, step_index: int, thought: str, action: str,
                            action_input: dict, observation: str):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                """INSERT INTO reasoning_steps
                   (run_id, step_index, thought, action, action_input, observation)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (run_id, step_index, thought, action, json.dumps(action_input), observation)
            )
            conn.commit()

    def finish_reasoning_run(self, run_id: str, status: str, final_answer: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE reasoning_runs SET status = ?, final_answer = ?, finished_at = datetime('now') WHERE id = ?",
                (status, final_answer, run_id)
            )
            conn.commit()

    def get_reasoning_run(self, run_id: str) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM reasoning_runs WHERE id = ?", (run_id,))
            row = c.fetchone()
            if not row:
                return None
            cols = [d[0] for d in c.description]
            run = dict(zip(cols, row))
            c.execute("SELECT * FROM reasoning_steps WHERE run_id = ? ORDER BY step_index", (run_id,))
            step_cols = [d[0] for d in c.description]
            run["steps"] = []
            for r in c.fetchall():
                step = dict(zip(step_cols, r))
                try:
                    step["action_input"] = json.loads(step["action_input"])
                except Exception:
                    pass
                run["steps"].append(step)
            return run

    # --- Facts ---
    def save_fact(self, key: str, value: str, category: str = "general", confidence: float = 1.0,
                  user_id: str = DEFAULT_USER_ID, source: str = "explicit"):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO facts (user_id, key, value, category, confidence, source, reinforcement_count)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(user_id, key) DO UPDATE SET
                    value=excluded.value,
                    confidence=min(1.0, excluded.confidence + 0.05 * facts.reinforcement_count),
                    source=excluded.source,
                    reinforcement_count=facts.reinforcement_count + 1,
                    timestamp=datetime('now')
            """, (user_id, key, value, category, confidence, source))
            conn.commit()

    def get_facts(self, category: str = None, user_id: str = DEFAULT_USER_ID) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            if category:
                c.execute(
                    "SELECT key, value FROM facts WHERE user_id = ? AND category = ? ORDER BY timestamp DESC",
                    (user_id, category)
                )
            else:
                c.execute(
                    "SELECT key, value FROM facts WHERE user_id = ? ORDER BY timestamp DESC",
                    (user_id,)
                )
            rows = c.fetchall()
            return {r[0]: r[1] for r in rows}

    def get_facts_with_meta(self, user_id: str = DEFAULT_USER_ID) -> list:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT key, value, category, confidence, source, reinforcement_count FROM facts WHERE user_id = ? ORDER BY timestamp DESC",
                (user_id,)
            )
            return [self._row_to_dict(c, r) for r in c.fetchall()]

    def delete_fact(self, key: str, user_id: str = DEFAULT_USER_ID) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM facts WHERE user_id = ? AND key = ?", (user_id, key))
            conn.commit()
            return c.rowcount > 0

    def _row_to_dict(self, cursor, row) -> dict:
        return {desc[0]: row[i] for i, desc in enumerate(cursor.description)}
