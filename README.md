# Frontier Atlas — AI Data Intelligence Ingestion

Production-oriented take-home implementation for large-scale AI data acquisition, extraction, entity resolution and evaluator-facing export.

## What is implemented

- **Phase I:** ArXiv/Papers with Code research acquisition, GitHub repository/star enrichment, YC AI startup acquisition and Product Hunt product acquisition.
- **Phase II:** five AI news feeds and five job sources, AI relevance filtering, full-text crawling for news, publication-date normalization and strict previous-24-hour freshness validation.
- **Phase III:** Gemini Flash → Groq Llama → DeepSeek provider fallback, schema-oriented JSON extraction, intelligent chunking, HTTP 413 recovery and HTTP 429 exponential backoff/jitter.
- **Phase IV:** deterministic normalization and seeded entity resolution with conservative fuzzy matching.
- **Phase V:** asyncio/aiohttp bounded concurrency, retries, checkpoints and compliant JS-rendered-page strategy. CAPTCHA/challenge bypass is explicitly not implemented.
- **Phase VI:** architecture document covering 500k+ scale, reliability, distributed freshness/dedup and storage choices.

## Core principles

1. **No hallucinated records.** Final records require source provenance and schema validation.
2. **Idempotency.** `(record_type, source_url)` is the entity uniqueness boundary; acquisition checkpoints make long jobs resumable.
3. **Freshness first.** Phase II rejects stale, future-dated and undated records rather than guessing.
4. **Bounded work.** Semaphores, database pools and chunk limits prevent unbounded resource growth.
5. **Auditability.** Raw observations, source URLs, timestamps, hashes and mapping decisions are retained.

## Run locally

```bash
cp .env.example .env
# fill API keys and Google Sheet settings as needed
docker compose up -d postgres redis
docker compose build app
docker compose run --rm app python -m src.main
docker compose run --rm app pytest -q
```

On Windows the database bootstrap uses `SelectorEventLoop` to avoid async PostgreSQL event-loop incompatibilities.

## Acquisition examples

```bash
python scripts/run_phase1_arxiv.py
python scripts/run_phase1_startups_products.py
python scripts/run_all_phase2.py
```

The Papers with Code acquisition expects a downloaded public snapshot because bulk historical acquisition should be streamed locally rather than issuing hundreds of small API requests. GitHub enrichment uses the public GitHub API and should use `FA_GITHUB_TOKEN` for dependable rate limits.

## LLM configuration

Set one or more of:

- `FA_GEMINI_API_KEY`
- `FA_GROQ_API_KEY`
- `FA_DEEPSEEK_API_KEY`

The provider order is Gemini Flash first, Groq (OpenAI GPT-OSS 120B) second, DeepSeek third. The orchestrator retries rate limits with jitter and shrinks chunks after a 413/too-large response.

## Google Sheets

The exporter targets exactly six tabs:

1. Startups
2. Products
3. Research Papers
4. Jobs
5. News
6. Entity Mapping Log

Use a service account with Editor access to the spreadsheet. Never commit `credentials.json` or `.env`.

## Compliance

Crawlers use public feeds/APIs where possible, identify themselves, and should respect robots.txt, terms and publisher rate limits. Playwright can be used for legitimately accessible JS-rendered pages. The system does **not** bypass CAPTCHA, Cloudflare, Datadome or other access controls.

## Architecture

See [`architecture.pdf`](architecture.pdf) for the three-page architecture and scaling/reliability design.
