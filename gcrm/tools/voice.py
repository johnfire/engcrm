"""Voice-memo structuring: transcript -> {summary, contact_query, follow_up_*, is_new_lead}.

Uses the cheap LLM (DeepSeek by default) — this is a text task, no vision needed.
"""
import logging

from gcrm.json_parsing import parse_llm_json

logger = logging.getLogger(__name__)


def structure_transcript(transcript: str, today: str) -> dict:
    """LLM-structure a memo transcript. Falls back to a summary-only dict on parse failure."""
    from gcrm.config import CHEAP_LLM
    from gcrm.tools.llm import get_llm
    from gcrm.prompts.voice import VOICE_SYSTEM_PROMPT
    from langchain_core.messages import HumanMessage, SystemMessage

    user = f"Today's date: {today}\n\nMemo transcript:\n{transcript}"
    try:
        resp = get_llm(CHEAP_LLM).invoke(
            [SystemMessage(content=VOICE_SYSTEM_PROMPT), HumanMessage(content=user)]
        )
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        data = parse_llm_json(content)
    except Exception:
        logger.warning("voice structuring failed; returning summary-only", exc_info=True)
        return {
            "summary": transcript,
            "contact_query": None,
            "follow_up_date": None,
            "follow_up_text": None,
            "is_new_lead": False,
        }
    data.setdefault("summary", transcript)
    return data
