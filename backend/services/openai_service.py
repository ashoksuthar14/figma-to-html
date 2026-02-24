"""OpenAI GPT-4 API wrapper with retry logic and vision support."""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass
from typing import Optional

from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APIStatusError

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class GPTResponse:
    """Structured response from a GPT-4 API call."""
    content: str
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def was_truncated(self) -> bool:
        """Check if the response was truncated due to max_tokens."""
        return self.finish_reason == "length"

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    """Lazy-initialize the OpenAI async client."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


async def call_gpt4(
    system_prompt: str,
    user_prompt: str,
    images: Optional[list[bytes]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
    image_detail: str = "high",
) -> GPTResponse:
    """Call GPT-4 (or GPT-4o) with retry logic.

    Args:
        system_prompt: The system message setting the AI's role.
        user_prompt: The user message with the task.
        images: Optional list of PNG image bytes to include (vision mode).
        temperature: Sampling temperature (default from settings).
        max_tokens: Max response tokens (default from settings).
        model: Model override (default from settings).
        image_detail: Detail level for vision images ("high", "low", or "auto").

    Returns:
        GPTResponse with content, finish_reason, and token usage.

    Raises:
        RuntimeError: If all retry attempts fail.
    """
    client = _get_client()
    temp = temperature if temperature is not None else settings.OPENAI_TEMPERATURE
    tokens = max_tokens if max_tokens is not None else settings.OPENAI_MAX_TOKENS
    mdl = model or settings.OPENAI_MODEL

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
    ]

    if images:
        user_content: list[dict] = [{"type": "text", "text": user_prompt}]
        for img_bytes in images:
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{b64}",
                    "detail": image_detail,
                },
            })
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": user_prompt})

    max_retries = 3
    last_error: Optional[Exception] = None

    _NEW_TOKEN_PARAM_MODELS = ("gpt-5", "o1", "o3", "o4")
    use_new_param = any(mdl.startswith(prefix) for prefix in _NEW_TOKEN_PARAM_MODELS)

    token_kwargs = (
        {"max_completion_tokens": tokens}
        if use_new_param
        else {"max_tokens": tokens}
    )

    for attempt in range(max_retries):
        try:
            response = await client.chat.completions.create(
                model=mdl,
                messages=messages,
                temperature=temp,
                **token_kwargs,
            )
            choice = response.choices[0]
            content = choice.message.content
            if content is None:
                content = ""

            finish_reason = choice.finish_reason or "stop"
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0

            logger.info(
                "GPT-4 call succeeded on attempt %d, tokens used: prompt=%d completion=%d, finish_reason=%s",
                attempt + 1, prompt_tokens, completion_tokens, finish_reason,
            )

            if finish_reason == "length":
                logger.warning(
                    "GPT-4 response was TRUNCATED (finish_reason=length, completion_tokens=%d/%d)",
                    completion_tokens, tokens,
                )

            return GPTResponse(
                content=content,
                finish_reason=finish_reason,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        except RateLimitError as e:
            last_error = e
            wait_time = 2 ** (attempt + 1)
            logger.warning(
                "Rate limited on attempt %d, waiting %ds: %s",
                attempt + 1, wait_time, e,
            )
            await asyncio.sleep(wait_time)

        except APIConnectionError as e:
            last_error = e
            wait_time = 2 ** attempt
            logger.warning(
                "Connection error on attempt %d, waiting %ds: %s",
                attempt + 1, wait_time, e,
            )
            await asyncio.sleep(wait_time)

        except APIStatusError as e:
            last_error = e
            if e.status_code >= 500:
                wait_time = 2 ** attempt
                logger.warning(
                    "Server error %d on attempt %d, waiting %ds",
                    e.status_code, attempt + 1, wait_time,
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error("API error (non-retryable): %s", e)
                raise RuntimeError(f"OpenAI API error: {e}") from e

    raise RuntimeError(
        f"Failed after {max_retries} attempts. Last error: {last_error}"
    )


async def call_gpt4_text(
    system_prompt: str,
    user_prompt: str,
    images: Optional[list[bytes]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
    image_detail: str = "high",
) -> str:
    """Call GPT-4 and return just the text content (backward-compatible wrapper).

    Same arguments as call_gpt4(). Returns only the response text string.
    """
    result = await call_gpt4(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        images=images,
        temperature=temperature,
        max_tokens=max_tokens,
        model=model,
        image_detail=image_detail,
    )
    return result.content


def count_tokens_estimate(text: str) -> int:
    """Rough token count estimate (4 chars per token heuristic).

    For precise counting, use tiktoken. This is a fast approximation
    used for budget checks before making API calls.
    """
    return max(1, len(text) // 4)
