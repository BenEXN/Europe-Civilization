// English number formatting (en-GB): decimal point, thousands commas, k / M / bn / tn suffixes, euros before the number.

/** Separator between a number and a unit suffix (%, k, M, bn, °C). English writes none: 12%, 1.2M.
 *  (Kept under its old name, "narrow no-break space", so every import still works.) */
export const NNBSP = "";

/** x.toFixed(d) (decimal point). */
export const dec = (x, d = 0) => x.toFixed(d);

export function compact(n) {
  if (n == null || Number.isNaN(n)) return "–";
  const a = Math.abs(n);
  if (a >= 1e12) return dec(n / 1e12, a >= 1e13 ? 1 : 2) + NNBSP + "tn";
  if (a >= 1e9) return dec(n / 1e9, a >= 1e11 ? 0 : 1) + NNBSP + "bn";
  if (a >= 1e6) return dec(n / 1e6, a >= 1e8 ? 0 : 1) + NNBSP + "M";
  if (a >= 1e3) return dec(n / 1e3, a >= 1e5 ? 0 : 1).replace(/\.0$/, "") + NNBSP + "k";
  return String(Math.round(n));
}

const euroSign = (n) => (n < 0 ? "−€" : "€");

/** Compact euros: €92.3bn, €1.2M, €34k, €850. */
export const money = (n) => (n == null ? "–" : euroSign(n) + (Math.abs(n) >= 1e3 ? compact(Math.abs(n)) : Math.round(Math.abs(n))));
/** Whole euros: €42,350. (Kept under its usaciv name so every import still works.) */
export const dollars = (n) => (n == null ? "–" : euroSign(n) + Math.round(Math.abs(n)).toLocaleString("en-GB"));
export const euros = dollars;
export const int = (n) => (n == null ? "–" : Math.round(n).toLocaleString("en-GB"));
export const pct = (x, d = 1) => (x == null ? "–" : dec(x * 100, d) + NNBSP + "%");
/** Signed percent: +2.1%, −0.4%. */
export const signedPct = (g, d = 1) => (g == null || !Number.isFinite(g) ? "–" : `${g >= 0 ? "+" : "−"}${dec(Math.abs(g * 100), d)}${NNBSP}%`);

export function yieldValue(y, v) {
  return y.unit === "usd" || y.unit === "eur" ? money(v) : compact(v);
}

export function popShort(n) {
  if (n >= 1e7) return Math.round(n / 1e6) + NNBSP + "M";
  if (n >= 1e6) return dec(n / 1e6, 1) + NNBSP + "M";
  return Math.round(n / 1e3) + NNBSP + "k";
}

/** Real km per map unit (world.json km_per_unit; the map may be drawn at a different scale than real km). */
export const kmPerUnit = (world) => (world && Number.isFinite(world.km_per_unit) && world.km_per_unit > 0 ? world.km_per_unit : 1);

export const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
