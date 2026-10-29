from tripsync.agents.budget import initial_split, reallocate

REQ = {"origin": "Delhi", "destination": "Jaipur", "start_date": "2026-12-10", "end_date": "2026-12-13",
       "travellers": 2, "budget_inr": 30000, "stay_tier": "mid"}


def test_split_sums_to_budget_with_buffer():
    alloc, _, _ = initial_split(REQ)
    assert sum(alloc.values()) == 30000
    assert alloc["buffer"] >= 0.09 * 30000


def test_reallocate_uses_buffer_then_slack():
    alloc = {"transport": 1000, "stay": 5000, "activities": 2000, "food": 2000, "buffer": 500}
    costs = {"transport": 2500, "stay": 4000, "activities": 2000, "food": 2000}
    new, covered = reallocate(alloc, costs, "transport", 1500)
    assert covered == 1500 and new["transport"] == 2500
    assert new["buffer"] == 0 and new["stay"] == 4000
    assert sum(new.values()) == sum(alloc.values())
