# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE v0.10 — Intent Classification
Structured intent detection for routing messages to the right handler.
"""
import re
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class Intent:
    type: str
    confidence: float
    subtype: Optional[str] = None
    entities: Dict[str, Any] = field(default_factory=dict)


class IntentClassifier:
    """Classifies user messages into structured intents for routing."""

    CODING_TRIGGERS = {
        "generate": [
            "write code", "write a", "generate code", "create a script",
            "code that", "program that", "function that", "script to",
            "make a", "build a", "implement"
        ],
        "fix": [
            "fix", "wrong", "bug", "error", "correct", "regenerate",
            "rewrite", "broken", "doesn't work", "not working", "debug",
            "refactor", "improve this"
        ],
        "analyze": [
            "explain", "what does this do", "walk me through",
            "how does this work", "analyze", "review this code",
            "what is this doing", "break down"
        ],
        "run": [
            "run", "execute", "test this", "try this code", "run it"
        ],
    }

    RESEARCH_TRIGGERS = [
        "research", "look up", "search online", "find out about",
        "what is", "who is", "latest news", "tell me about",
        "current events", "recent developments"
    ]

    FILE_TRIGGERS = [
        "list my files", "upload", "read file", "delete file",
        "show files", "file manager", "my files", "workspace"
    ]

    MEMORY_TRIGGERS = [
        "remember that", "don't forget", "save this", "note that",
        "store this", "add to my memory"
    ]

    MEMORY_QUERY_TRIGGERS = [
        "what is my", "do you remember", "what did i", "tell me about",
        "recall", "what was my", "have we talked about", "remind me"
    ]

    AGENTIC_TRIGGERS = [
        "plan and execute", "do this for me", "make it happen",
        "research and then", "find out and then", "write a script that",
        "create a script that", "summarize and save", "and then save",
        "and then write", "and then run", "after that", "next, ",
        "step by step", "break this down"
    ]

    TOOL_KEYWORDS = {
        "get_balance": ["balance", "account", "how much money"],
        "network_scan": ["scan network", "network scan", "who is on my wifi", "devices on network"],
        "notes": ["take a note", "save note", "write down"],
        "self_update": ["check for updates", "update yourself", "any updates"],
        "transfer_funds": ["transfer", "send money", "wire", "pay", "send $"],
    }

    def _has_code(self, text: str) -> bool:
        """Detect if the user pasted or referenced code."""
        code_indicators = [
            "```", "def ", "class ", "import ", "from ", "return ",
            "for ", "if ", "while ", "print(", "console.log",
            "function ", "const ", "let ", "var ", "#include",
            "public static", "func ", "fn ", "async def"
        ]
        return any(ind in text for ind in code_indicators)

    def _detect_coding_subtype(self, text: str) -> Optional[str]:
        """Determine coding intent subtype based on presence of code and action words."""
        lower = text.lower()
        has_code = self._has_code(text)

        if has_code:
            for subtype, triggers in self.CODING_TRIGGERS.items():
                if subtype == "generate":
                    continue
                if any(t in lower for t in triggers):
                    return subtype
            return "analyze"  # Default when code is present but no clear action

        # No code present — check for generation request
        for trigger in self.CODING_TRIGGERS["generate"]:
            if trigger in lower:
                return "generate"

        if any(w in lower for w in ["code", "script", "function", "program"]):
            return "generate"

        return None

    def _detect_tool(self, text: str) -> Optional[str]:
        lower = text.lower()
        for tool_name, keywords in self.TOOL_KEYWORDS.items():
            if any(k in lower for k in keywords):
                return tool_name
        return None

    def _extract_research_query(self, text: str) -> str:
        lower = text.lower()
        query = text
        for trigger in self.RESEARCH_TRIGGERS:
            if trigger in lower:
                idx = lower.find(trigger)
                if idx >= 0:
                    query = text[idx + len(trigger):].strip(" ,:.?!")
                break
        return query

    def _is_agentic(self, text: str) -> bool:
        """Detect multi-step requests that should use the ReAct agent."""
        lower = text.lower()
        # Explicit agentic triggers
        if any(t in lower for t in self.AGENTIC_TRIGGERS):
            return True
        # Multiple intent keywords suggesting chained tasks
        intent_markers = ["research", "look up", "search", "write", "create", "generate",
                          "code", "script", "save", "run", "execute", "compare"]
        found = sum(1 for m in intent_markers if m in lower)
        if found >= 3:
            return True
        # Sequencing words combined with tool keywords
        sequencing = ["and then", "then ", "after that", "next,", "first", "finally"]
        if any(s in lower for s in sequencing):
            return True
        return False

    def classify(self, user_msg: str) -> Intent:
        lower = user_msg.lower()

        # 1. Tool confirmations (highest priority)
        confirm_match = re.match(r'^confirm\s+(\w+)', lower)
        if confirm_match:
            return Intent("tool_confirm", 0.98, subtype=confirm_match.group(1))

        # 2. Explicit memory commands
        if any(t in lower for t in self.MEMORY_TRIGGERS):
            return Intent("explicit_memory", 0.95, entities={"text": user_msg})

        # 3. Agentic / multi-step planning
        if self._is_agentic(user_msg):
            return Intent("agentic", 0.85, entities={"goal": user_msg})

        # 4. Coding intents
        coding_subtype = self._detect_coding_subtype(user_msg)
        if coding_subtype:
            return Intent("coding", 0.9, subtype=coding_subtype, entities={"request": user_msg})

        # 5. Research
        if any(t in lower for t in self.RESEARCH_TRIGGERS):
            query = self._extract_research_query(user_msg)
            return Intent("research", 0.85, entities={"query": query})

        # 6. File operations
        if any(t in lower for t in self.FILE_TRIGGERS):
            return Intent("file_ops", 0.8)

        # 7. Memory queries
        if any(t in lower for t in self.MEMORY_QUERY_TRIGGERS):
            return Intent("memory_query", 0.85)

        # 8. Direct tool calls
        tool_name = self._detect_tool(user_msg)
        if tool_name:
            return Intent("tool_use", 0.9, subtype=tool_name)

        # 9. General chat fallback
        return Intent("general_chat", 0.6)
