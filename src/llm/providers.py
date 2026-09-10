from __future__ import annotations

import asyncio
import json
import random

import aiohttp


class HTTPJSONProvider:
    """OpenAI-compatible provider for Groq/DeepSeek with explicit HTTP errors."""

    def __init__(self, name, url, model, api_key, timeout=60):
        self.name = name
        self.url = url
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    async def extract(self, prompt, schema):
        if not self.api_key:
            raise RuntimeError(f"{self.name}: API key not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "FrontierAtlas/1.0",
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return only valid JSON matching the requested schema. "
                        "Do not invent facts. Preserve source URLs supplied in "
                        "the input."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                self.url, headers=headers, json=payload
            ) as response:
                body = await response.text()

                if response.status >= 400:
                    retry_after = response.headers.get("Retry-After")
                    detail = body[:500]
                    suffix = (
                        f"; Retry-After={retry_after}" if retry_after else ""
                    )
                    raise RuntimeError(
                        f"{self.name} HTTP {response.status}{suffix}: {detail}"
                    )

                try:
                    data = json.loads(body)
                    content = data["choices"][0]["message"]["content"]
                    return json.loads(content)
                except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                    raise RuntimeError(
                        f"{self.name}: invalid JSON response: {body[:500]}"
                    ) from exc


def build_providers(settings):
    from src.llm.gemini import GeminiProvider

    providers = []

    if settings.gemini_api_key:
        providers.append(GeminiProvider(settings.gemini_api_key))

    if settings.groq_api_key:
        providers.append(
            HTTPJSONProvider(
                "groq",
                "https://api.groq.com/openai/v1/chat/completions",
                "openai/gpt-oss-120b",
                settings.groq_api_key,
            )
        )

    if settings.deepseek_api_key:
        providers.append(
            HTTPJSONProvider(
                "deepseek",
                "https://api.deepseek.com/chat/completions",
                "deepseek-chat",
                settings.deepseek_api_key,
            )
        )

    if not providers:
        raise RuntimeError("No LLM providers are configured")

    return providers
