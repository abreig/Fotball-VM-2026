"""Hovedsteg: bygg prediksjoner og skriv site/data/predictions.json.

Kjøring: python -m pipeline.predict (etter python -m pipeline.fetch)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from . import config, elo as elo_mod, markets, model as model_mod, simulate
from .fetch import load_text
from .openfootball import is_placeholder, parse_tournament

STAGE_LABELS = {
    "group": "Gruppespill",
    "r32": "Sekstendedelsfinale",
    "r16": "Åttendedelsfinale",
    "qf": "Kvartfinale",
    "sf": "Semifinale",
    "third": "Bronsefinale",
    "final": "Finale",
}


def build_elo_state() -> elo_mod.EloResult:
    csv_text = load_text("results.csv")
    if csv_text:
        return elo_mod.compute_from_results_csv(csv_text)
    seed_file = config.SEED_DIR / "elo_seed.json"
    if seed_file.exists():
        print("Advarsel: results.csv mangler, bruker elo_seed.json", file=sys.stderr)
        seed = json.loads(seed_file.read_text(encoding="utf-8"))
        state = elo_mod.EloResult()
        state.ratings = seed["ratings"]
        state.match_counts = {t: 999 for t in seed["ratings"]}
        return state
    raise SystemExit("Ingen resultatdata tilgjengelig (kjør pipeline.fetch først)")


def fit_goal_model(state: elo_mod.EloResult) -> model_mod.GoalModel:
    if state.samples:
        gm = model_mod.fit_model(state.samples, state.match_samples)
    else:
        # Fallback-parametre fra tidligere kalibrering på martj42-datasettet
        gm = model_mod.GoalModel(a=0.24, b=1.0, rho=-0.05)
    print(
        f"Målmodell: a={gm.a:.4f} b={gm.b:.4f} rho={gm.rho:.3f} "
        f"({len(state.samples)} observasjoner)"
    )
    return gm


def main() -> int:
    cup_text = load_text("cup.txt")
    finals_text = load_text("cup_finals.txt")
    if not cup_text or not finals_text:
        raise SystemExit("Kampoppsett mangler (kjør pipeline.fetch først)")
    tournament = parse_tournament(cup_text, finals_text, config.TOURNAMENT_YEAR)
    print(
        f"Kampoppsett: {len(tournament.groups)} grupper, "
        f"{len(tournament.matches)} kamper"
    )

    state = build_elo_state()

    # Oppdater Elo med VM-kamper som er spilt, men ennå ikke i resultatdatasettet
    folded = 0
    for m in tournament.matches:
        if m.played and not is_placeholder(m.home):
            home = config.results_name(m.home)
            away = config.results_name(m.away)
            if elo_mod.fold_in_match(
                state, m.date or "", home, away, m.home_goals, m.away_goals
            ):
                folded += 1
    if folded:
        print(f"La til {folded} spilte VM-kamper i Elo-grunnlaget")

    goal_model = fit_goal_model(state)

    all_teams = sorted({t for teams in tournament.groups.values() for t in teams})
    elo_table = {t: state.rating(config.results_name(t)) for t in all_teams}

    odds = markets.load_or_fetch_market_odds()
    if odds.get("available"):
        print(f"Markedsodds: {len(odds['events'])} kamper fra The Odds API")
    else:
        print(f"Markedsodds: ikke tilgjengelig ({odds.get('note', odds.get('error', ''))})")

    # Kampprediksjoner
    matches_out = []
    for m in sorted(
        tournament.matches, key=lambda x: (x.utc or "9", x.num or 0)
    ):
        entry = {
            "num": m.num,
            "round": m.round,
            "stage": STAGE_LABELS[m.round],
            "group": m.group,
            "date": m.date,
            "utc": m.utc,
            "venue": m.venue,
            "home": m.home,
            "away": m.away,
            "placeholder": is_placeholder(m.home) or is_placeholder(m.away),
            "status": "played" if m.played else "scheduled",
        }
        if m.played:
            entry["score"] = [m.home_goals, m.away_goals]
            if m.pens:
                entry["pens"] = list(m.pens)
            entry["aet"] = m.aet

        if not entry["placeholder"]:
            adv_h, adv_a = simulate._advantages(m.home, m.away, m.venue)
            pred = model_mod.predict_match(
                goal_model,
                elo_table[m.home] + adv_h,
                elo_table[m.away] + adv_a,
            )
            market = markets.lookup(odds, m.home, m.away)
            blended = markets.blend(
                (pred.p_home, pred.p_draw, pred.p_away), market
            )
            entry["pred"] = {
                "p_home": round(pred.p_home, 4),
                "p_draw": round(pred.p_draw, 4),
                "p_away": round(pred.p_away, 4),
                "xg_home": round(pred.xg_home, 2),
                "xg_away": round(pred.xg_away, 2),
                "top_scores": [[s, round(p, 4)] for s, p in pred.top_scores],
                "elo_home": round(elo_table[m.home]),
                "elo_away": round(elo_table[m.away]),
                "market": (
                    {
                        "p_home": round(market["p_home"], 4),
                        "p_draw": round(market["p_draw"], 4),
                        "p_away": round(market["p_away"], 4),
                        "bookmakers": market["bookmakers"],
                    }
                    if market
                    else None
                ),
                "blended": {
                    "p_home": round(blended["p_home"], 4),
                    "p_draw": round(blended["p_draw"], 4),
                    "p_away": round(blended["p_away"], 4),
                    "source": blended["source"],
                },
            }
        matches_out.append(entry)

    # Turneringssimulering
    ctx = simulate.SimContext(model=goal_model, elo=elo_table)
    print(f"Simulerer turneringen {config.N_SIMULATIONS} ganger ...")
    stats = simulate.simulate_tournament(tournament, ctx)
    team_table = simulate.stats_to_team_table(stats, tournament)
    for team in all_teams:
        team_table[team]["elo"] = round(elo_table[team])

    for entry in matches_out:
        if entry["placeholder"] and entry["num"]:
            entry["likely_participants"] = simulate.likely_participants(
                stats, entry["num"]
            )

    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tournament": "FIFA Fotball-VM 2026",
        "n_simulations": stats.n,
        "model": {
            "a": round(goal_model.a, 4),
            "b": round(goal_model.b, 4),
            "rho": round(goal_model.rho, 3),
            "calibration_matches": len(state.match_samples),
            "market_weight": config.MARKET_WEIGHT,
            "market_available": bool(odds.get("available")),
        },
        "sources": {
            "fixtures": "openfootball/worldcup (public domain)",
            "results": "martj42/international_results (CC0)",
            "odds": "The Odds API" if odds.get("available") else None,
        },
        "groups": tournament.groups,
        "teams": {
            t: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}
            for t, d in team_table.items()
        },
        "matches": matches_out,
    }

    config.SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_file = config.SITE_DATA_DIR / "predictions.json"
    out_file.write_text(
        json.dumps(output, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Skrev {out_file} ({out_file.stat().st_size // 1024} kB)")

    # Oppdater Elo-seed slik at pipelinen virker uten resultatdata
    seed = {
        "generated_at": output["generated_at"],
        "ratings": {config.results_name(t): elo_table[t] for t in all_teams},
    }
    (config.SEED_DIR / "elo_seed.json").write_text(
        json.dumps(seed, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
