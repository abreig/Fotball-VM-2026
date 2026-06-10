"""Målmodell: Poisson-regresjon på Elo-differanse, med Dixon-Coles-justering.

For hvert lag i en kamp antas antall mål ~ Poisson(lambda), der
log(lambda) = a + b * (elo_lag_justert - elo_motstander_justert) / 400.
Parametrene (a, b) tilpasses historiske landskamper med Newtons metode,
og Dixon-Coles-parameteren rho estimeres ved profilert sannsynlighetsmaksimering.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import config


@dataclass
class GoalModel:
    a: float  # grunnivå: log forventede mål mot jevn motstander
    b: float  # følsomhet for Elo-differanse
    rho: float  # Dixon-Coles-korrelasjon for lave resultater

    def expected_goals(self, elo_diff: float) -> float:
        """Forventede mål for et lag, gitt justert Elo-differanse i lagets favør."""
        lam = math.exp(self.a + self.b * elo_diff / 400.0)
        return min(lam, 6.0)


def fit_poisson(samples: list[tuple[float, int]], iterations: int = 50) -> tuple[float, float]:
    """Tilpass log(lambda) = a + b*x med Newton-Raphson på Poisson-loglikelihood."""
    if not samples:
        return math.log(1.3), 1.0
    a, b = math.log(1.3), 1.0
    for _ in range(iterations):
        g_a = g_b = 0.0
        h_aa = h_ab = h_bb = 0.0
        for x, y in samples:
            lam = math.exp(min(a + b * x, 4.0))
            r = y - lam
            g_a += r
            g_b += x * r
            h_aa -= lam
            h_ab -= x * lam
            h_bb -= x * x * lam
        det = h_aa * h_bb - h_ab * h_ab
        if abs(det) < 1e-12:
            break
        da = (g_a * h_bb - g_b * h_ab) / det
        db = (g_b * h_aa - g_a * h_ab) / det
        a -= da
        b -= db
        if abs(da) < 1e-10 and abs(db) < 1e-10:
            break
    return a, b


def dc_tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    """Dixon-Coles-justeringsfaktor for resultater med 0 eller 1 mål."""
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    if x == 0 and y == 1:
        return 1.0 + lam * rho
    if x == 1 and y == 0:
        return 1.0 + mu * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def fit_rho(
    match_samples: list[tuple[int, int, float]], a: float, b: float
) -> float:
    """Finn rho som maksimerer Dixon-Coles-bidraget til loglikelihood (gittersøk)."""
    if not match_samples:
        return -0.05
    best_rho, best_ll = 0.0, -math.inf
    for step in range(-30, 11):
        rho = step / 100.0
        ll = 0.0
        valid = True
        for hg, ag, dh in match_samples:
            lam = math.exp(min(a + b * dh, 4.0))
            mu = math.exp(min(a - b * dh, 4.0))
            tau = dc_tau(hg, ag, lam, mu, rho)
            if tau <= 0:
                valid = False
                break
            if hg <= 1 and ag <= 1:
                ll += math.log(tau)
        if valid and ll > best_ll:
            best_ll, best_rho = ll, rho
    return best_rho


def fit_model(
    samples: list[tuple[float, int]],
    match_samples: list[tuple[int, int, float]],
) -> GoalModel:
    a, b = fit_poisson(samples)
    rho = fit_rho(match_samples, a, b)
    return GoalModel(a=a, b=b, rho=rho)


def _poisson_pmf(lam: float, kmax: int) -> list[float]:
    pmf = [math.exp(-lam)]
    for k in range(1, kmax + 1):
        pmf.append(pmf[-1] * lam / k)
    return pmf


def score_matrix(model: GoalModel, lam_home: float, lam_away: float) -> list[list[float]]:
    """Sannsynlighetsmatrise P(hjemmemål=i, bortemål=j) med DC-justering."""
    kmax = config.MAX_GOALS
    ph = _poisson_pmf(lam_home, kmax)
    pa = _poisson_pmf(lam_away, kmax)
    matrix = [[ph[i] * pa[j] for j in range(kmax + 1)] for i in range(kmax + 1)]
    for i in (0, 1):
        for j in (0, 1):
            matrix[i][j] *= dc_tau(i, j, lam_home, lam_away, model.rho)
    total = sum(sum(row) for row in matrix)
    return [[v / total for v in row] for row in matrix]


@dataclass
class MatchPrediction:
    p_home: float
    p_draw: float
    p_away: float
    xg_home: float
    xg_away: float
    top_scores: list[tuple[str, float]]


def predict_match(
    model: GoalModel,
    elo_home: float,
    elo_away: float,
    home_advantage: float = 0.0,
) -> MatchPrediction:
    """Prediker en enkeltkamp. home_advantage er Elo-bonus til hjemmelaget."""
    diff = elo_home + home_advantage - elo_away
    lam_h = model.expected_goals(diff)
    lam_a = model.expected_goals(-diff)
    matrix = score_matrix(model, lam_h, lam_a)
    p_home = sum(matrix[i][j] for i in range(len(matrix)) for j in range(len(matrix)) if i > j)
    p_draw = sum(matrix[i][i] for i in range(len(matrix)))
    p_away = 1.0 - p_home - p_draw
    scores = [
        (f"{i}-{j}", matrix[i][j])
        for i in range(len(matrix))
        for j in range(len(matrix))
    ]
    scores.sort(key=lambda s: -s[1])
    return MatchPrediction(
        p_home=p_home,
        p_draw=p_draw,
        p_away=p_away,
        xg_home=lam_h,
        xg_away=lam_a,
        top_scores=scores[:5],
    )
