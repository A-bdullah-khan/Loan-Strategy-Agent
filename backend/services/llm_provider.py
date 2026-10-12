"""Groq LLM utility — Groq is this app's sole LLM provider.

Two entry points, for the two shapes of caller in this codebase:

- `call_llm` — one system/user prompt in, full reply text out. Used by
  `agents.policy_crawler_agent`, which parses the reply as JSON and so
  needs the complete body before it can do anything with it.
- `build_tool_calling_model` — a `langchain_groq.ChatGroq` instance for the
  LangChain tool-calling loop in `mcp_server.agent`; callers bind their own
  tool schemas with `.bind_tools(tools)`.

Both request `reasoning_format="hidden"` — `settings.GROQ_MODEL` defaults to
a reasoning model (`openai/gpt-oss-120b`), which otherwise interleaves its
internal chain-of-thought into the same content stream as its answer. Hiding
it at the API level keeps every reply — and every `mcp_server.agent` tool
loop turn built on top of it — free of leaked scratchpad text.
"""

from __future__ import annotations

import logging

from django.conf import settings
from groq import Groq, GroqError
from langchain_groq import ChatGroq

logger = logging.getLogger(__name__)

GROQ_ERROR_MESSAGE = (
    "GROQ_API_KEY is missing or invalid. Please check backend .env file."
)


class LLMProviderError(RuntimeError):
    """Raised when Groq isn't configured, or fails to answer a request."""


# Lazily built, module-level so the SDK client (and its underlying HTTP
# connection pool) isn't reconstructed on every call.
_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if not settings.GROQ_API_KEY:
        raise LLMProviderError(GROQ_ERROR_MESSAGE)
    if _client is None:
        _client = Groq(api_key=settings.GROQ_API_KEY)
    return _client


def call_llm(
    system_prompt: str,
    user_prompt: str,
    response_format_json: bool = False,
    temperature: float = 0,
) -> str:
    """Answers one system/user prompt via Groq and returns the full reply text.

    Args:
        system_prompt: The system/instruction message.
        user_prompt: The user message.
        response_format_json: When True, asks Groq to return a raw JSON
            object (no markdown fences) instead of free text.
        temperature: Sampling temperature.

    Returns:
        The reply text.

    Raises:
        LLMProviderError: If `GROQ_API_KEY` isn't configured, or the Groq
            API call fails (rate limit, connection error, bad request, ...).
    """
    try:
        completion = _get_client().chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            response_format={"type": "json_object"} if response_format_json else None,
            reasoning_format="hidden",
        )
        return completion.choices[0].message.content or ""
    except GroqError as exc:
        logger.exception("Groq API call failed")
        raise LLMProviderError(str(exc)) from exc


def build_tool_calling_model(temperature: float = 0) -> ChatGroq:
    """Returns a `ChatGroq` chat model for the LangChain tool-calling agent loop.

    Callers bind their tool schemas themselves, e.g.
    `build_tool_calling_model().bind_tools(tools)` (see
    `mcp_server.agent.run_chat_agent`).

    Raises:
        LLMProviderError: If `GROQ_API_KEY` isn't configured.
    """
    if not settings.GROQ_API_KEY:
        raise LLMProviderError(GROQ_ERROR_MESSAGE)
    return ChatGroq(
        model=settings.GROQ_MODEL,
        api_key=settings.GROQ_API_KEY,
        temperature=temperature,
        reasoning_format="hidden",
    )
