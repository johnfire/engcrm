"""
Cost tracking for LLM and web-search usage within an agent run.

Module-level state guarded by a lock so concurrent record_*() calls in the same
process (e.g. background enrichment tasks) can't corrupt the counters. The
counters are still process-global: concurrent agent RUNS in one process share
them, so true per-run isolation would need a per-run context, not module state.
"""
import logging
import threading

logger = logging.getLogger(__name__)

# USD per million tokens
PRICING: dict[str, dict[str, float]] = {
    "deepseek-v4-flash":         {"input": 0.14, "output": 0.28, "cached": 0.0028},
    "deepseek-v4-pro":           {"input": 0.435, "output": 0.87, "cached": 0.003625},
    "deepseek-chat":             {"input": 0.27, "output": 1.10, "cached": 0.07},
    "deepseek-reasoner":         {"input": 0.55, "output": 2.19, "cached": 0.14},
    "claude-sonnet-4-6":         {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
}

# engcrm uses DuckDuckGo (free) for web search — queries are counted, cost is $0.
SEARCH_COST_PER_QUERY: float = 0.0

_lock = threading.Lock()
_search_queries: int = 0
_llm_usage: dict[str, dict[str, int]] = {}  # model -> {input, output, cached}


def reset_costs() -> None:
    global _search_queries, _llm_usage
    with _lock:
        _search_queries = 0
        _llm_usage = {}


def record_search(count: int = 1) -> None:
    global _search_queries
    with _lock:
        _search_queries += count


def record_llm(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> None:
    with _lock:
        if model not in _llm_usage:
            _llm_usage[model] = {"input": 0, "output": 0, "cached": 0}
        _llm_usage[model]["input"] += input_tokens
        _llm_usage[model]["output"] += output_tokens
        _llm_usage[model]["cached"] += cached_tokens


def get_costs() -> dict:
    """Return a cost breakdown dict with total_usd."""
    with _lock:
        search_queries = _search_queries
        usage_snapshot = {model: dict(usage) for model, usage in _llm_usage.items()}

    total = 0.0
    breakdown: dict = {}

    search_cost = search_queries * SEARCH_COST_PER_QUERY
    total += search_cost
    if search_queries:
        breakdown["web_search"] = {"queries": search_queries, "cost_usd": round(search_cost, 6)}

    for model, usage in usage_snapshot.items():
        pricing = PRICING.get(model, {"input": 0.0, "output": 0.0, "cached": 0.0})
        cost = (
            usage["input"] * pricing["input"]
            + usage["output"] * pricing["output"]
            + usage["cached"] * pricing.get("cached", 0.0)
        ) / 1_000_000
        total += cost
        breakdown[model] = {
            "input_tokens": usage["input"],
            "output_tokens": usage["output"],
            "cached_tokens": usage["cached"],
            "cost_usd": round(cost, 6),
        }

    return {"total_usd": round(total, 6), "breakdown": breakdown}


def format_costs() -> str:
    """One-line cost summary for log output."""
    costs = get_costs()
    parts = [f"cost=${costs['total_usd']:.4f}"]
    breakdown = costs["breakdown"]
    if "web_search" in breakdown:
        parts.append(f"search:{breakdown['web_search']['queries']}q")
    for model, usage in breakdown.items():
        if model == "web_search":
            continue
        short_name = model.split("-")[0]
        token_count = usage["input_tokens"] + usage["output_tokens"]
        parts.append(f"{short_name}:{token_count}tok")
    return " | ".join(parts)
