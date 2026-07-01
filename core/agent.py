"""EUNICE v0.10 — ReAct Agentic Reasoning
Multi-step thought → action → observation loop for complex tasks.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator, List, Optional
import uuid

from config import BASE_DIR
from core.inference import generate_non_stream
from core.tool_router import ToolRouter
from core.coder import CoderAgent
from core.research import ResearchAssistant
from core.file_manager import FileManager


@dataclass
class ReActStep:
    index: int
    thought: str = ""
    action: str = ""           # tool name
    action_input: dict = field(default_factory=dict)
    observation: str = ""
    is_final: bool = False
    final_answer: str = ""


class ReActAgent:
    """Autonomous ReAct loop with risk-tiered tool execution."""

    def __init__(self, memory=None, tools: ToolRouter = None, research: ResearchAssistant = None):
        self.memory = memory
        self.tools = tools or ToolRouter()
        self.research = research
        self.prompt_path = BASE_DIR / "core" / "prompts" / "react.txt"
        self.prompt_template = self.prompt_path.read_text(encoding="utf-8") if self.prompt_path.exists() else self._default_prompt()

    def _default_prompt(self) -> str:
        return """You are EUNICE. Reason step-by-step using:
Thought: ...
Action: tool_name({"param": "value"})
Observation: ...
...
Final Answer: ...
Available Tools:
{tool_descriptions}
Goal: {goal}
Prior Steps:
{steps}
"""

    def _format_tool_descriptions(self) -> str:
        lines = []
        for t in self.tools.get_available_tools():
            lines.append(f"- {t['name']} (risk: {t['risk']}): {t['description']}")
        lines.append("- research: Search the web and summarize with citations.")
        lines.append("- coder: Write, edit, analyze, or run code in the sandboxed workspace.")
        lines.append("- file_manager: Read, write, list, or delete files in the sandboxed workspace.")
        return "\n".join(lines)

    def _format_steps(self, steps: List[ReActStep]) -> str:
        if not steps:
            return "None yet."
        lines = []
        for s in steps:
            lines.append(f"Step {s.index + 1}:")
            lines.append(f"Thought: {s.thought}")
            if s.action:
                lines.append(f"Action: {s.action}({json.dumps(s.action_input)})")
            if s.observation:
                lines.append(f"Observation: {s.observation}")
        return self._escape_braces("\n".join(lines))

    @staticmethod
    def _escape_braces(text: str) -> str:
        """Double braces so str.format() treats them as literals."""
        return text.replace("{", "{{").replace("}", "}}")

    def _parse_step(self, text: str) -> Optional[dict]:
        """Parse a ReAct step from model output."""
        text = text.strip()
        if not text:
            return None

        # Final Answer
        if "Final Answer:" in text:
            answer = text.split("Final Answer:", 1)[1].strip()
            return {"type": "final", "answer": answer}

        thought = ""
        action = ""
        action_input = {}

        # Thought
        thought_match = re.search(r'Thought:\s*(.*?)(?=\nAction:|\nFinal Answer:|$)', text, re.DOTALL)
        if thought_match:
            thought = thought_match.group(1).strip()

        # Action: tool_name({...})
        action_match = re.search(r'Action:\s*(\w+)\s*\((.*?)\)(?=\n|$)', text, re.DOTALL)
        if action_match:
            action = action_match.group(1).strip()
            raw_params = action_match.group(2).strip()
            if raw_params:
                try:
                    action_input = json.loads(raw_params)
                except json.JSONDecodeError:
                    # Fallback: treat as string request
                    action_input = {"request": raw_params}

        if thought or action:
            return {"type": "step", "thought": thought, "action": action, "params": action_input}

        return None

    async def _execute_action(self, action: str, params: dict, user_id: str) -> str:
        """Execute a single action and return observation string."""
        # Special internal tools (must be handled before subprocess tools to avoid
        # shadowing by tools/coder.py, tools/file_manager.py, etc.)

        # Research
        if action == "research":
            query = params.get("query") or params.get("request") or params.get("topic", "")
            if not query:
                return "[Error: research requires a query]"
            if self.research is None:
                self.research = ResearchAssistant(self.memory)
            try:
                result = await self.research.research(query)
                answer = result.get("answer", "")
                sources = result.get("sources", [])
                source_text = "\n".join([f"- {s.get('title', 'Unknown')}: {s.get('url', '')}" for s in sources[:3]])
                return f"{answer}\n\nSources:\n{source_text}" if source_text else answer
            except Exception as e:
                return f"[Research failed: {e}]"

        # Coder
        if action == "coder":
            request = params.get("request") or params.get("prompt") or params.get("description", "")
            filename = params.get("filename") or "generated.py"
            language = params.get("language") or "python"
            if not request:
                return "[Error: coder requires a request]"
            try:
                agent = CoderAgent(user_id)
                subtype = params.get("action", "generate")
                if subtype == "run":
                    result = agent.run(filename, language, timeout=params.get("timeout", 10))
                elif subtype == "edit":
                    result = await agent.edit(request, filename)
                elif subtype == "analyze":
                    result = agent.analyze(filename)
                else:
                    result = await agent.generate(request, filename, language)
                return f"Wrote {result.get('filename')}.\n\n```\n{result.get('code', '')}\n```"
            except Exception as e:
                return f"[Coder failed: {e}]"

        # File manager
        if action == "file_manager":
            try:
                fm = FileManager(user_id)
                op = params.get("action", "list")
                path = params.get("path", "")
                if op == "list":
                    entries = fm.list(path)
                    return "\n".join([f"- {e['name']} ({e['type']}, {e.get('size', 0)} bytes)" for e in entries])
                elif op == "read":
                    return fm.read(path)
                elif op == "write":
                    fm.write(path, params.get("content", ""))
                    return f"Wrote {path}."
                elif op == "delete":
                    return "[Error: delete requires explicit confirmation]"
                else:
                    return f"[Unknown file_manager action: {op}]"
            except Exception as e:
                return f"[File manager failed: {e}]"

        # Subprocess tools (get_balance, network_scan, notes, self_update, transfer_funds)
        available = {t["name"]: t for t in self.tools.get_available_tools()}
        if action in available:
            params_with_user = dict(params)
            params_with_user.setdefault("user_id", user_id)
            result = await self.tools.execute(action, params_with_user)
            return result

        return f"[Unknown action: {action}]"

    async def run(self, goal: str, session: str, user_id: str, max_steps: int = 5, trail_id: str = ""):
        """Run the ReAct loop and yield events."""
        steps: List[ReActStep] = []
        run_id = str(uuid.uuid4())
        if self.memory:
            self.memory.create_reasoning_run(run_id, user_id, session, trail_id or "", goal)
        tool_descriptions = self._format_tool_descriptions()

        for step_idx in range(max_steps):
            prompt = self.prompt_template.format(
                tool_descriptions=self._escape_braces(tool_descriptions),
                goal=self._escape_braces(goal),
                steps=self._format_steps(steps)
            )

            raw = await generate_non_stream(prompt=prompt, format_json=False)
            if not raw:
                yield {"type": "error", "content": "Model returned empty response"}
                return

            parsed = self._parse_step(raw)
            if not parsed:
                yield {"type": "error", "content": f"Could not parse model output: {raw[:200]}"}
                return

            if parsed["type"] == "final":
                step = ReActStep(index=step_idx, is_final=True, final_answer=parsed["answer"])
                steps.append(step)
                if self.memory:
                    self.memory.finish_reasoning_run(run_id, "completed", parsed["answer"])
                yield {"type": "final", "content": parsed["answer"], "steps": steps}
                return

            # New step
            step = ReActStep(
                index=step_idx,
                thought=parsed.get("thought", ""),
                action=parsed.get("action", ""),
                action_input=parsed.get("params", {})
            )
            yield {"type": "thought", "content": step.thought, "step": step}

            if self.memory:
                self.memory.save_reasoning_step(run_id, step_idx, step.thought, step.action, step.action_input, "")

            if not step.action:
                yield {"type": "error", "content": "Model produced a thought but no action"}
                return

            yield {"type": "action", "tool": step.action, "params": step.action_input, "step": step}

            observation = await self._execute_action(step.action, step.action_input, user_id)
            step.observation = observation
            yield {"type": "observation", "content": observation, "step": step}

            if self.memory:
                self.memory.save_reasoning_step(run_id, step_idx, step.thought, step.action, step.action_input, observation)

            # Pause if pending approval
            if observation.startswith("[PENDING:"):
                if self.memory:
                    self.memory.finish_reasoning_run(run_id, "pending_approval", observation)
                yield {"type": "pending", "tool": step.action, "message": observation, "steps": steps}
                return

            steps.append(step)

        # Max steps reached without final answer
        if self.memory:
            self.memory.finish_reasoning_run(run_id, "max_steps", "")
        yield {"type": "error", "content": f"Reached maximum steps ({max_steps}) without a final answer."}
