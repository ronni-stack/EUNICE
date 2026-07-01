# # EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""EUNICE Enterprise — LocalAI inference backend.

LocalAI exposes an OpenAI-compatible API, so this backend maps EUNICE's
backend-agnostic interface to `/v1/chat/completions` and `/v1/completions`.
"""
import json
import logging
from typing import AsyncGenerator, Optional

import httpx

from core.backends.base import InferenceBackend

logger = logging.getLogger("eunice.backends.localai")


class LocalAIBackend(InferenceBackend):
    """Backend that talks to a LocalAI (OpenAI-compatible) server."""

    name = "localai"

    def __init__(self, base_url: str = "http://localhost:8080", timeout: float = 300.0, api_key: str = "dummy"):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.chat_url = f"{self.base_url}/v1/chat/completions"
        self.completions_url = f"{self.base_url}/v1/completions"
        self.models_url = f"{self.base_url}/v1/models"

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
            "temperature": temperature,
            "max_tokens": num_predict,
        }
        if tools:
            payload["tools"] = tools

        logger.info(f"[LOCALAI] stream_chat request model={model} messages={len(messages)}")
        logger.debug(f"[LOCALAI] stream_chat payload={json.dumps(payload, default=str)[:500]}")

        full_response = ""
        is_tool = False

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", self.chat_url, json=payload, headers=self.headers) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or line == "data: [DONE]":
                            continue
                        if not line.startswith("data: "):
                            continue
                        try:
                            data = json.loads(line[6:])
                            if data.get("choices"):
                                delta = data["choices"][0].get("delta", {})
                                token = delta.get("content", "")
                                if token:
                                    full_response += token
                                    if full_response.strip().startswith("{") and '"tool"' in full_response:
                                        is_tool = True
                                    elif not is_tool:
                                        yield json.dumps({"token": token, "done": False})
                        except json.JSONDecodeError as e:
                            logger.warning(f"[LOCALAI] JSON decode error: {e}")
                            continue
                        except Exception as e:
                            logger.warning(f"[LOCALAI] Unexpected parse error: {type(e).__name__}: {e}")
                            continue
        except httpx.ConnectError as e:
            logger.error(f"[LOCALAI] ConnectError: {e}")
            yield json.dumps({"error": f"LocalAI is not running at {self.base_url}"})
            return
        except httpx.ReadTimeout as e:
            logger.error(f"[LOCALAI] ReadTimeout: {e}")
            yield json.dumps({"error": f"LocalAI timed out after {self.timeout}s."})
            return
        except Exception as e:
            error_msg = str(e) or f"Unknown inference error: {type(e).__name__}"
            logger.exception(f"[LOCALAI] {error_msg}")
            yield json.dumps({"error": error_msg})
            return

        logger.info(f"[LOCALAI] stream_chat complete response_len={len(full_response)} is_tool={is_tool}")

        if is_tool and full_response.strip():
            try:
                parsed = json.loads(full_response.strip())
                if isinstance(parsed, dict) and "tool" in parsed:
                    logger.info(f"[LOCALAI] detected tool_call: {parsed['tool']}")
                    yield json.dumps({"tool_call": True, "tool": parsed["tool"], "params": parsed.get("params", {})})
                    return
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"[LOCALAI] Tool JSON parse failed: {e}")

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
                "temperature": temperature,
                "max_tokens": num_predict,
            }
            url = self.chat_url
        else:
            payload = {
                "model": model,
                "prompt": prompt or "",
                "stream": False,
                "temperature": temperature,
                "max_tokens": num_predict,
            }
            url = self.completions_url

        if format_json:
            payload["response_format"] = {"type": "json_object"}

        logger.info(f"[LOCALAI] generate request model={model} url={url.split('/')[-1]}")
        logger.debug(f"[LOCALAI] generate prompt={prompt[:200]!r}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=self.headers)
                resp.raise_for_status()
                data = resp.json()
                if messages:
                    result = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                else:
                    result = data.get("choices", [{}])[0].get("text", "").strip()
                logger.info(f"[LOCALAI] generate response_len={len(result)}")
                return result
        except Exception as e:
            logger.exception(f"[LOCALAI] generate failed: {type(e).__name__}: {e}")
            return ""

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.models_url, headers=self.headers)
                resp.raise_for_status()
                data = resp.json()
                return [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        except Exception as e:
            logger.warning(f"[LOCALAI] list_models failed: {e}")
            return []
