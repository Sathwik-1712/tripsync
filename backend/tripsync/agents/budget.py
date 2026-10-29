"""Step 2: Budget Agent (budget-first). Runs alone before the other agents and
writes hard per-category limits into shared state."""
from datetime import date

from .. import db
from ..config import BUFFER_SHARE
from ..state import change, trip_dates
from ..tools.geo import city_info
from ..tools.transport import transport_options
from .costs import food_per_person_day, food_tier

CATEGORIES = ["transport", "stay", "activities", "food"]


# What each priority boosts, and how it is explained to the traveller.
PRIORITY_BOOST = 1.5
PRIORITY_CATEGORY = {"stay": "stay", "travel": "transport", "food": "food", "experiences": "activities"}
PRIORITY_REASON = {
    "stay": "You chose a nicer stay, so stay gets {x}× its usual share and we look at premium hotels first.",
    "travel": "You chose faster travel, so transport gets {x}× its usual share and the quickest option that "
              "fits is picked.",
    "food": "You chose better food, so food gets {x}× its usual share, priced at premium restaurants.",
    "experiences": "You chose more experiences, so activities get {x}× its usual share: more stops a day and "
                   "paid sights are fine.",
    "balanced": "You kept it balanced, so each category gets what it typically costs.",
}


def typical_costs(req: dict) -> dict:
    """What each category typically costs for this trip, from the static tables (no live calls).
    The traveller's priority changes what 'typical' means: premium stay, fastest transport, etc."""
    days = len(trip_dates(req))
    n, info = req["travellers"], city_info(req["destination"])
    tier, priority = req.get("stay_tier", "mid"), req.get("priority")
    opts = transport_options(req["origin"], req["destination"], date.fromisoformat(req["start_date"]),
                             date.fromisoformat(req["end_date"]), n, live=False)
    for o in opts:  # fares seen for this route and month beat the static table
        if seen := db.fare_stats(req["origin"], req["destination"], o["mode"], date.fromisoformat(req["start_date"])):
            o["total"] = seen["median"] * n * 2
    totals = sorted(o["total"] for o in opts) or [0]
    transport = totals[len(totals) // 2]
    if priority == "travel" and opts:
        transport = min(opts, key=lambda o: o["hours"])["total"]
    rooms, cabs = -(-n // 2), -(-n // 4)
    nightly = info[f"stay_{tier}"]
    if seen := db.hotel_price_stats(req["destination"], tier):  # real prices seen beat the static table
        nightly = seen["median"]
    return {
        "transport": transport + 2 * cabs * 600,  # plus a cab each way between airport/station and stay
        "stay": nightly * rooms * max(1, days - 1),
        "activities": ((450 if priority == "experiences" else 250) * n + info["local_per_day"]) * days,
        "food": food_per_person_day(req["destination"], food_tier(req, tier)) * n * days,
    }


def initial_split(req: dict) -> tuple[dict, dict, list[str]]:
    """Weight each category by its typical cost (the priority category counts 1.5×), then scale to
    (1 - buffer) of the budget. Also returns the reasoning shown to the traveller."""
    typical = typical_costs(req)
    budget, priority = req["budget_inr"], req.get("priority") or "balanced"
    boosted = PRIORITY_CATEGORY.get(priority)
    weights = {c: typical[c] * (PRIORITY_BOOST if c == boosted else 1) for c in CATEGORIES}
    spendable = budget * (1 - BUFFER_SHARE)
    total_w = sum(weights.values()) or 1
    alloc = {c: int(round(spendable * weights[c] / total_w, -2)) for c in CATEGORIES}
    alloc["buffer"] = int(budget - sum(alloc.values()))
    days, typical_total = len(trip_dates(req)), sum(typical.values())
    basis = [
        f"Typical costs for {req['travellers']} {'person' if req['travellers'] == 1 else 'people'} in "
        f"{req['destination']} over {days} day{'s' if days != 1 else ''} come to ₹{typical_total:,}.",
        PRIORITY_REASON[priority].format(x=PRIORITY_BOOST),
        f"{int(BUFFER_SHARE * 100)}% (₹{alloc['buffer']:,}) is held back as a buffer for surprises.",
    ]
    if typical_total > budget:
        basis.append(f"Your budget is ₹{typical_total - budget:,} under the typical total, so every category is "
                     "scaled down and the agents look for cheaper options.")
    return alloc, typical, basis


def reallocate(alloc: dict, costs: dict, category: str, deficit: int) -> tuple[dict, int]:
    """Cover `deficit` in `category`: buffer first, then slack in other categories."""
    alloc, need = dict(alloc), deficit
    sources = ["buffer"] + [c for c in CATEGORIES if c != category]
    for src in sources:
        if need <= 0:
            break
        slack = alloc[src] if src == "buffer" else alloc[src] - costs.get(src, alloc[src])
        take = max(0, min(slack, need))
        alloc[src] -= take
        alloc[category] += take
        need -= take
    return alloc, deficit - need


def rebalance(budget: int, costs: dict) -> dict | None:
    """After the user raises the budget or cuts a day: give each category what the
    current plan actually needs, keep up to the normal buffer, spread the rest."""
    need = {c: costs[c] for c in CATEGORIES}
    spare = budget - sum(need.values())
    if spare < 0:
        return None
    buffer = min(spare, int(budget * BUFFER_SHARE))
    extra = spare - buffer
    alloc = {c: need[c] + int(extra * need[c] / (sum(need.values()) or 1)) for c in CATEGORIES}
    alloc["buffer"] = budget - sum(alloc.values())
    return alloc


def budget_node(state: dict) -> dict:
    req, action = state["request"], state.get("budget_action") or {"type": "split"}
    if action["type"] == "realloc" and state.get("allocations"):
        alloc, covered = reallocate(state["allocations"], state.get("costs", {}), action["category"], action["deficit"])
        cat, old = action["category"], state["allocations"][action["category"]]
        msg = (f"[Budget] moved ₹{covered:,} into {cat} "
               f"(needed ₹{action['deficit']:,}{'' if covered >= action['deficit'] else ', could not cover all'})")
        note = [change("budget", f"{cat.title()} limit ₹{old:,}", f"₹{alloc[cat]:,}",
                       f"{cat.title()} cost ₹{action['deficit']:,} more than its share, so ₹{covered:,} was moved from "
                       "the buffer and categories with money left over, instead of downgrading anything")] if covered else []
        return {"allocations": alloc, "budget_action": None, "log": [msg], "changes": note}
    if action["type"] == "rebalance" and state.get("costs"):
        alloc = rebalance(req["budget_inr"], state["costs"])
        if alloc:
            return {"allocations": alloc, "budget_action": None,
                    "log": ["[Budget] rebalanced around the current plan: "
                            + ", ".join(f"{k} ₹{v:,}" for k, v in alloc.items())]}
    alloc, typical, basis = initial_split(req)
    tier = req.get("stay_tier", "mid")
    if seen := db.hotel_price_stats(req["destination"], tier):
        basis.insert(1, f"Stay is estimated from {seen['n']} real {tier} hotel prices in {req['destination']} seen "
                        f"since {seen['since']} (median ₹{seen['median']:,} a room a night).")
    tight = sum(typical.values()) > req["budget_inr"]
    msg = "[Budget] limits: " + ", ".join(f"{k} ₹{v:,}" for k, v in alloc.items())
    if tight:
        msg += f" (tight: typical mid-range total is ₹{sum(typical.values()):,})"
    return {"allocations": alloc, "budget_action": None, "log": [msg],
            "constraints": {"budget": {"typical": typical, "basis": basis}}}
