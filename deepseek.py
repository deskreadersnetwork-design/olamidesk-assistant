"""
deepseek.py — DeepSeek chat API client.

Responsibilities:
- Build the system prompt from the knowledge base.
- Send the user's history + new message to DeepSeek.
- Return plain text, or a safe fallback message on failure.
- Enforce a timeout and never leak the API key in logs.
"""

import logging
from typing import List, Dict

import httpx

from config import Settings
from knowledge_base import build_system_prompt

logger = logging.getLogger(__name__)

# How long to wait for DeepSeek before giving up (seconds).
REQUEST_TIMEOUT = 30.0

# User-facing message when the AI is unavailable.
FALLBACK_MESSAGE = (
    "I'm sorry — I'm having trouble reaching my knowledge service right now. "
    "Please try again in a moment, or use 💬 Talk to Support so a human can help you."
)


class DeepSeekClient:
    """Thin async wrapper around DeepSeek's /chat/completions endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._system_prompt = build_system_prompt()
        self._endpoint = f"{settings.deepseek_base_url}/chat/completions"

    async def reply(self, history: List[Dict[str, str]], user_message: str) -> str:
        """
        Ask DeepSeek for a response.

        `history` is the prior conversation (already in {role, content} form).
        `user_message` is the new message to answer.
        Returns the assistant's text, or FALLBACK_MESSAGE on any failure.
        """
        messages: List[Dict[str, str]] = [{"role": "system", "content": self._system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self._settings.deepseek_model,
            "messages": messages,
            "temperature": 0.6,
            "max_tokens": 600,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self._settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.post(self._endpoint, json=payload, headers=headers)
        except httpx.TimeoutException:
            logger.warning("DeepSeek request timed out after %ss", REQUEST_TIMEOUT)
            return FALLBACK_MESSAGE
        except httpx.HTTPError as exc:
            # Log the exception class only — never the headers (which contain the key).
            logger.warning("DeepSeek network error: %s", type(exc).__name__)
            return FALLBACK_MESSAGE

        if response.status_code != 200:
            # Log status and a short snippet of body; body never contains our key.
            logger.warning(
                "DeepSeek HTTP %s: %s",
                response.status_code,
                response.text[:300].replace("\n", " "),
            )
            return FALLBACK_MESSAGE

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            logger.warning("Unexpected DeepSeek response shape: %s", type(exc).__name__)
            return FALLBACK_MESSAGE

        text = (content or "").strip()
        return text or FALLBACK_MESSAGE
