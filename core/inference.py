"""EUNICE v0.8 — Ollama Inference & Streaming (Hardened)
Added explicit error logging to catch silent failures.
"""
import json
import logging
import httpx
from typing import AsyncGenerator
from config import OLLAMA_URL, MODEL_NAME, OLLAMA_TIMEOUT

logger = logging.getLogger("eunice.inference")

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

    logger.info(f"[OLLAMA] stream_chat request model={MODEL_NAME} messages={len(messages)}")
    logger.debug(f"[OLLAMA] stream_chat payload={json.dumps(payload, default=str)[:500]}")

    full_response = ""
    is_tool = False

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
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
                        logger.warning(f"[OLLAMA] JSON decode error on line: {line[:80]}... | Error: {e}")
                        continue
                    except Exception as e:
                        logger.warning(f"[OLLAMA] Unexpected parse error: {type(e).__name__}: {e}")
                        continue
    except httpx.ConnectError as e:
        logger.error(f"[OLLAMA] ConnectError: {e}")
        yield json.dumps({"error": "Ollama is not running. Start it with: ollama serve"})
        return
    except httpx.ReadTimeout as e:
        logger.error(f"[OLLAMA] ReadTimeout (model took too long to respond): {e}")
        yield json.dumps({"error": f"Ollama timed out after {OLLAMA_TIMEOUT}s. Try a smaller model (e.g. llama3.2:3b) or increase EUNICE_OLLAMA_TIMEOUT."})
        return
    except httpx.ReadError as e:
        logger.error(f"[OLLAMA] ReadError (connection dropped): {e}")
        yield json.dumps({"error": "Connection to Ollama dropped. Retry your message."})
        return
    except Exception as e:
        error_msg = str(e) or f"Unknown inference error: {type(e).__name__}"
        logger.exception(f"[OLLAMA] {error_msg}")
        yield json.dumps({"error": error_msg})
        return

    logger.info(f"[OLLAMA] stream_chat complete response_len={len(full_response)} is_tool={is_tool}")

    # Handle tool call detection at end of stream
    if is_tool and full_response.strip():
        try:
            parsed = json.loads(full_response.strip())
            if isinstance(parsed, dict) and "tool" in parsed:
                logger.info(f"[OLLAMA] detected tool_call: {parsed['tool']}")
                yield json.dumps({"tool_call": True, "tool": parsed["tool"], "params": parsed.get("params", {})})
                return
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"[OLLAMA] Tool JSON parse failed: {e}")
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

    logger.info(f"[OLLAMA] generate_non_stream request model={MODEL_NAME} url={url.split('/')[-1]}")
    logger.debug(f"[OLLAMA] generate_non_stream prompt={prompt[:200]!r}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if messages:
                result = data.get("message", {}).get("content", "").strip()
            else:
                result = data.get("response", "").strip()
            logger.info(f"[OLLAMA] generate_non_stream response_len={len(result)}")
            return result
    except Exception as e:
        logger.exception(f"[OLLAMA] generate_non_stream failed: {type(e).__name__}: {e}")
        return ""
