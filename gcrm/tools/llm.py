"""
LLM factory. Returns a LangChain BaseChatModel that satisfies the
LanguageModel Protocol used by all agents.

Supported model strings:
  deepseek-chat       — DeepSeek Chat (fast, low cost, routine tasks)
  deepseek-reasoner   — DeepSeek R1 (slower, better reasoning, drafts)
  claude-haiku        — Claude Haiku 4.5 (cheap Anthropic alternative for routine tasks)
  claude              — Claude Sonnet 4.6 (high-stakes writing)
"""
import logging
from gcrm.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

_cost_cb = None


def _get_cost_callback():
    """
    Lazily build a callback that captures token usage into the cost tracker.
    Built on demand so this module stays importable without the agents extra
    (langchain) installed — the base web app imports get_llm transitively.
    """
    global _cost_cb
    if _cost_cb is not None:
        return _cost_cb
    from langchain_core.callbacks import BaseCallbackHandler

    class _CostCallback(BaseCallbackHandler):
        def on_llm_end(self, response, **kwargs) -> None:
            from gcrm.tools.costs import record_llm
            try:
                for gen_list in response.generations:
                    for gen in gen_list:
                        msg = getattr(gen, "message", None)
                        if msg and hasattr(msg, "usage_metadata"):
                            meta = msg.usage_metadata or {}
                            rmeta = getattr(msg, "response_metadata", None) or {}
                            model = rmeta.get("model_name") or rmeta.get("model", "unknown")
                            cached = (meta.get("input_token_details") or {}).get("cache_read", 0)
                            record_llm(model, meta.get("input_tokens", 0), meta.get("output_tokens", 0), cached)
                            return
                # Fallback: OpenAI-compatible response (DeepSeek)
                usage = (response.llm_output or {}).get("token_usage", {})
                if usage:
                    model = (response.llm_output or {}).get("model_name", "deepseek-chat")
                    record_llm(model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
            except Exception as error:
                logger.debug("cost callback error: %s", error)

    _cost_cb = _CostCallback()
    return _cost_cb


def get_llm(model: str = "deepseek-chat"):
    """
    Return a LangChain chat model instance.
    All returned objects satisfy the LanguageModel Protocol (have .invoke(messages)).
    """
    if model.startswith("deepseek"):
        from langchain_openai import ChatOpenAI
        model_name = "deepseek-reasoner" if model == "deepseek-reasoner" else "deepseek-chat"
        return ChatOpenAI(
            model=model_name,
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            temperature=0.3,
            callbacks=[_get_cost_callback()],
        )
    elif model in ("claude", "claude-sonnet"):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=ANTHROPIC_API_KEY,
            temperature=0.3,
            max_tokens=8192,
            callbacks=[_get_cost_callback()],
        )
    elif model == "claude-haiku":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model="claude-haiku-4-5-20251001",
            api_key=ANTHROPIC_API_KEY,
            temperature=0.3,
            max_tokens=8192,
            callbacks=[_get_cost_callback()],
        )
    else:
        raise ValueError(f"Unknown model '{model}'. Use: deepseek-chat, deepseek-reasoner, claude-haiku, claude")
