"""Felles konfigurasjon for VM 2026-prediksjonspipelinen."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SEED_DIR = DATA_DIR / "seed"
CACHE_DIR = DATA_DIR / "cache"
SITE_DATA_DIR = ROOT / "site" / "data"

TOURNAMENT_YEAR = 2026

# Åpne datakilder
OPENFOOTBALL_BASE = (
    "https://raw.githubusercontent.com/openfootball/worldcup/master/2026--usa"
)
CUP_URL = f"{OPENFOOTBALL_BASE}/cup.txt"
CUP_FINALS_URL = f"{OPENFOOTBALL_BASE}/cup_finals.txt"
RESULTS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
)

# Markedsodds (valgfritt, gratis nøkkel fra https://the-odds-api.com)
ODDS_API_KEY = os.environ.get("THE_ODDS_API_KEY", "").strip()
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Modellparametre
ELO_START = 1500.0
ELO_HOME_ADVANTAGE = 100.0  # Elo-poeng for hjemmebane (eloratings.net-konvensjon)
CALIBRATION_FROM = "2015-01-01"  # kamper brukt til å kalibrere målmodellen
MIN_MATCHES_FOR_CALIBRATION = 30
MAX_GOALS = 10  # størrelse på scoringsmatrisen
MARKET_WEIGHT = 0.65  # vekt på markedsodds når de finnes
N_SIMULATIONS = int(os.environ.get("N_SIMULATIONS", "10000"))
SIM_SEED = 2026

# Vertsland: lag som spiller i eget land får hjemmebanefordel
VENUE_COUNTRY = {
    "Mexico City": "Mexico",
    "Guadalajara (Zapopan)": "Mexico",
    "Monterrey (Guadalupe)": "Mexico",
    "Toronto": "Canada",
    "Vancouver": "Canada",
}
DEFAULT_VENUE_COUNTRY = "USA"

# openfootball-navn -> martj42-navn (resultatdatasettet)
RESULTS_NAME_ALIASES = {
    "USA": "United States",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
}

# Vanlige varianter fra odds-leverandører -> openfootball-navn
ODDS_NAME_ALIASES = {
    "United States": "USA",
    "United States of America": "USA",
    "Bosnia and Herzegovina": "Bosnia & Herzegovina",
    "Korea Republic": "South Korea",
    "IR Iran": "Iran",
    "Cabo Verde": "Cape Verde",
    "Congo DR": "DR Congo",
    "Cote d'Ivoire": "Ivory Coast",
    "Côte d'Ivoire": "Ivory Coast",
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey",
    "Turkiye": "Turkey",
    "Curacao": "Curaçao",
}

# K-faktor per turneringstype (eloratings.net-inspirert)
ELO_K_WORLD_CUP = 60
ELO_K_CONTINENTAL = 50
ELO_K_QUALIFIER = 40
ELO_K_NATIONS_LEAGUE = 40
ELO_K_OTHER = 30
ELO_K_FRIENDLY = 20

CONTINENTAL_TOURNAMENTS = (
    "UEFA Euro",
    "Copa América",
    "Copa America",
    "African Cup of Nations",
    "Africa Cup of Nations",
    "AFC Asian Cup",
    "Gold Cup",
    "CONCACAF Championship",
    "Oceania Nations Cup",
    "OFC Nations Cup",
    "Confederations Cup",
)


def results_name(openfootball_name: str) -> str:
    """Oversett et openfootball-lagnavn til navnet i resultatdatasettet."""
    return RESULTS_NAME_ALIASES.get(openfootball_name, openfootball_name)


def canonical_name(name: str) -> str:
    """Normaliser et eksternt lagnavn (f.eks. fra oddsleverandør) til openfootball-navn."""
    return ODDS_NAME_ALIASES.get(name.strip(), name.strip())
