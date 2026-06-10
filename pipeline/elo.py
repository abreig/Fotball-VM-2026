"""Elo-ratinger for landslag, beregnet fra historiske resultater.

Metoden følger eloratings.net-konvensjonene: K-faktor etter kampens viktighet,
multiplikator for målforskjell og +100 Elo-poeng i hjemmebanefordel.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from . import config


@dataclass
class EloResult:
    ratings: dict[str, float] = field(default_factory=dict)
    match_counts: dict[str, int] = field(default_factory=dict)
    # Kalibreringsutvalg: (elo_diff_just_for_side, mål) per lag per kamp
    samples: list[tuple[float, int]] = field(default_factory=list)
    # Per kamp: (hjemmemål, bortemål, diff_hjemme) til Dixon-Coles-estimering
    match_samples: list[tuple[int, int, float]] = field(default_factory=list)
    seen_keys: set[str] = field(default_factory=set)

    def rating(self, team: str) -> float:
        return self.ratings.get(team, config.ELO_START)


def k_factor(tournament: str) -> float:
    t = tournament.lower()
    if "friendly" in t:
        return config.ELO_K_FRIENDLY
    if "qualification" in t or "qualifier" in t:
        return config.ELO_K_QUALIFIER
    if "fifa world cup" in t:
        return config.ELO_K_WORLD_CUP
    if "nations league" in t:
        return config.ELO_K_NATIONS_LEAGUE
    if any(name.lower() in t for name in (s.lower() for s in config.CONTINENTAL_TOURNAMENTS)):
        return config.ELO_K_CONTINENTAL
    return config.ELO_K_OTHER


def goal_multiplier(diff: int) -> float:
    if diff <= 1:
        return 1.0
    if diff == 2:
        return 1.5
    return 1.75 + (diff - 3) / 8.0


def expected_score(elo_diff: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-elo_diff / 400.0))


def match_key(date: str, home: str, away: str) -> str:
    return f"{date}|{home}|{away}"


def update_pair(
    state: EloResult,
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
    k: float,
    neutral: bool,
) -> None:
    """Oppdater ratingene for én spilt kamp."""
    rh = state.rating(home)
    ra = state.rating(away)
    home_adv = 0.0 if neutral else config.ELO_HOME_ADVANTAGE
    diff = rh + home_adv - ra
    exp_home = expected_score(diff)
    if home_goals > away_goals:
        score = 1.0
    elif home_goals == away_goals:
        score = 0.5
    else:
        score = 0.0
    change = k * goal_multiplier(abs(home_goals - away_goals)) * (score - exp_home)
    state.ratings[home] = rh + change
    state.ratings[away] = ra - change
    state.match_counts[home] = state.match_counts.get(home, 0) + 1
    state.match_counts[away] = state.match_counts.get(away, 0) + 1


def compute_from_results_csv(csv_text: str) -> EloResult:
    """Spill gjennom hele resultathistorikken og bygg ratinger + kalibreringsdata."""
    state = EloResult()
    reader = csv.DictReader(io.StringIO(csv_text))
    min_n = config.MIN_MATCHES_FOR_CALIBRATION
    for row in reader:
        hg, ag = row["home_score"], row["away_score"]
        if not hg or not ag or hg == "NA" or ag == "NA":
            continue
        home, away = row["home_team"], row["away_team"]
        try:
            hg, ag = int(float(hg)), int(float(ag))
        except ValueError:
            continue
        neutral = row.get("neutral", "FALSE").upper() == "TRUE"
        date = row["date"]

        if (
            date >= config.CALIBRATION_FROM
            and state.match_counts.get(home, 0) >= min_n
            and state.match_counts.get(away, 0) >= min_n
        ):
            rh, ra = state.rating(home), state.rating(away)
            adv = 0.0 if neutral else config.ELO_HOME_ADVANTAGE
            dh = (rh + adv - ra) / 400.0
            state.samples.append((dh, hg))
            state.samples.append((-dh, ag))
            state.match_samples.append((hg, ag, dh))

        update_pair(state, home, away, hg, ag, k_factor(row["tournament"]), neutral)
        state.seen_keys.add(match_key(date, home, away))
    return state


def fold_in_match(
    state: EloResult,
    date: str,
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
    neutral: bool = True,
    k: float = config.ELO_K_WORLD_CUP,
) -> bool:
    """Legg til en spilt kamp (f.eks. fra openfootball) som ikke finnes i CSV-en.

    Returnerer True hvis kampen ble lagt til, False hvis den allerede var kjent.
    """
    key = match_key(date, home, away)
    if key in state.seen_keys:
        return False
    update_pair(state, home, away, home_goals, away_goals, k, neutral)
    state.seen_keys.add(key)
    return True
