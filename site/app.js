/* Frontend for VM 2026-prediksjoner. Leser data/predictions.json (statisk). */
"use strict";

const NB_DATE = new Intl.DateTimeFormat("nb-NO", {
  weekday: "long", day: "numeric", month: "long",
  timeZone: "Europe/Oslo",
});
const NB_TIME = new Intl.DateTimeFormat("nb-NO", {
  hour: "2-digit", minute: "2-digit", timeZone: "Europe/Oslo",
});

const TEAM_NO = {
  "Mexico": "Mexico", "South Africa": "Sør-Afrika", "South Korea": "Sør-Korea",
  "Czech Republic": "Tsjekkia", "Canada": "Canada",
  "Bosnia & Herzegovina": "Bosnia-Hercegovina", "Qatar": "Qatar",
  "Switzerland": "Sveits", "Brazil": "Brasil", "Morocco": "Marokko",
  "Haiti": "Haiti", "Scotland": "Skottland", "USA": "USA",
  "Paraguay": "Paraguay", "Australia": "Australia", "Turkey": "Tyrkia",
  "Germany": "Tyskland", "Curaçao": "Curaçao", "Ivory Coast": "Elfenbenskysten",
  "Ecuador": "Ecuador", "Netherlands": "Nederland", "Japan": "Japan",
  "Sweden": "Sverige", "Tunisia": "Tunisia", "Belgium": "Belgia",
  "Egypt": "Egypt", "Iran": "Iran", "New Zealand": "New Zealand",
  "Spain": "Spania", "Cape Verde": "Kapp Verde", "Saudi Arabia": "Saudi-Arabia",
  "Uruguay": "Uruguay", "France": "Frankrike", "Senegal": "Senegal",
  "Iraq": "Irak", "Norway": "Norge", "Argentina": "Argentina",
  "Algeria": "Algerie", "Austria": "Østerrike", "Jordan": "Jordan",
  "Portugal": "Portugal", "DR Congo": "DR Kongo", "Uzbekistan": "Usbekistan",
  "Colombia": "Colombia", "England": "England", "Croatia": "Kroatia",
  "Ghana": "Ghana", "Panama": "Panama",
};

const no = (team) => TEAM_NO[team] || team;
const pct = (p) => (p * 100).toFixed(0) + " %";

let DATA = null;
let currentFilter = "upcoming";

async function init() {
  try {
    const resp = await fetch("data/predictions.json", { cache: "no-store" });
    DATA = await resp.json();
  } catch (err) {
    document.querySelector("main").innerHTML =
      '<p class="error">Kunne ikke laste prediksjonene. Prøv igjen senere.</p>';
    return;
  }
  const generated = new Date(DATA.generated_at);
  document.getElementById("meta").textContent =
    `Sist oppdatert ${NB_DATE.format(generated)} kl. ${NB_TIME.format(generated)}` +
    ` | ${DATA.n_simulations.toLocaleString("nb-NO")} simuleringer` +
    (DATA.model.market_available ? " | med markedsodds" : " | uten markedsodds");

  document.getElementById("model-params").textContent =
    `Gjeldende parametre: a=${DATA.model.a}, b=${DATA.model.b}, ` +
    `rho=${DATA.model.rho}, kalibrert på ${DATA.model.calibration_matches} kamper.`;

  setupTabs();
  setupFilters();
  renderMatches();
  renderGroups();
  renderTitleChart();
}

function setupTabs() {
  const buttons = document.querySelectorAll("nav#tabs button");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.toggle("active", b === btn));
      document.querySelectorAll("main > section").forEach((sec) => {
        sec.hidden = sec.id !== "tab-" + btn.dataset.tab;
      });
    });
  });
}

function setupFilters() {
  const buttons = document.querySelectorAll("#filters button");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.toggle("active", b === btn));
      currentFilter = btn.dataset.filter;
      renderMatches();
    });
  });
}

function matchVisible(m) {
  if (currentFilter === "all") return true;
  if (currentFilter === "played") return m.status === "played";
  return m.status !== "played";
}

function probBar(p) {
  return `
    <div class="probbar">
      <div class="h" style="width:${p.p_home * 100}%"></div>
      <div class="d" style="width:${p.p_draw * 100}%"></div>
      <div class="a" style="width:${p.p_away * 100}%"></div>
    </div>
    <div class="problabels">
      <span>H ${pct(p.p_home)}</span>
      <span>U ${pct(p.p_draw)}</span>
      <span>B ${pct(p.p_away)}</span>
    </div>`;
}

function teamLabel(m, side) {
  const name = m[side];
  if (!m.placeholder) return no(name);
  return name; // plassholder som "1A" eller "W73"
}

function renderMatch(m) {
  const when = m.utc ? NB_TIME.format(new Date(m.utc)) : (m.time || "");
  const stage = m.group ? `Gruppe ${m.group}` : m.stage;
  let scoreHtml;
  if (m.status === "played") {
    let s = `${m.score[0]}–${m.score[1]}`;
    if (m.pens) s += ` (${m.pens[0]}–${m.pens[1]} str.)`;
    scoreHtml = `<span class="score played">${s}</span>`;
  } else if (m.pred) {
    scoreHtml = `<span class="score" title="Mest sannsynlige resultat">${m.pred.top_scores[0][0].replace("-", "–")}</span>`;
  } else {
    scoreHtml = `<span class="score">kl. ${when}</span>`;
  }

  let body = "";
  if (m.pred && m.status !== "played") {
    const p = m.pred.blended;
    const marketBadge = m.pred.market
      ? '<span class="badge market">marked + modell</span>'
      : '<span class="badge">modell</span>';
    body = probBar(p) +
      `<div class="extra">Forventede mål ${m.pred.xg_home.toFixed(1)}–${m.pred.xg_away.toFixed(1)}` +
      ` | Elo ${m.pred.elo_home} mot ${m.pred.elo_away}${marketBadge}</div>`;
  } else if (m.placeholder && m.likely_participants && m.likely_participants.length) {
    const names = m.likely_participants.slice(0, 4)
      .map((t) => `${no(t.team)} ${pct(t.p)}`).join(", ");
    body = `<div class="extra">Mest sannsynlige deltakere: ${names}</div>`;
  }

  return `
    <div class="match">
      <div class="top">
        <span>${stage}${m.num ? " | kamp " + m.num : ""}</span>
        <span>kl. ${when} | ${m.venue || ""}</span>
      </div>
      <div class="teams">
        <span class="home">${teamLabel(m, "home")}</span>
        ${scoreHtml}
        <span class="away">${teamLabel(m, "away")}</span>
      </div>
      ${body}
    </div>`;
}

function renderMatches() {
  const container = document.getElementById("matches");
  const visible = DATA.matches.filter(matchVisible);
  if (!visible.length) {
    container.innerHTML = '<p class="error">Ingen kamper i dette utvalget.</p>';
    return;
  }
  const parts = [];
  let lastDate = null;
  for (const m of visible) {
    const day = m.utc ? NB_DATE.format(new Date(m.utc)) : m.date;
    if (day !== lastDate) {
      parts.push(`<h3 class="date-heading">${day}</h3>`);
      lastDate = day;
    }
    parts.push(renderMatch(m));
  }
  container.innerHTML = parts.join("");
}

function renderGroups() {
  const container = document.getElementById("groups");
  const parts = [];
  for (const [group, teams] of Object.entries(DATA.groups)) {
    const rows = teams
      .map((t) => ({ team: t, ...DATA.teams[t] }))
      .sort((a, b) => b.p_r32 - a.p_r32)
      .map((t) => `
        <tr>
          <td>${no(t.team)}</td>
          <td>${t.elo}</td>
          <td>${pct(t.p_group_winner)}</td>
          <td>${pct(t.p_r32)}</td>
        </tr>`)
      .join("");
    parts.push(`
      <div class="group-card">
        <h3>Gruppe ${group}</h3>
        <table>
          <tr><th>Lag</th><th>Elo</th><th>Gr.vinner</th><th>Videre</th></tr>
          ${rows}
        </table>
      </div>`);
  }
  container.innerHTML = parts.join("");
}

function renderTitleChart() {
  const container = document.getElementById("title-chart");
  const ranked = Object.entries(DATA.teams)
    .map(([team, v]) => ({ team, p: v.p_champion }))
    .sort((a, b) => b.p - a.p)
    .filter((t, i) => i < 20 && t.p > 0.0005);
  const max = ranked.length ? ranked[0].p : 1;
  container.innerHTML = ranked
    .map((t) => `
      <div class="bar-row">
        <span class="name">${no(t.team)}</span>
        <div class="bar"><div style="width:${(t.p / max) * 100}%"></div></div>
        <span class="val">${(t.p * 100).toFixed(1)} %</span>
      </div>`)
    .join("");
}

init();
