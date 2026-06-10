"""Markedsodds fra The Odds API (valgfritt).

Registrer en gratis nøkkel på https://the-odds-api.com og legg den som
hemmeligheten THE_ODDS_API_KEY (GitHub Actions secret eller miljøvariabel).
Uten nøkkel hopper pipelinen stille over markedsdata og bruker ren modell.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import config
from .fetch import http_get


def _devig(prices: dict[str, float]) -> dict[str, float] | None:
    """Fjern bookmakermarginen proporsjonalt fra desimalodds."""
    if any(p <= 1.0 for p in prices.values()):
        return None
    implied = {k: 1.0 / p for k, p in prices.items()}
    total = sum(implied.values())
    if total <= 0:
        return None
    return {k: v / total for k, v in implied.items()}


def _find_world_cup_sport_keys(api_key: str) -> list[str]:
    text = http_get(f"{config.ODDS_API_BASE}/sports/?all=true&apiKey={api_key}")
    sports = json.loads(text)
    keys = []
    for s in sports:
        key = s.get("key", "")
        if "world_cup" not in key:
            continue
        if any(skip in key for skip in ("winner", "qualif", "women")):
            continue
        if s.get("group") != "Soccer":
            continue
        keys.append(key)
    return keys


def fetch_market_odds() -> dict:
    """Hent 1X2-odds for VM-kamper. Returnerer {"(hjemme, borte)": {...}}.

    Nøkkelformat i retur: "Hjemmelag|Bortelag" med openfootball-navn.
    """
    result = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "available": False,
        "events": {},
    }
    if not config.ODDS_API_KEY:
        result["note"] = "THE_ODDS_API_KEY ikke satt, markedsodds hoppes over"
        return result

    try:
        sport_keys = _find_world_cup_sport_keys(config.ODDS_API_KEY)
        for sport_key in sport_keys:
            url = (
                f"{config.ODDS_API_BASE}/sports/{sport_key}/odds"
                f"?regions=eu&markets=h2h&oddsFormat=decimal"
                f"&apiKey={config.ODDS_API_KEY}"
            )
            events = json.loads(http_get(url))
            for ev in events:
                home = config.canonical_name(ev.get("home_team", ""))
                away = config.canonical_name(ev.get("away_team", ""))
                probs_per_book = []
                for book in ev.get("bookmakers", []):
                    for market in book.get("markets", []):
                        if market.get("key") != "h2h":
                            continue
                        prices = {}
                        for outcome in market.get("outcomes", []):
                            name = outcome.get("name", "")
                            price = float(outcome.get("price", 0))
                            if name == "Draw":
                                prices["draw"] = price
                            elif config.canonical_name(name) == home:
                                prices["home"] = price
                            elif config.canonical_name(name) == away:
                                prices["away"] = price
                        if set(prices) == {"home", "draw", "away"}:
                            devigged = _devig(prices)
                            if devigged:
                                probs_per_book.append(devigged)
                if not probs_per_book:
                    continue
                n = len(probs_per_book)
                avg = {
                    k: sum(p[k] for p in probs_per_book) / n
                    for k in ("home", "draw", "away")
                }
                total = sum(avg.values())
                result["events"][f"{home}|{away}"] = {
                    "p_home": avg["home"] / total,
                    "p_draw": avg["draw"] / total,
                    "p_away": avg["away"] / total,
                    "bookmakers": n,
                    "commence": ev.get("commence_time"),
                }
        result["available"] = bool(result["events"])
    except Exception as exc:  # noqa: BLE001 - odds er en valgfri kilde
        result["error"] = str(exc)
    return result


def load_or_fetch_market_odds() -> dict:
    """Hent ferske odds; fall tilbake til cache ved feil."""
    cache_file = config.CACHE_DIR / "market_odds.json"
    odds = fetch_market_odds()
    if odds["available"]:
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(odds, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return odds
    if cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        cached["note"] = "bruker mellomlagrede odds (ferskt kall feilet eller manglet)"
        return cached
    return odds


def lookup(odds: dict, home: str, away: str) -> dict | None:
    """Finn markedssannsynligheter for et kampoppgjør, uansett banerekkefølge."""
    ev = odds.get("events", {}).get(f"{home}|{away}")
    if ev:
        return ev
    rev = odds.get("events", {}).get(f"{away}|{home}")
    if rev:
        return {
            "p_home": rev["p_away"],
            "p_draw": rev["p_draw"],
            "p_away": rev["p_home"],
            "bookmakers": rev["bookmakers"],
            "commence": rev.get("commence"),
        }
    return None


def blend(model_probs: tuple[float, float, float], market: dict | None) -> dict:
    """Vektet blanding av modell- og markedssannsynligheter."""
    p_h, p_d, p_a = model_probs
    if not market:
        return {"p_home": p_h, "p_draw": p_d, "p_away": p_a, "source": "modell"}
    w = config.MARKET_WEIGHT
    blended = {
        "p_home": w * market["p_home"] + (1 - w) * p_h,
        "p_draw": w * market["p_draw"] + (1 - w) * p_d,
        "p_away": w * market["p_away"] + (1 - w) * p_a,
    }
    total = sum(blended.values())
    return {
        **{k: v / total for k, v in blended.items()},
        "source": f"marked ({market['bookmakers']} bookmakere) + modell",
    }
