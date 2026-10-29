"""LangGraph wiring for the final TripSync architecture.

intake -> clarify (interrupt) -> budget -> {transport, accommodation, activity} -> review (interrupt, once)
-> planner -> critic
critic --violation--> the agent that can fix it (max 3 rounds) --> ask_user (interrupt) --> budget
critic --pass--> finalize.  A follow-up message on a finished trip enters at refine instead."""
import sqlite3

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .agents.accommodation import accommodation_node
from .agents.activity import activity_node
from .agents.budget import budget_node
from .agents.critic import ask_user_node, critic_node
from .agents.finalize import finalize_node
from .agents.intake import clarify_node, intake_node, route_after_clarify
from .agents.planner import planner_node
from .agents.refine import refine_node
from .agents.review import review_node
from .agents.transport import transport_node
from .config import CHECKPOINT_DB
from .state import TripState

AGENTS = ["transport", "accommodation", "activity"]


def build_graph(checkpointer=None):
    g = StateGraph(TripState)
    g.add_node("intake", intake_node)
    g.add_node("clarify", clarify_node)
    g.add_node("budget", budget_node)
    g.add_node("transport", transport_node)
    g.add_node("accommodation", accommodation_node)
    g.add_node("activity", activity_node)
    g.add_node("review", review_node)
    g.add_node("planner", planner_node)
    g.add_node("critic", critic_node)
    g.add_node("ask_user", ask_user_node)
    g.add_node("finalize", finalize_node)
    g.add_node("refine", refine_node)

    g.add_conditional_edges(START, lambda s: "refine" if s.get("final") else "intake", ["intake", "refine"])
    g.add_edge("intake", "clarify")
    g.add_conditional_edges("clarify", route_after_clarify, ["clarify", "budget"])
    for agent in AGENTS:
        g.add_edge("budget", agent)   # fan-out: the three agents run in parallel
        g.add_edge(agent, "review")   # runs once all scheduled agents finish; asks the traveller the first time
    g.add_edge("review", "planner")
    g.add_edge("planner", "critic")
    g.add_conditional_edges("critic", lambda s: s.get("next_agent") or "finalize",
                            ["finalize", "planner", "budget", "ask_user", *AGENTS])
    g.add_conditional_edges("ask_user", lambda s: s["next_agent"], ["budget", "finalize"])
    g.add_edge("finalize", END)
    g.add_conditional_edges("refine", lambda s: s.get("next_agent") or END,
                            ["review", "planner", "budget", *AGENTS, END])
    return g.compile(checkpointer=checkpointer or InMemorySaver())


def sqlite_graph(path=CHECKPOINT_DB):
    from langgraph.checkpoint.sqlite import SqliteSaver
    return build_graph(SqliteSaver(sqlite3.connect(str(path), check_same_thread=False)))


def pending_interrupt(graph, config) -> dict | None:
    snap = graph.get_state(config)
    for task in snap.tasks:
        for it in task.interrupts:
            return it.value
    return None
