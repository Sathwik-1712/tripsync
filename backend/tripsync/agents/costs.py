"""Cost model shared by the Budget Agent (estimates) and the Planner/Critic (actuals)."""
from ..tools.geo import city_info


def food_per_person_day(city: str, stay_tier: str) -> int:
    info = city_info(city)
    return info["food_budget" if stay_tier == "budget" else "food_premium" if stay_tier == "premium" else "food_mid"]


def food_tier(req: dict, stay_tier: str) -> str:
    """Eat at the level of the stay, or better if the traveller wants to spend more on food."""
    return "premium" if req.get("priority") == "food" else stay_tier


def compute_costs(req: dict, transport: dict, stay: dict, itinerary: dict) -> dict:
    n, days = req["travellers"], len(itinerary["days"])
    info = city_info(req["destination"])
    fees = sum(s["fee"] for d in itinerary["days"] for s in d["stops"]) * n
    # Autos and cabs between the day's stops, from the planner's directions (typical fares).
    local = sum(leg["fare"] for d in itinerary["days"] for leg in d.get("legs") or [])
    costs = {
        "transport": transport["choice"]["total"],
        "stay": stay["choice"]["total"],
        "activities": fees + local,  # entry fees + local autos/cabs
        "food": food_per_person_day(req["destination"], food_tier(req, stay["choice"]["tier"])) * n * days,
    }
    transfers = sum(t["fare"] for t in (itinerary.get("transfers") or {}).values() if t)
    costs["transport"] += transfers  # cabs between the airport/station and the stay
    costs["total"] = sum(costs.values())
    costs["budget"] = req["budget_inr"]
    costs["entry_fees"], costs["local_travel"], costs["transfers"] = fees, local, transfers
    return costs
