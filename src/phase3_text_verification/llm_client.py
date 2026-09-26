"""
llm_client.py — OpenAI-compatible HTTP client for local llama-server.

Connects to http://127.0.0.1:8080/v1 (or the URL passed via CLI/env).
Provides a simple `complete()` function that returns the assistant text.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── defaults ────────────────────────────────────────────────────────────────
DEFAULT_BASE_URL = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8080/v1")
DEFAULT_MODEL = os.environ.get("LLM_MODEL_NAME", "gemma-4-e2b")
DEFAULT_TIMEOUT = 120          # seconds per request
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.1      # near-deterministic for proofreading
DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY = 5        # seconds between retries


class LLMClient:
    """Thin wrapper around the OpenAI-compatible /v1/chat/completions endpoint."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model_name: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        max_retries: int = DEFAULT_RETRIES,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer not-needed",
            },
        )

    # ── public API ──────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Return True if the llama-server is reachable and models are listed."""
        try:
            resp = self._client.get("/models", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            models = [m.get("id", "") for m in data.get("data", [])]
            logger.info("LLM server reachable. Available models: %s", models)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("LLM health check failed: %s", exc)
            return False

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        extra_stop: Optional[list[str]] = None,
    ) -> str:
        """
        Send a chat completion request and return the assistant's response text.

        Retries up to `max_retries` times on transient errors.
        Raises `RuntimeError` if all retries fail.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        payload: dict = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False,
        }
        if extra_stop:
            payload["stop"] = extra_stop

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return content.strip()
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Attempt %d/%d HTTP %s: %s",
                    attempt, self.max_retries, exc.response.status_code, exc,
                )
                last_exc = exc
            except (httpx.RequestError, KeyError, IndexError) as exc:
                logger.warning("Attempt %d/%d error: %s", attempt, self.max_retries, exc)
                last_exc = exc

            if attempt < self.max_retries:
                time.sleep(DEFAULT_RETRY_DELAY)

        raise RuntimeError(
            f"LLM request failed after {self.max_retries} attempts. "
            f"Last error: {last_exc}"
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
