"""EUNICE Trails — Associative Memory Manager (multi-user)
Manages trails, nodes, activation, and cross-trail linking.
"""
import re
import sqlite3
import hashlib
from datetime import datetime
from typing import List, Dict, Optional
from memory.trail_store import TrailStore
from memory.vector_store import VectorStore

DEFAULT_USER_ID = "ronny"

class TrailManager:
    """Manages associative memory trails for EUNICE."""

    def __init__(self):
        self.store = TrailStore()
        self.vector = VectorStore()

    # --- Trail Lifecycle ---
    def detect_or_create_trail(self, user_msg: str, session: str, user_id: str = DEFAULT_USER_ID) -> str:
        """Detect which trail a message belongs to, or create a new one."""
        entities = self._extract_entities(user_msg)

        # Try to find existing trail by entity (user-scoped)
        for entity in entities:
            trail_id = self.store.find_trail_by_entity(entity, user_id=user_id)
            if trail_id:
                return trail_id

        # Try semantic search on vector store (user-scoped)
        try:
            results = self.vector.search_conversations(user_msg, n_results=3, user_id=user_id)
            for r in results:
                trail_id = self.store.find_trail_by_content(r.get('content', ''), user_id=user_id)
                if trail_id:
                    return trail_id
        except Exception:
            pass

        # Create new trail
        name = self._generate_trail_name(user_msg, entities)
        trail_id = f"trail_{user_id}_{session}_{hashlib.md5(name.encode()).hexdigest()[:8]}"
        node_id = f"node_{trail_id}_root"

        self.store.create_trail(trail_id, name, node_id, user_id=user_id)
        self.store.add_node(
            node_id, trail_id, user_msg, None, user_id=user_id,
            tags=','.join(self._extract_tags(user_msg)),
            entities=','.join(entities)
        )

        # Index entities
        for entity in entities:
            self.store.upsert_entity(trail_id, entity, self._entity_type(entity), user_id=user_id)

        return trail_id

    def append_to_trail(self, trail_id: str, content: str, role: str = "user",
                        user_id: str = DEFAULT_USER_ID, source_type: str = "chat",
                        source_id: str = None):
        """Append a new event to an existing trail."""
        parent_id = self.store.get_current_leaf(trail_id, user_id=user_id)
        node_id = f"node_{trail_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        tags = ','.join(self._extract_tags(content))
        entities = ','.join(self._extract_entities(content))

        self.store.add_node(
            node_id, trail_id, content, parent_id, user_id=user_id,
            tags=tags, entities=entities,
            source_type=source_type, source_id=source_id
        )
        self.store.update_trail_leaf(trail_id, node_id, user_id=user_id)
        self.store.update_trail_accessed(trail_id, user_id=user_id)

        # Update entities
        for entity in self._extract_entities(content):
            self.store.upsert_entity(trail_id, entity, self._entity_type(entity), user_id=user_id)

        # Store in vector DB for semantic search
        try:
            turn_count = self.store.get_node_count(trail_id, user_id=user_id)
            self.vector.store_conversation_turn(
                session_id=trail_id, role=role, content=content, turn_id=turn_count, user_id=user_id
            )
        except Exception:
            pass

        return node_id

    def follow_trail(self, trail_id: str, n: int = 3, user_id: str = DEFAULT_USER_ID) -> List[Dict]:
        """Get the last N nodes from a trail (most recent context)."""
        return self.store.get_trail_nodes(trail_id, n, user_id=user_id)

    def get_trail_summary_text(self, trail_id: str, user_id: str = DEFAULT_USER_ID) -> str:
        """Get a human-readable summary of recent trail activity."""
        trail = self.store.get_trail(trail_id, user_id=user_id)
        if not trail:
            return ""

        nodes = self.follow_trail(trail_id, n=3, user_id=user_id)
        if not nodes:
            return trail.get('name', 'Unknown trail')

        lines = [f"Trail: {trail['name']}"]
        for node in nodes:
            lines.append(f"- {node['content'][:80]}")
        return "\n".join(lines)

    # --- Activation ---
    def activate_trail(self, trail_id: str, trigger_type: str = "user_mention",
                       user_id: str = DEFAULT_USER_ID):
        """Activate a trail (load into working memory)."""
        self.store.set_trail_status(trail_id, "active", user_id=user_id)
        self.store.log_activation(trail_id, trigger_type)
        self.store.update_trail_accessed(trail_id, user_id=user_id)

    def dormant_trail(self, trail_id: str, user_id: str = DEFAULT_USER_ID):
        """Background a trail (still monitored, not in working memory)."""
        self.store.set_trail_status(trail_id, "dormant", user_id=user_id)

    def archive_trail(self, trail_id: str, user_id: str = DEFAULT_USER_ID):
        """Archive a completed trail."""
        self.store.set_trail_status(trail_id, "archived", user_id=user_id)

    def get_active_trails(self, user_id: str = DEFAULT_USER_ID) -> List[Dict]:
        return self.store.get_trails_by_status("active", user_id=user_id)

    def get_dormant_trails(self, user_id: str = DEFAULT_USER_ID) -> List[Dict]:
        return self.store.get_trails_by_status("dormant", user_id=user_id)

    # --- Cross-trail intelligence ---
    def find_related_trails(self, entity: str, user_id: str = DEFAULT_USER_ID) -> List[Dict]:
        """Find all trails that mention a given entity."""
        with sqlite3.connect(self.store.db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT t.* FROM trails t
                JOIN trail_entities e ON t.id = e.trail_id
                WHERE t.user_id = ? AND e.user_id = ? AND e.entity = ? COLLATE NOCASE
            """, (user_id, user_id, entity))
            return [self.store._row_to_dict(c, r) for r in c.fetchall()]

    def find_cross_trail_conflicts(self, user_id: str = DEFAULT_USER_ID) -> List[Dict]:
        """Find temporal conflicts between dormant trails with deadlines."""
        upcoming = self.store.get_trails_with_deadlines(days=7, user_id=user_id)
        conflicts = []
        for i, t1 in enumerate(upcoming):
            for t2 in upcoming[i+1:]:
                if t1.get('deadline') == t2.get('deadline'):
                    conflicts.append({
                        'trail_a': t1.get('name', 'Unknown'),
                        'trail_b': t2.get('name', 'Unknown'),
                        'deadline': t1['deadline'],
                        'trail_a_id': t1['id'],
                        'trail_b_id': t2['id']
                    })
        return conflicts

    def spawn_branch_trail(self, parent_trail_id: str, branch_name: str,
                          branch_content: str, session: str, user_id: str = DEFAULT_USER_ID) -> str:
        """Create a new trail that branches from an existing one."""
        branch_id = self.detect_or_create_trail(branch_content, session, user_id=user_id)

        # Link parent leaf to branch root
        parent_leaf = self.store.get_current_leaf(parent_trail_id, user_id=user_id)
        branch_root = self.store.get_current_leaf(branch_id, user_id=user_id)

        if parent_leaf and branch_root:
            self.store.add_edge(parent_leaf, branch_root, edge_type="spawns", weight=0.8)

        return branch_id

    # --- Entity & Tag Extraction (rule-based, no LLM) ---
    def _extract_entities(self, text: str) -> List[str]:
        """Extract key entities from text."""
        entities = set()

        # Proper nouns (2+ words)
        for match in re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text):
            if len(match) > 3:
                entities.add(match.lower())

        # Known entity patterns
        car_brands = re.findall(r'\b(Tesla|Toyota|Honda|BMW|Mercedes|Audi|Ford|Chevy|Nissan)\b', text, re.I)
        family = re.findall(r'\b(mom|mother|dad|father|sister|brother|wife|husband|daughter|son)\b', text, re.I)
        money = re.findall(r'\$[\d,]+(?:\.\d{2})?|\b\d+\s*(dollars|usd|bucks)\b', text, re.I)
        dates = re.findall(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\b', text, re.I)

        entities.update([e.lower() for e in car_brands])
        entities.update([e.lower() for e in family])
        entities.update([e.lower() for e in money])
        entities.update([e.lower() for e in dates])

        # Single significant nouns (capitalized or specific)
        for word in re.findall(r'\b[A-Z][a-z]{2,}\b', text):
            entities.add(word.lower())

        return list(entities)

    def _extract_tags(self, text: str) -> List[str]:
        """Extract topic tags."""
        text_lower = text.lower()
        tags = []

        topic_map = {
            'transportation': ['car', 'tesla', 'drive', 'vehicle', 'road', 'traffic', 'service', 'mechanic'],
            'family': ['mom', 'mother', 'dad', 'father', 'sister', 'brother', 'wife', 'husband', 'daughter', 'son', 'family'],
            'work': ['work', 'job', 'office', 'meeting', 'presentation', 'client', 'boss', 'colleague', 'project'],
            'finance': ['money', 'buy', 'purchase', 'gift', 'balance', 'bank', 'pay', 'cost', 'expensive', 'cheap', 'budget'],
            'health': ['gym', 'workout', 'run', 'exercise', 'doctor', 'sick', 'tired', 'sleep', 'diet', 'food'],
            'social': ['friend', 'party', 'dinner', 'date', 'call', 'visit', 'weekend', 'plan'],
            'home': ['house', 'apartment', 'rent', 'move', 'repair', 'kitchen', 'bedroom'],
            'technology': ['computer', 'phone', 'app', 'software', 'bug', 'code', 'server', 'website']
        }

        for topic, keywords in topic_map.items():
            if any(k in text_lower for k in keywords):
                tags.append(topic)

        return tags

    def _entity_type(self, entity: str) -> str:
        """Classify entity type."""
        entity_lower = entity.lower()

        if any(c in entity_lower for c in ['tesla', 'toyota', 'honda', 'bmw', 'car', 'vehicle']):
            return 'transportation'
        if any(f in entity_lower for f in ['mom', 'mother', 'dad', 'father', 'sister', 'brother']):
            return 'family'
        if any(w in entity_lower for w in ['work', 'office', 'meeting', 'project']):
            return 'work'
        if re.search(r'\$?\d+', entity):
            return 'finance'

        return 'general'

    def _generate_trail_name(self, text: str, entities: List[str]) -> str:
        """Auto-generate a trail name from content."""
        if entities:
            return f"Topic: {entities[0].title()}"

        # Extract first 4 significant words
        words = re.findall(r'\b[a-z]{4,}\b', text.lower())
        if words:
            return f"Topic: {' '.join(words[:3]).title()}"

        return f"Trail {datetime.now().strftime('%H%M')}"

    def get_trail_context_for_prompt(self, trail_id: str, user_id: str = DEFAULT_USER_ID,
                                     user_name: str = "the user", max_nodes: int = 3) -> str:
        """Generate a prompt-ready context string from a trail."""
        nodes = self.follow_trail(trail_id, n=max_nodes, user_id=user_id)
        if not nodes:
            return ""

        lines = [f"What {user_name} has told you about this topic:"]
        for node in nodes:
            content = node['content'][:80]
            if len(node['content']) > 80:
                content += "..."
            lines.append(f"- {user_name} said: '{content}'")

        return "\n".join(lines)
