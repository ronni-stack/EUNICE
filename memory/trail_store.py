# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Trails — SQLite storage for associative memory trails (multi-user)."""
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
from config import DB_PATH

DEFAULT_USER_ID = "ronny"

class TrailStore:
    """Manages trail graph storage in SQLite, scoped by user_id."""

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
            c.execute("""
                CREATE TABLE IF NOT EXISTS trails (
                    id TEXT PRIMARY KEY,
                    user_id TEXT DEFAULT 'ronny',
                    name TEXT NOT NULL,
                    root_node_id TEXT,
                    current_leaf_id TEXT,
                    status TEXT DEFAULT 'dormant',
                    priority REAL DEFAULT 0.5,
                    deadline TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TEXT DEFAULT CURRENT_TIMESTAMP,
                    summary TEXT
                )
            """)
            if not self._column_exists(conn, "trails", "user_id"):
                c.execute("ALTER TABLE trails ADD COLUMN user_id TEXT DEFAULT 'ronny'")

            c.execute("""
                CREATE TABLE IF NOT EXISTS trail_nodes (
                    id TEXT PRIMARY KEY,
                    user_id TEXT DEFAULT 'ronny',
                    trail_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    parent_id TEXT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    tags TEXT,
                    entities TEXT,
                    emotional_valence REAL DEFAULT 0.0,
                    source_type TEXT,
                    source_id TEXT,
                    FOREIGN KEY (trail_id) REFERENCES trails(id)
                )
            """)
            if not self._column_exists(conn, "trail_nodes", "user_id"):
                c.execute("ALTER TABLE trail_nodes ADD COLUMN user_id TEXT DEFAULT 'ronny'")

            c.execute("""
                CREATE TABLE IF NOT EXISTS trail_edges (
                    from_node TEXT,
                    to_node TEXT,
                    edge_type TEXT DEFAULT 'leads_to',
                    weight REAL DEFAULT 1.0,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (from_node, to_node, edge_type)
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS trail_activations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trail_id TEXT,
                    activated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    trigger_type TEXT,
                    context TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS trail_entities (
                    trail_id TEXT,
                    user_id TEXT DEFAULT 'ronny',
                    entity TEXT,
                    entity_type TEXT DEFAULT 'general',
                    first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
                    mention_count INTEGER DEFAULT 1,
                    PRIMARY KEY (trail_id, entity)
                )
            """)
            if not self._column_exists(conn, "trail_entities", "user_id"):
                c.execute("ALTER TABLE trail_entities ADD COLUMN user_id TEXT DEFAULT 'ronny'")

            conn.commit()

    # --- Trail CRUD ---
    def create_trail(self, trail_id: str, name: str, root_node_id: str,
                     user_id: str = DEFAULT_USER_ID, deadline: str = None):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO trails (id, user_id, name, root_node_id, current_leaf_id, deadline)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (trail_id, user_id, name, root_node_id, root_node_id, deadline))
            conn.commit()

    def get_trail(self, trail_id: str, user_id: str = DEFAULT_USER_ID) -> Optional[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM trails WHERE id = ? AND user_id = ?", (trail_id, user_id))
            row = c.fetchone()
            if row:
                return self._row_to_dict(c, row)
            return None

    def get_trails_by_status(self, status: str, user_id: str = DEFAULT_USER_ID) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT * FROM trails WHERE user_id = ? AND status = ? ORDER BY last_accessed DESC",
                (user_id, status)
            )
            return [self._row_to_dict(c, r) for r in c.fetchall()]

    def set_trail_status(self, trail_id: str, status: str, user_id: str = DEFAULT_USER_ID):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE trails SET status = ? WHERE id = ? AND user_id = ?",
                (status, trail_id, user_id)
            )
            conn.commit()

    def update_trail_leaf(self, trail_id: str, node_id: str, user_id: str = DEFAULT_USER_ID):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE trails SET current_leaf_id = ? WHERE id = ? AND user_id = ?",
                (node_id, trail_id, user_id)
            )
            conn.commit()

    def update_trail_accessed(self, trail_id: str, user_id: str = DEFAULT_USER_ID):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE trails SET last_accessed = datetime('now') WHERE id = ? AND user_id = ?",
                (trail_id, user_id)
            )
            conn.commit()

    def update_trail_summary(self, trail_id: str, summary: str, user_id: str = DEFAULT_USER_ID):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE trails SET summary = ? WHERE id = ? AND user_id = ?",
                (summary, trail_id, user_id)
            )
            conn.commit()

    def update_trail_deadline(self, trail_id: str, deadline: str, user_id: str = DEFAULT_USER_ID):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE trails SET deadline = ? WHERE id = ? AND user_id = ?",
                (deadline, trail_id, user_id)
            )
            conn.commit()

    # --- Node CRUD ---
    def add_node(self, node_id: str, trail_id: str, content: str, parent_id: str = None,
                 user_id: str = DEFAULT_USER_ID, tags: str = None, entities: str = None,
                 emotional_valence: float = 0.0, source_type: str = None, source_id: str = None):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO trail_nodes (id, user_id, trail_id, content, parent_id, tags, entities,
                                         emotional_valence, source_type, source_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (node_id, user_id, trail_id, content, parent_id, tags, entities,
                  emotional_valence, source_type, source_id))
            conn.commit()

    def get_trail_nodes(self, trail_id: str, n: int = 5, user_id: str = DEFAULT_USER_ID) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT id, trail_id, content, parent_id, timestamp, tags, entities, emotional_valence
                FROM trail_nodes WHERE user_id = ? AND trail_id = ? ORDER BY timestamp DESC LIMIT ?
            """, (user_id, trail_id, n))
            rows = c.fetchall()
            return [{
                "id": r[0], "trail_id": r[1], "content": r[2], "parent_id": r[3],
                "timestamp": r[4], "tags": r[5], "entities": r[6], "emotional_valence": r[7]
            } for r in reversed(rows)]

    def get_node_count(self, trail_id: str, user_id: str = DEFAULT_USER_ID) -> int:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT COUNT(*) FROM trail_nodes WHERE user_id = ? AND trail_id = ?",
                (user_id, trail_id)
            )
            return c.fetchone()[0]

    # --- Entity linking ---
    def upsert_entity(self, trail_id: str, entity: str, entity_type: str = "general",
                      user_id: str = DEFAULT_USER_ID):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO trail_entities (trail_id, user_id, entity, entity_type, last_seen, mention_count)
                VALUES (?, ?, ?, ?, datetime('now'), 1)
                ON CONFLICT(trail_id, entity) DO UPDATE SET
                    last_seen = datetime('now'),
                    mention_count = mention_count + 1
            """, (trail_id, user_id, entity, entity_type))
            conn.commit()

    def find_trail_by_entity(self, entity: str, user_id: str = DEFAULT_USER_ID) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT trail_id FROM trail_entities
                WHERE user_id = ? AND entity = ? COLLATE NOCASE
                ORDER BY mention_count DESC LIMIT 1
            """, (user_id, entity))
            row = c.fetchone()
            return row[0] if row else None

    def find_trail_by_content(self, content: str, user_id: str = DEFAULT_USER_ID) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT trail_id FROM trail_nodes
                WHERE user_id = ? AND content = ? COLLATE NOCASE
                LIMIT 1
            """, (user_id, content))
            row = c.fetchone()
            return row[0] if row else None

    def get_entities_for_trail(self, trail_id: str, user_id: str = DEFAULT_USER_ID) -> List[str]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT entity FROM trail_entities WHERE user_id = ? AND trail_id = ?",
                (user_id, trail_id)
            )
            return [r[0] for r in c.fetchall()]

    # --- Activation logging ---
    def log_activation(self, trail_id: str, trigger_type: str, context: str = None):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO trail_activations (trail_id, activated_at, trigger_type, context)
                VALUES (?, datetime('now'), ?, ?)
            """, (trail_id, trigger_type, context))
            conn.commit()

    # --- Deadline queries ---
    def get_trails_with_deadlines(self, days: int = 7, user_id: str = DEFAULT_USER_ID) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT * FROM trails
                WHERE user_id = ? AND deadline IS NOT NULL
                AND deadline <= datetime('now', '+' || ? || ' days')
                AND status = 'dormant'
                ORDER BY deadline ASC
            """, (user_id, days))
            return [self._row_to_dict(c, r) for r in c.fetchall()]

    def get_current_leaf(self, trail_id: str, user_id: str = DEFAULT_USER_ID) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute(
                "SELECT current_leaf_id FROM trails WHERE id = ? AND user_id = ?",
                (trail_id, user_id)
            )
            row = c.fetchone()
            return row[0] if row else None

    # --- Edge management ---
    def add_edge(self, from_node: str, to_node: str, edge_type: str = "leads_to", weight: float = 1.0):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO trail_edges (from_node, to_node, edge_type, weight)
                VALUES (?, ?, ?, ?)
            """, (from_node, to_node, edge_type, weight))
            conn.commit()

    def get_edges_from(self, node_id: str) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM trail_edges WHERE from_node = ?", (node_id,))
            return [{"to": r[1], "type": r[2], "weight": r[3]} for r in c.fetchall()]

    # --- Utility ---
    def _row_to_dict(self, cursor, row) -> Dict:
        return {desc[0]: row[i] for i, desc in enumerate(cursor.description)}
