// Économie Homéostatique (EH) : la calibration empirique de l'EH portée sur la carte.
//
//   bouton « EH » dans la barre du haut, mode « eh » (Échap pour sortir), lien #eh=<vue>
//   découpages transfrontaliers : quatre couches statiques (districts hydrographiques, régions marines, zones CIEM,
//     régions biogéographiques), chacune avec son interrupteur dans le menu « Map » et dans le panneau
//   la carte colorée par pays : IED d'une configuration de la grille de sensibilité, ou rapport d'un
//     sous-indicateur à son repère normatif
//
// Données : web/data/eh.json, produit par analyse/carte_eh.py à partir de calibration/sensibilite_ied.json et des
// découpages téléchargés (calibration/decoupages/). Aucune valeur affichée n'est une mesure de l'IED : chacune dépend
// des choix de construction indiqués avec elle.
import { esc } from "../../format.js";

const CSS_HREF = new URL("../../../css/eh.css", import.meta.url).href;
const DOCK_W = 420;
const fin = (v) => typeof v === "number" && Number.isFinite(v);
const d2 = (v) => (fin(v) ? v.toFixed(2).replace(".", ",") : "–");
const d1 = (v) => (fin(v) ? v.toFixed(1).replace(".", ",") : "–");

// IED sur [0, 2], valeur 1 au centre ; rapport au repère en échelle logarithmique, 1 au centre.
const RAMP_IED = ["#7a1d2b", "#c2513f", "#eea46f", "#f4ecd8", "#9fcfb0", "#3f9a7f", "#145a57"];
const RAMP_RAPPORT = ["#145a57", "#3f9a7f", "#9fcfb0", "#f4ecd8", "#eea46f", "#c2513f", "#7a1d2b"];

function loadCss() {
  if (document.querySelector(`link[href="${CSS_HREF}"]`)) return;
  const l = document.createElement("link");
  l.rel = "stylesheet";
  l.href = CSS_HREF;
  document.head.appendChild(l);
}

// --- géométrie ---------------------------------------------------------------------------------------------------

/** Pair-impair sur tous les anneaux d'une entité (anneaux à plat : x0, y0, x1, y1, …). */
function inside(feature, x, y) {
  const b = feature.bbox;
  if (x < b[0] || x > b[2] || y < b[1] || y > b[3]) return false;
  let c = false;
  for (const r of feature.rings) {
    for (let i = 0, j = r.length - 2; i < r.length; j = i, i += 2) {
      const xi = r[i], yi = r[i + 1], xj = r[j], yj = r[j + 1];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
    }
  }
  return c;
}

function tracePath(ctx, feature) {
  for (const r of feature.rings) {
    ctx.moveTo(r[0], r[1]);
    for (let i = 2; i < r.length; i += 2) ctx.lineTo(r[i], r[i + 1]);
    ctx.closePath();
  }
}

// Les cartouches (Açores, Canaries…) ont leur propre projection : les découpages n'y sont pas tracés.
let insetFrames = null;
function clipInsets(ctx) {
  if (!insetFrames?.length) return;
  ctx.beginPath();
  ctx.rect(-1e6, -1e6, 2e6, 2e6);
  for (const [x0, y0, x1, y1] of insetFrames) ctx.rect(x0, y0, x1 - x0, y1 - y0);
  ctx.clip("evenodd");
}

const visibleIn = (f, vp) => !(f.bbox[2] < vp.x0 || f.bbox[0] > vp.x1 || f.bbox[3] < vp.y0 || f.bbox[1] > vp.y1);

// --- l'extension -------------------------------------------------------------------------------------------------

export function install(app) {
  insetFrames = (app.data.world?.insets || []).map((i) => i.frame).filter((f) => Array.isArray(f) && f.length === 4);
  let data = null;
  let root = null;
  let prevLens = null;
  let mapLens = null;
  const on = {}; // id du découpage → affiché
  const hover = { layer: null, feature: null };
  // Vue : ce qui colore la carte. kind "ied" (configuration de la grille), "rapport" (sous-indicateur), "aucune".
  const view = { kind: "ied", indic: "ied", cfg: null, sous: null, seuil: null };
  // Composantes : l'IEE dépend de la normalisation et de l'agrégation ; l'IRNR, de la normalisation et du repère.
  const INDICS = { ied: "IED", iee: "IEE", irnr: "IRNR" };
  const DEPEND = { ied: "napsb", iee: "na", irnr: "ns" };

  const btn = app.ui.addTopButton({
    id: "btn-eh", label: "EH", title: "Économie Homéostatique : calibration empirique et découpages transfrontaliers",
    onClick: () => (app.mode === "eh" ? app.setMode(null) : app.setMode("eh")),
  });
  if (btn) {
    btn.innerHTML = `<svg class="icon" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M5 13c3-4 5 3 7-1s4-5 7-1" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg><span class="lbl">EH</span>`;
    btn.setAttribute("aria-pressed", "false");
  }
  app.on("mode", ({ name }) => btn?.setAttribute("aria-pressed", String(name === "eh")));

  // --- données ---------------------------------------------------------------------------------------------------
  const ready = app.loadData("eh").then((d) => {
    if (!d) {
      console.info("eh: web/data/eh.json absent ; l'extension reste inactive");
      return null;
    }
    data = d;
    view.cfg = { ...d.reference_indices };
    view.sous = d.sous_indicateurs_ordre[0];
    view.seuil = Object.keys(d.sous_indicateurs[view.sous].seuils)[0];
    for (const dec of d.decoupages) {
      on[dec.id] = false;
      registerLayer(dec);
      app.ui.addMapToggle({
        id: `eh-${dec.id}`, label: dec.court, icon: "layers", title: `${dec.nom} (${dec.source})`, default: false,
        get: () => !!on[dec.id],
        set: (v) => { on[dec.id] = !!v; app.requestDraw(); render(); },
      });
    }
    if (app.mode === "eh") { render(); colour(); }
    return d;
  });

  // --- couches des découpages ------------------------------------------------------------------------------------
  function registerLayer(dec) {
    const layer = {
      id: `eh-${dec.id}`, z: 52 + dec.ordre * 0.1,
      visible: () => !!on[dec.id],
      draw(ctx, vp, w, o) {
        const s = vp.s;
        clipInsets(ctx);
        ctx.lineJoin = "round";
        for (let k = 0; k < dec.features.length; k++) {
          const f = dec.features[k];
          if (!visibleIn(f, vp)) continue;
          ctx.beginPath();
          tracePath(ctx, f);
          ctx.strokeStyle = "rgba(10,12,16,.55)";
          ctx.lineWidth = 4 / s;
          ctx.setLineDash([]);
          ctx.stroke();
          ctx.strokeStyle = dec.couleur;
          ctx.lineWidth = 2.2 / s;
          ctx.setLineDash(dec.tirets.map((t) => t / s));
          ctx.stroke();
        }
        ctx.setLineDash([]);
      },
      hit(x, y) {
        for (let k = dec.features.length - 1; k >= 0; k--) {
          if (inside(dec.features[k], x, y)) {
            if (hover.layer !== dec.id || hover.feature !== k) {
              hover.layer = dec.id;
              hover.feature = k;
              app.requestDraw();
            }
            return { dec, k };
          }
        }
        return null;
      },
      tooltip: ({ dec: dd, k }) => {
        const f = dd.features[k];
        const extra = f.detail ? `<br><span class="muted">${esc(f.detail)}</span>` : "";
        return `<b>${esc(f.nom)}</b>${extra}<br><span class="muted">${esc(dd.nom)} — ${esc(dd.source)}</span>`;
      },
    };
    app.registerStaticLayer(layer);
  }
  // La surbrillance de l'entité survolée, dessinée par-dessus la carte en cache.
  app.registerOverlay({
    id: "eh-survol", z: 20, space: "world",
    draw(ctx, cam) {
      if (!data || !hover.layer || !on[hover.layer]) return;
      const dec = data.decoupages.find((d) => d.id === hover.layer);
      const f = dec?.features[hover.feature];
      if (!f) return;
      clipInsets(ctx);
      ctx.beginPath();
      tracePath(ctx, f);
      ctx.fillStyle = dec.remplissage;
      ctx.fill("evenodd");
      ctx.strokeStyle = dec.couleur;
      ctx.lineWidth = 2.6 / cam.scale;
      ctx.stroke();
    },
  });
  // Le survol d'une autre chose efface la surbrillance.
  app.on("hover", (h) => {
    if (hover.layer && (!h || h.layer !== `eh-${hover.layer}`)) {
      hover.layer = null;
      hover.feature = null;
      app.requestDraw();
    }
  });

  // --- coloration de la carte ------------------------------------------------------------------------------------
  function scenario(cfg) {
    return data.scenarios.find((sc) => sc.n === cfg.n && sc.a === cfg.a && sc.p === cfg.p && sc.s === cfg.s && sc.b === cfg.b);
  }
  function valeurs(indic, cfg) {
    if (indic === "ied") return scenario(cfg)?.ied || {};
    if (indic === "iee") return data.composantes?.iee.find((c) => c.n === cfg.n && c.a === cfg.a)?.valeurs || {};
    return data.composantes?.irnr.find((c) => c.n === cfg.n && c.s === cfg.s)?.valeurs || {};
  }
  function cfgLabel(cfg) {
    const o = data.options;
    return `${o.normalisation[cfg.n]} ; ${o.agregation[cfg.a]} ; poids ${o.poids[cfg.p]} ; repère IRNR ${o.seuil_irnr[cfg.s]} ; IBD supposé ${d1(o.ibd[cfg.b])}`;
  }
  function countryLens(id, byAbbr, spec) {
    const owner = app.w.raw.owner, states = app.w.raw.states, n = owner.length;
    const values = new Array(n).fill(null);
    for (let i = 0; i < n; i++) {
      if (owner[i] < 0) continue;
      const v = byAbbr[states[owner[i]].abbr];
      if (fin(v)) values[i] = v;
    }
    return { id, group: "eh", icon: "layers", higher_is: "neutral", source: "eh", values, ...spec };
  }
  function colour() {
    if (!data || app.mode !== "eh") return;
    if (view.kind === "aucune") {
      if (mapLens && app.state.lens === mapLens) app.setLens(prevLens);
      mapLens = null;
      return;
    }
    if (view.kind === "ied") {
      const c = view.cfg, ind = view.indic, o = data.options;
      const v = valeurs(ind, c);
      const desc = ind === "ied"
        ? `IED ${data.annee} d'une configuration de l'analyse de sensibilité : ${cfgLabel(c)}. ${data.pays_complets.length} pays disposent de toutes les séries.`
        : ind === "iee"
          ? `IEE ${data.annee} : ${o.normalisation[c.n]} ; agrégation entre empreinte CO2, azote et phosphore : ${o.agregation[c.a]}. ${Object.keys(v).length} pays disposent des trois séries.`
          : `IRNR ${data.annee} : empreinte matière non renouvelable, ${o.normalisation[c.n]}, repère ${o.seuil_irnr[c.s]}. ${Object.keys(v).length} pays disposent de la série.`;
      mapLens = countryLens(`eh-${ind}-${c.n}${c.a}${c.p}${c.s}${c.b}`, v, {
        name: `${INDICS[ind]} — scénario`, unit: "", format: "float", scale: "linear", domain: [0, 2], ramp: RAMP_IED,
        description: `${desc} ${data.avertissement}`,
      });
    } else {
      const si = data.sous_indicateurs[view.sous];
      const by = {};
      for (const [abbr, p] of Object.entries(data.pays)) {
        const r = p.rapports?.[view.sous]?.[view.seuil];
        if (fin(r)) by[abbr] = r;
      }
      mapLens = countryLens(`eh-rap-${view.sous}-${Object.keys(si.seuils).indexOf(view.seuil)}`, by, {
        name: `${si.court} / repère`, unit: "× le repère", format: "float", scale: "log", domain: [0.25, 4], ramp: RAMP_RAPPORT,
        description: `${si.libelle} (${si.unite}), rapportée au repère ${view.seuil} : ${si.seuils[view.seuil].nature_texte}, `
          + `périmètre : ${si.seuils[view.seuil].perimetre}. Valeur 1 : égale au repère ; au-delà, dépassement. ${data.annee}.`,
      });
    }
    app.setLens(mapLens);
  }

  // --- panneau ---------------------------------------------------------------------------------------------------
  function select(name, label, options, value, fmt = (x) => x) {
    const opts = options.map((o, k) => `<option value="${k}"${k === value ? " selected" : ""}>${esc(fmt(o))}</option>`).join("");
    return `<label class="eh-field"><span>${esc(label)}</span><select data-cfg="${name}">${opts}</select></label>`;
  }

  function tableIed() {
    const sc = scenario(view.cfg);
    const ref = scenario(data.reference_indices);
    const rows = data.pays_complets.map((a) => ({ a, v: sc?.ied[a], r: ref?.ied[a], p: data.pays[a] }))
      .sort((x, y) => (y.v ?? -1) - (x.v ?? -1) || x.a.localeCompare(y.a));
    const body = rows.map((r) => `<tr data-abbr="${r.a}"><th>${esc(r.p.nom)}</th><td>${d2(r.v)}</td><td>${d2(r.r)}</td>`
      + `<td>${d2(r.p.plage?.min)} – ${d2(r.p.plage?.max)}</td><td>${r.p.marques ? r.p.marques : ""}</td></tr>`).join("");
    return `<table class="eh-table"><thead><tr><th>Pays</th><th>Scénario</th><th>Référence</th><th>Enveloppe</th><th title="Termes portant un code Eurostat (provisoire, estimé, définition différente…)">Codes</th></tr></thead><tbody>${body}</tbody></table>
      <p class="eh-note">Enveloppe : minimum et maximum sur les ${data.nb_configurations} configurations de la grille, IBD de 0 à 2 compris ; c'est une enveloppe de scénarios, non un intervalle de confiance. Rangs et moyennes portent sur ces ${data.pays_complets.length} pays seulement.</p>`;
  }

  function tableComposante() {
    const ind = view.indic;
    const v = valeurs(ind, view.cfg), ref = valeurs(ind, data.reference_indices);
    const rows = Object.keys(v).map((a) => ({ a, v: v[a], r: ref[a], p: data.pays[a] })).sort((x, y) => y.v - x.v);
    const body = rows.map((r) => `<tr data-abbr="${r.a}"><th>${esc(r.p?.nom || r.a)}</th><td>${d2(r.v)}</td><td>${d2(r.r)}</td><td>${r.p?.complet ? "oui" : ""}</td></tr>`).join("");
    const note = ind === "iee"
      ? "IEE : empreinte CO2, azote fixé et phosphore minéral, chacun normalisé par son repère puis agrégés. Les pondérations, le repère IRNR et l'IBD n'interviennent pas à cet étage."
      : "IRNR : empreinte matière non renouvelable normalisée par le repère choisi. L'agrégation, les pondérations et l'IBD n'interviennent pas à cet étage.";
    return `<table class="eh-table"><thead><tr><th>Pays</th><th>Scénario</th><th>Référence</th><th title="Pays disposant de toutes les séries de l'IED">IED calculé</th></tr></thead><tbody>${body}</tbody></table>
      <p class="eh-note">${note} Valeur 1 : égale au repère ; en dessous, dépassement.</p>`;
  }

  function tableRapport() {
    const si = data.sous_indicateurs[view.sous];
    const rows = Object.entries(data.pays)
      .map(([a, p]) => ({ a, p, x: p.mesures?.[view.sous], r: p.rapports?.[view.sous]?.[view.seuil] }))
      .filter((r) => fin(r.r)).sort((x, y) => y.r - x.r);
    const body = rows.map((r) => `<tr data-abbr="${r.a}"><th>${esc(r.p.nom)}</th><td>${d2(r.x)}</td><td>${d2(r.r)}</td></tr>`).join("");
    const T = si.seuils[view.seuil];
    return `<table class="eh-table"><thead><tr><th>Pays</th><th>${esc(si.unite)}</th><th>× repère</th></tr></thead><tbody>${body}</tbody></table>
      <p class="eh-note">Repère ${esc(view.seuil)} : ${esc(T.nature_texte)} ; périmètre : ${esc(T.perimetre)} ; source : ${esc(data.sources[T.source] || T.source)}.${si.note ? " " + esc(si.note) : ""}</p>`;
  }

  function render() {
    if (!root) return;
    if (!data) {
      const manq = (data.decoupages_manquants || []).map((m) => `<p class="eh-note">Pas encore sur la carte : <b>${esc(m.nom)}</b> — ${esc(m.raison)}.</p>`).join("");
    root.innerHTML = `<div class="eh-head"><h2>Économie Homéostatique</h2></div><p class="eh-pad">Chargement des données…</p>`;
      return;
    }
    const o = data.options;
    const c = view.cfg;
    const si = data.sous_indicateurs[view.sous];
    const vues = [["ied", "Indices par scénario"], ["rapport", "Rapport au repère"], ["aucune", "Aucune"]]
      .map(([k, l]) => `<button type="button" data-vue="${k}" aria-pressed="${view.kind === k}">${l}</button>`).join("");
    let controls = "";
    if (view.kind === "ied") {
      const dep = DEPEND[view.indic];
      const off = (k, html) => (dep.includes(k) ? html : html.replace("<select", "<select disabled"));
      const indics = Object.entries(INDICS).map(([k, l]) => `<button type="button" data-indic="${k}" aria-pressed="${view.indic === k}">${l}</button>`).join("");
      controls = `<div class="eh-vues eh-indics">${indics}</div><div class="eh-grid">
        ${off("n", select("n", "Normalisation", o.normalisation, c.n))}
        ${off("a", select("a", view.indic === "iee" ? "Agrégation des sous-indicateurs" : "Agrégation (deux étages)", o.agregation, c.a))}
        ${off("p", select("p", "Pondérations (IBD, IEE, IRNR)", o.poids, c.p))}
        ${off("s", select("s", "Repère IRNR", o.seuil_irnr, c.s))}
        ${off("b", select("b", "IBD supposé, commun à tous les pays", o.ibd, c.b, d1))}
      </div>
      <p class="eh-cfg">${c.n === data.reference_indices.n && c.a === data.reference_indices.a && c.p === data.reference_indices.p && c.s === data.reference_indices.s && c.b === data.reference_indices.b ? "Configuration de référence." : `<button type="button" data-reset>Revenir à la configuration de référence</button>`}</p>
      ${view.indic === "ied" ? tableIed() : tableComposante()}`;
    } else if (view.kind === "rapport") {
      const sous = data.sous_indicateurs_ordre.map((k, i) => [k, i]);
      controls = `<div class="eh-grid">
        <label class="eh-field"><span>Sous-indicateur</span><select data-sous>${sous.map(([k]) => `<option value="${k}"${k === view.sous ? " selected" : ""}>${esc(data.sous_indicateurs[k].composante)} — ${esc(data.sous_indicateurs[k].court)}</option>`).join("")}</select></label>
        <label class="eh-field"><span>Repère</span><select data-seuil>${Object.keys(si.seuils).map((k) => `<option${k === view.seuil ? " selected" : ""}>${esc(k)}</option>`).join("")}</select></label>
      </div>${tableRapport()}`;
    }
    const decs = data.decoupages.map((dd) => `<label class="eh-dec"><input type="checkbox" data-dec="${dd.id}"${on[dd.id] ? " checked" : ""}>
        <i style="border-color:${dd.couleur};border-style:${dd.tirets.length ? "dashed" : "solid"}"></i>
        <span><b>${esc(dd.nom)}</b> <span class="muted">${dd.features.length} entités</span><br><span class="muted">${esc(dd.description)}</span><br><span class="muted">Source : <a href="${esc(dd.page)}" target="_blank" rel="noopener">${esc(dd.source)}</a>, ${esc(dd.licence)} ; récupéré le ${esc(dd.recupere.slice(0, 10))}</span></span></label>`).join("");
    const manq = (data.decoupages_manquants || []).map((m) => `<p class="eh-note">Pas encore sur la carte : <b>${esc(m.nom)}</b> — ${esc(m.raison)}.</p>`).join("");
    root.innerHTML = `
      <div class="eh-head"><div><h2>Économie Homéostatique</h2><div class="muted">Calibration empirique — lot ${esc(data.lot)}, année ${data.annee}</div></div>
        <button type="button" class="eh-close" data-close aria-label="Fermer">×</button></div>
      <p class="eh-warn">${esc(data.avertissement)}</p>
      <section class="eh-sec"><h3>Colorer la carte</h3><div class="eh-vues">${vues}</div>${controls}</section>
      <section class="eh-sec"><h3>Découpages transfrontaliers</h3>
        <p class="eh-note">${esc(data.texte_decoupages)}</p>${decs}${manq}</section>
      <section class="eh-sec"><h3>Sources et méthode</h3>
        <p class="eh-note">${esc(data.texte_methode)}</p>
        <p class="eh-note"><a href="${esc(data.depot)}" target="_blank" rel="noopener">Dépôt et provenance de chaque fichier</a> · <a href="${esc(data.rapport)}" target="_blank" rel="noopener">Rapport d'étape</a></p></section>`;
  }

  function wire(el) {
    el.addEventListener("change", (e) => {
      const t = e.target;
      if (t.dataset.cfg) { view.cfg = { ...view.cfg, [t.dataset.cfg]: +t.value }; }
      else if (t.hasAttribute("data-sous")) { view.sous = t.value; view.seuil = Object.keys(data.sous_indicateurs[view.sous].seuils)[0]; }
      else if (t.hasAttribute("data-seuil")) { view.seuil = t.value; }
      else if (t.dataset.dec) {
        if (!app.ui.setMapToggle?.(`eh-${t.dataset.dec}`, t.checked)) { on[t.dataset.dec] = t.checked; app.requestDraw(); }
        return;
      }
      else return;
      colour();
      render();
      app.hash.update?.();
    });
    el.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.hasAttribute("data-close")) return app.setMode(null);
      if (b.dataset.vue) view.kind = b.dataset.vue;
      else if (b.dataset.indic) view.indic = b.dataset.indic;
      else if (b.hasAttribute("data-reset")) view.cfg = { ...data.reference_indices };
      else return;
      colour();
      render();
      app.hash.update?.();
    });
    el.addEventListener("pointerover", (e) => {
      const tr = e.target.closest("tr[data-abbr]");
      const k = tr ? app.w.raw.states.findIndex((st) => st.abbr === tr.dataset.abbr) : -1;
      app.setHighlight(k >= 0 ? { states: new Set([k]) } : null);
    });
    el.addEventListener("pointerleave", () => app.setHighlight(null));
  }

  app.registerMode("eh", {
    enter() {
      loadCss();
      prevLens = app.state.lens || null;
      const dock = app.ui.dock("left", { width: DOCK_W, label: "Économie Homéostatique" });
      dock.innerHTML = "";
      root = document.createElement("div");
      root.className = "eh-root";
      dock.appendChild(root);
      wire(root);
      render();
      ready.then(() => { if (app.mode === "eh") { render(); colour(); } });
    },
    exit() {
      if (mapLens && app.state.lens === mapLens) app.setLens(prevLens);
      mapLens = null;
      app.setHighlight(null);
      app.ui.undock("left");
      root = null;
    },
  });

  // Lien : #eh=<ied|iee|irnr>.<n><a><p><s><b> | rapport.<sous>.<k> | aucune
  app.hash.register("eh", {
    get() {
      if (app.mode !== "eh") return null;
      if (view.kind === "ied" && view.cfg) { const c = view.cfg; return `${view.indic}.${c.n}${c.a}${c.p}${c.s}${c.b}`; }
      if (view.kind === "rapport" && data) return `rapport.${view.sous}.${Object.keys(data.sous_indicateurs[view.sous].seuils).indexOf(view.seuil)}`;
      return view.kind;
    },
    set(v) {
      if (v == null) { if (app.mode === "eh") app.setMode(null); return; }
      ready.then((d) => {
        if (!d) return;
        const [kind, a, b] = String(v).split(".");
        if (INDICS[kind] && /^\d{5}$/.test(a || "")) {
          const [n, ag, p, s, ib] = a.split("").map(Number);
          const cfg = { n, a: ag, p, s, b: ib };
          if (scenario(cfg)) view.cfg = cfg;
          view.kind = "ied";
          view.indic = kind;
        } else if (kind === "rapport" && d.sous_indicateurs[a]) {
          view.kind = "rapport";
          view.sous = a;
          const ks = Object.keys(d.sous_indicateurs[a].seuils);
          view.seuil = ks[+b] ?? ks[0];
        } else if (kind === "aucune") view.kind = "aucune";
        if (app.mode !== "eh") app.setMode("eh");
        else { render(); colour(); }
      });
    },
  });

  app.eh = { get data() { return data; }, view, on };
}
