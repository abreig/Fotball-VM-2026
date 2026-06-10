# Fotball-VM 2026 - prediksjoner

Daglig oppdaterte prediksjoner for alle 104 kampene i fotball-VM 2026, bygget
utelukkende på gratis og åpne datakilder. Pipelinen er ren Python uten
tredjepartsavhengigheter, kjører i GitHub Codespaces med build tasks, og
publiseres automatisk til GitHub Pages én gang om dagen.

## Hvordan det virker

```
Åpne datakilder            Modell                       Resultat
-----------------          --------------------------   --------------------
openfootball/worldcup  ->  Football.TXT-parser      \
(kampoppsett + resultater)                            \
                                                       -> prediksjoner per kamp
martj42/international_ ->  Elo-ratinger (eloratings- /   (H/U/B, forventede mål,
results (49 000 kamper)    metoden) + Poisson-regresjon  mest sannsynlig resultat)
                           med Dixon-Coles-justering  \
The Odds API (valgfritt) -> markedssannsynligheter     -> Monte Carlo-simulering
                            (de-vigget, blandes inn)      av hele turneringen
                                                          (gruppespill, tredje-
                                                          plasser, sluttspilltre)
```

1. **Kampoppsett og resultater**: [openfootball/worldcup](https://github.com/openfootball/worldcup)
   (public domain). Filene oppdateres med faktiske resultater underveis i VM,
   slik at simuleringene alltid bygger på spilte kamper.
2. **Historiske landskamper**: [martj42/international_results](https://github.com/martj42/international_results)
   (CC0). Brukes til å beregne Elo-ratinger for alle landslag (K-faktor etter
   kampens viktighet, målforskjellsmultiplikator, +100 Elo i hjemmebanefordel -
   vertsnasjonene får dette i sine egne kamper).
3. **Målmodell**: Poisson-regresjon `log(lambda) = a + b * elodiff/400` tilpasset
   med Newtons metode på alle landskamper siden 2015 (ca. 10 000 kamper /
   20 000 observasjoner), pluss Dixon-Coles-justering (rho estimert ved
   profilert sannsynlighetsmaksimering) som korrigerer for at uavgjort
   undervurderes av uavhengige Poisson-fordelinger.
4. **Markedsodds** (valgfritt): 1X2-odds fra [The Odds API](https://the-odds-api.com)
   de-vigges proporsjonalt, snittes over bookmakere og blandes med
   modellsannsynlighetene (65 % marked / 35 % modell). Uten API-nøkkel brukes
   ren modell.
5. **Turneringssimulering**: 10 000 Monte Carlo-simuleringer av hele
   turneringen gir sannsynligheter for gruppeseier, avansement til hver
   sluttspillrunde og VM-tittelen. Tredjeplasslagene tildeles sluttspillkamper
   med backtracking-matching mot plassholderne i kampoppsettet (f.eks.
   `1E v 3A/B/C/D/F`).

## Kom i gang i Codespaces

Åpne repoet i GitHub Codespaces. Devcontaineren installerer ingenting (ren
Python) og kjører pipelinen automatisk ved oppstart. Deretter:

- **Build task** (`Ctrl/Cmd+Shift+B`): "Bygg alt (hent data + prediker)"
- **Terminal > Run Task**: "Hent data", "Lag prediksjoner", "Kjør tester",
  "Start nettsiden (port 8000)"

Eller fra terminalen:

```bash
make data     # hent ferske data + bygg prediksjoner
make serve    # nettsiden på http://localhost:8000
make test     # 24 enhetstester
```

## Daglig oppdatering og GitHub Pages

`.github/workflows/daily.yml` kjører hver dag kl. 05:30 UTC (og ved push til
main eller manuelt via *Run workflow*):

1. Henter ferske data fra alle kilder
2. Bygger `site/data/predictions.json` og committer endringene
3. Publiserer `site/` til GitHub Pages

**Engangsoppsett**: I repoinnstillingene, velg *Settings > Pages > Source:
GitHub Actions*.

**Markedsodds (valgfritt)**: Registrer en gratis nøkkel på
[the-odds-api.com](https://the-odds-api.com) og legg den inn som secret
`THE_ODDS_API_KEY` (*Settings > Secrets and variables > Actions*). Pipelinen
finner selv riktig sport-nøkkel for VM og faller stille tilbake til ren modell
uten nøkkel.

## Prosjektstruktur

```
pipeline/            datapipeline (ren Python 3.11+, ingen avhengigheter)
  config.py          kilder, modellparametre, navnemapping
  fetch.py           henter data med cache- og seed-fallback
  openfootball.py    parser for Football.TXT-formatet
  elo.py             Elo-ratinger fra historiske resultater
  model.py           Poisson-regresjon + Dixon-Coles
  markets.py         markedsodds fra The Odds API (valgfritt)
  simulate.py        Monte Carlo-simulering av hele turneringen
  predict.py         hovedsteg, skriver site/data/predictions.json
site/                statisk nettside (GitHub Pages)
data/seed/           innsjekket fallback: kampoppsett + Elo-seed
data/cache/          nedlastede rådata (ikke i git)
tests/               enhetstester (unittest)
.github/workflows/   daglig cron + Pages-publisering
.devcontainer/       Codespaces-oppsett
.vscode/tasks.json   build tasks
```

## Forbehold

Prediksjonene er statistisk underholdning, ikke spilletips. Modellen kjenner
ikke til skader, form utover resultater, eller taktiske forhold. Gruppespillets
tiebreak-regler er forenklet (poeng, målforskjell, mål, deretter loddtrekning),
og tildelingen av tredjeplasslag følger kampoppsettets begrensninger, ikke
FIFAs fulle tildelingstabell.
