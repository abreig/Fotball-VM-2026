"""Henter åpne data og mellomlagrer dem lokalt.

Kjøres én gang om dagen (GitHub Actions) eller manuelt. Alle kilder har
fallback: først ferske data fra nettet, deretter lokal cache, til slutt
medfølgende seed-filer i data/seed/.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import config

USER_AGENT = "Fotball-VM-2026-predictor (+https://github.com/abreig/fotball-vm-2026)"


def http_get(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def fetch_to_cache(url: str, filename: str) -> tuple[Path, bool]:
    """Hent en URL til cache. Returnerer (sti, ble_oppdatert)."""
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = config.CACHE_DIR / filename
    try:
        text = http_get(url)
        target.write_text(text, encoding="utf-8")
        print(f"  ok      {url} -> {target} ({len(text)} tegn)")
        return target, True
    except Exception as exc:  # noqa: BLE001 - alle nettfeil skal gi fallback
        print(f"  FEIL    {url}: {exc}", file=sys.stderr)
        return target, False


def load_text(filename: str, seed_name: str | None = None) -> str | None:
    """Les fra cache, ellers fra seed-katalogen."""
    cached = config.CACHE_DIR / filename
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    seed = config.SEED_DIR / (seed_name or filename)
    if seed.exists():
        return seed.read_text(encoding="utf-8")
    return None


def refresh_seeds() -> None:
    """Oppdater seed-kopiene av kampoppsettet når ferske data finnes.

    Seed-filene sjekkes inn i git slik at pipelinen virker uten nett.
    """
    for filename in ("cup.txt", "cup_finals.txt"):
        cached = config.CACHE_DIR / filename
        if cached.exists():
            config.SEED_DIR.mkdir(parents=True, exist_ok=True)
            (config.SEED_DIR / filename).write_text(
                cached.read_text(encoding="utf-8"), encoding="utf-8"
            )


def main() -> int:
    print("Henter åpne datakilder ...")
    status = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {},
    }
    jobs = [
        (config.CUP_URL, "cup.txt", "openfootball gruppespill"),
        (config.CUP_FINALS_URL, "cup_finals.txt", "openfootball sluttspill"),
        (config.RESULTS_URL, "results.csv", "martj42 internasjonale resultater"),
    ]
    any_fresh = False
    for url, filename, label in jobs:
        _, fresh = fetch_to_cache(url, filename)
        has_fallback = (config.CACHE_DIR / filename).exists() or (
            config.SEED_DIR / filename
        ).exists()
        status["sources"][filename] = {
            "label": label,
            "url": url,
            "fresh": fresh,
            "available": fresh or has_fallback,
        }
        any_fresh = any_fresh or fresh

    refresh_seeds()

    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (config.CACHE_DIR / "fetch_status.json").write_text(
        json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if not any_fresh:
        print("Advarsel: ingen kilder kunne hentes, bruker cache/seed.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
