from gcrm_opportunity_agent import create_opportunity_agent
from langchain_core.messages import AIMessage


class FakeLLM:
    def __init__(self):
        self.messages = []

    def invoke(self, messages):
        self.messages = messages
        return AIMessage(content='''{
          "opportunity_score": 84,
          "confidence_score": 70,
          "priority_score": 80,
          "fit_reasoning": "The site describes manual quote preparation.",
          "evidence": ["Manual quotes", "Owner-led operation"],
          "recommended_services": [{"service": "Quote assistant", "outcome": "Faster quotes", "rationale": "Manual workflow"}],
          "suggested_approach": "Review their quote workflow.",
          "discovery_questions": ["How are quotes prepared?"]
        }''')


def test_opportunity_agent_persists_structured_assessment():
    saved = []
    llm = FakeLLM()
    agent = create_opportunity_agent(
        llm=llm,
        fetch_contacts=lambda limit: [{"id": 7, "name": "Example", "city": "Augsburg", "website": "https://example.test"}],
        fetch_interactions=lambda contact_id: [{"summary": "Uses spreadsheets"}],
        fetch_page=lambda url: "Manual quote process described here.",
        save_analysis=lambda contact_id, analysis, model_name: saved.append((contact_id, analysis, model_name)),
        start_run=lambda name, data: 1,
        finish_run=lambda run_id, status, summary, output: None,
        mission=type("Mission", (), {"identity": "Chris", "goal": "Find workflow needs"})(),
        model_name="test-model",
    )

    result = agent.invoke({"limit": 10})

    assert result["analyzed_count"] == 1
    assert saved[0][0] == 7
    assert saved[0][1]["opportunity_score"] == 84
    assert saved[0][1]["recommended_services"][0]["service"] == "Quote assistant"
    assert "Manual quote process described here." in llm.messages[1].content
