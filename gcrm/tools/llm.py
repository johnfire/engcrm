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
        )
    elif model in ("claude", "claude-sonnet"):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=ANTHROPIC_API_KEY,
            temperature=0.3,
            max_tokens=8192,
        )
    elif model == "claude-haiku":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model="claude-haiku-4-5-20251001",
            api_key=ANTHROPIC_API_KEY,
            temperature=0.3,
            max_tokens=8192,
        )
    else:
        raise ValueError(f"Unknown model '{model}'. Use: deepseek-chat, deepseek-reasoner, claude-haiku, claude")
