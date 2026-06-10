"""Tester for Football.TXT-parseren mot seed-dataene."""

import unittest
from pathlib import Path

from pipeline.openfootball import is_placeholder, parse_file, parse_tournament

SEED = Path(__file__).resolve().parent.parent / "data" / "seed"


class TestParser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tournament = parse_tournament(
            (SEED / "cup.txt").read_text(encoding="utf-8"),
            (SEED / "cup_finals.txt").read_text(encoding="utf-8"),
            2026,
        )

    def test_twelve_groups_with_four_teams(self):
        self.assertEqual(len(self.tournament.groups), 12)
        for teams in self.tournament.groups.values():
            self.assertEqual(len(teams), 4)

    def test_104_matches(self):
        self.assertEqual(len(self.tournament.matches), 104)
        rounds = {}
        for m in self.tournament.matches:
            rounds[m.round] = rounds.get(m.round, 0) + 1
        self.assertEqual(rounds["group"], 72)
        self.assertEqual(rounds["r32"], 16)
        self.assertEqual(rounds["r16"], 8)
        self.assertEqual(rounds["qf"], 4)
        self.assertEqual(rounds["sf"], 2)
        self.assertEqual(rounds["third"], 1)
        self.assertEqual(rounds["final"], 1)

    def test_group_matches_have_real_teams_and_utc(self):
        for m in self.tournament.matches:
            if m.round == "group":
                self.assertFalse(is_placeholder(m.home), m)
                self.assertFalse(is_placeholder(m.away), m)
                self.assertIsNotNone(m.utc, m)
                self.assertIsNotNone(m.group, m)

    def test_knockout_numbering(self):
        nums = sorted(m.num for m in self.tournament.matches if m.num)
        self.assertEqual(nums, list(range(73, 105)))

    def test_opening_match(self):
        opening = self.tournament.matches[0]
        self.assertEqual(opening.home, "Mexico")
        self.assertEqual(opening.away, "South Africa")
        self.assertEqual(opening.utc, "2026-06-11T19:00:00Z")

    def test_played_match_with_score(self):
        text = """= World Cup Test
▪ Group A
Sun Nov 20
  19:00      Qatar   0-2 (0-2)   Ecuador    @ Al Bayt Stadium, Al Khor
             (Enner Valencia 16' (pen.), 31')
"""
        t = parse_file(text, 2022)
        self.assertEqual(len(t.matches), 1)
        m = t.matches[0]
        self.assertTrue(m.played)
        self.assertEqual((m.home_goals, m.away_goals), (0, 2))
        self.assertEqual(m.winner, "Ecuador")

    def test_penalties(self):
        text = """= Test
▪ Final
Sun Dec 18
   18:00     Argentina  3-3 a.e.t. (3-3, 2-2, 2-0), 4-2 pen.  France   @ Lusail
"""
        t = parse_file(text, 2022, default_round="final")
        m = t.matches[0]
        self.assertTrue(m.aet)
        self.assertEqual(m.pens, (4, 2))
        self.assertEqual(m.winner, "Argentina")

    def test_placeholders(self):
        self.assertTrue(is_placeholder("1A"))
        self.assertTrue(is_placeholder("2L"))
        self.assertTrue(is_placeholder("3A/B/C/D/F"))
        self.assertTrue(is_placeholder("W104"))
        self.assertTrue(is_placeholder("L101"))
        self.assertFalse(is_placeholder("Norway"))
        self.assertFalse(is_placeholder("South Korea"))


if __name__ == "__main__":
    unittest.main()
