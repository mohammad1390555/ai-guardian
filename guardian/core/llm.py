# ─── Made by Mohammad — github.com/mohammad1390555 ───
"""LLM client built on the OpenAI SDK with retry, backoff, and reasoning support."""

from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore


class LLMError(Exception):
    """Raised when the model call fails after retries."""


class LLMClient:
    """Thin wrapper around an OpenAI-compatible endpoint."""

    def __init__(self, config) -> None:
        if OpenAI is None:
            raise LLMError("The 'openai' package is not installed. Run: pip install openai")
        self.config = config
        self.client = OpenAI(
            base_url=config.get("provider.base_url"),
            api_key=config.resolve_api_key(),
            timeout=float(config.get("generation.request_timeout", 300)),
        )
        self.requests_used = 0
        self.tokens_used = 0

    # ------------------------------------------------------------------

    def chat(self, messages: List[Dict[str, str]], max_retries: int = 3) -> Dict[str, Any]:
        """Send a chat completion and return {'content', 'reasoning', 'raw'}."""
        gen = self.config.data.get("generation", {})
        reasoning_cfg = gen.get("reasoning", {})
        extra_body: Dict[str, Any] = {}
        if reasoning_cfg.get("enabled"):
            extra_body["chat_template_kwargs"] = {
                "thinking": True,
                "reasoning_effort": reasoning_cfg.get("effort", "high"),
            }

        kwargs: Dict[str, Any] = dict(
            model=self.config.get("provider.model"),
            messages=messages,
            temperature=gen.get("temperature", 1),
            top_p=gen.get("top_p", 0.95),
            max_tokens=int(gen.get("max_tokens", 16384)),
            stream=bool(gen.get("stream", False)),
        )
        if extra_body:
            kwargs["extra_body"] = extra_body

        last_error: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                completion = self.client.chat.completions.create(**kwargs)
                self.requests_used += 1
                usage = getattr(completion, "usage", None)
                if usage is not None:
                    self.tokens_used += int(getattr(usage, "total_tokens", 0) or 0)
                message = completion.choices[0].message
                reasoning = (
                    getattr(message, "reasoning", None)
                    or getattr(message, "reasoning_content", None)
                    or ""
                )
                return {"content": message.content or "", "reasoning": reasoning,
                        "raw": completion}
            except Exception as exc:  # noqa: BLE001 - deliberate broad catch with backoff
                last_error = exc
                wait = min(2 ** attempt * 2, 60)
                if _is_rate_limit(exc):
                    wait = min(2 ** attempt * 5, 120)
                wait += random.uniform(0, 1)  # jitter to prevent thundering herd
                if attempt < max_retries:
                    time.sleep(wait)
        raise LLMError(f"Model request failed after {max_retries} attempts: {last_error}")


def _is_rate_limit(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status == 429:
        return True
    text = str(exc).lower()
    return "rate limit" in text or "too many requests" in text
