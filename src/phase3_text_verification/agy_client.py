"""
agy_client.py — Drop-in LLM client that uses the Antigravity CLI (agy).

Replaces the HTTP-based LLMClient for Phase 3 verification.
Calls `agy --model <model> --output-format text --print "<prompt>"` as a
subprocess and returns stdout as the assistant response.

Same public interface as LLMClient:
    client.complete(system_prompt, user_message) -> str
    client.health_check() -> bool
    Context-manager support (__enter__ / __exit__)
"""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── defaults ─────────────────────────────────────────────────────────────────
DEFAULT_MODEL = "gemini-3.6-flash-low"
DEFAULT_TIMEOUT = 120          # seconds per subprocess call
DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY = 5        # seconds between retries


class AgyClient:
    """
    Thin wrapper around `agy --print` for Phase 3 OCR verification.

    The system prompt and user message are concatenated with a clear
    XML-style delimiter so the model sees both in a single --print call.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_RETRIES,
    ) -> None:
        self.model_name = model_name
        self.timeout = timeout
        self.max_retries = max_retries

    # ── public API ────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Return True if `agy models` exits cleanly (AGY is reachable)."""
        try:
            result = subprocess.run(
                ["agy", "models"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info(
                    "AGY reachable. Available models snippet:\n%s",
                    result.stdout[:300],
                )
                return True
            logger.error("agy models failed (exit %d): %s", result.returncode, result.stderr)
            return False
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.error("AGY health check failed: %s", exc)
            return False

    def complete(
        self,
        system_prompt: str,
        user_message: str,
        extra_stop: Optional[list[str]] = None,  # kept for interface parity, unused
    ) -> str:
        """
        Send system + user prompt via `agy --print` and return the response.

        The two parts are joined with an XML-style delimiter so the model
        receives clear role separation even in a single --print call.

        Retries up to `max_retries` times on non-zero exit codes.
        Raises `RuntimeError` if all retries fail.
        """
        combined_prompt = (
            f"<system>\n{system_prompt}\n</system>\n\n"
            f"<user>\n{user_message}\n</user>"
        )

        cmd = [
            "agy",
            "--model", self.model_name,
            "--output-format", "text",
            "--print", combined_prompt,
        ]

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
                if result.returncode == 0:
                    return result.stdout.strip()

                err = result.stderr.strip() or result.stdout.strip()
                logger.warning(
                    "Attempt %d/%d — agy exited %d: %s",
                    attempt, self.max_retries, result.returncode, err[:300],
                )
                last_exc = RuntimeError(
                    f"agy exited {result.returncode}: {err[:200]}"
                )

            except subprocess.TimeoutExpired as exc:
                logger.warning(
                    "Attempt %d/%d — agy timed out after %.0fs",
                    attempt, self.max_retries, self.timeout,
                )
                last_exc = exc

            if attempt < self.max_retries:
                time.sleep(DEFAULT_RETRY_DELAY)

        raise RuntimeError(
            f"agy request failed after {self.max_retries} attempts. "
            f"Last error: {last_exc}"
        )

    # ── context-manager support (no-op, kept for interface parity) ───────────

    def close(self) -> None:
        pass

    def __enter__(self) -> "AgyClient":
        return self

    def __exit__(self, *_: object) -> None:
        pass
