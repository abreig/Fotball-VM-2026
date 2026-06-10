"""Tester for turneringssimuleringen."""

import unittest
from pathlib import Path

from pipeline import config, model, simulate
from pipeline.openfootball import parse_tournament

SEED = Path(__file__).resolve().parent.parent / "data" / "seed"


class TestSimulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tournament = parse_tournament(
            (SEED / "cup.txt").read_text(encoding="utf-8"),
            (SEED / "cup_finals.txt").read_text(encoding="utf-8"),
            2026,
        )
        # Syntetiske ratinger: alfabetisk styrkeordning er irrelevant,
        # vi gir alle 1700 og to kjente lag tydelig styrkeforskjell.
        teams = {t for ts in cls.tournament.groups.values() for t in ts}
        cls.elo = {t: 1700.0 for t in teams}
        cls.elo["Spain"] = 2200.0
        cls.elo["Haiti"] = 1400.0
        gm = model.GoalModel(a=0.2, b=0.8, rho=-0.05)
        cls.ctx = simulate.SimContext(model=gm, elo=cls.elo)
        cls.stats = simulate.simulate_tournament(
            cls.tournament, cls.ctx, n_sims=500, seed=1
        )

    def test_probabilities_consistent(self):
        table = simulate.stats_to_team_table(self.stats, self.tournament)
        self.assertEqual(len(table), 48)
        for team, row in table.items():
            # Monotont fallende sjanser utover i turneringen
            self.assertGreaterEqual(row["p_r32"], row["p_r16"], team)
            self.assertGreaterEqual(row["p_r16"], row["p_qf"], team)
            self.assertGreaterEqual(row["p_qf"], row["p_sf"], team)
            self.assertGreaterEqual(row["p_sf"], row["p_final"], team)
            self.assertGreaterEqual(row["p_final"], row["p_champion"], team)

    def test_total_champions_is_one(self):
        self.assertEqual(sum(self.stats.champion.values()), self.stats.n)

    def test_r32_has_32_participants_per_sim(self):
        total = sum(self.stats.reach["r32"].values())
        self.assertEqual(total, 32 * self.stats.n)

    def test_stronger_team_does_better(self):
        table = simulate.stats_to_team_table(self.stats, self.tournament)
        self.assertGreater(
            table["Spain"]["p_champion"], table["Haiti"]["p_champion"]
        )
        self.assertGreater(table["Spain"]["p_r16"], table["Haiti"]["p_r16"])

    def test_host_advantage_in_own_country(self):
        lam_home, lam_away = self.ctx.lambdas("Mexico", "South Africa", "Mexico City")
        lam_h2, lam_a2 = self.ctx.lambdas("Mexico", "South Africa", "Atlanta")
        self.assertGreater(lam_home, lam_h2)  # Mexico sterkere i Mexico City

    def test_third_place_assignment_respects_constraints(self):
        slots = [
            (74, frozenset("ABCDF")),
            (77, frozenset("CDFGH")),
            (79, frozenset("CEFHI")),
            (80, frozenset("EHIJK")),
            (81, frozenset("BEFIJ")),
            (82, frozenset("AEHIJ")),
            (85, frozenset("EFGIJ")),
            (87, frozenset("DEIJL")),
        ]
        import random

        qualified = ["A", "B", "C", "E", "F", "I", "J", "L"]
        assignment = simulate._assign_thirds(qualified, slots, random.Random(7))
        self.assertIsNotNone(assignment)
        self.assertEqual(sorted(assignment.values()), sorted(qualified))
        allowed = dict(slots)
        for num, group in assignment.items():
            self.assertIn(group, allowed[num])


if __name__ == "__main__":
    unittest.main()
