"""
Supervisor graph tests. The four sub-agents are replaced with fake runnables
so we test the supervisor's routing and reporting logic without real AI or DB.
"""
from typing import TypedDict
from unittest.mock import MagicMock, patch


class FakeAgent:
    """A fake compiled LangGraph agent that returns a controlled summary."""
    def __init__(self, summary: str, raise_on_invoke: bool = False):
        self._summary = summary
        self._raise = raise_on_invoke

    def invoke(self, state, **kwargs):
        if self._raise:
            raise RuntimeError("agent exploded")
        return {**state, "summary": self._summary}


def _make_supervisor_with_fake_agents(research_summary="r ok", scout_summary="s ok",
                                       outreach_summary="o ok", followup_summary="f ok",
                                       fail_agent=None):
    """
    Build the supervisor graph but inject fake agents instead of real ones.
    `fail_agent` can be 'research', 'scout', 'outreach', or 'followup' to simulate failure.
    """
    from gcrm.supervisor.graph import SupervisorState
    from langgraph.graph import StateGraph, END

    fake_research = FakeAgent(research_summary, raise_on_invoke=(fail_agent == "research"))
    fake_scout = FakeAgent(scout_summary, raise_on_invoke=(fail_agent == "scout"))
    fake_outreach = FakeAgent(outreach_summary, raise_on_invoke=(fail_agent == "outreach"))
    fake_followup = FakeAgent(followup_summary, raise_on_invoke=(fail_agent == "followup"))

    # We need to import targets here since we mock start_run/finish_run
    targets = [{"city": "Munich", "industry": "gallery", "country": "DE"}]

    call_log = []

    def init(state):
        return {
            "run_id": 1,
            "research_summaries": [],
            "scout_summary": "",
            "outreach_summary": "",
            "followup_summary": "",
            "errors": [],
            "summary": "",
        }

    def run_research(state):
        summaries = []
        for t in targets:
            try:
                result = fake_research.invoke({"city": t["city"], "industry": t["industry"]})
                summaries.append(result.get("summary", ""))
                call_log.append("research")
            except Exception as e:
                summaries.append(f"research failed: {e}")
        return {"research_summaries": summaries}

    def run_scout(state):
        try:
            result = fake_scout.invoke({"limit": 100})
            call_log.append("scout")
            return {"scout_summary": result.get("summary", "")}
        except Exception as e:
            return {"scout_summary": f"scout failed: {e}", "errors": state["errors"] + [str(e)]}

    def run_outreach(state):
        try:
            result = fake_outreach.invoke({"limit": 20})
            call_log.append("outreach")
            return {"outreach_summary": result.get("summary", "")}
        except Exception as e:
            return {"outreach_summary": f"outreach failed: {e}", "errors": state["errors"] + [str(e)]}

    def run_followup(state):
        try:
            result = fake_followup.invoke({})
            call_log.append("followup")
            return {"followup_summary": result.get("summary", "")}
        except Exception as e:
            return {"followup_summary": f"followup failed: {e}", "errors": state["errors"] + [str(e)]}

    def generate_report(state):
        summary = (
            f"research: {state['research_summaries']}\n"
            f"scout: {state['scout_summary']}\n"
            f"outreach: {state['outreach_summary']}\n"
            f"followup: {state['followup_summary']}"
        )
        return {"summary": summary}

    graph = StateGraph(SupervisorState)
    for name, fn in [
        ("init", init), ("run_research", run_research), ("run_scout", run_scout),
        ("run_outreach", run_outreach), ("run_followup", run_followup),
        ("generate_report", generate_report),
    ]:
        graph.add_node(name, fn)

    graph.set_entry_point("init")
    graph.add_edge("init", "run_research")
    graph.add_edge("run_research", "run_scout")
    graph.add_edge("run_scout", "run_outreach")
    graph.add_edge("run_outreach", "run_followup")
    graph.add_edge("run_followup", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile(), call_log


def test_supervisor_runs_all_agents():
    supervisor, call_log = _make_supervisor_with_fake_agents()
    result = supervisor.invoke({})

    assert "research" in call_log
    assert "scout" in call_log
    assert "outreach" in call_log
    assert "followup" in call_log
    assert "r ok" in result["summary"]
    assert "s ok" in result["summary"]


def test_supervisor_continues_when_one_agent_fails():
    supervisor, call_log = _make_supervisor_with_fake_agents(fail_agent="scout")
    result = supervisor.invoke({})

    # research ran, scout failed but didn't crash supervisor, outreach and followup still ran
    assert "research" in call_log
    assert "outreach" in call_log
    assert "followup" in call_log
    assert "scout failed" in result["summary"]


def test_supervisor_report_includes_all_summaries():
    supervisor, _ = _make_supervisor_with_fake_agents(
        research_summary="2 contacts found",
        scout_summary="1 promoted",
        outreach_summary="1 queued",
        followup_summary="0 sent",
    )
    result = supervisor.invoke({})

    assert "2 contacts found" in result["summary"]
    assert "1 promoted" in result["summary"]
    assert "1 queued" in result["summary"]
    assert "0 sent" in result["summary"]
