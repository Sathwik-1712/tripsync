"""Step 1: Intake + Clarify. Rule-based parsing is always run (deterministic,
no hallucination); the LLM only fills gaps the rules couldn't."""
import re
from datetime import date, timedelta

from langgraph.types import interrupt

from .. import llm
from ..state import FIELD_QUESTIONS, TripDraft, missing_fields, validation_errors
from ..tools.currency import to_inr
from ..tools.geo import find_cities, geocode, resolve_city

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
INTEREST_WORDS = {
    "history": r"histor|heritage|forts?\b|palace|monument",
    "culture": r"cultur|temple|church|spiritual|religio|\bart\b",
    "nature": r"nature|hik|trek|\bparks?\b|garden|hills|mountain|waterfall|lake",
    "beach": r"beach|\bsea\b",
    "food": r"\bfood|caf[eé]|cuisine|restaurant",
    "shopping": r"shopping|market|bazaar",
    "museums": r"museum|galler",
    "nightlife": r"nightlife|party|clubs?\b|\bbars?\b|\bpubs?\b",
    "adventure": r"adventure|rafting|paraglid",
}


def _year_for(month: int, day: int, today: date, year: str | None) -> date | None:
    try:
        if year:
            return date(int(year), month, day)
        d = date(today.year, month, day)
        return d if d >= today else date(today.year + 1, month, day)
    except ValueError:
        return None


def parse_dates(text: str, today: date) -> list[date]:
    low, found, spans = text.lower(), [], []

    def add(m, d):
        if d and not any(s < m.end() and m.start() < e for s, e in spans):
            spans.append((m.start(), m.end()))
            found.append((m.start(), d))

    # "10-14 Dec" / "10 to 14 December 2026"
    for m in re.finditer(rf"\b(\d{{1,2}})\s*(?:-|–|to)\s*(\d{{1,2}})\s+{MON}(?:\s*,?\s*(\d{{4}}))?", low):
        mon = MONTHS[m.group(3)[:3]]
        a, b = _year_for(mon, int(m.group(1)), today, m.group(4)), _year_for(mon, int(m.group(2)), today, m.group(4))
        if a and b:
            spans.append((m.start(), m.end()))
            found += [(m.start(), a), (m.start() + 1, b)]
    for m in re.finditer(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", low):
        try:
            add(m, date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", low):
        try:
            add(m, date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass
    for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{MON}(?:\s*,?\s*(\d{{4}}))?", low):
        add(m, _year_for(MONTHS[m.group(2)[:3]], int(m.group(1)), today, m.group(3)))
    for m in re.finditer(rf"\b{MON}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:\s*,?\s*(\d{{4}}))?", low):
        add(m, _year_for(MONTHS[m.group(1)[:3]], int(m.group(2)), today, m.group(3)))
    if re.search(r"\btomorrow\b", low):
        found.append((low.index("tomorrow"), today + timedelta(days=1)))
    return [d for _, d in sorted(found)]


def _amount(num: str, suffix: str | None) -> float:
    v = float(num.replace(",", ""))
    s = (suffix or "").lower()
    return v * 1000 if s == "k" else v * 100000 if s.startswith("l") else v


def parse_budget(text: str) -> tuple[float, str] | None:
    low = text.lower()
    num, suf = r"(\d[\d,]*(?:\.\d+)?)", r"\s*(k|lakhs?|lacs?|l)?\b"
    for pat, cur in [
        (rf"(?:₹|rs\.?|inr)\s*{num}{suf}", "INR"),
        (rf"{num}{suf}\s*(?:rupees|inr|rs\b)", "INR"),
        (rf"(?:\$|usd)\s*{num}\s*(k)?\b", "USD"),
        (rf"{num}\s*(k)?\s*(?:usd|dollars)", "USD"),
        (rf"(?:€|eur)\s*{num}\s*(k)?\b", "EUR"),
        (rf"{num}\s*(k)?\s*(?:eur|euros)", "EUR"),
        (rf"budget\s*(?:of|is|:|around|about|~|under|max)?\s*{num}{suf}", "INR"),
        # "about 60k total", "under 1.5 lakh": a k/lakh amount is money even without a currency sign
        (rf"(?<![\w.]){num}\s*(k|lakhs?|lacs?)\b(?!\s*(?:m|km|steps|ft|feet)\b)", "INR"),
    ]:
        m = re.search(pat, low)
        if m:
            return _amount(m.group(1), m.group(2)), cur
    return None


def parse_travellers(text: str) -> int | None:
    low = text.lower()
    parts = re.findall(r"(\d+)\s*(?:adults?|kids?|children|child)", low)
    if parts:
        return sum(map(int, parts))
    m = re.search(r"(\d+)\s*(?:people|persons?|pax|travell?ers|friends|of us|members|guests|ppl)\b", low)
    if m:
        return int(m.group(1))
    m = re.search(r"family of (\d+)", low)
    if m:
        return int(m.group(1))
    # "for 2," / "for 3 on 5 Dec" - a small bare number after "for" that isn't a duration or an amount.
    m = re.search(r"\bfor\s+(\d{1,2})\b(?!\s*-?\s*(?:days?|nights?|weeks?|k\b|thousand|lakhs?|rs|inr|₹|/|:|\d))", low)
    if m:
        return int(m.group(1))
    if re.search(r"\b(solo|alone|by myself|just me)\b", low):
        return 1
    if re.search(r"\b(couple|honeymoon|two of us|my (wife|husband|partner|girlfriend|boyfriend))\b", low):
        return 2
    return None


PRIORITY_WORDS = {  # what the traveller wants to spend more on; checked in this order
    "balanced": r"\bbalanced\b|no preference|(doesn'?t|does not) matter|keep it even|evenly",
    "stay": r"(nicer|better|comfortable|good|great|luxur\w*|fancy) (stay|hotel|room|accommodation)|"
            r"(splurge|spend more) on (the )?(stay|hotel|accommodation)|stay matters",
    "travel": r"(faster|fast|quick|quicker|comfortable|shorter) (travel|journey|transport|flights?)|"
              r"(splurge|spend more) on (travel|transport|flights?)",
    "food": r"(better|good|great|nice|fine) (food|dining|meals|restaurants)|(splurge|spend more) on (food|dining|eating)",
    "experiences": r"more (experiences|activities|things to do|sightseeing)|(splurge|spend more) on "
                   r"(experiences|activities|sightseeing)",
}
BARE_PRIORITY = {"balanced": "balanced", "even": "balanced", "stay": "stay", "hotel": "stay", "hotels": "stay",
                 "travel": "travel", "flight": "travel", "flights": "travel", "transport": "travel",
                 "food": "food", "dining": "food", "experiences": "experiences", "experience": "experiences",
                 "activities": "experiences", "sightseeing": "experiences"}


def parse_priority(text: str) -> str | None:
    low = text.lower()
    return next((k for k, pat in PRIORITY_WORDS.items() if re.search(pat, low)), None)


def parse_message(text: str, today: date) -> dict:
    """Rule-based extraction. Returns only the fields it found."""
    low, out = text.lower(), {}

    cities = find_cities(text)
    for pos, city in cities:
        before = low[max(0, pos - 25):pos]
        if re.search(r"\bfrom\s+$", before):
            out.setdefault("origin", city)
        elif re.search(r"\b(to|visit|visiting|in|explore|for|at)\s+(the\s+)?$", before):
            out.setdefault("destination", city)
    for _, city in cities:
        if city in out.values():
            continue
        if "destination" not in out:
            out["destination"] = city
        elif "origin" not in out:
            out["origin"] = city

    dates = parse_dates(text, today)
    if dates:
        out["start_date"] = dates[0].isoformat()
        if len(dates) > 1 and dates[1] >= dates[0]:
            out["end_date"] = dates[1].isoformat()
    m = re.search(r"(\d+)\s*-?\s*(day|night)s?\b", low) or (re.search(r"\b(a)\s+(week)\b", low))
    if m:
        n = 7 if m.group(2) == "week" else int(m.group(1)) + (1 if m.group(2) == "night" else 0)
        out["num_days"] = n

    if (t := parse_travellers(text)) is not None:
        out["travellers"] = t
    if (b := parse_budget(text)) is not None:
        out["budget_amount"], out["budget_currency"] = b

    interests = [k for k, pat in INTEREST_WORDS.items() if re.search(pat, low)]
    if interests:
        out["interests"] = interests
    if re.search(r"\b(relax|slow|chill|leisure|easy)", low):
        out["pace"] = "relaxed"
    elif re.search(r"\b(packed|fast|busy|action|as much as)", low):
        out["pace"] = "packed"
    if m := re.search(r"\b(?:by|take|prefer|via)\s+(?:a\s+|the\s+)?(train|flight|bus|air|plane)\b|\b(fly|flying)\b", low):
        word = m.group(1) or "flight"
        out["preferred_mode"] = {"air": "flight", "plane": "flight"}.get(word, word)
    if p := parse_priority(text):
        out["priority"] = p
    if re.search(r"\b(luxury|premium|5[- ]?star|five[- ]star)\b", low):
        out["stay_tier"] = "premium"
    elif re.search(r"\b(cheap|backpack|hostel|budget (hotel|stay))", low):
        out["stay_tier"] = "budget"
    return out


def parse_bare_answer(text: str, field: str, today: date) -> dict:
    """Clarify answers like 'Mumbai' or '4' when exactly one field is missing."""
    text = text.strip()
    if field in ("origin", "destination"):
        city = resolve_city(text) or (text.title() if re.fullmatch(r"[A-Za-z .'-]{2,40}", text) else None)
        return {field: city} if city else {}
    if field == "travellers" and (m := re.fullmatch(r"(\d+)", text)):
        return {"travellers": int(m.group(1))}
    if field == "budget_inr" and (m := re.fullmatch(r"(\d[\d,]*(?:\.\d+)?)\s*(k|lakhs?|l)?", text.lower())):
        return {"budget_amount": _amount(m.group(1), m.group(2)), "budget_currency": "INR"}
    if field == "priority":
        words = re.findall(r"[a-z]+", text.lower())
        hit = next((BARE_PRIORITY[w] for w in words if w in BARE_PRIORITY), None)
        return {"priority": hit} if hit else {}
    if field == "end_date" and (m := re.fullmatch(r"(\d+)", text)):
        return {"num_days": int(m.group(1))}
    return {}


def _llm_extract(text: str, today: date) -> dict:
    draft = llm.structured(TripDraft, (
        f"Today is {today.isoformat()}. Extract trip details from the user's message for a trip within India. "
        "Use null for anything not stated; never guess. Dates as YYYY-MM-DD.\n\nMessage: " + text))
    return {k: v for k, v in (draft.model_dump() if draft else {}).items() if v not in (None, [], "")}


def merge_into_request(req: dict, found: dict) -> dict:
    req = dict(req)
    for k in ("origin", "destination", "start_date", "end_date", "travellers", "pace", "preferred_mode", "stay_tier",
              "priority"):
        if found.get(k):
            req[k] = found[k]
    if found.get("stay_tier"):
        req["_tier_chosen"] = True
    if found.get("interests"):
        req["interests"] = sorted(set(req.get("interests", [])) | set(found["interests"]))
    if found.get("num_days") and req.get("start_date") and not found.get("end_date"):
        req["end_date"] = (date.fromisoformat(req["start_date"]) + timedelta(days=found["num_days"] - 1)).isoformat()
    elif found.get("num_days"):
        req["_num_days"] = found["num_days"]
    if req.get("_num_days") and req.get("start_date") and not req.get("end_date"):
        req["end_date"] = (date.fromisoformat(req["start_date"]) + timedelta(days=req.pop("_num_days") - 1)).isoformat()
    if found.get("budget_amount"):
        cur = (found.get("budget_currency") or "INR").upper()
        inr, _ = to_inr(found["budget_amount"], cur)
        req["budget_inr"] = round(inr)
        req["budget_original"] = {"amount": found["budget_amount"], "currency": cur}
    req.setdefault("interests", [])
    req.setdefault("pace", "moderate")
    req.setdefault("stay_tier", "mid")
    req.setdefault("preferred_mode", None)
    # "Nicer stay" means a premium hotel unless the traveller picked a hotel tier themselves.
    if req.get("priority") == "stay" and not req.get("_tier_chosen"):
        req["stay_tier"] = "premium"
    return req


def extract(text: str, today: date, missing: list[str] | None = None) -> dict:
    found = parse_message(text, today)
    if missing and len(missing) == 1 and not any(k in found for k in (missing[0], "num_days", "budget_amount")):
        found.update(parse_bare_answer(text, missing[0], today))
    gaps = [f for f in (missing or ["origin", "destination", "start_date", "travellers", "budget_inr"])
            if not found.get({"budget_inr": "budget_amount"}.get(f, f))]
    if gaps:
        for k, v in _llm_extract(text, today).items():
            found.setdefault(k, v)
    return found


def intake_node(state: dict) -> dict:
    today = date.today()
    req = merge_into_request({}, extract(state.get("user_message", ""), today))
    got = [k for k in ("origin", "destination", "start_date", "end_date", "travellers", "budget_inr") if req.get(k)]
    return {"request": req, "revision_count": 0, "constraints": {}, "final": None, "replans": [],
            "log": [f"[Intake] understood: {', '.join(got) or 'nothing yet'}"]}


def _place_errors(req: dict) -> list[str]:
    """Origin and destination must be places we can put on a map."""
    return [f"I couldn't find {req[f]} on the map." for f in ("origin", "destination")
            if req.get(f) and not geocode(req[f])]


def clarify_node(state: dict) -> dict:
    """Human-in-the-loop: pause with interrupt() until every required field is known and valid."""
    req = dict(state["request"])
    place_errs = _place_errors(req)
    for f in ("origin", "destination"):  # drop unknown places so the question asks for them again
        if req.get(f) and not geocode(req[f]):
            req.pop(f)
    missing, errors = missing_fields(req), validation_errors(req) + place_errs
    if not missing and not errors:
        return {}
    question = " ".join(errors + [FIELD_QUESTIONS[f] for f in missing])
    answer = interrupt({"type": "clarify", "question": question, "missing": missing, "errors": errors})
    if errors:  # let the answer overwrite bad values
        for f in ("start_date", "end_date"):
            if any("date" in e for e in errors):
                req = {k: v for k, v in req.items() if k != f}
    req = merge_into_request(req, extract(str(answer), date.today(), missing_fields(req)))
    return {"request": req, "log": [f"[Clarify] asked: {question}"]}


def route_after_clarify(state: dict) -> str:
    req = state["request"]
    ok = not missing_fields(req) and not validation_errors(req) and not _place_errors(req)
    return "budget" if ok else "clarify"
