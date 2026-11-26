import { css } from "../color.js";
import { esc, int, popShort } from "../format.js";
import { isCapital } from "../world.js";
import { icon } from "./icon.js";
import { yieldGrid, amenities, industries, gdpRow, popLine, growthSpan, showPanel } from "./infoPanel.js";

/**
 * Opens the panel for state `idx` (index into world.json states / states.json).
 * ctx: {w, nation, states (states.json or null), cities, onClose, onPedia, onCity(city)}
 */
export function openStatePanel(idx, ctx) {
  const { w, nation } = ctx;
  const n = nation.nation;
  const geo = w.raw.states[idx] || {};
  // states.json is in the same order as world.json states; fall back to matching by fips.
  let st = ctx.states?.[idx];
  if (st && geo.fips && st.fips && st.fips !== geo.fips) st = ctx.states.find((s) => s.fips === geo.fips);
  st = st || { ...geo };
  const name = st.name || geo.name || "Country";
  const abbr = st.abbr || geo.abbr || "";
  const region = st.region || geo.region || "";
  const count = ctx.states?.length || w.raw.states.length;

  const cities = (ctx.cities || []).filter((c) => (c.states || []).includes(abbr)).slice(0, 8);
  const cityRows = cities.length
    ? `<div class="city-list">${cities
        .map((c) => {
          const multi = (c.states || []).length > 1 ? `<span class="muted"> · ${esc(c.states.join("–"))}</span>` : "";
          // The municipality first (as on the banners), the whole urban area beside it; the list is ranked by urban
          // area, the size that compares across countries (municipal borders differ a lot).
          const own = c.commune_population;
          const area = own != null && own !== c.population ? `<span class="muted cr-aire"> · area ${popShort(c.population)}</span>` : "";
          const tip = own != null && own !== c.population
            ? `${int(own)} people in ${c.centre || c.name}, ${int(c.population)} in its urban area`
            : `${int(c.population)} people`;
          return `<button class="city-row" data-city="${esc(c.id)}" title="${esc(tip)}">
            <span class="cr-name">${isCapital(c) ? `${icon("capital", null, { size: 11, title: "National capital" })} ` : ""}${esc(c.name)}${multi}</span>
            <span class="cr-pop">${popShort(own ?? c.population)}${area}</span><span class="cr-go" aria-hidden="true">›</span></button>`;
        })
        .join("")}</div>`
    : `<p class="muted">No urban areas in this country's data.</p>`;

  const hasEcon = st.population != null || st.yields;
  showPanel({
    kind: "state",
    stripe: css(w.stateColor[idx] || [190, 190, 190]),
    title: name,
    sub: `${esc(abbr)}${region ? ` · ${esc(region)}` : ""}`,
    headExtra: hasEcon ? popLine(st, growthSpan(st, n)) : "",
    sections: [
      st.yields && { title: "Yields · rank among countries", html: `<div class="yield-grid">${yieldGrid(nation, st.yields, st.ranks, count)}</div>` },
      hasEcon && { title: "Living standards", html: amenities(st, n) + gdpRow(st) },
      st.jobs && { title: "Top industries · where people work", html: industries(st, nation, 8) },
      { title: "Biggest cities", html: cityRows },
      !hasEcon && { title: "Data", html: `<p class="muted">Country statistics are not in this data build (states.json is missing).</p>` },
    ],
    foot: `Source: ${esc(nation.vintage)}${nation.gdp_vintage ? `; GDP: ${esc(nation.gdp_vintage)}` : ""}. Ranks are among the ${count} mapped countries (1 = largest).`,
    onClose: ctx.onClose,
    onPedia: ctx.onPedia,
    wire(panel) {
      panel.querySelectorAll("[data-city]").forEach((b) => {
        b.onclick = () => {
          const c = ctx.cities.find((x) => x.id === b.dataset.city);
          if (c) ctx.onCity(c);
        };
      });
    },
  });
}
