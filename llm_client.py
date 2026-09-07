"""
LLM client — OpenAI-compatible wrapper supporting MaaS and standard OpenAI endpoints.
Provides text review, summarization, explanation, and streaming chat.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Generator, Iterator

MAAS_BASE_URL = "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3.6-flash"

_REVIEW_SYSTEM = (
    "You are a text formatting assistant for a Text-to-Speech system. "
    "Clean and format the text so it reads naturally when spoken aloud. "
    "Fix paragraph breaks and hyphenation artifacts. Expand abbreviations. "
    "Remove tables, code blocks, and markdown formatting. "
    "Keep the original meaning and language (Portuguese or English). "
    "Return ONLY the cleaned text with no commentary or explanation."
)

_SUMMARIZE_SYSTEM = (
    "You are a document summarization assistant. "
    "Create a clear, concise summary preserving key facts and main points. "
    "Format the output as natural prose in the same language as the input."
)

_EXPLAIN_SYSTEM = (
    "You are a document explanation assistant. "
    "Explain the content clearly, as if to someone unfamiliar with the topic. "
    "Use simple language and highlight key concepts. "
    "Respond in the same language as the document."
)

_TRANSLATE_SYSTEM = (
    "You translate technical documents accurately. Preserve formulas, LaTeX, code, "
    "citations, names, and units exactly. Translate only natural-language prose and "
    "return only the translated document with no commentary."
)

_CHAT_SYSTEM = (
    "You are an intelligent document assistant. "
    "Help the user understand, summarize, and explore the provided document. "
    "Be concise and answer in the same language the user writes in."
)


class LLMClient:
    """OpenAI-compatible client for MaaS and OpenAI-pattern APIs."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", MAAS_BASE_URL)).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODEL)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_client(self):
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "openai package is not installed. Run: pip install openai"
            ) from exc
        return OpenAI(api_key=self.api_key or "no-key", base_url=self.base_url)

    def _complete(self, system: str, user: str) -> str:
        client = self._make_client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            stream=False,
        )
        return response.choices[0].message.content.strip()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def review_text(self, text: str) -> str:
        """Review and reformat text for TTS. Returns cleaned text."""
        return self._complete(_REVIEW_SYSTEM, text)

    def summarize(self, text: str) -> str:
        """Summarize a document or chapter."""
        return self._complete(_SUMMARIZE_SYSTEM, text)

    def explain(self, text: str) -> str:
        """Explain the content in simple terms."""
        return self._complete(_EXPLAIN_SYSTEM, text)

    def translate(self, text: str, target_language: str) -> str:
        """Translate prose while preserving technical notation."""
        return self._complete(
            _TRANSLATE_SYSTEM,
            f"Translate the following document to {target_language}:\n\n{text}",
        )

    def test_connection(self) -> bool:
        """Verify the API is reachable. Returns True on success."""
        try:
            result = self._complete("Reply with one word: ok", "ping")
            return bool(result)
        except Exception:
            return False

    def chat_stream(
        self,
        messages: list[dict],
        document_context: str | None = None,
    ) -> Iterator[str]:
        """Stream chat completions. Yields text delta strings."""
        client = self._make_client()
        system_content = _CHAT_SYSTEM
        if document_context:
            # Truncate to avoid exceeding context limits
            system_content += f"\n\n---\nDocumento:\n{document_context[:12000]}"

        full_messages = [{"role": "system", "content": system_content}] + messages
        stream = client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# ---------------------------------------------------------------------------
# Module-level singleton — updated via PUT /api/llm/config
# ---------------------------------------------------------------------------
_client: LLMClient | None = None
_lock = threading.Lock()


def get_llm_client() -> LLMClient:
    global _client
    with _lock:
        if _client is None:
            _client = LLMClient()
        return _client


def update_llm_client(api_key: str, base_url: str, model: str) -> LLMClient:
    global _client
    with _lock:
        _client = LLMClient(api_key=api_key, base_url=base_url, model=model)
        return _client
