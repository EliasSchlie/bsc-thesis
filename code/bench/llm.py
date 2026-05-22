"""OpenAI-compatible chat client. Used for both target models (via any OpenAI-compat
endpoint -- Nebius, OpenRouter, OpenAI itself) and the GPT-5.4-nano judge.

Decoding params: temperature=0.0, top_p=0.95 (match upstream DeceptionBench,
https://github.com/Aries-iai/DeceptionBench/blob/main/config.py#L11-L16).
max_tokens defaults to 16384 (raised from upstream's 500) to give reasoning
models generous headroom for internal CoT plus the required thought+response
JSON; unused tokens do not bill, so the cap is generous on purpose. Judge
callers override to a tighter cap via JUDGE_MAX_TOKENS (default 500, since
judge output mean is ~90 tokens). Retries 3 times with exponential backoff
(1s, 2s, 4s). Post-processing strips newlines and markdown code fences
(https://github.com/Aries-iai/DeceptionBench/blob/main/utils.py#L27-L28);
raw text is kept too so nothing is lost.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    """One chat completion call's full record. Everything needed to avoid re-running."""

    raw_text: str
    cleaned_text: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    latency_ms: int
    attempts: int
    error: str | None = None
    request: dict[str, Any] = field(default_factory=dict)
    reasoning: str | None = None
    reasoning_tokens: int | None = None
    response_full: dict[str, Any] | None = None


def _clean(text: str) -> str:
    return text.replace("\n", " ").replace("```json", "").replace("```", "").strip()


def _needs_max_completion_tokens(model: str) -> bool:
    """GPT-5 and o1/o3/o4 reasoning models require `max_completion_tokens`.

    Matches bare IDs (e.g. `gpt-5.4`) and provider-prefixed slugs
    (e.g. `openai/gpt-5.4` via OpenRouter).
    """
    m = model.lower().rsplit("/", 1)[-1]
    return (
        m.startswith("gpt-5")
        or m.startswith("o1")
        or m.startswith("o3")
        or m.startswith("o4")
    )


class OpenAICompatClient:
    """Thin wrapper around the OpenAI Python SDK for any OpenAI-compatible endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        *,
        default_model: str,
        max_tokens: int = 16384,
        temperature: float = 0.0,
        top_p: float = 0.95,
        retries: int = 3,
        use_max_completion_tokens: bool | None = None,
        max_connections: int = 1000,
        extra_body: dict[str, Any] | None = None,
    ):
        http_client = httpx.Client(
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_connections,
            ),
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        kwargs = {"api_key": api_key, "http_client": http_client}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self.default_model = default_model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.retries = retries
        if use_max_completion_tokens is None:
            use_max_completion_tokens = _needs_max_completion_tokens(default_model)
        self.use_max_completion_tokens = use_max_completion_tokens
        self.extra_body = extra_body or None

    def chat(
        self,
        *,
        system: str | None,
        user: str,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        msgs: list[dict[str, str]] = []
        if system is not None:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": user})

        resolved_model = model or self.default_model
        use_mct = (
            _needs_max_completion_tokens(resolved_model)
            if model is not None
            else self.use_max_completion_tokens
        )
        token_budget = max_tokens or self.max_tokens
        req: dict[str, Any] = {
            "model": resolved_model,
            "messages": msgs,
            "top_p": self.top_p,
        }
        if use_mct:
            req["max_completion_tokens"] = token_budget
        else:
            req["max_tokens"] = token_budget
            req["temperature"] = self.temperature

        last_err: str | None = None
        for attempt in range(1, self.retries + 1):
            t0 = time.monotonic()
            try:
                if self.extra_body:
                    resp = self._client.chat.completions.create(
                        **req, extra_body=self.extra_body
                    )
                else:
                    resp = self._client.chat.completions.create(**req)
                latency_ms = int((time.monotonic() - t0) * 1000)
                msg = resp.choices[0].message
                raw = msg.content or ""
                reasoning = getattr(msg, "reasoning", None) or getattr(
                    msg, "reasoning_content", None
                )
                try:
                    response_full = resp.model_dump()
                except Exception:
                    response_full = None
                usage = resp.usage
                reasoning_tokens = None
                if response_full:
                    u = response_full.get("usage") or {}
                    ctd = (
                        u.get("completion_tokens_details")
                        if isinstance(u, dict)
                        else None
                    )
                    if isinstance(ctd, dict):
                        reasoning_tokens = ctd.get("reasoning_tokens")
                return ChatResult(
                    raw_text=raw,
                    cleaned_text=_clean(raw),
                    model=resolved_model,
                    prompt_tokens=getattr(usage, "prompt_tokens", None),
                    completion_tokens=getattr(usage, "completion_tokens", None),
                    total_tokens=getattr(usage, "total_tokens", None),
                    latency_ms=latency_ms,
                    attempts=attempt,
                    request=req,
                    reasoning=reasoning,
                    reasoning_tokens=reasoning_tokens,
                    response_full=response_full,
                )
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                logger.warning(
                    "chat attempt %d/%d failed: %s", attempt, self.retries, last_err
                )
                if attempt < self.retries:
                    time.sleep(2 ** (attempt - 1))

        return ChatResult(
            raw_text="",
            cleaned_text="",
            model=resolved_model,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            latency_ms=0,
            attempts=self.retries,
            error=last_err,
            request=req,
        )
