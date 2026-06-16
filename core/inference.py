"""EUNICE v0.6 — Ollama Inference & Streaming (Hardened)
Added explicit error logging to catch silent failures.
"""
import json
import httpx
from typing import AsyncGenerator
from config import OLLAMA_URL, MODEL_NAME

OLLAMA_GENERATE_URL = f"{OLLAMA_URL}/api/generate"
OLLAMA_CHAT_URL = f"{OLLAMA_URL}/api/chat"

async def stream_chat(messages: list, tools: list = None) -> AsyncGenerator[str, None]:
    """Stream chat completion from Ollama. Yields JSON strings."""
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": True,
        "options": {"temperature": 0.7, "num_predict": 512}
    }

    full_response = ""
    is_tool = False

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream("POST", OLLAMA_CHAT_URL, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("done"):
                            break
                        token = data.get("message", {}).get("content", "")
                        if token:
                            full_response += token
                            # Detect tool call pattern
                            if full_response.strip().startswith("{") and '"tool"' in full_response:
                                is_tool = True
                            elif not is_tool:
                                yield json.dumps({"token": token, "done": False})
                    except json.JSONDecodeError as e:
                        print(f"[INFERENCE WARN] JSON decode error on line: {line[:80]}... | Error: {e}")
                        continue
                    except Exception as e:
                        print(f"[INFERENCE WARN] Unexpected parse error: {type(e).__name__}: {e}")
                        continue
    except httpx.ConnectError as e:
        print(f"[INFERENCE ERROR] ConnectError: {e}")
        yield json.dumps({"error": "Ollama is not running. Start it with: ollama serve"})
        return
    except httpx.ReadError as e:
        print(f"[INFERENCE ERROR] ReadError (connection dropped): {e}")
        yield json.dumps({"error": "Connection to Ollama dropped. Retry your message."})
        return
    except Exception as e:
        error_msg = str(e) or f"Unknown inference error: {type(e).__name__}"
        print(f"[INFERENCE ERROR] {error_msg}")
        yield json.dumps({"error": error_msg})
        return

    # Handle tool call detection at end of stream
    if is_tool and full_response.strip():
        try:
            parsed = json.loads(full_response.strip())
            if isinstance(parsed, dict) and "tool" in parsed:
                yield json.dumps({"tool_call": True, "tool": parsed["tool"], "params": parsed.get("params", {})})
                return
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[INFERENCE WARN] Tool JSON parse failed: {e}")
            pass

    yield json.dumps({"done": True, "full": full_response})

async def generate_non_stream(messages: list = None, prompt: str = None, format_json: bool = False) -> str:
    """Non-streaming generation for background tasks and dynamic denials.
    Accepts either messages list or raw prompt string.
    """
    if messages:
        payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.8, "num_predict": 128}
        }
        url = OLLAMA_CHAT_URL
    else:
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt or "",
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 256}
        }
        if format_json:
            payload["format"] = "json"
        url = OLLAMA_GENERATE_URL

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if messages:
                return data.get("message", {}).get("content", "").strip()
            return data.get("response", "").strip()
    except Exception as e:
        print(f"[INFERENCE ERROR] generate_non_stream failed: {type(e).__name__}: {e}")
        return ""
