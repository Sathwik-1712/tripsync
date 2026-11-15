"""Steps 5-7: Critic Agent (code checks + optional LLM review), the conditional
router that sends each violation to the agent that can fix it, and the retry cap."""
import math
from datetime import date

from langgraph.types import interrupt

from . import ai
from ..config import MAX_ROUNDS
from ..state import trip_dates
from ..tools.hours import visit_problem
from .planner import schedule

PRIORITY = ["hallucinated_place", "transport_over", "stay_over", "rain_outdoor", "closed_place", "overpacked_day",
            "activities_over", "food_over", "total_over"]
COST_TYPES = {"transport_over", "stay_over", "activities_over", "food_over", "total_over"}
MAX_DAY_MIN, MAX_TRAVEL_MIN = 600, 180


def check(state: dict) -> list[dict]:
    costs, alloc, itin = state["costs"], state["allocations"], state["itinerary"]
    allowed = {c["id"] for c in state["activities"]["candidates"]}
    vs = []
    fake = [s["name"] for d in itin["days"] for s in d["stops"] if s["id"] not in allowed]
    if fake:
        vs.append({"type": "hallucinated_place", "places": fake})
    wanted = (state.get("constraints", {}).get("transport") or {}).get("preferred_mode")
    for cat, vtype, key in (("transport", "transport_over", "transport"), ("stay", "stay_over", "stay")):
        if costs[cat] > alloc[cat]:
            vs.append({"type": vtype, "category": cat, "deficit": costs[cat] - alloc[cat],
                       "at_cheapest": state[key]["at_cheapest"],
                       # the traveller asked for this mode; worth paying for if the total allows
                       "preferred": cat == "transport" and bool(wanted) and state[key]["choice"]["mode"] == wanted})
    rainy = [d["date"] for d in itin["days"] if d["rainy"] and any(not s["indoor"] for s in d["stops"])]
    if rainy:
        vs.append({"type": "rain_outdoor", "dates": rainy})
    closed = [{"day": d["day"], "id": s["id"], "name": s["name"], "why": why}
              for d in itin["days"] for s in schedule(d) if s["type"] == "stop"
              if (why := visit_problem(s.get("opening_hours"), date.fromisoformat(d["date"]).weekday(),
                                       s["arrive_min"], s["minutes"]))]
    if closed:
        vs.append({"type": "closed_place", "places": closed})
    for d in itin["days"]:
        if len(d["stops"]) > 1 and (d["visit_min"] + d["travel_min"] > MAX_DAY_MIN or d["travel_min"] > MAX_TRAVEL_MIN):
            vs.append({"type": "overpacked_day", "day": d["day"], "count": len(d["stops"]),
                       "travel_min": d["travel_min"]})
            break
    if costs["activities"] > alloc["activities"]:
        max_fee = (state.get("constraints", {}).get("activity") or {}).get("max_fee")
        vs.append({"type": "activities_over", "category": "activities",
                   "deficit": costs["activities"] - alloc["activities"], "at_cheapest": max_fee == 0})
    if costs["food"] > alloc["food"]:
        vs.append({"type": "food_over", "category": "food", "deficit": costs["food"] - alloc["food"],
                   "at_cheapest": True})
    if costs["total"] > costs["budget"]:
        vs.append({"type": "total_over", "deficit": costs["total"] - costs["budget"]})
    return sorted(vs, key=lambda v: PRIORITY.index(v["type"]))


ROUTES = {"hallucinated_place": "planner", "transport_over": "transport", "stay_over": "accommodation",
          "rain_outdoor": "activity", "closed_place": "planner", "overpacked_day": "activity", "activities_over": "activity",
          "food_over": "budget", "total_over": "budget"}


def describe(v: dict) -> str:
    t = v["type"]
    if t in ("transport_over", "stay_over", "activities_over", "food_over"):
        return f"{v['category'].title()} is ₹{v['deficit']:,} over its limit"
    if t == "total_over":
        return f"Total is ₹{v['deficit']:,} over budget"
    if t == "rain_outdoor":
        return f"Rain expected on {', '.join(v['dates'])} with outdoor stops planned"
    if t == "overpacked_day" and v.get("source") == "ai":
        return f"AI reviewer: day {v['day']} is too much for your pace ({v['reason']})"
    if t == "overpacked_day":
        return f"Day {v['day']} is overpacked ({v['count']} stops, {v['travel_min']} min travelling)"
    if t == "closed_place":
        return "Not open at the planned time: " + ", ".join(
            f"{p['name']} on day {p['day']} ({p['why']})" for p in v["places"])
    return f"Places not from tool results: {', '.join(v['places'])}"


def critic_node(state: dict) -> dict:
    vs = check(state)
    knobs = dict(state.get("constraints", {}).get("critic") or {})
    rounds_so_far = state.get("revision_count", 0)
    if not vs:
        # The rules found nothing. Ask the AI for a second opinion, once per plan: it may send one day back to be
        # lightened (only a real day with more than one stop) or leave tips for the traveller.
        fix, tips = (None, knobs.get("tips", [])) if knobs.get("ai_reviewed") else ai.review_plan(state)
        knobs.update(ai_reviewed=True, tips=tips)
        if fix and rounds_so_far + 1 < MAX_ROUNDS:
            vs = [fix]
        else:
            return {"violations": [], "last_violation": None, "next_agent": "finalize", "constraints": {"critic": knobs},
                    "log": ["[Critic] pass: within every limit, no rain conflicts, days are manageable"]
                    + [f"[Critic] AI tip: {t}" for t in tips],
                    "explain": {"decided": "Passed: the plan goes to the final step",
                                "why": "Every rule check passed: each category within its limit, the total within "
                                       "budget, no outdoor stops on rainy days, every place open when visited, no day "
                                       "too long, and every place comes from a real source"
                                       + (". The AI reviewer added tips for you" if tips else ""),
                                "inputs": _inputs(state)}}

    fits = state["costs"]["total"] <= state["costs"]["budget"]

    def route(v: dict) -> str:
        # An agent already at its cheapest option can't fix an overspend. And while the whole plan fits the
        # budget, downgrading is pointless: ask the Budget Agent to move spare money into that category.
        if v["type"] in COST_TYPES and (v.get("at_cheapest") or fits):
            return "budget"
        return ROUTES[v["type"]]

    # Fix what a specialist agent can fix before asking the Budget Agent to move money around, and
    # trim everything else before touching a choice the traveller explicitly asked for.
    fixable = sorted((v for v in vs if route(v) != "budget"), key=lambda v: bool(v.get("preferred")))
    # ...unless the other overspends are too small to close the gap: then shaving them only wrecks the plan.
    over = state["costs"]["total"] - state["costs"]["budget"]
    others = sum(v.get("deficit", 0) for v in fixable if not v.get("preferred") and v["type"] in COST_TYPES)
    if over > 0 and others < over:
        fixable.sort(key=lambda v: (v["type"] not in COST_TYPES, -v.get("deficit", 0)))
    ordered = fixable or vs
    # The AI may pick which problem to fix first, but only among the ones the rules would also accept as first:
    # not a choice the traveller asked for, and costs first when only the big overspends can close the gap.
    first_tier = [v for v in ordered if not v.get("preferred")] or ordered
    if over > 0 and others < over:
        first_tier = [v for v in first_tier if v["type"] in COST_TYPES] or first_tier
    pick = ai.choose_first([(v, describe(v), route(v)) for v in first_tier]) if len(first_tier) > 1 else None
    primary, rounds = (first_tier[pick] if pick is not None else ordered[0]), rounds_so_far + 1
    target = route(primary)
    out = {"violations": vs, "last_violation": primary, "revision_count": rounds, "constraints": {"critic": knobs},
           "log": [f"[Critic] round {rounds}: {describe(primary)} -> {target}"
                   + (f" (+{len(vs) - 1} more)" if len(vs) > 1 else "")]}
    if rounds >= MAX_ROUNDS:
        cost_issue = any(v["type"] in COST_TYPES for v in vs)
        if cost_issue and fits and rounds == MAX_ROUNDS:
            # The whole plan fits the budget; only the per-category limits are off. Rebalance instead of asking.
            target = "budget"
            out["budget_action"] = {"type": "rebalance"}
        else:
            target = "ask_user" if cost_issue and not fits else "finalize"
        out["log"].append(f"[Critic] {MAX_ROUNDS} failed rounds -> {target}")
    elif target == "budget" and fits and len(vs) > 1 and all(route(v) == "budget" for v in vs):
        # Several categories a little over their own limits while the whole trip fits: re-split the money around
        # the actual plan in one go, instead of one category per round (each round reruns every search agent).
        out["budget_action"] = {"type": "rebalance"}
        out["log"].append(f"[Critic] {len(vs)} categories over their limits but the trip fits: rebalance at once")
    elif target == "budget":
        out["budget_action"] = ({"type": "realloc", "category": primary["category"], "deficit": primary["deficit"]}
                                if primary.get("category") else {"type": "split"})
    out["next_agent"] = target
    out["replans"] = state.get("replans", []) + [{"problem": describe(primary), "type": primary["type"],
                                                  "target": target}]
    out["explain"] = {"decided": f"Round {rounds}: sent back to the {target.replace('_', ' ')} step",
                      "why": _why_route(primary, target, state), "sent_to": target,
                      "inputs": _inputs(state) + [f"Problems found: {len(vs)}"] + [describe(v) for v in vs]}
    if (out.get("budget_action") or {}).get("type") == "rebalance" and rounds < MAX_ROUNDS:
        out["explain"]["why"] = (f"{len(vs)} categories are a little over their own limits, but the whole trip is "
                                 f"₹{-over:,} under budget. So the Budget agent re-splits the money around the actual "
                                 "plan in one go, instead of fixing one category per round")
    return out


def _inputs(state: dict) -> list[str]:
    c = state["costs"]
    return [f"Total ₹{c['total']:,} of ₹{c['budget']:,}", f"{len(state['itinerary']['days'])} days",
            f"{sum(len(d['stops']) for d in state['itinerary']['days'])} stops"]


def _why_route(v: dict, target: str, state: dict) -> str:
    problem = describe(v)
    if v.get("source") == "ai":
        return f"The AI reviewer found day {v['day']} too much ({v['reason']}), so the Activity agent caps that day"
    if target == "budget":
        return (f"{problem}. That agent is already at its cheapest option or the whole trip still fits, so the Budget "
                "agent moves money between categories instead of downgrading")
    if target in ("ask_user", "finalize"):
        return f"{problem}. {MAX_ROUNDS} rounds didn't fix it, so it stops here"
    return f"{problem}. The {target} agent is the one that can fix this, so only it reruns"


def ask_user_node(state: dict) -> dict:
    """Retry cap: pause and let the user raise the budget, cut a day, or accept."""
    req, costs = dict(state["request"]), state["costs"]
    over = costs["total"] - costs["budget"]  # only reached when the whole plan is over budget
    raise_by = max(500, int(math.ceil(over / 500) * 500))
    n_days = len(trip_dates(req))
    question = (f"After {MAX_ROUNDS} rounds the plan still doesn't fit: "
                + "; ".join(describe(v) for v in state["violations"])
                + f". Raise the budget by ₹{raise_by:,}"
                + (", cut a day," if n_days > 1 else "") + " or accept the plan as it is?")
    answer = interrupt({"type": "retry_cap", "question": question, "raise_by": raise_by,
                        "options": ["raise", "cut", "accept"] if n_days > 1 else ["raise", "accept"]})
    low = str(answer).lower()
    choice = ("raise" if any(w in low for w in ("raise", "increase", "more", "yes"))
              else "cut" if any(w in low for w in ("cut", "day", "short")) and n_days > 1 else "accept")
    if choice == "raise":
        req["budget_inr"] += raise_by
    elif choice == "cut":
        req["end_date"] = trip_dates(req)[-2].isoformat()
    return {"request": req, "revision_count": 0, "last_violation": None,
            "budget_action": {"type": "rebalance"}, "next_agent": "finalize" if choice == "accept" else "budget",
            "log": [f"[User] chose to {choice}" + (f" (+₹{raise_by:,})" if choice == "raise" else "")]}
