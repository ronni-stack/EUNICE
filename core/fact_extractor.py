"""EUNICE v0.8 — Implicit Fact Extractor
Extracts facts, relationships, and profile gaps from every exchange.
"""
import json
import re
from typing import Optional
from core.inference import generate_non_stream
from memory.manager import MemoryManager

DEFAULT_USER_ID = "ronny"

EXTRACTION_PROMPT = """You are a fact extraction engine for a personal AI assistant.
Analyze the following conversation exchange and extract structured information.

Return a JSON object with this exact structure:
{
  "facts": [
    {"key": "snake_case_key", "value": "natural language fact", "category": "personal|work|family|preference|schedule|location|health|other", "confidence": 0.0-1.0}
  ],
  "relationships": [
    {"entity": "Name or thing", "entity_type": "person|organization|object|place|other", "relationship_type": "sister|brother|friend|employer|owns|lives_in|works_at|other", "confidence": 0.0-1.0}
  ],
  "gaps_filled": ["name", "work", "family", "location", "preferences"]
}

Rules:
- Only extract facts the USER explicitly states or strongly implies.
- Do NOT extract facts about the assistant.
- Confidence 0.9-1.0 for explicit statements ("I am a doctor").
- Confidence 0.6-0.8 for reasonable inferences.
- Confidence <0.6: omit unless it's a direct statement.
- Use empty arrays [] when nothing extractable.
- "gaps_filled" lists which profile topics were addressed (name, work, family, location, preferences).

User: {user_msg}
Assistant: {assistant_msg}

JSON:"""


class FactExtractor:
    """Background extractor for implicit learning."""

    def __init__(self, memory: MemoryManager = None):
        self.memory = memory or MemoryManager()

    async def extract(self, user_msg: str, assistant_msg: str, user_id: str = DEFAULT_USER_ID):
        """Extract facts and relationships from an exchange and store them."""
        prompt = EXTRACTION_PROMPT.format(user_msg=user_msg, assistant_msg=assistant_msg)
        raw = await generate_non_stream(prompt=prompt, format_json=True)
        if not raw:
            return

        raw = re.sub(r'^```json\s*', '', raw)
        raw = re.sub(r'```\s*$', '', raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            print(f"[EXTRACT] Failed to parse extraction JSON for user={user_id}")
            return

        if not isinstance(data, dict):
            return

        # Store facts
        facts = data.get("facts", [])
        if isinstance(facts, list):
            for f in facts:
                if not isinstance(f, dict):
                    continue
                value = f.get("value", "").strip()
                if not value or len(value) < 5:
                    continue
                confidence = float(f.get("confidence", 0.5))
                if confidence < 0.5:
                    continue
                category = f.get("category", "general")
                self.memory.store_fact(value, category=category, source="extracted", user_id=user_id)

        # Store relationships
        relationships = data.get("relationships", [])
        if isinstance(relationships, list):
            for r in relationships:
                if not isinstance(r, dict):
                    continue
                entity = r.get("entity", "").strip()
                relationship_type = r.get("relationship_type", "").strip()
                if not entity or not relationship_type:
                    continue
                confidence = float(r.get("confidence", 0.5))
                entity_type = r.get("entity_type", "general")
                self.memory.store_relationship(
                    user_id, entity, relationship_type, entity_type=entity_type, confidence=confidence
                )

        # Update profile gaps
        gaps_filled = data.get("gaps_filled", [])
        if isinstance(gaps_filled, list):
            for gap in gaps_filled:
                self.memory.update_profile_gap(user_id, gap, known=True, confidence=0.8)

        print(f"[EXTRACT] user={user_id}: {len(facts)} facts, {len(relationships)} relationships, gaps={gaps_filled}")
