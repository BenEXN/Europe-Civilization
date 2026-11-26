// Hover tooltips for the map-art layers (HTML strings; every data value is escaped). Each says where the number comes
// from and the caveat that matters for it (freight values are model estimates; bases have no published headcount; the
// trade arc is a drawing aid; curated landmarks are an editorial pick). Money is in euros.
import { esc, compact, dec, int, pct, signedPct } from "../../format.js";
import { FORT_KINDS, fortKind, WONDER_KINDS } from "../../render/art/sites.js";
import { MODE_STYLE } from "../../render/art/improvements.js";

const muted = (s) => `<span class="muted">${s}</span>`;
const num = (n, d = 1) => (n == null || !Number.isFinite(n) ? "–" : compact(n));

function usd(n) {
  if (n == null || !Number.isFinite(n)) return "–";
  const a = Math.abs(n);
  if (a >= 1e12) return `€${dec(n / 1e12, 2)} trillion`;
  if (a >= 1e9) return `€${dec(n / 1e9, a >= 1e10 ? 1 : 2)} billion`;
  if (a >= 1e6) return `€${dec(n / 1e6, 1)} million`;
  return `€${int(n)}`;
}

const HUB_NAME = { L: "Large airport", M: "Medium airport", S: "Small airport", N: "Regional airport" };
const PORT_TYPE = { coastal: "Seaport", great_lakes: "Lake port", inland: "River port" };

export const tips = {
  port(p, m) {
    const yr = p.year ?? "";
    const lines = [
      `<b>${esc(p.name)}</b> ${muted(`${esc(PORT_TYPE[p.type] || "Port")}${p.state ? `, ${esc(p.state)}` : ""}`)}`,
      p.tons != null ? `#${esc(p.rank)} by tonnage · <b>${num(p.tons)}</b> tonnes (${esc(yr)})` : `#${esc(p.rank)}`,
    ];
    if (p.foreign != null || p.domestic != null) lines.push(`International ${num(p.foreign)} · domestic ${num(p.domestic)}`);
    if (p.imports != null || p.exports != null) lines.push(`Unloaded ${num(p.imports)} t · loaded ${num(p.exports)} t`);
    lines.push(muted("Gross weight of goods handled (Eurostat); the port is placed at the centre of its municipality."));
    return lines.join("<br>");
  },
  airport(a) {
    const lines = [`<b>${esc(a.id)} · ${esc(a.name)}</b> ${muted(esc([a.city, a.state].filter(Boolean).join(", ")))}`];
    lines.push(a.hub ? esc(HUB_NAME[a.hub] || a.hub) : "Cargo airport (not a major passenger airport)");
    if (a.enplanements != null) {
      let ch = "";
      if (a.enplanements_prev > 0) {
        const r = a.enplanements / a.enplanements_prev - 1;
        ch = ` (${signedPct(r)} on ${a.year - 1})`;
      }
      lines.push(`<b>${num(a.enplanements)}</b> passengers in ${esc(a.year)}${ch}`);
    }
    if (a.cargo_lbs != null) lines.push(`Freight ${num(a.cargo_lbs)}`);
    lines.push(muted("Annual airport traffic."));
    return lines.join("<br>");
  },
  fort(f, m) {
    const comp = m.data.military?.components?.find((c) => c.id === f.component);
    const name = comp?.name || FORT_KINDS[fortKind(f.component)]?.name || "Defence site";
    const tier = { major: "Major installation", base: "Base", site: "Site" }[f.tier] || "";
    const status = { act: "", semi: " · semi-active", care: " · caretaker status" }[f.status] ?? "";
    const lines = [
      `<b>${esc(f.name)}</b> ${muted(esc(f.state || ""))}`,
      `${esc(name)}${f.joint ? " · joint base" : ""} · ${esc(tier)}${esc(status)}`,
    ];
    if (f.area_km2 != null) lines.push(`Boundary ${int(f.area_km2)} km²`);
    lines.push(muted("Sized by boundary area: no per-base headcount is published."));
    return lines.join("<br>");
  },
  range(r, m) {
    const comp = m.data.military?.components?.find((c) => c.id === r.component);
    return [
      `<b>${esc(r.name)}</b> ${muted(esc(r.state || ""))}`,
      `Restricted ground · ${esc(comp?.name || "")} · ${int(r.area_km2)} km²`,
      muted("One of the largest military grounds, drawn on the hexes it covers."),
    ].join("<br>");
  },
  wonder(x, m) {
    const k = WONDER_KINDS[x.kind]?.name || "Wonder";
    const rule = m.data.wonders?.rules?.find((r) => r.id === x.rule);
    const mt = x.metrics || {};
    const lines = [`<b>${esc(x.name)}</b> ${muted(esc([x.state].filter(Boolean).join("")))}`];
    if (x.kind === "university") {
      lines.push(`${esc(k)} · #${esc(x.rank)}${mt.enrollment != null && mt.rd_usd == null ? " by enrolment" : " by research spending"}`);
      if (mt.rd_usd != null) lines.push(`R&amp;D ${usd(mt.rd_usd)} (${esc(mt.year)})${mt.federal_usd != null ? `, ${pct(mt.federal_usd / mt.rd_usd, 0)} public funding` : ""}`);
      if (mt.enrollment != null) lines.push(`${int(mt.enrollment)} students (${esc(mt.enrollment_year)})`);
    } else if (x.curated) {
      lines.push(`${esc(k)} · hand-picked (curated, not ranked by data)`);
      if (mt.visits != null) lines.push(`${num(mt.visits)} visits (${esc(mt.year)})`);
      if (mt.designated) lines.push(`Protected since ${esc(mt.designated)}`);
    } else if (x.rule === "museum") {
      lines.push(`${esc(k)} · #${esc(x.rank)} most-visited museum`);
      if (mt.visits != null) lines.push(`<b>${num(mt.visits)}</b> visitors in ${esc(mt.year)}`);
    } else if (x.rule === "unesco") {
      lines.push(`${esc(k)} · UNESCO World Heritage${mt.inscribed ? `, inscribed in ${esc(mt.inscribed)}` : ""}`);
      if (mt.visits != null) lines.push(`<b>${num(mt.visits)}</b> visitors in ${esc(mt.visits_year)}${mt.visits_of ? ` ${muted(`(${esc(mt.visits_of)})`)}` : ""}`);
    } else if (x.rule === "national_park") {
      lines.push(`${esc(k)} · national park${mt.year ? `, created in ${esc(mt.year)}` : ""}`);
      if (mt.area_km2 != null) lines.push(`${int(mt.area_km2)} km²`);
    } else {
      lines.push(`${esc(k)} · #${esc(x.rank)} by visits${mt.unit_type ? ` among ${esc(mt.unit_type)}` : ""}`);
      if (mt.visits != null) lines.push(`<b>${num(mt.visits)}</b> visits (${esc(mt.year)})${mt.visits_of ? ` ${muted(`(${esc(mt.visits_of)})`)}` : ""}`);
      if (mt.area_km2 != null) lines.push(`${int(mt.area_km2)} km²`);
    }
    if (rule?.text) lines.push(muted(esc(rule.text)));
    return lines.join("<br>");
  },
  route(rt, m) {
    const r = rt.route;
    const t = m.data.trade || {};
    const a = rt.a?.short || rt.a?.name || r.a, b = rt.b?.short || rt.b?.name || r.b;
    const modes = Object.entries(r.modes || {}).filter(([, v]) => v >= 0.05).sort((p, q) => q[1] - p[1])
      .map(([k, v]) => `${esc(MODE_STYLE[k]?.label || k)} ${Math.round(v * 100)}%`).join(" · ");
    const com = t.commodities?.[r.top_commodity];
    const lines = [
      `<b>${esc(a)} ⇄ ${esc(b)}</b> ${muted(`trade route #${esc(r.rank)}`)}`,
      r.value_musd != null
        ? `<b>${usd(r.value_musd * 1e6)}</b> of freight a year, ${num(r.tons_k * 1e3)} tonnes (${esc(t.year ?? "")} estimate)`
        : `<b>${num(r.tkm_m * 1e6)}</b> tonne-km of freight in ${esc(t.year ?? "")}${r.rail_water_tons_k ? `, of which ${num(r.rail_water_tons_k * 1e3)} tonnes by rail and waterway` : ""}`,
    ];
    if (modes) lines.push(modes);
    if (com) lines.push(`Top commodity: ${esc(com)}`);
    lines.push(muted(r.value_musd != null
      ? "Both directions summed. Drawn as an arc between each zone's largest city: the data records where freight starts and ends, not its route."
      : "Both directions summed (road, rail and waterway), between the two regions. Drawn as an arc between their largest cities: the data records where freight starts and ends, not its route."));
    return lines.join("<br>");
  },
};
