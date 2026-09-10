from src.resolution.seed import DEFAULT_SEED
from src.resolution.resolver import EntityResolver
from src.resolution.normalizer import normalize_name


def test_seed_contains_at_least_50_canonical_entities():
    assert len(DEFAULT_SEED) >= 50


def test_openai_aliases_resolve_to_same_canonical_entity():
    resolver = EntityResolver(DEFAULT_SEED)

    for name in ["OpenAI", "Open AI", "OpenAI, Inc.", "OpenAI Inc"]:
        result = resolver.resolve(name)
        assert result.canonical_name == "OpenAI"
        assert result.method == "seed_exact"
        assert result.confidence == 1.0


def test_common_aliases_resolve():
    resolver = EntityResolver(DEFAULT_SEED)

    cases = {
        "AWS": "Amazon",
        "Google LLC": "Google",
        "Microsoft Corp.": "Microsoft",
        "Facebook AI": "Meta",
        "Nvidia": "NVIDIA",
        "HuggingFace": "Hugging Face",
        "GitHub, Inc.": "GitHub",
        "MistralAI": "Mistral AI",
        "RunwayML": "Runway",
    }

    for raw, expected in cases.items():
        result = resolver.resolve(raw)
        assert result.canonical_name == expected
        assert result.method == "seed_exact"


def test_empty_name_is_unresolved():
    resolver = EntityResolver(DEFAULT_SEED)
    result = resolver.resolve("")

    assert result.method == "unresolved"
    assert result.confidence == 0.0


def test_fuzzy_matching_requires_high_confidence():
    resolver = EntityResolver(DEFAULT_SEED)

    result = resolver.resolve_against(
        "OpenAI Inc",
        ["OpenAI", "Anthropic", "Microsoft"],
    )

    assert result.canonical_name == "OpenAI"
    assert result.method == "seed_exact"
    assert result.confidence == 1.0
