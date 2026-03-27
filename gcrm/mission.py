from dataclasses import dataclass


@dataclass(frozen=True)
class Mission:
    """
    Defines what the agent system is working toward.
    Swap this out to repurpose all agents for a different domain.
    All fields are injected into agent system prompts at startup.
    """
    goal: str            # what the system is trying to achieve
    identity: str        # who the agents represent
    targets: str         # what kinds of contacts to find
    fit_criteria: str    # what makes a good match
    outreach_style: str  # tone and approach for written contact
    language_default: str  # ISO 639-1, used when contact has no preference set
    website: str = ""    # artist/business website, included in email signatures
