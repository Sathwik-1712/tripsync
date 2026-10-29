"""Parser for the common subset of OpenStreetMap `opening_hours`, e.g.
"Mo-Su 09:00-17:00", "Tu-Su 10:00-17:00; Mo off", "Mo-Fr 09:00-13:00,14:00-18:00", "24/7", "sunrise-sunset".
Anything it can't read (PH rules, month ranges, comments) returns None, meaning "unknown"."""
import re
from functools import lru_cache

DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
_DAY_SPEC = re.compile(r"^(Mo|Tu|We|Th|Fr|Sa|Su)(-(Mo|Tu|We|Th|Fr|Sa|Su))?$")
_SPAN = re.compile(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\+?$")
SUN = {"sunrise": 6 * 60, "sunset": 18 * 60 + 30}  # good enough for India


def _days(spec: str) -> set[int] | None:
    out = set()
    for part in spec.split(","):
        m = _DAY_SPEC.match(part.strip())
        if not m:
            return None
        a, b = DAYS.index(m.group(1)), DAYS.index(m.group(3) or m.group(1))
        out |= set(range(a, b + 1)) if a <= b else set(range(a, 7)) | set(range(0, b + 1))
    return out


def _spans(spec: str) -> list[tuple[int, int]] | None:
    out = []
    for part in spec.split(","):
        part = part.strip()
        for word, minute in SUN.items():
            part = part.replace(word, f"{minute // 60:02d}:{minute % 60:02d}")
        m = _SPAN.match(part)
        if not m:
            return None
        h1, m1, h2, m2 = map(int, m.groups())
        start, end = h1 * 60 + m1, h2 * 60 + m2
        out.append((start, end if end > start else end + 24 * 60))
    return out


@lru_cache(maxsize=2048)
def parse(spec: str | None) -> tuple[tuple[tuple[int, int], ...], ...] | None:
    """Per weekday (Mo=0) a tuple of open (start, end) minute spans; an empty tuple means closed."""
    if not spec:
        return None
    spec = spec.strip()
    if spec == "24/7":
        return tuple(((0, 24 * 60),) for _ in DAYS)
    week: list[list[tuple[int, int]] | None] = [None] * 7
    for rule in filter(None, (r.strip() for r in spec.split(";"))):
        head, _, rest = rule.partition(" ")
        days = _days(head)
        if days is None:  # no weekday prefix: the rule applies to every day
            days, rest = set(range(7)), rule
        rest = rest.strip()
        if rest in ("off", "closed"):
            spans = []
        elif rest == "24/7" or rest == "00:00-24:00":
            spans = [(0, 24 * 60)]
        else:
            spans = _spans(rest)
            if spans is None:
                return None
        for d in days:  # later rules override earlier ones for the same day
            week[d] = spans
    if all(w is None for w in week):
        return None
    # Days never mentioned in a weekday-specific spec are closed.
    return tuple(tuple(w or ()) for w in week)


def closed_on(spec: str | None, weekday: int) -> bool:
    """True only when the hours are known and the place is shut all day."""
    week = parse(spec)
    return week is not None and not week[weekday]


def visit_problem(spec: str | None, weekday: int, arrive_min: int, visit_min: int) -> str | None:
    """Why a visit starting at `arrive_min` doesn't work, or None if it does (or the hours are unknown)."""
    week = parse(spec)
    if week is None:
        return None
    spans = week[weekday]
    if not spans:
        return f"closed on {['Mondays', 'Tuesdays', 'Wednesdays', 'Thursdays', 'Fridays', 'Saturdays', 'Sundays'][weekday]}"
    need = min(visit_min, 45)  # at least 45 minutes (or the whole visit, if shorter) before closing
    if any(s <= arrive_min and arrive_min + need <= e for s, e in spans):
        return None
    hours = ", ".join(f"{s // 60:02d}:{s % 60:02d}–{e // 60 % 24:02d}:{e % 60:02d}" for s, e in spans)
    return f"open {hours}"
