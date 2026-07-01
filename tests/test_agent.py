# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE v0.10 — ReAct Agent Tests"""
import json
import pytest

from core.agent import ReActAgent, ReActStep


class FakeToolRouter:
    def __init__(self, result="ok"):
        self.result = result
        self.calls = []
        self._tools = [
            {"name": "get_balance", "description": "Get balance", "risk": "low", "params": {}},
            {"name": "transfer_funds", "description": "Transfer money", "risk": "critical", "params": {}},
        ]

    def get_available_tools(self):
        return self._tools

    async def execute(self, tool_name, params, permissions=None):
        self.calls.append((tool_name, params))
        return self.result


class FakeMemory:
    def __init__(self):
        self.runs = []
        self.steps = []

    def create_reasoning_run(self, run_id, user_id, session, trail_id, goal):
        self.runs.append({"run_id": run_id, "user_id": user_id, "session": session,
                          "trail_id": trail_id, "goal": goal, "status": "running"})

    def save_reasoning_step(self, run_id, step_index, thought, action, action_input, observation):
        self.steps.append({"run_id": run_id, "step_index": step_index, "thought": thought,
                           "action": action, "action_input": action_input, "observation": observation})

    def finish_reasoning_run(self, run_id, status, final_answer=""):
        for r in self.runs:
            if r["run_id"] == run_id:
                r["status"] = status
                r["final_answer"] = final_answer


@pytest.fixture
def agent(monkeypatch):
    tools = FakeToolRouter()
    mem = FakeMemory()
    a = ReActAgent(memory=mem, tools=tools)
    return a, mem, tools


def test_parse_step_thought_action(agent):
    a, _, _ = agent
    raw = "Thought: I need the balance\nAction: get_balance({\"user_id\": \"u1\"})"
    parsed = a._parse_step(raw)
    assert parsed["type"] == "step"
    assert parsed["thought"] == "I need the balance"
    assert parsed["action"] == "get_balance"
    assert parsed["params"] == {"user_id": "u1"}


def test_parse_step_final_answer(agent):
    a, _, _ = agent
    parsed = a._parse_step("Some intro\nFinal Answer: The answer is 42.")
    assert parsed["type"] == "final"
    assert parsed["answer"] == "The answer is 42."


def test_parse_step_invalid_json_fallback(agent):
    a, _, _ = agent
    parsed = a._parse_step("Thought: I will ask\nAction: coder({not valid json})")
    assert parsed["type"] == "step"
    assert parsed["action"] == "coder"
    assert parsed["params"] == {"request": "{not valid json}"}


@pytest.mark.asyncio
async def test_execute_action_known_tool(agent):
    a, _, tools = agent
    result = await a._execute_action("get_balance", {"user_id": "u1"}, "u1")
    assert result == "ok"
    assert tools.calls == [("get_balance", {"user_id": "u1"})]


@pytest.mark.asyncio
async def test_execute_action_unknown_tool(agent):
    a, _, _ = agent
    result = await a._execute_action("nonexistent", {}, "u1")
    assert "Unknown action" in result


@pytest.mark.asyncio
async def test_execute_action_research(monkeypatch, agent):
    a, _, _ = agent

    class FakeResearch:
        async def research(self, query):
            return {"answer": f"Answer for {query}", "sources": [{"title": "T", "url": "http://x"}]}

    a.research = FakeResearch()
    result = await a._execute_action("research", {"query": "python"}, "u1")
    assert "Answer for python" in result
    assert "http://x" in result


@pytest.mark.asyncio
async def test_run_final_answer(agent, monkeypatch):
    a, mem, _ = agent
    responses = ["Thought: I know it\nFinal Answer: 42"]

    async def fake_generate(*, prompt, format_json=False):
        return responses.pop(0)

    monkeypatch.setattr("core.agent.generate_non_stream", fake_generate)
    events = []
    async for e in a.run(goal="what is the answer", session="s1", user_id="u1"):
        events.append(e)

    assert events[0]["type"] == "final"
    assert events[0]["content"] == "42"
    assert mem.runs[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_run_thought_action_observation(agent, monkeypatch):
    a, mem, tools = agent
    tools.result = "Balance: $100"
    responses = [
        "Thought: I need the balance\nAction: get_balance({})",
        "Final Answer: You have $100."
    ]

    async def fake_generate(*, prompt, format_json=False):
        return responses.pop(0)

    monkeypatch.setattr("core.agent.generate_non_stream", fake_generate)
    events = []
    async for e in a.run(goal="check balance", session="s1", user_id="u1"):
        events.append(e)

    assert events[0]["type"] == "thought"
    assert events[1]["type"] == "action"
    assert events[1]["tool"] == "get_balance"
    assert events[2]["type"] == "observation"
    assert "$100" in events[2]["content"]
    assert events[3]["type"] == "final"
    assert len(mem.steps) == 2  # saved once without observation, once with


@pytest.mark.asyncio
async def test_run_pending_approval(agent, monkeypatch):
    a, mem, tools = agent
    tools.result = "[PENDING: approval required]"
    responses = [
        "Thought: I need to transfer\nAction: transfer_funds({})",
    ]

    async def fake_generate(*, prompt, format_json=False):
        return responses.pop(0)

    monkeypatch.setattr("core.agent.generate_non_stream", fake_generate)
    events = []
    async for e in a.run(goal="send money", session="s1", user_id="u1"):
        events.append(e)

    assert events[-1]["type"] == "pending"
    assert mem.runs[0]["status"] == "pending_approval"


@pytest.mark.asyncio
async def test_run_max_steps(agent, monkeypatch):
    a, mem, _ = agent

    async def fake_generate(*, prompt, format_json=False):
        return "Thought: still thinking\nAction: get_balance({})"

    monkeypatch.setattr("core.agent.generate_non_stream", fake_generate)
    events = []
    async for e in a.run(goal="loop", session="s1", user_id="u1", max_steps=2):
        events.append(e)

    assert events[-1]["type"] == "error"
    assert "maximum steps" in events[-1]["content"].lower()
    assert mem.runs[0]["status"] == "max_steps"


def test_format_tool_descriptions(agent):
    a, _, _ = agent
    desc = a._format_tool_descriptions()
    assert "get_balance" in desc
    assert "research" in desc
    assert "coder" in desc
