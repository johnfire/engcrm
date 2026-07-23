"""First-contact prompts must include the approved privacy-information link."""
from gcrm.mission import Mission
from gcrm.prompts.outreach import draft_email_prompt


def test_first_contact_prompt_requires_privacy_information_line():
    mission = Mission(
        goal="Help local businesses",
        identity="Chris",
        targets="SMBs",
        fit_criteria="Relevant need",
        outreach_style="direct",
        language_default="de",
        privacy_notice_url="https://engcrm.example/privacy",
    )

    _, prompt = draft_email_prompt(
        mission,
        {"name": "Example GmbH", "type": "business", "city": "Munich"},
        "de",
        interactions=[],
        website_content="",
    )

    assert "Datenschutzhinweise: https://engcrm.example/privacy" in prompt
