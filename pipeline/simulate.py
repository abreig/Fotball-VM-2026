"""Monte Carlo-simulering av hele VM 2026.

Simulerer gruppespill (spilte kamper bruker faktisk resultat), rangerer
gruppene og de åtte beste treerne, fyller sluttspilltreet i henhold til
plassholderne i kampoppsettet (1A, 2B, 3A/B/C/D/F, W73 osv.) og spiller
sluttspillet til ferdig finale. Resultatet er sannsynligheter per lag for
å nå hver runde, pluss deltakerfordeling per sluttspillkamp.
"""

from __future__ import annotations

import math
import random
import re
from collections import defaultdict
from dataclasses import dataclass, field

from . import config
from .elo import expected_score
from .model import GoalModel
from .openfootball import Match, Tournament, is_placeholder

ROUND_ORDER = ["group", "r32", "r16", "qf", "sf", "third", "final"]
THIRD_SLOT_RE = re.compile(r"^3([A-L](?:/[A-L])*)$")
RANK_SLOT_RE = re.compile(r"^([12])([A-L])$")
WINNER_RE = re.compile(r"^W(\d+)$")
LOSER_RE = re.compile(r"^L(\d+)$")


def _sample_poisson(lam: float, rng: random.Random) -> int:
    """Knuth-sampling, raskt nok for lambda < 6."""
    threshold = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= threshold:
            return k
        k += 1


@dataclass
class SimContext:
    model: GoalModel
    elo: dict[str, float]

    def lambdas(self, home: str, away: str, venue: str | None) -> tuple[float, float]:
        adv_home, adv_away = _advantages(home, away, venue)
        diff = self.elo[home] + adv_home - (self.elo[away] + adv_away)
        return self.model.expected_goals(diff), self.model.expected_goals(-diff)

    def ko_win_prob(self, home: str, away: str, venue: str | None) -> float:
        """P(hjemmelaget går videre) inkl. ekstraomganger/straffer."""
        adv_home, adv_away = _advantages(home, away, venue)
        diff = self.elo[home] + adv_home - (self.elo[away] + adv_away)
        return expected_score(diff)


def _advantages(home: str, away: str, venue: str | None) -> tuple[float, float]:
    country = config.VENUE_COUNTRY.get(venue or "", config.DEFAULT_VENUE_COUNTRY)
    adv = config.ELO_HOME_ADVANTAGE
    return (adv if home == country else 0.0, adv if away == country else 0.0)


@dataclass
class SimStats:
    n: int = 0
    reach: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )  # runde -> lag -> antall
    group_winner: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    champion: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    ko_participants: dict[int, dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )  # kampnummer -> lag -> antall


def _rank_group(table: dict[str, list[int]], rng: random.Random) -> list[str]:
    """Sorter på poeng, målforskjell, mål scoret, deretter tilfeldig."""
    return sorted(
        table,
        key=lambda t: (table[t][0], table[t][1], table[t][2], rng.random()),
        reverse=True,
    )


def _assign_thirds(
    qualified: list[str],
    slots: list[tuple[int, frozenset[str]]],
    rng: random.Random,
) -> dict[int, str] | None:
    """Backtracking-matching av kvalifiserte tredjeplassgrupper til sluttspillslots."""
    order = sorted(slots, key=lambda s: len(s[1] & set(qualified)))
    assignment: dict[int, str] = {}
    used: set[str] = set()

    def bt(i: int) -> bool:
        if i == len(order):
            return True
        num, allowed = order[i]
        candidates = [g for g in qualified if g not in used and g in allowed]
        rng.shuffle(candidates)
        for g in candidates:
            assignment[num] = g
            used.add(g)
            if bt(i + 1):
                return True
            used.discard(g)
            del assignment[num]
        return False

    if bt(0):
        return assignment
    return None


def simulate_tournament(
    tournament: Tournament,
    ctx: SimContext,
    n_sims: int = config.N_SIMULATIONS,
    seed: int = config.SIM_SEED,
) -> SimStats:
    rng = random.Random(seed)
    stats = SimStats(n=n_sims)

    group_matches = [m for m in tournament.matches if m.round == "group"]
    ko_matches = sorted(
        (m for m in tournament.matches if m.round != "group" and m.num),
        key=lambda m: m.num,
    )
    third_slots = []
    for m in ko_matches:
        for team in (m.home, m.away):
            ts = THIRD_SLOT_RE.match(team)
            if ts:
                third_slots.append((m.num, frozenset(ts.group(1).split("/"))))

    # Forhåndsberegn lambda for uspilte gruppekamper
    group_lambdas = {}
    for m in group_matches:
        if not m.played:
            group_lambdas[id(m)] = ctx.lambdas(m.home, m.away, m.venue)

    for _ in range(n_sims):
        # 1) Gruppespill
        tables: dict[str, dict[str, list[int]]] = {
            g: {t: [0, 0, 0] for t in teams}  # poeng, målforskjell, mål
            for g, teams in tournament.groups.items()
        }
        for m in group_matches:
            if m.played:
                hg, ag = m.home_goals, m.away_goals
            else:
                lh, la = group_lambdas[id(m)]
                hg = _sample_poisson(lh, rng)
                ag = _sample_poisson(la, rng)
            th, ta = tables[m.group][m.home], tables[m.group][m.away]
            th[1] += hg - ag
            th[2] += hg
            ta[1] += ag - hg
            ta[2] += ag
            if hg > ag:
                th[0] += 3
            elif hg < ag:
                ta[0] += 3
            else:
                th[0] += 1
                ta[0] += 1

        ranked: dict[str, list[str]] = {}
        thirds: list[tuple[str, tuple]] = []
        for g, table in tables.items():
            order = _rank_group(table, rng)
            ranked[g] = order
            stats.group_winner[order[0]] += 1
            third = order[2]
            thirds.append((g, (*table[third],)))

        thirds.sort(key=lambda t: (t[1], rng.random()), reverse=True)
        qualified_third_groups = [g for g, _ in thirds[:8]]
        third_of = {g: ranked[g][2] for g in qualified_third_groups}

        assignment = _assign_thirds(qualified_third_groups, third_slots, rng)
        if assignment is None:
            # Fallback: tilfeldig tildeling uten gruppebegrensninger
            shuffled = qualified_third_groups[:]
            rng.shuffle(shuffled)
            assignment = {num: g for (num, _), g in zip(third_slots, shuffled)}

        # 2) Sluttspill
        winners: dict[int, str] = {}
        losers: dict[int, str] = {}

        def resolve(token: str, num: int) -> str:
            ts = THIRD_SLOT_RE.match(token)
            if ts:
                return third_of[assignment[num]]
            rs = RANK_SLOT_RE.match(token)
            if rs:
                return ranked[rs.group(2)][int(rs.group(1)) - 1]
            ws = WINNER_RE.match(token)
            if ws:
                return winners[int(ws.group(1))]
            ls = LOSER_RE.match(token)
            if ls:
                return losers[int(ls.group(1))]
            return token  # allerede et lagnavn (openfootball har fylt inn)

        for m in ko_matches:
            home = resolve(m.home, m.num)
            away = resolve(m.away, m.num)
            stats.ko_participants[m.num][home] += 1
            stats.ko_participants[m.num][away] += 1
            stats.reach[m.round][home] += 1
            stats.reach[m.round][away] += 1
            if m.played:
                win = m.winner
                winners[m.num] = win if win else home
                losers[m.num] = away if winners[m.num] == home else home
            else:
                p_home = ctx.ko_win_prob(home, away, m.venue)
                if rng.random() < p_home:
                    winners[m.num], losers[m.num] = home, away
                else:
                    winners[m.num], losers[m.num] = away, home
            if m.round == "final":
                stats.champion[winners[m.num]] += 1

    return stats


def stats_to_team_table(stats: SimStats, tournament: Tournament) -> dict[str, dict]:
    """Per lag: sannsynlighet for å nå hver runde og vinne tittelen."""
    teams = {}
    group_of = {
        team: g for g, members in tournament.groups.items() for team in members
    }
    n = max(stats.n, 1)
    for team, group in group_of.items():
        teams[team] = {
            "group": group,
            "p_group_winner": stats.group_winner.get(team, 0) / n,
            "p_r32": stats.reach["r32"].get(team, 0) / n,
            "p_r16": stats.reach["r16"].get(team, 0) / n,
            "p_qf": stats.reach["qf"].get(team, 0) / n,
            "p_sf": stats.reach["sf"].get(team, 0) / n,
            "p_final": stats.reach["final"].get(team, 0) / n,
            "p_champion": stats.champion.get(team, 0) / n,
        }
    return teams


def likely_participants(stats: SimStats, num: int, top: int = 3) -> list[dict]:
    """De mest sannsynlige deltakerne i en sluttspillkamp."""
    counts = stats.ko_participants.get(num, {})
    n = max(stats.n, 1)
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    return [{"team": t, "p": c / n} for t, c in ranked[: top * 2]]
