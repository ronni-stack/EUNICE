# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — Ollama inference backend."""
import json
import logging
from typing import AsyncGenerator, Optional

import httpx

from core.backends.base import InferenceBackend

logger = logging.getLogger("eunice.backends.ollama")


class OllamaBackend(InferenceBackend):
    """Backend that talks to an Ollama server."""

    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.generate_url = f"{self.base_url}/api/generate"
        self.chat_url = f"{self.base_url}/api/chat"

    async def stream_chat(
        self,
        messages: list,
        model: Optional[str] = None,
        tools: Optional[list] = None,
        temperature: float = 0.7,
        num_predict: int = 512,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        from config import MODEL_NAME

        model = model or MODEL_NAME
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature, "num_predict": num_predict},
        }
        if tools:
            payload["tools"] = tools

        logger.info(f"[OLLAMA] stream_chat request model={model} messages={len(messages)}")
        logger.debug(f"[OLLAMA] stream_chat payload={json.dumps(payload, default=str)[:500]}")

        full_response = ""
        is_tool = False

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", self.chat_url, json=payload) as response:
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
            yield json.dumps({"error": f"Ollama timed out after {self.timeout}s. Try a smaller model or increase EUNICE_OLLAMA_TIMEOUT."})
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

        if is_tool and full_response.strip():
            try:
                parsed = json.loads(full_response.strip())
                if isinstance(parsed, dict) and "tool" in parsed:
                    logger.info(f"[OLLAMA] detected tool_call: {parsed['tool']}")
                    yield json.dumps({"tool_call": True, "tool": parsed["tool"], "params": parsed.get("params", {})})
                    return
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"[OLLAMA] Tool JSON parse failed: {e}")

        yield json.dumps({"done": True, "full": full_response})

    async def generate(
        self,
        prompt: Optional[str] = None,
        messages: Optional[list] = None,
        model: Optional[str] = None,
        format_json: bool = False,
        temperature: float = 0.1,
        num_predict: int = 256,
        **kwargs
    ) -> str:
        from config import MODEL_NAME

        model = model or MODEL_NAME

        if messages:
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": num_predict},
            }
            url = self.chat_url
        else:
            payload = {
                "model": model,
                "prompt": prompt or "",
                "stream": False,
                "options": {"temperature": temperature, "num_predict": num_predict},
            }
            if format_json:
                payload["format"] = "json"
            url = self.generate_url

        logger.info(f"[OLLAMA] generate request model={model} url={url.split('/')[-1]}")
        logger.debug(f"[OLLAMA] generate prompt={prompt[:200]!r}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if messages:
                    result = data.get("message", {}).get("content", "").strip()
                else:
                    result = data.get("response", "").strip()
                logger.info(f"[OLLAMA] generate response_len={len(result)}")
                return result
        except Exception as e:
            logger.exception(f"[OLLAMA] generate failed: {type(e).__name__}: {e}")
            return ""

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception as e:
            logger.warning(f"[OLLAMA] list_models failed: {e}")
            return []
