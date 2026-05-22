"""Minimal Claude agent wrapper around claude-agent-sdk. No tools."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeAgentOptions,
    query,
    get_session_messages,
)
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    UserMessage,
)


@dataclass
class RunResult:
    """Result of a single .run() call."""

    messages: list[dict[str, Any]]
    session_id: str
    cost_usd: float | None
    duration_ms: int
    num_turns: int


class Claude:
    """Tool-less Claude agent.

    System prompt can be changed until the first .run() call.
    Subsequent .run() calls continue the same conversation.
    To start a new conversation, create a new Claude instance.
    """

    DEFAULT_MODEL = "claude-opus-4-7"

    def __init__(
        self,
        log_file: str | Path,
        model: str = DEFAULT_MODEL,
        *,
        system_prompt: str | None = None,
        max_turns: int | None = None,
        env: dict[str, str] | None = None,
    ):
        self.model = model
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.env = env or {}
        self._session_id: str | None = None

        self._log_event(
            "init",
            {
                "model": model,
                "system_prompt": system_prompt or None,
                "max_turns": max_turns,
            },
        )

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def run(self, message: str) -> RunResult:
        """Send a message and run until completion.

        First call starts a new session. Subsequent calls resume it.
        """
        self._log_event(
            "run_start",
            {
                "message": message,
                "session_id": self._session_id,
                "is_followup": self._session_id is not None,
            },
        )

        options = ClaudeAgentOptions(
            model=self.model,
            tools=[],
            permission_mode="bypassPermissions",
            max_turns=self.max_turns,
            env=self.env,
            # Lockdown: no CLAUDE.md, no memory, no MCP, no global hooks
            extra_args={
                "strict-mcp-config": None,
                "setting-sources": "",
            },
            settings=json.dumps({"autoMemoryEnabled": False}),
        )

        if self.system_prompt is not None:
            options.system_prompt = self.system_prompt

        if self._session_id:
            options.resume = self._session_id

        collected: list[dict[str, Any]] = []
        result_info: dict[str, Any] = {}

        try:
            async for msg in query(prompt=message, options=options):
                if isinstance(msg, AssistantMessage):
                    blocks = []
                    for block in msg.content:
                        if hasattr(block, "text"):
                            blocks.append({"type": "text", "text": block.text})
                        elif hasattr(block, "name"):
                            blocks.append(
                                {
                                    "type": "tool_use",
                                    "name": block.name,
                                    "input": block.input,
                                }
                            )
                    collected.append({"role": "assistant", "content": blocks})
                    self._log_event("assistant_message", {"content": blocks})

                elif isinstance(msg, UserMessage):
                    content = (
                        msg.content
                        if isinstance(msg.content, str)
                        else str(msg.content)
                    )
                    collected.append({"role": "user", "content": content})
                    self._log_event("tool_result", {"content": content[:500]})

                elif isinstance(msg, ResultMessage):
                    self._session_id = msg.session_id
                    result_info = {
                        "cost_usd": msg.total_cost_usd,
                        "duration_ms": msg.duration_ms,
                        "num_turns": msg.num_turns,
                    }
        except Exception as e:
            # CLI may exit with code 1 after yielding all messages including
            # ResultMessage. If we got a result, treat it as success.
            if not result_info:
                self._log_event("error", {"error": str(e)})
                raise

        result = RunResult(
            messages=collected,
            session_id=self._session_id or "",
            cost_usd=result_info.get("cost_usd"),
            duration_ms=result_info.get("duration_ms", 0),
            num_turns=result_info.get("num_turns", 0),
        )

        self._log_event(
            "run_complete",
            {
                "session_id": result.session_id,
                "cost_usd": result.cost_usd,
                "duration_ms": result.duration_ms,
                "num_turns": result.num_turns,
                "message_count": len(result.messages),
            },
        )

        return result

    def _log_event(self, event: str, data: dict[str, Any]) -> None:
        """Append a JSONL event to the log file."""
        entry = {
            "ts": time.time(),
            "event": event,
            **data,
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def get_history(self) -> list[dict[str, Any]] | None:
        """Retrieve full session history from SDK."""
        if not self._session_id:
            return None
        msgs = get_session_messages(self._session_id)
        return [{"type": m.type, "uuid": m.uuid, "message": m.message} for m in msgs]
