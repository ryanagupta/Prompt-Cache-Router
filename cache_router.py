"""Build stable-first Claude requests and estimate input cost from usage."""

from collections.abc import Sequence
from decimal import Decimal
import json


def build_request(
    *, model: str, instructions: str, documents: Sequence[str], query: str, max_tokens: int = 256
) -> dict:
    system = [{"type": "text", "text": text} for text in (instructions, *documents)]
    system[-1]["cache_control"] = {"type": "ephemeral", "ttl": "5m"}
    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": query}],
    }


def summarize_usage(
    records: Sequence[dict],
    *,
    base_per_million: Decimal,
    read_multiplier: Decimal,
    write_multiplier: Decimal,
) -> dict:
    hits = writes = uncached = reads = created = ordinary = 0
    for usage in records:
        read = usage.get("cache_read_input_tokens", 0)
        write = usage.get("cache_creation_input_tokens", 0)
        input_tokens = usage.get("input_tokens", 0)
        if any(type(value) is not int or value < 0 for value in (read, write, input_tokens)):
            raise ValueError("usage counts must be non-negative integers")
        reads += read
        created += write
        ordinary += input_tokens
        hits += bool(read)
        writes += bool(write and not read)
        uncached += not (read or write)

    unit_price = base_per_million / 1_000_000
    baseline = (ordinary + reads + created) * unit_price
    estimate = (ordinary + reads * read_multiplier + created * write_multiplier) * unit_price
    return {
        "requests_with_cache_reads": hits,
        "write_only_requests": writes,
        "uncached_requests": uncached,
        "tokens_read_from_cache": reads,
        "uncached_input_cost_usd": str(baseline),
        "estimated_input_cost_usd": str(estimate),
        "estimated_input_savings_usd": str(baseline - estimate),
    }


if __name__ == "__main__":
    context = {
        "model": "demo-model",
        "instructions": "Answer using the supplied handbook.",
        "documents": ["Version 1 handbook. Stable sample context."],
    }
    first = build_request(**context, query="User A: What changed?")
    second = build_request(**context, query="User B: What stayed the same?")
    print(f"Stable prefix: {first['system'] == second['system']}")
    print(f"Dynamic suffix changed: {first['messages'] != second['messages']}")
    sample = [
        {"input_tokens": 100, "cache_creation_input_tokens": 2400},
        {"input_tokens": 110, "cache_read_input_tokens": 2400},
    ]
    print(json.dumps(summarize_usage(
        sample,
        base_per_million=Decimal("3.00"),
        read_multiplier=Decimal("0.10"),
        write_multiplier=Decimal("1.25"),
    ), indent=2))
