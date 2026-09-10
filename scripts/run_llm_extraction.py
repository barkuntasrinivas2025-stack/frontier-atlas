import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.settings import get_settings
from src.extraction.chunker import IntelligentChunker
from src.llm.orchestrator import LLMOrchestrator
from src.llm.providers import build_providers


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", help="Text to extract from")
    parser.add_argument("--file", help="Read extraction text from a UTF-8 file")
    args = parser.parse_args()

    if bool(args.text) == bool(args.file):
        parser.error("provide exactly one of --text or --file")

    text = (
        args.text
        if args.text is not None
        else Path(args.file).read_text(encoding="utf-8")
    )

    settings = get_settings()
    providers = build_providers(settings)

    result = await LLMOrchestrator(
        providers,
        chunker=IntelligentChunker(),
    ).extract(
        text,
        {"type": "object"},
    )

    print(
        json.dumps(
            {
                "provider": result.provider,
                "payload": result.payload,
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(main())
