"""EUNICE v0.8 — SQLite Episodic Memory (multi-user)"""
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
                    onboarding_complete BOOLEAN DEFAULT FALSE
                )
            """)

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

            # Migrate legacy sessions if old table still exists
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
            if c.fetchone():
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

            # Facts table: migrate to (user_id, key) uniqueness
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

            # Migrate legacy facts if old table still exists
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='facts'")
            if c.fetchone():
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

            conn.commit()

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
