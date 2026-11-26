// Knowledge advisor: degrees, broadband and the Science yield.
import { esc, fin, ratio, colorScale, robustDomain, RAMPS } from "../core/util.js";
import { money, pct, int, count3, fmtShort, dec } from "../core/fmt.js";
import { barList, histogram, rampLegend } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { createScatter } from "../core/scatter.js";
import { section, tiles, segmented, mapPicker, frameBtn, sourcesHtml, topBy } from "../core/view.js";
import { rowsHighlight } from "../core/data.js";
import { scienceLens } from "../core/lenses.js";

const METRO_MIN = 100000; // Europe has about 550 urban areas of 100,000+ people

export function mount(ctx) {
  const { app, data, el, link } = ctx;
  const n = data.nat;
  const nation = app.data.nation;
  const { metros, counties } = data.levels;
  const sci = nation.yields?.find((y) => y.key === "science");
  const usSci = n.yields?.science;
  const usShare = ratio(usSci, n.employed);
  const wavg = (k) => {
    if (!counties) return null;
    let a = 0, w = 0;
    for (const r of counties.rows) if (fin(r.v[k]) && fin(r.v.population)) { a += r.v[k] * r.v.population; w += r.v.population; }
    return w ? a / w : null;
  };

  el.insertAdjacentHTML("beforeend", tiles([
    { label: "Science workers", value: count3(usSci), sub: `${pct(usShare)} of jobs`, color: sci?.color },
    { label: "Degree holders", value: pct(wavg("bachelors")), sub: "aged 25–64, tertiary education" },
    { label: "Broadband", value: pct(wavg("broadband")), sub: "of homes connected" },
  ]));

  // --- the map: degrees by default (the scatter's x axis), or the Science yield's share by urban area -----------
  const mapRow = document.createElement("div");
  mapRow.className = "adv-sec adv-mapsec";
  el.appendChild(mapRow);
  const picker = mapPicker(ctx, mapRow, {
    value: counties ? "bachelors" : "science",
    options: [
      ...(counties ? [{ value: "bachelors", label: "Degrees", lens: () => "bachelors" }] : []),
      { value: "science", label: "Science jobs", lens: () => scienceLens(data) },
      ...(counties ? [{ value: "broadband", label: "Broadband", lens: () => "broadband" }] : []),
      { value: "terrain", label: "Terrain", lens: () => null },
    ],
  });

  // --- science yield --------------------------------------------------------------------------------------------
  const sBody = section(el, { title: "The Science yield", note: `${esc(sci?.description || "Jobs in information and communication, and in professional, scientific and technical activities.")} Urban areas of ${count3(METRO_MIN)}+ people for the share ranking.` });
  const sHost = document.createElement("div");
  let mode = "share";
  segmented(sBody, { label: "Rank by", value: mode, options: [{ value: "share", label: "Share of jobs" }, { value: "abs", label: "Most workers" }], onChange: (v) => { mode = v; drawSci(); } });
  const sMap = document.createElement("button");
  sMap.type = "button";
  sMap.className = "adv-mini";
  sMap.textContent = "Colour the map by science jobs";
  sMap.addEventListener("click", () => picker.set("science"));
  sBody.querySelector(".adv-seg")?.after(sMap);
  sBody.appendChild(sHost);
  const share = (r) => ratio(r.v.y_science, r.v.employed);
  function drawSci() {
    sHost.innerHTML = "";
    const list = mode === "abs" ? topBy(metros.rows, (r) => r.v.y_science, { n: 12 }) : topBy(metros.rows, share, { n: 12, min: METRO_MIN });
    barList(sHost, {
      rank: true, ariaLabel: "Science leaders",
      rows: list.map((x) => ({ key: x.r.key, label: x.r.name, sub: mode === "abs" ? pct(share(x.r)) : `×${dec(share(x.r) / usShare, 2)} Europe`, value: x.v, text: mode === "abs" ? count3(x.v) : pct(x.v), color: sci?.color, row: x.r })),
      onHover: (r) => link.hover(r ? rowsHighlight(metros, [r.row]) : null),
      onClick: (r) => metros.focus(r.row),
    });
  }
  drawSci();

  if (!counties) {
    el.insertAdjacentHTML("beforeend", `<p class="adv-empty pad">counties.json is not built, so the region charts are missing.</p>`);
    el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["eurostat"], []));
    return {};
  }

  // --- degrees vs income ----------------------------------------------------------------------------------------
  const dBody = section(el, { title: "Degrees and income", note: "Share of 25–64 year-olds with tertiary education against disposable income per inhabitant; colour = broadband. Drag to select; hover the map to find a place." });
  const dCtl = document.createElement("div");
  dCtl.className = "adv-row";
  dBody.appendChild(dCtl);
  let level = "counties";
  segmented(dCtl, { label: "Places", value: level, options: [{ value: "counties", label: "Regions" }, { value: "metros", label: "Urban areas" }], onChange: (v) => { level = v; drawDeg(); } });
  const lv = () => data.levels[level];
  const inc = (r) => (level === "counties" ? r.v.income : r.v.median_income);
  const bbDom = robustDomain(counties.rows.map((r) => r.v.broadband), 0.02) || [0.7, 0.95];
  const bbColor = colorScale({ type: "seq", domain: bbDom, ramp: RAMPS.seq });
  const scatter = createScatter(dBody, {
    height: 300, points: [],
    x: { label: "Adults with a degree", fmt: (v) => fmtShort("pct", v) },
    y: { label: "Disposable income per inhabitant", fmt: money, log: true },
    size: { label: "Population", fmt: count3, max: 14, min: 1.4 },
    color: (c) => bbColor(c), colorLabel: "Broadband", colorFmt: (v) => pct(v),
    onHover: (p) => link.hover(p ? rowsHighlight(lv(), [p.row]) : null),
    onClick: (p) => lv().focus(p.row),
    onBrush: (set) => {
      const sel = set ? lv().rows.filter((r) => set.has(r.key)) : [];
      link.base(sel.length ? rowsHighlight(lv(), sel, { dim: true }) : null, { frame: sel.length > 1 });
      selInfo.innerHTML = sel.length ? `<b>${int(sel.length)}</b> ${esc(lv().label.toLowerCase())} · ${count3(sel.reduce((a, r) => a + (r.v.population || 0), 0))} people ${frameBtn()}<button type="button" class="adv-mini" data-clear>Clear</button>` : "";
    },
  });
  dBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: RAMPS.seq, domain: bbDom, fmt: (v) => fmtShort("pct", v), label: "Homes with broadband" }));
  const selInfo = document.createElement("div");
  selInfo.className = "adv-brushinfo";
  dBody.appendChild(selInfo);
  const clearSel = () => { scatter.setSelected(null); link.base(null); selInfo.innerHTML = ""; };
  selInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) clearSel(); });
  function drawDeg() {
    clearSel();
    const rows = lv().rows;
    scatter.update({
      points: rows.map((r) => ({ key: r.key, x: r.v.bachelors, y: inc(r), s: r.v.population, c: r.v.broadband, label: r.name, sub: r.sub, row: r })),
      labels: topBy(rows, (r) => r.v.population, { n: 6 }).map((x) => x.r.key),
    });
  }
  drawDeg();

  // --- broadband ------------------------------------------------------------------------------------------------
  const bBody = section(el, { title: "Who is offline", note: "Regions by the share of homes with a broadband connection. Hover a bar to outline those regions." });
  const bHost = document.createElement("div");
  bBody.appendChild(bHost);
  const bbHist = histogram(bHost, {
    values: counties.rows.map((r) => ({ key: r.key, v: r.v.broadband })), bins: 30, domain: [0.5, 1], height: 120,
    fmt: (v) => fmtShort("pct", v), unitLabel: "regions", label: "Histogram of broadband by region",
    colorOf: (_, t) => colorScale({ type: "seq", domain: [0, 1], ramp: RAMPS.seq })(t),
    onHover: (bin) => link.hover(bin ? rowsHighlight(counties, bin.keys.map((k) => counties.byKey.get(k)), { dim: true }) : null),
  });
  createTable(bBody, {
    caption: "Broadband by region", rank: true, maxHeight: 240, search: "Search regions",
    rows: counties.rows.filter((r) => fin(r.v.broadband)),
    columns: [
      { key: "name", label: "Region", align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
      { key: "population", label: "People", value: (r) => r.v.population, text: (r) => count3(r.v.population) },
      { key: "broadband", label: "Broadband", value: (r) => r.v.broadband, text: (r) => pct(r.v.broadband), bar: { max: 1, color: "rgba(74,134,214,.4)" } },
      { key: "bachelors", label: "Degrees", value: (r) => r.v.bachelors, text: (r) => pct(r.v.bachelors) },
    ],
    sort: { key: "broadband", dir: "asc" },
    onHover: (r) => link.hover(r ? rowsHighlight(counties, [r]) : null),
    onClick: (r) => counties.focus(r),
  });

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["eurostat"], [
    "Science jobs are counted where people work and cover whole industries (an engineering firm's receptionist counts; a hospital's researcher does not).",
    `Degrees and income are NUTS 2 figures, so every region of a NUTS 2 area shares its value (region data: ${esc(data.countyVintage)}). Urban-area values are population-weighted means over their regions.`,
    "Income is in purchasing power standards (PPS) for regions and in euros for urban areas.",
    "The Science jobs map colours urban areas only (grey hexes are outside them).",
    "Broadband measures whether homes are connected, not the speed they get.",
    ...(data.countiesOffMap ? [`${int(data.countiesOffMap)} of the smallest regions are smaller than one hex, so selecting them outlines nothing on the map.`] : []),
  ]));

  return {
    onMapHover(h) {
      const r = h.cell >= 0 ? lv().rowAtCell(h.cell) : null;
      scatter.setHot(r ? r.key : null);
      const c = h.cell >= 0 ? counties.rowAtCell(h.cell) : null;
      bbHist.setHot(c ? bbHist.binOf(c.v.broadband)?.i ?? null : null);
    },
    onEscape() {
      if (scatter.selected) { clearSel(); return true; }
      return false;
    },
  };
}
