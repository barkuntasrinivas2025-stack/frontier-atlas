from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any

from src.extraction.chunker import IntelligentChunker


@dataclass
class ProviderResult:
    provider: str
    payload: dict


class LLMOrchestrator:
    """Reliable tiered LLM extraction.

    Provider order is supplied by build_providers(): Gemini -> Groq -> DeepSeek.
    429s are retried with exponential backoff and jitter. 413/too-large errors
    trigger adaptive chunk shrinking before the same provider is abandoned.
    """

    def __init__(
        self,
        providers,
        max_retries: int = 4,
        chunker=None,
        max_chunk_reductions: int = 4,
    ):
        self.providers = providers
        self.max_retries = max_retries
        self.chunker = chunker or IntelligentChunker()
        self.max_chunk_reductions = max_chunk_reductions

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        msg = str(exc).lower()
        return "429" in msg or "rate limit" in msg or "too many requests" in msg

    @staticmethod
    def _is_too_large(exc: Exception) -> bool:
        msg = str(exc).lower()
        return (
            "413" in msg
            or "payload too large" in msg
            or "request entity too large" in msg
            or "too large" in msg
            or "context length" in msg
            or "maximum context" in msg
        )

    async def _call_with_retry(self, provider, text, schema):
        last = None
        for attempt in range(self.max_retries + 1):
            try:
                return await provider.extract(text, schema)
            except Exception as exc:
                last = exc
                if not self._is_rate_limited(exc) or attempt >= self.max_retries:
                    raise

                delay = min(30.0, 2.0 ** attempt) + random.uniform(0.1, 0.8)
                await asyncio.sleep(delay)
        raise last

    def _split_smaller(self, text: str, current_tokens: int):
        next_tokens = max(100, current_tokens // 2)
        overlap = min(100, max(0, next_tokens // 10))
        if next_tokens >= current_tokens:
            return []
        return IntelligentChunker(
            max_tokens=next_tokens,
            overlap_tokens=overlap,
        ).split(text)

    async def _extract_with_provider(self, provider, text, schema):
        current_chunker = self.chunker
        chunks = current_chunker.split(text)
        results = []

        for chunk in chunks:
            current_text = chunk.text
            current_tokens = getattr(current_chunker, "max_tokens", 1000)

            for reduction in range(self.max_chunk_reductions + 1):
                try:
                    results.append(
                        await self._call_with_retry(provider, current_text, schema)
                    )
                    break
                except Exception as exc:
                    if not self._is_too_large(exc):
                        raise

                    if reduction >= self.max_chunk_reductions:
                        raise

                    smaller = self._split_smaller(current_text, current_tokens)
                    if not smaller:
                        raise

                    # A 413 applies to the current chunk. Process its smaller
                    # pieces independently and stop reducing this chunk.
                    for small in smaller:
                        results.append(
                            await self._call_with_retry(provider, small.text, schema)
                        )
                    break

        if not results:
            raise RuntimeError(f"{provider.name}: no extraction results")

        payload: Any = results[0] if len(results) == 1 else {"chunks": results}
        return ProviderResult(provider.name, payload)

    async def extract(self, text: str, schema):
        if not text or not text.strip():
            raise ValueError("Cannot extract from empty text")

        last_error = None
        for provider in self.providers:
            try:
                return await self._extract_with_provider(provider, text, schema)
            except Exception as exc:
                last_error = exc
                # Move to the next tier. The exception is retained for a useful
                # final diagnostic; individual provider failures do not abort
                # the complete extraction pipeline.
                continue

        raise RuntimeError(f"All LLM providers failed: {last_error}")
