"""The "Under the hood" trace, and the rule that the AI only chooses among real options: anything else it says
is thrown away, and without a model the rule-based choice is used."""
from datetime import date, timedelta

from langgraph.types import Command

from tripsync import llm, trace
from tripsync.agents import ai
from tripsync.graph import build_graph, pending_interrupt

START = date.today() + timedelta(days=30)
TRIP = f"3 days from Delhi to Jaipur on {START}, 2 people, ₹60000, balanced"


def _plan(thread: str):
    g = build_graph()
    cfg = {"configurable": {"thread_id": thread}}
    g.invoke({"user_message": TRIP}, cfg)
    while ask := pending_interrupt(g, cfg):
        g.invoke(Command(resume={"accept": True} if ask["type"] == "select" else "accept"), cfg)
    return g.get_state(cfg).values


def _fake_llm(monkeypatch, answers: dict):
    """llm.structured answers by schema; anything not listed gets no answer (like no model available)."""
    def fake(schema, prompt, purpose="AI answer"):
        trace.record("FakeAI", purpose, kind="ai")
        return answers.get(schema)
    monkeypatch.setattr(llm, "structured", fake)


def test_every_agent_step_is_traced():
    v = _plan("trace")
    agents = [t["agent"] for t in v["trace"]]
    for a in ("intake", "budget", "transport", "accommodation", "activity", "review", "planner", "critic", "finalize"):
        assert a in agents
    step = next(t for t in v["trace"] if t["agent"] == "transport")
    assert step["decided"] and step["why"] and step["inputs"]
    assert next(t for t in v["trace"] if t["agent"] == "critic")["why"]


def test_calls_are_recorded_inside_a_node_and_nowhere_else():
    def node(state):
        with trace.call("OSRM (road routes)", "table") as info:
            info["cached"] = True
        try:
            with trace.call("LiteAPI (hotels)", "rates"):
                raise TimeoutError("slow")
        except TimeoutError:
            pass
        return {"log": ["[Test] did things"]}
    out = trace.traced("test", node)({})
    calls = out["trace"][0]["calls"]
    assert [c["ok"] for c in calls] == [True, False] and calls[0]["cached"] and calls[1]["error"] == "slow"
    assert out["trace"][0]["decided"] == "did things"
    trace.record("X", "outside a node")  # no node running: ignored, no error


def test_ai_place_picks_keep_only_real_places(monkeypatch):
    cands = [{"id": f"p{i}", "name": f"Place {i}", "kind": "fort", "indoor": False, "minutes": 60, "fee": 0}
             for i in range(5)]
    _fake_llm(monkeypatch, {ai.Curation: ai.Curation(picks=[
        ai.Pick(n=3, reason="Great views"), ai.Pick(n=99, reason="Made up"), ai.Pick(n=3, reason="Again"),
        ai.Pick(n=1, reason="Famous")])})
    picks = ai.curate_places(cands, {"travellers": 2, "destination": "Jaipur"}, [], 2)
    assert list(picks) == ["p2", "p0"] and picks["p2"] == "Great views"


def test_ai_fix_first_must_be_one_of_the_given_problems(monkeypatch):
    opts = [({"type": "stay_over"}, "Stay over", "accommodation"), ({"type": "transport_over"}, "Transport over",
                                                                      "transport")]
    _fake_llm(monkeypatch, {ai.FixFirst: ai.FixFirst(n=5, reason="?")})
    assert ai.choose_first(opts) is None  # not a real option: keep the rule order
    _fake_llm(monkeypatch, {ai.FixFirst: ai.FixFirst(n=2, reason="Flights are the big cost")})
    assert ai.choose_first(opts) == 1


def test_ai_review_can_lighten_one_real_day_once(monkeypatch):
    _fake_llm(monkeypatch, {ai.Review: ai.Review(concerns=[
        ai.Concern(day=2, type="overpacked", reason="Too many forts in one day"),
        ai.Concern(day=9, type="crowds", reason="No such day")])})
    v = _plan("ai-review")
    sent = [r for r in v["replans"] if r["type"] == "overpacked_day"]
    assert len(sent) == 1 and sent[0]["target"] == "activity" and "AI reviewer" in sent[0]["problem"]
    assert v["final"] and v["constraints"]["critic"]["ai_reviewed"]
    verdicts = [a for t in v["trace"] if t["agent"] == "critic" for a in t["ai"]]
    assert verdicts and "accepted" in verdicts[0]["verdict"]


def test_without_a_model_the_rules_decide(monkeypatch):
    _fake_llm(monkeypatch, {})
    v = _plan("no-ai")
    assert v["final"] and not any(c.get("ai_reason") for c in v["activities"]["candidates"])
    assert not any(t["ai"] for t in v["trace"])
