"""Parser for openfootball sitt Football.TXT-format (cup.txt / cup_finals.txt)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

DATE_RE = re.compile(
    r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Z][a-z]+)\.?\s+(\d{1,2})\s*$"
)
GROUP_DEF_RE = re.compile(r"^Group\s+([A-L])\s*\|\s*(.+)$")
SECTION_RE = re.compile(r"^[▪>]\s*(.+?)\s*$")
MATCH_LINE_RE = re.compile(
    r"^\s*(?:\((\d+)\)\s*)?(\d{1,2})[.:](\d{2})"
    r"(?:\s*UTC([+-]\d{1,2})(?::(\d{2}))?)?"
    r"\s+(.+?)\s+@\s+(.+?)\s*$"
)
# Kamper uten klokkeslett (fortsettelseslinjer i eldre filer)
BARE_MATCH_RE = re.compile(r"^\s+(.+?)\s+@\s+(.+?)\s*$")
VS_RE = re.compile(r"^(.+?)\s+v(?:s\.?)?\s+(.+)$")
SCORE_RE = re.compile(
    r"^(.+?)\s+(\d+)-(\d+)"
    r"(?P<aet>\s*a\.?e\.?t\.?)?"
    r"\s*(?:\(([^()]*)\))?"
    r"(?:\s*,?\s*(?P<ph>\d+)-(?P<pa>\d+)\s*pen\.?)?"
    r"\s+(.+)$"
)
PLACEHOLDER_RE = re.compile(r"^(?:[123][A-L](?:/[A-L])*|[WL]\d{1,3})$")

ROUND_KEYS = (
    ("round of 32", "r32"),
    ("round of 16", "r16"),
    ("quarter", "qf"),
    ("semi", "sf"),
    ("third place", "third"),
    ("final", "final"),
)


@dataclass
class Match:
    home: str
    away: str
    round: str  # group | r32 | r16 | qf | sf | third | final
    group: str | None = None
    num: int | None = None
    date: str | None = None  # ISO-dato (lokal)
    time: str | None = None  # lokal tid HH:MM
    utc: str | None = None  # ISO-tidspunkt i UTC, hvis kjent
    venue: str | None = None
    home_goals: int | None = None
    away_goals: int | None = None
    pens: tuple[int, int] | None = None
    aet: bool = False

    @property
    def played(self) -> bool:
        return self.home_goals is not None

    @property
    def winner(self) -> str | None:
        if not self.played:
            return None
        if self.pens:
            return self.home if self.pens[0] > self.pens[1] else self.away
        if self.home_goals > self.away_goals:
            return self.home
        if self.away_goals > self.home_goals:
            return self.away
        return None


@dataclass
class Tournament:
    groups: dict[str, list[str]] = field(default_factory=dict)
    matches: list[Match] = field(default_factory=list)


def is_placeholder(name: str) -> bool:
    """Plassholdere som '1A', '2B', '3A/B/C/D/F', 'W73', 'L101'."""
    return bool(PLACEHOLDER_RE.match(name))


def _parse_teams(middle: str) -> tuple[str, str, dict] | None:
    m = SCORE_RE.match(middle)
    if m and not is_placeholder(m.group(1).strip()):
        info = {
            "home_goals": int(m.group(2)),
            "away_goals": int(m.group(3)),
            "aet": bool(m.group("aet")),
            "pens": None,
        }
        if m.group("ph") is not None:
            info["pens"] = (int(m.group("ph")), int(m.group("pa")))
        return m.group(1).strip(), m.group(8).strip(), info
    m = VS_RE.match(middle)
    if m:
        return m.group(1).strip(), m.group(2).strip(), {}
    return None


def _round_key(header: str) -> str | None:
    low = header.lower()
    if "matchday" in low:
        return None
    for needle, key in ROUND_KEYS:
        if needle in low:
            return key
    return None


def parse_file(text: str, year: int, default_round: str = "group") -> Tournament:
    """Parse en Football.TXT-fil til grupper og kamper."""
    tournament = Tournament()
    current_group: str | None = None
    current_round = default_round
    current_date: str | None = None
    last_time: tuple[str, str | None] | None = None  # (HH:MM, utc-offset)

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("="):
            continue

        gd = GROUP_DEF_RE.match(stripped)
        if gd:
            teams = [t.strip() for t in re.split(r"\s{2,}|\t+", gd.group(2)) if t.strip()]
            tournament.groups[gd.group(1)] = teams
            continue

        sec = SECTION_RE.match(stripped)
        if sec:
            header = sec.group(1)
            gm = re.match(r"^Group\s+([A-L])\s*$", header)
            if gm:
                current_group = gm.group(1)
                current_round = "group"
                continue
            rk = _round_key(header)
            if rk:
                current_round = rk
                current_group = None
            continue

        dm = DATE_RE.match(stripped)
        if dm:
            mon = MONTHS.get(dm.group(1)[:3].lower())
            if mon:
                current_date = f"{year:04d}-{mon:02d}-{int(dm.group(2)):02d}"
            continue

        match = _try_parse_match(line, current_round, current_group, current_date, last_time)
        if match:
            m, last_time = match
            tournament.matches.append(m)

    return tournament


def _try_parse_match(line, rnd, group, date, last_time):
    mm = MATCH_LINE_RE.match(line)
    num = None
    if mm:
        num = int(mm.group(1)) if mm.group(1) else None
        hh, mins = int(mm.group(2)), int(mm.group(3))
        offset = None
        if mm.group(4) is not None:
            offset = (int(mm.group(4)), int(mm.group(5) or 0))
        middle, venue = mm.group(6), mm.group(7)
        time_str = f"{hh:02d}:{mins:02d}"
    else:
        # Linjer uten klokkeslett: bruk forrige kamps tidspunkt
        if line.lstrip().startswith("("):
            return None  # målscorer-linje
        bm = BARE_MATCH_RE.match(line)
        if not bm or last_time is None:
            return None
        middle, venue = bm.group(1), bm.group(2)
        time_str, offset = last_time

    teams = _parse_teams(middle)
    if not teams:
        return None
    home, away, score = teams

    utc_iso = None
    if date and offset is not None:
        hh, mins = (int(p) for p in time_str.split(":"))
        local = datetime.fromisoformat(date).replace(hour=hh, minute=mins)
        sign = 1 if offset[0] >= 0 else -1
        delta = timedelta(hours=offset[0], minutes=sign * offset[1])
        utc_iso = (
            (local - delta)
            .replace(tzinfo=timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )

    m = Match(
        home=home,
        away=away,
        round=rnd,
        group=group,
        num=num,
        date=date,
        time=time_str,
        utc=utc_iso,
        venue=venue,
        home_goals=score.get("home_goals"),
        away_goals=score.get("away_goals"),
        pens=score.get("pens"),
        aet=score.get("aet", False),
    )
    return m, (time_str, offset)


def parse_tournament(cup_text: str, finals_text: str, year: int) -> Tournament:
    """Slå sammen gruppespill (cup.txt) og sluttspill (cup_finals.txt)."""
    cup = parse_file(cup_text, year, default_round="group")
    finals = parse_file(finals_text, year, default_round="r32")
    cup.matches.extend(finals.matches)
    return cup
