"""Frankfurter exchange rates (no key), with rough static fallbacks."""
import logging

from ..http import get_json

log = logging.getLogger(__name__)
FALLBACK_TO_INR = {"INR": 1.0, "USD": 88.0, "EUR": 102.0, "GBP": 117.0, "AED": 24.0, "SGD": 68.0}


def to_inr(amount: float, currency: str) -> tuple[float, str]:
    currency = (currency or "INR").upper()
    if currency == "INR":
        return amount, "n/a"
    for url in ("https://api.frankfurter.dev/v1/latest", "https://api.frankfurter.app/latest"):
        try:
            res = get_json(url, {"from": currency, "to": "INR"})
            return amount * res["rates"]["INR"], "Frankfurter"
        except Exception as e:  # noqa: BLE001
            log.info("Frankfurter failed: %s", e)
    return amount * FALLBACK_TO_INR.get(currency, 1.0), "static rate"
