"""
Weekly outreach quality analysis.

Reads outreach_outcomes for the last 90 days, groups warm vs cold,
fetches the draft bodies, and asks Claude Sonnet to synthesise patterns.
Writes the synthesis to Open Brain.

Skips if fewer than MIN_WARM_OUTCOMES warm outcomes exist (not enough signal).

Usage:
    uv run python -m gcrm.supervisor.run_outreach_analysis
    uv run python -m gcrm.supervisor.run_outreach_analysis --days 60
"""
import argparse
import logging

from gcrm.supervisor.logging_setup import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

MIN_WARM_OUTCOMES = 5


def main():
    parser = argparse.ArgumentParser(description="Analyse outreach outcomes and write learnings to Open Brain")
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()

    from langchain_core.messages import HumanMessage, SystemMessage

    from gcrm.config import SMART_LLM
    from gcrm.tools.db import get_outreach_outcomes
    from gcrm.tools.llm import get_llm
    from gcrm.tools.memory import capture_thought

    outcomes = get_outreach_outcomes(days=args.days)
    warm = [outcome for outcome in outcomes if outcome["warm"]]
    cold = [outcome for outcome in outcomes if not outcome["warm"]]

    if len(warm) < MIN_WARM_OUTCOMES:
        logger.info(
            "analysis: only %d warm outcomes (need %d) — skipping, not enough signal yet",
            len(warm), MIN_WARM_OUTCOMES,
        )
        return

    def _fmt(o: dict) -> str:
        body = (o.get("draft_body") or "")[:800]
        subject = o.get("draft_subject") or ""
        words = o.get("word_count") or "?"
        city = o.get("city") or "?"
        ctype = o.get("contact_type") or "?"
        return f"[{ctype} / {city} / {words} words]\nSubject: {subject}\n{body}"

    warm_block = "\n\n---\n\n".join(_fmt(outcome) for outcome in warm[:20])
    cold_block  = "\n\n---\n\n".join(_fmt(outcome) for outcome in cold[:20])

    system = (
        "You are analysing email outreach patterns for an AI engineer and consultant "
        "reaching out to SMBs, professional practices, and research institutions in Bavaria. "
        "Be specific and actionable. Write in English. "
        "Keep your answer under 200 words — bullet points preferred."
    )
    user = (
        f"Below are emails that received WARM replies ({len(warm)} total, showing up to 20):\n\n"
        f"{warm_block}\n\n"
        f"---\n\n"
        f"And emails that did NOT receive warm replies ({len(cold)} total, showing up to 20):\n\n"
        f"{cold_block}\n\n"
        f"What patterns distinguish the emails that got warm replies? "
        f"Consider: tone, length, subject line style, personalization, opening sentence, "
        f"mention of specific company details, and language style. "
        f"Be specific — mention word counts, phrases, or structural patterns you notice."
    )

    llm = get_llm(SMART_LLM)
    response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    synthesis = response.content.strip()

    thought = (
        f"gcrm outreach learning ({args.days}-day analysis, "
        f"{len(warm)} warm / {len(cold)} cold):\n\n{synthesis}"
    )
    capture_thought(thought)
    logger.info("analysis: learning written to Open Brain (%d chars)", len(thought))
    logger.info("synthesis:\n%s", synthesis)


if __name__ == "__main__":
    main()
