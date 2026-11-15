"""Every decision the AI model takes part in, in one place. The pattern is always the same:

  1. the model is shown only real data (places from OpenStreetMap, the real day plan, the real problems found)
     and may only choose from it, by number;
  2. code checks the answer, and anything that isn't one of the given choices is thrown away;
  3. if no model answers (offline, rate limit), the rule-based choice is used instead;
  4. what the model suggested and what the code did with it go into the trace ("Under the hood").

So the AI can change *which* real option is chosen and explain it, but it can never add a place, a price or a
distance that didn't come from a real source."""
from typing import Literal

from pydantic import BaseModel, Field

from .. import llm, trace

# ---------- Activity agent: which places to suggest ----------


class Pick(BaseModel):
    n: int = Field(description="The number of the place in the list")
    reason: str = Field(description="One short sentence: why this place suits this traveller")


class Curation(BaseModel):
    picks: list[Pick] = Field(default_factory=list)


def curate_places(cands: list[dict], req: dict, weather: list, days: int) -> dict[str, str]:
    """{place id: reason} for the places the AI suggests, best first. Empty if no model answered."""
    if not cands:
        return {}
    shown = cands[:40]
    want = max(3, days * {"relaxed": 2, "moderate": 3, "packed": 4}.get(req.get("pace") or "moderate", 3))
    rain = [w["date"] for w in weather if w.get("precip_mm", 0) >= 5 or (w.get("precip_prob") or 0) >= 60]
    lines = [f"{i + 1}. {p['name']} | {p['kind']} | {'indoor' if p['indoor'] else 'outdoor'} | ~{p['minutes']} min"
             f" | fee ₹{p['fee']}{' | ' + p['description'][:90] if p.get('description') else ''}"
             for i, p in enumerate(shown)]
    answer = llm.structured(Curation, (
        f"You are the Activity agent of a trip planner. Traveller: {req['travellers']} people, {days} days in "
        f"{req['destination']}, pace {req.get('pace') or 'moderate'}, interests: "
        f"{', '.join(req.get('interests') or []) or 'not stated'}, priority: {req.get('priority') or 'balanced'}."
        f"{' Rain is likely on ' + ', '.join(rain) + ', so include some indoor places.' if rain else ''}\n"
        f"Choose about {want} places from this list ONLY, best first, as a balanced mix (not all one kind). "
        "Answer with their numbers and one short reason each. Never name a place that is not in the list.\n"
        + "\n".join(lines)), purpose="Activity: choose places to suggest")
    if answer is None:
        return {}
    picks, bad = {}, []
    for p in answer.picks:
        if 1 <= p.n <= len(shown) and shown[p.n - 1]["id"] not in picks:
            picks[shown[p.n - 1]["id"]] = p.reason.strip()[:160]
        else:
            bad.append(p.n)
    names = [c["name"] for c in shown if c["id"] in picks]
    trace.ai("Choose places to suggest", ", ".join(names) or "nothing usable",
             f"Kept {len(picks)} real places from the list" + (f"; ignored {len(bad)} invalid numbers" if bad else ""),
             bool(picks))
    return picks


# ---------- Critic: a second opinion on a plan that passed the rule checks ----------


class Concern(BaseModel):
    day: int
    type: Literal["overpacked", "too_much_travel", "heat", "crowds", "other"]
    reason: str


class Review(BaseModel):
    concerns: list[Concern] = Field(default_factory=list)


ACTIONABLE = {"overpacked", "too_much_travel"}


def review_plan(state: dict) -> tuple[dict | None, list[str]]:
    """Ask the AI to look over the days. Returns (a day to lighten, if the AI found one and the code agrees it
    is a real day with more than one stop; tips to show the traveller)."""
    days, req = state["itinerary"]["days"], state["request"]
    lines = []
    for d in days:
        w = d.get("weather") or {}
        wx = f", {w.get('tmax', 0):.0f}°C, rain {w.get('precip_mm', 0):.0f} mm" if w else ""
        lines.append(f"Day {d['day']} ({d['date']}{wx}): " + ", ".join(f"{s['name']} (~{s['minutes']} min)"
                                                                        for s in d["stops"])
                     + f"; {d['travel_min']} min on the road" if d["stops"] else f"Day {d['day']}: free")
    answer = llm.structured(Review, (
        "You are the Critic agent of a trip planner. This plan already passed the budget, weather and opening-hours "
        f"checks. Pace asked for: {req.get('pace') or 'moderate'}. Point out at most 2 real practical concerns. "
        "Use type 'overpacked' or 'too_much_travel' only if a day is clearly too much for that pace. Do not suggest "
        "new places. If the plan is fine, return no concerns.\n" + "\n".join(lines)),
        purpose="Critic: second opinion on the days")
    if answer is None:
        return None, []
    by_day = {d["day"]: d for d in days}
    fix, tips, notes = None, [], []
    for c in answer.concerns[:2]:
        d = by_day.get(c.day)
        if c.type in ACTIONABLE and d and len(d["stops"]) > 1 and fix is None:
            fix = {"type": "overpacked_day", "day": d["day"], "count": len(d["stops"]),
                   "travel_min": d["travel_min"], "source": "ai", "reason": c.reason.strip()[:200]}
            notes.append(f"day {c.day} {c.type.replace('_', ' ')}: accepted, sent back to lighten it")
        elif d or c.type not in ACTIONABLE:
            tips.append(f"Day {c.day}: {c.reason.strip()[:200]}" if d else c.reason.strip()[:200])
            notes.append(f"day {c.day} {c.type}: shown as a tip" if c.type not in ACTIONABLE
                         else f"day {c.day}: only one stop, nothing to lighten, shown as a tip")
        else:
            notes.append(f"day {c.day}: no such day, ignored")
    trace.ai("Second opinion on the plan",
             "; ".join(f"day {c.day} {c.type}: {c.reason}" for c in answer.concerns[:2]) or "No concerns",
             "; ".join(notes) or "The plan is fine as it is, so nothing changes", True)
    return fix, tips


# ---------- Critic: which problem to fix first ----------


class FixFirst(BaseModel):
    n: int = Field(description="The number of the problem to fix first")
    reason: str


def choose_first(options: list[tuple[dict, str, str]]) -> int | None:
    """options: (violation, description, agent that would fix it), all already allowed by the rules.
    Returns the index the AI picked, or None to keep the rule order."""
    if len({agent for _, _, agent in options}) < 2:  # every choice goes to the same agent: nothing to decide
        return None
    lines = [f"{i + 1}. {desc} -> {agent} agent" for i, (_, desc, agent) in enumerate(options)]
    answer = llm.structured(FixFirst, (
        "You are the Critic agent of a trip planner. The plan has several problems; each can be sent to the agent "
        "that fixes it. Fixing one may also fix others (e.g. a cheaper stay helps the total). Which should be fixed "
        "first? Answer with its number and a short reason.\n" + "\n".join(lines)),
        purpose="Critic: which problem to fix first")
    if answer is None:
        return None
    ok = 1 <= answer.n <= len(options)
    trace.ai("Which problem to fix first", f"#{answer.n}: {answer.reason}",
             f"Accepted: send to the {options[answer.n - 1][2]} agent" if ok else
             "Not one of the given problems, so the rule order was kept", ok)
    return answer.n - 1 if ok else None


# ---------- Final step: why each day is grouped the way it is ----------


class DayNote(BaseModel):
    day: int
    note: str


class DayNotes(BaseModel):
    days: list[DayNote] = Field(default_factory=list)


def day_notes(days: list[dict], hotel: str) -> dict[int, str]:
    """{day number: one line on why these stops are together}, from the real road distances."""
    lines = []
    for d in days:
        if not d["stops"]:
            continue
        legs = d.get("legs") or []
        hops = "; ".join(f"{l['from']} → {l['to']} {l['km']} km ~{l['minutes']} min" for l in legs)
        lines.append(f"Day {d['day']}: {', '.join(s['name'] for s in d['stops'])}. Real routes: {hops}")
    if not lines:
        return {}
    answer = llm.structured(DayNotes, (
        f"For each day of this trip (hotel: {hotel}), write one short, friendly sentence for the traveller on why these "
        "stops share a day: what kind of day it is (e.g. churches and museums, beaches and a fort) and whether the "
        "stops are a short hop apart or spread out, using the distances given. No new places, prices or opening "
        "times, and don't list every number.\n" + "\n".join(lines)),
        purpose="Explain how the days are grouped")
    if answer is None:
        return {}
    real = {d["day"] for d in days if d["stops"]}
    notes = {n.day: n.note.strip()[:220] for n in answer.days if n.day in real}
    trace.ai("Explain how the days are grouped", f"{len(answer.days)} day notes",
             f"Kept {len(notes)} (text only; no places or numbers changed)", bool(notes))
    return notes
