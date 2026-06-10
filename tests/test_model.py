"""Tester for Elo-beregning og målmodell."""

import math
import random
import unittest

from pipeline import elo, model


class TestElo(unittest.TestCase):
    def test_expected_score_symmetry(self):
        self.assertAlmostEqual(elo.expected_score(0), 0.5)
        self.assertAlmostEqual(
            elo.expected_score(200) + elo.expected_score(-200), 1.0
        )

    def test_update_moves_ratings(self):
        state = elo.EloResult()
        elo.update_pair(state, "A", "B", 3, 0, k=40, neutral=True)
        self.assertGreater(state.rating("A"), 1500)
        self.assertLess(state.rating("B"), 1500)
        # Nullsum
        self.assertAlmostEqual(state.rating("A") + state.rating("B"), 3000)

    def test_goal_multiplier(self):
        self.assertEqual(elo.goal_multiplier(1), 1.0)
        self.assertEqual(elo.goal_multiplier(2), 1.5)
        self.assertEqual(elo.goal_multiplier(3), 1.75)
        self.assertGreater(elo.goal_multiplier(5), elo.goal_multiplier(4))

    def test_k_factor(self):
        self.assertEqual(elo.k_factor("FIFA World Cup"), 60)
        self.assertEqual(elo.k_factor("FIFA World Cup qualification"), 40)
        self.assertEqual(elo.k_factor("Friendly"), 20)
        self.assertEqual(elo.k_factor("UEFA Euro"), 50)

    def test_csv_parsing_and_dedup(self):
        csv_text = (
            "date,home_team,away_team,home_score,away_score,tournament,city,country,neutral\n"
            "2020-01-01,A,B,2,0,Friendly,X,Y,FALSE\n"
            "2020-02-01,B,A,NA,NA,Friendly,X,Y,FALSE\n"
        )
        state = elo.compute_from_results_csv(csv_text)
        self.assertGreater(state.rating("A"), state.rating("B"))
        # Samme kamp skal ikke kunne legges til to ganger
        self.assertFalse(elo.fold_in_match(state, "2020-01-01", "A", "B", 2, 0))
        self.assertTrue(elo.fold_in_match(state, "2026-06-11", "A", "B", 1, 0))


class TestGoalModel(unittest.TestCase):
    def test_poisson_fit_recovers_parameters(self):
        rng = random.Random(42)
        a_true, b_true = 0.3, 0.8
        samples = []
        for _ in range(20000):
            x = rng.uniform(-1.5, 1.5)
            lam = math.exp(a_true + b_true * x)
            # Knuth-sampling
            threshold, k, p = math.exp(-lam), 0, 1.0
            while True:
                p *= rng.random()
                if p <= threshold:
                    break
                k += 1
            samples.append((x, k))
        a, b = model.fit_poisson(samples)
        self.assertAlmostEqual(a, a_true, delta=0.05)
        self.assertAlmostEqual(b, b_true, delta=0.05)

    def test_score_matrix_sums_to_one(self):
        gm = model.GoalModel(a=0.2, b=0.8, rho=-0.05)
        matrix = model.score_matrix(gm, 1.5, 1.1)
        total = sum(sum(row) for row in matrix)
        self.assertAlmostEqual(total, 1.0, places=9)

    def test_prediction_favours_stronger_team(self):
        gm = model.GoalModel(a=0.2, b=0.8, rho=-0.05)
        pred = model.predict_match(gm, 2000, 1700)
        self.assertGreater(pred.p_home, 0.5)
        self.assertGreater(pred.p_home, pred.p_away)
        self.assertAlmostEqual(pred.p_home + pred.p_draw + pred.p_away, 1.0, places=9)

    def test_home_advantage_helps(self):
        gm = model.GoalModel(a=0.2, b=0.8, rho=-0.05)
        neutral = model.predict_match(gm, 1800, 1800)
        at_home = model.predict_match(gm, 1800, 1800, home_advantage=100)
        self.assertGreater(at_home.p_home, neutral.p_home)

    def test_dc_tau_inflates_draws_for_negative_rho(self):
        self.assertGreater(model.dc_tau(0, 0, 1.2, 1.0, -0.1), 1.0)
        self.assertGreater(model.dc_tau(1, 1, 1.2, 1.0, -0.1), 1.0)
        self.assertLess(model.dc_tau(0, 1, 1.2, 1.0, -0.1), 1.0)


if __name__ == "__main__":
    unittest.main()
