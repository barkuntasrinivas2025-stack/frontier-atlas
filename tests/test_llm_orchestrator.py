import asyncio

from src.llm.orchestrator import LLMOrchestrator


class FakeProvider:
    def __init__(self, name, responses):
        self.name = name
        self.responses = list(responses)
        self.calls = []

    async def extract(self, text, schema):
        self.calls.append(text)
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class Chunk:
    def __init__(self, text):
        self.text = text


class FakeChunker:
    max_tokens = 1000
    overlap_tokens = 100

    def split(self, text):
        return [Chunk(text)]


def test_provider_fallback():
    async def run():
        first = FakeProvider("gemini", [RuntimeError("provider failure")])
        second = FakeProvider("groq", [{"ok": True}])
        result = await LLMOrchestrator(
            [first, second], max_retries=0, chunker=FakeChunker()
        ).extract("hello", {})
        assert result.provider == "groq"
        assert result.payload == {"ok": True}

    asyncio.run(run())


def test_429_retries_then_succeeds(monkeypatch):
    async def run():
        provider = FakeProvider(
            "groq",
            [RuntimeError("HTTP 429"), RuntimeError("HTTP 429"), {"ok": True}],
        )
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(asyncio, "sleep", fake_sleep)
        result = await LLMOrchestrator(
            [provider], max_retries=3, chunker=FakeChunker()
        ).extract("hello", {})
        assert result.payload == {"ok": True}
        assert len(provider.calls) == 3
        assert len(sleeps) == 2

    asyncio.run(run())


def test_413_shrinks_chunk():
    class ShrinkingChunker(FakeChunker):
        max_tokens = 1000
        overlap_tokens = 100

        def split(self, text):
            if len(text) > 20:
                return [Chunk(text[:10]), Chunk(text[10:])]
            return [Chunk(text)]

    async def run():
        provider = FakeProvider("gemini", [{"piece": 1}, {"piece": 2}])
        result = await LLMOrchestrator(
            [provider], max_retries=0, chunker=ShrinkingChunker()
        ).extract("a" * 40, {})
        assert result.provider == "gemini"
        assert result.payload == {"chunks": [{"piece": 1}, {"piece": 2}]}

    asyncio.run(run())
