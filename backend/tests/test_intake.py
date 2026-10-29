from datetime import date

from tripsync.agents.intake import extract, merge_into_request, parse_budget

TODAY = date(2026, 10, 27)


def test_full_message():
    req = merge_into_request({}, extract(
        "Plan a 4 day trip from Delhi to Jaipur for 2 people starting 10 Dec, budget ₹30k, love history", TODAY))
    assert req["origin"] == "Delhi" and req["destination"] == "Jaipur"
    assert req["start_date"] == "2026-12-10" and req["end_date"] == "2026-12-13"
    assert req["travellers"] == 2 and req["budget_inr"] == 30000
    assert "history" in req["interests"]


def test_aliases_range_and_preferences():
    found = extract("Bangalore to Goa, 12-15 Nov, 3 friends, budget of 45,000, beaches, relaxed, by train", TODAY)
    assert found["origin"] == "Bengaluru" and found["destination"] == "Goa"
    assert (found["start_date"], found["end_date"]) == ("2026-11-12", "2026-11-15")
    assert found["pace"] == "relaxed" and found["preferred_mode"] == "train"


def test_budget_formats():
    assert parse_budget("₹1.5 lakh") == (150000, "INR")
    assert parse_budget("Rs. 40,000") == (40000, "INR")
    assert parse_budget("$500") == (500, "USD")


def test_bare_clarify_answer():
    assert extract("Mumbai", TODAY, missing=["origin"])["origin"] == "Mumbai"
    assert extract("4", TODAY, missing=["travellers"])["travellers"] == 4
