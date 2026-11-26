// Places: every municipality and town of the map (communes.json, about 98,000), named on the map as you zoom in.
// The biggest come first; smaller ones appear zoom step by zoom step until, close in, every village has its name.
// Names never overlap one another and step aside for the city hexes (their banners carry the city's name).
// Hover: population and country; click: the place's card. Toggle: "Places" in the map layers menu.
import { esc, int } from "../../format.js";

// Smallest population named at each hex size (hex radius in css px), and the name's size.
const TIERS = [
  { rpx: 14, min: 60000 }, { rpx: 20, min: 25000 }, { rpx: 28, min: 10000 }, { rpx: 40, min: 4000 },
  { rpx: 58, min: 1500 }, { rpx: 85, min: 500 }, { rpx: 120, min: 0 },
];
const FONT = '"Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif';

const minPopFor = (Rpx) => {
  let min = Infinity;
  for (const t of TIERS) if (Rpx >= t.rpx) min = t.min;
  return min;
};
// The map shows the bare name; the homonym hint ("Aalst (Aalst)", "Buchs (AG)") stays in the tooltip.
const label = (name) => String(name).replace(/\s*\([^)]*\)$/, "");
const sizeFor = (pop) => (pop >= 100000 ? 13 : pop >= 20000 ? 12 : pop >= 5000 ? 11 : 10);

export function install(app) {
  let data = null, loading = false, version = 0, on = true;
  let byCell = null; // cell → place indices, most populous first
  let drawn = []; // the labels of the last render: {i, x0, y0, x1, y1} in map units, for hover and click

  function load() {
    if (data || loading) return;
    loading = true;
    app.loadData("communes").then((d) => {
      loading = false;
      if (!d?.rows || !d.columns.includes("x")) return;
      const col = Object.fromEntries(d.columns.map((c, k) => [c, k]));
      data = { rows: d.rows, col };
      byCell = new Map();
      d.rows.forEach((r, i) => {
        const cell = r[col.cell];
        if (cell == null) return;
        if (!byCell.has(cell)) byCell.set(cell, []);
        byCell.get(cell).push(i);
      });
      for (const list of byCell.values()) list.sort((a, b) => (d.rows[b][col.pop] || 0) - (d.rows[a][col.pop] || 0));
      version++;
      app.requestDraw();
    }, () => { loading = false; });
  }

  const layer = {
    id: "places", z: 88, minRpx: TIERS[0].rpx,
    visible() {
      if (!on) return false;
      if (!data) { load(); return false; }
      return true;
    },
    sig: () => `p${version}`,
    draw(ctx, vp, w, o) {
      const { rows, col } = data;
      const minPop = minPopFor(o.Rpx);
      const cityCells = w.cityByCell;
      const cityNames = new Set([...cityCells.values()].map((c) => c.name.toLowerCase()));
      // candidates in view, most populous first
      const cand = [];
      for (const cell of o.cells) {
        const list = byCell.get(cell);
        if (!list) continue;
        for (const i of list) {
          const pop = rows[i][col.pop] || 0;
          if (pop < minPop) break;
          if (cityNames.has(label(rows[i][col.name]).toLowerCase())) continue; // the city banner names it already
          cand.push(i);
        }
      }
      cand.sort((a, b) => (rows[b][col.pop] || 0) - (rows[a][col.pop] || 0));
      o.screen();
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.lineJoin = "round";
      const boxes = [];
      // city hexes are taken (their banners sit there)
      const R = w.grid.R * o.s;
      for (const cell of o.cells) {
        if (!cityCells.has(cell)) continue;
        const [sx, sy] = o.toScreen(w.grid.cx(cell), w.grid.cy(cell));
        boxes.push([sx - R, sy - R * 0.9, sx + R, sy + R * 0.9]);
      }
      const overlaps = (b) => boxes.some((p) => b[0] < p[2] && p[0] < b[2] && b[1] < p[3] && p[1] < b[3]);
      drawn = [];
      const limit = 900; // names per render: plenty for a screen, cheap to draw
      for (const i of cand) {
        if (drawn.length >= limit) break;
        const r = rows[i];
        const pop = r[col.pop] || 0;
        const [sx, sy] = o.toScreen(r[col.x], r[col.y]);
        if (sx < -50 || sy < -20 || sx > vp.cssW + 50 || sy > vp.cssH + 20) continue;
        const px = sizeFor(pop);
        ctx.font = `${pop >= 20000 ? "600 " : ""}${px}px ${FONT}`;
        const name = label(r[col.name]);
        const tw = ctx.measureText(name).width;
        const box = [sx - 4, sy - px * 0.62, sx + 6 + tw + 2, sy + px * 0.62];
        if (overlaps(box)) continue;
        boxes.push(box);
        // dot
        ctx.beginPath();
        ctx.arc(sx, sy, pop >= 20000 ? 2.6 : 2, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(255,246,222,.92)";
        ctx.strokeStyle = "rgba(25,18,10,.75)";
        ctx.lineWidth = 1.2;
        ctx.fill();
        ctx.stroke();
        // name
        ctx.lineWidth = 2.6;
        ctx.strokeStyle = "rgba(20,14,8,.62)";
        ctx.fillStyle = pop >= 20000 ? "rgba(255,244,214,.96)" : "rgba(244,236,214,.9)";
        ctx.strokeText(name, sx + 5, sy);
        ctx.fillText(name, sx + 5, sy);
        const s = o.s;
        drawn.push({ i, x0: vp.x0 + box[0] / s, y0: vp.y0 + box[1] / s, x1: vp.x0 + box[2] / s, y1: vp.y0 + box[3] / s });
      }
    },
    hit(x, y) {
      if (!data) return null;
      for (const d of drawn) if (x >= d.x0 && x <= d.x1 && y >= d.y0 && y <= d.y1) return d.i;
      return null;
    },
    tooltip(i) {
      const { rows, col } = data, r = rows[i];
      const country = app.data.states?.find((s) => s.abbr === r[col.dep])?.name || r[col.dep];
      const kind = /^GN_/.test(r[col.code]) ? "Town" : "Municipality";
      return `<b>${esc(r[col.name])}</b><br><span class="muted">${kind}, ${esc(country)}${r[col.pop] ? ` · ${int(r[col.pop])} people` : ""}</span><br><span class="muted">Click for its card</span>`;
    },
    click(i) {
      const { rows, col } = data;
      app.showPlace?.(rows[i][col.code], { fly: false });
      return true;
    },
  };
  app.registerStaticLayer(layer);
  app.ui.addMapToggle?.({
    id: "places", label: "Places", icon: "l-home", title: "Names of the municipalities and towns, more as you zoom in", default: true,
    get: () => on,
    set: (v) => { on = !!v; app.requestDraw(); },
  });
}
