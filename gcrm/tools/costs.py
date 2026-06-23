"""
Cost tracking for LLM and web-search usage within a single agent run.
Module-level state — safe because each agent run is a separate process.
"""
import logging

logger = logging.getLogger(__name__)

# USD per million tokens
PRICING: dict[str, dict[str, float]] = {
    "deepseek-chat":             {"input": 0.27, "output": 1.10, "cached": 0.07},
    "deepseek-reasoner":         {"input": 0.55, "output": 2.19, "cached": 0.14},
    "claude-sonnet-4-6":         {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
}

# engcrm uses DuckDuckGo (free) for web search — queries are counted, cost is $0.
SEARCH_COST_PER_QUERY: float = 0.0

_search_queries: int = 0
_llm_usage: dict[str, dict[str, int]] = {}  # model -> {input, output, cached}


def reset_costs() -> None:
    global _search_queries, _llm_usage
    _search_queries = 0
    _llm_usage = {}


def record_search(n: int = 1) -> None:
    global _search_queries
    _search_queries += n


def record_llm(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> None:
    if model not in _llm_usage:
        _llm_usage[model] = {"input": 0, "output": 0, "cached": 0}
    _llm_usage[model]["input"] += input_tokens
    _llm_usage[model]["output"] += output_tokens
    _llm_usage[model]["cached"] += cached_tokens


def get_costs() -> dict:
    """Return a cost breakdown dict with total_usd."""
    total = 0.0
    breakdown: dict = {}

    search_cost = _search_queries * SEARCH_COST_PER_QUERY
    total += search_cost
    if _search_queries:
        breakdown["web_search"] = {"queries": _search_queries, "cost_usd": round(search_cost, 6)}

    for model, usage in _llm_usage.items():
        p = PRICING.get(model, {"input": 0.0, "output": 0.0, "cached": 0.0})
        cost = (
            usage["input"] * p["input"]
            + usage["output"] * p["output"]
            + usage["cached"] * p.get("cached", 0.0)
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
    b = costs["breakdown"]
    if "web_search" in b:
        parts.append(f"search:{b['web_search']['queries']}q")
    for model, u in b.items():
        if model == "web_search":
            continue
        short = model.split("-")[0]
        tok = u["input_tokens"] + u["output_tokens"]
        parts.append(f"{short}:{tok}tok")
    return " | ".join(parts)
