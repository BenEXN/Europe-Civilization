// Économie Homéostatique (EH) : la calibration empirique de l'EH portée sur la carte.
//
//   bouton « EH » dans la barre du haut, mode « eh » (Échap pour sortir), lien #eh=<vue>
//   découpages transfrontaliers : quatre couches statiques (districts hydrographiques, régions marines, zones CIEM,
//     régions biogéographiques), chacune avec son interrupteur dans le menu « Map » et dans le panneau
//   la carte colorée par pays : IED d'une configuration de la grille de sensibilité, ou rapport d'un
//     sous-indicateur à son repère normatif
//   l'exercice monétaire, à activer : écodotations e = Φ(IED) · e_base par canal (État, citoyens, entreprises,
//     dotation globale), à l'échelle de l'IED national ou de zone, en euros constants 2017, en part du PIB ou en
//     rapport au flux de référence (u)
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
const RAMP_MONNAIE = ["#f4ecd8", "#e8d4a2", "#d6b46e", "#bb8d42", "#8f652a", "#5c4119"];

// Exercice monétaire. Φ₀ est la fonction candidate du WP ; les autres formes vérifient ses propriétés minimales
// (continue, croissante, Φ(0) = 0, Φ(1) = 1) et servent à l'illustration.
const PHI = [
  { nom: "Φ₀(z) = z (WP)", f: (z) => z },
  { nom: "min(z, 1) : expansion bornée au régime neutre", f: (z) => Math.min(z, 1) },
  { nom: "z² : contraction renforcée sous 1", f: (z) => z * z },
  { nom: "√z : contraction atténuée sous 1", f: (z) => Math.sqrt(z) },
];
const CANAUX = { dg: "DG", eta: "État", cit: "Citoyens", ent: "Entreprises" };
const CANAUX_LONG = { dg: "Dotation globale (DG)", eta: "Canal État (DTETA)", cit: "Canal citoyens (DTCIT)", ent: "Canal entreprises (DTENT)" };
const ECHELLES = { u1: "u = 1 (flux de référence)", nat: "IED national", zone: "IED de zone" };
const AFFICHAGES = { hab: "€ constants 2017 par habitant", pib: "Part du PIB", u: "Rapport au flux de référence (u)" };
const md = (v) => (fin(v) ? Math.round(v / 1e9).toLocaleString("fr-FR") : "–");
const eur = (v) => (fin(v) ? Math.round(v).toLocaleString("fr-FR") : "–");
const pc = (v) => (fin(v) ? (100 * v).toFixed(0) + " %" : "–");

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
  const view = { kind: "ied", indic: "ied", cfg: null, sous: null, seuil: null,
    mon: { canal: "dg", echelle: "nat", aff: "pib", phi: 0, assiette: "reference" } };
  let exo = false; // exercice monétaire activé
  let echec = false; // chargement de web/data/eh.json impossible
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
  const ready = app.loadData("eh").catch((err) => {
    console.warn("eh: chargement de web/data/eh.json impossible", err);
    return null;
  }).then((d) => {
    if (!d) {
      console.info("eh: web/data/eh.json absent ; l'extension reste inactive");
      echec = true;
      render();
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
    addLensGroup();
    if (app.mode === "eh") { render(); colour(); }
    return d;
  });

  // --- groupe « Économie Homéostatique » du sélecteur de lentilles : configuration de référence ----------------------
  function addLensGroup() {
    if (typeof app.addLenses !== "function") return;
    const r = data.reference_indices, o = data.options;
    const refTxt = `Configuration de référence : ${cfgLabel(r)}.`;
    const ind = (id, nom, icon, indic, texte) => countryLens(`eh-ref-${id}`, valeurs(indic, r), {
      group: "eh", name: nom, icon, unit: "", format: "float", scale: "linear", domain: [0, 2], ramp: RAMP_IED,
      description: `${texte} ${data.annee}. ${refTxt} Valeur 1 : niveau de référence. Le bouton EH permet de changer de scénario. ${data.avertissement}`,
    });
    const lenses = [
      ind("ied", "IED", "g-life", "ied", `IED : moyenne des composantes IBD, IEE et IRNR, pour les ${data.pays_complets.length} pays qui disposent de toutes les séries.`),
      ind("iee", "IEE", "l-warming", "iee", "IEE : empreinte CO2, azote fixé et phosphore minéral, normalisés par leurs repères puis agrégés."),
      ind("irnr", "IRNR", "l-developed", "irnr", `IRNR : empreinte matière totale (RMC, biomasse comprise) rapportée au repère ${o.seuil_irnr[r.s]}, même périmètre que le repère ; elle mesure la pression matérielle totale, non le seul objet IRNR du WP.`),
      { id: "eh-ref-ibd", group: "eh", name: "IBD non mesuré", icon: "l-forest", disabled: true,
        description: "IBD non mesuré : aucune série nationale ne renseigne l'état de la biodiversité. Il entre dans les scénarios comme une valeur supposée (de 0 à 2), sans être cartographié." },
    ];
    const COURTS = { iee_co2_empreinte: "CO2 / repère", irnr_rmc_abiotique: "Matière NR (variante)", irnr_rmc_totale: "Matière totale (IRNR)",
      iee_azote: "Azote / repère", iee_phosphore: "Phosphore" };
    const icones = { iee_co2_empreinte: "l-warming", irnr_rmc_abiotique: "l-developed", irnr_rmc_totale: "l-developed",
      iee_azote: "l-farmland", iee_phosphore: "l-farmland" };
    for (const k of data.sous_indicateurs_ordre) {
      const si = data.sous_indicateurs[k];
      const seuil = Object.keys(si.seuils)[0];
      const by = {};
      for (const [a, p] of Object.entries(data.pays)) {
        const v = p.rapports?.[k]?.[seuil];
        if (fin(v)) by[a] = v;
      }
      lenses.push(countryLens(`eh-ref-${k}`, by, {
        group: "eh", name: COURTS[k] || si.court, icon: icones[k] || "layers", unit: "× le repère", format: "float",
        scale: "log", domain: [0.25, 4], ramp: RAMP_RAPPORT,
        description: `Rapport au repère. ${si.libelle} (${si.unite}), rapportée au repère ${seuil} : ${si.seuils[seuil].nature_texte}. `
          + `Valeur 1 : égale au repère ; au-delà, dépassement. ${data.annee}.`,
      }));
    }
    if (data.monnaie) {
      const m = data.monnaie;
      const mon = (id, nom, cfgMon, texte) => {
        const v = monnaieValeurs({ ...view.mon, ...cfgMon }, r);
        const by = {};
        for (const [a, x] of Object.entries(v)) by[a] = x.pib;
        return countryLens(`eh-mon-${id}`, by, {
          group: "eh", name: nom, icon: "layers", unit: "", format: "pct", scale: "linear", domain: [0, 4], ramp: RAMP_MONNAIE,
          description: `Exercice monétaire, part du PIB ${m.annee}. ${texte} ${m.texte}`,
        });
      };
      lenses.push(
        mon("eta-u1", "Canal État / PIB (u = 1)", { canal: "eta", echelle: "u1", aff: "pib" },
          `Canal État au flux de référence : β_pub × c rapporté au PIB, pour tous les pays. ${m.texte_harmonisation}`),
        mon("ent-u1", "Canal entreprises / PIB (u = 1)", { canal: "ent", echelle: "u1", aff: "pib", assiette: "reference" },
          `Canal entreprises au flux de référence : Σ𝒴 (${m.assiettes.reference.libelle}, lissé sur ${m.lissage_y} ans) rapporté au PIB.`),
        mon("dg-nat", "DG / PIB (u = IED)", { canal: "dg", echelle: "nat", aff: "pib", phi: 0, assiette: "reference" },
          `Dotation globale à u = Φ₀(IED national), configuration de référence : ${cfgLabel(r)}.`),
      );
    }
    app.addLenses({ id: "eh", name: "Économie Homéostatique", icon: "g-life" }, lenses);
  }

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
  const cfgKey = (c) => `${c.n}${c.a}${c.p}${c.s}${c.b}`;
  // Écodotations par pays : {abbr: {z, u, tot (€2017), hab (€2017/hab), pib (part du PIB)}}.
  function monnaieValeurs(mon, cfg) {
    const m = data.monnaie, out = {};
    if (!m) return out;
    const phi = PHI[mon.phi]?.f || PHI[0].f;
    const nat = mon.echelle === "nat" ? scenario(cfg)?.ied || {} : null;
    const zz = mon.echelle === "zone" ? m.zone?.ied[cfgKey(cfg)] : null;
    for (const [a, p] of Object.entries(m.pays)) {
      let z = 1;
      if (mon.echelle === "nat") z = nat[a];
      else if (mon.echelle === "zone") z = m.zone?.pays.includes(a) ? zz : null;
      if (!fin(z)) continue;
      const u = mon.echelle === "u1" ? 1 : phi(z);
      const pop = p.population_milliers * 1e3, publique = m.beta_pub_eur2017 * pop;
      const y = fin(p.y_mio_eur2017?.[mon.assiette]) ? p.y_mio_eur2017[mon.assiette] * 1e6 : null;
      const base = { eta: publique, cit: publique, ent: y, dg: y == null ? null : 2 * publique + y }[mon.canal];
      if (!fin(base)) continue;
      const tot = u * base;
      out[a] = { z, u, tot, hab: tot / pop, pib: tot / (p.pib_mio_eur2017 * 1e6) };
    }
    return out;
  }
  function monLabel(mon, cfg) {
    const m = data.monnaie;
    const parts = [CANAUX_LONG[mon.canal], ECHELLES[mon.echelle]];
    if (mon.echelle !== "u1") parts.push(`Φ : ${PHI[mon.phi].nom}`, `configuration : ${cfgLabel(cfg)}`);
    if (mon.canal === "ent" || mon.canal === "dg") parts.push(`assiette 𝒴 : ${m.assiettes[mon.assiette].libelle}`);
    return parts.join(" ; ");
  }
  function countryLens(id, byAbbr, spec) {
    const owner = app.w.raw.owner, states = app.w.raw.states, n = owner.length;
    const values = new Array(n).fill(null);
    for (let i = 0; i < n; i++) {
      if (owner[i] < 0) continue;
      const v = byAbbr[states[owner[i]].abbr];
      if (fin(v)) values[i] = v;
    }
    return { id, group: "eh", icon: "layers", higher_is: "neutral", source: "eh",
      source_line: `Eurostat ; repères O'Neill et al. 2018, Bringezu 2015 · lot ${data.lot}`, values, ...spec };
  }
  function colour() {
    if (!data || app.mode !== "eh") return;
    if (view.kind === "aucune") {
      if (mapLens && app.state.lens === mapLens) app.setLens(prevLens);
      mapLens = null;
      return;
    }
    if (view.kind === "monnaie") {
      const mon = view.mon, v = monnaieValeurs(mon, view.cfg), by = {};
      for (const [a, x] of Object.entries(v)) by[a] = mon.aff === "u" ? x.u : mon.aff === "hab" ? x.hab : x.pib;
      const max = Math.max(0, ...Object.values(by));
      const spec = mon.aff === "u"
        ? { unit: "", format: "float", domain: [0, 2], ramp: RAMP_IED }
        : mon.aff === "hab"
          ? { unit: "€2017/hab", format: "float", domain: [0, Math.max(1, max)], ramp: RAMP_MONNAIE }
          : { unit: "", format: "pct", domain: [0, Math.max(0.01, max)], ramp: RAMP_MONNAIE };
      mapLens = countryLens(`eh-mon-${mon.canal}-${mon.echelle}-${mon.aff}-${mon.phi}-${mon.assiette}-${cfgKey(view.cfg)}`, by, {
        name: `${CANAUX[mon.canal]} — ${AFFICHAGES[mon.aff]}`, scale: "linear", ...spec,
        description: `Exercice monétaire ${data.monnaie.annee} : ${monLabel(mon, view.cfg)}. ${data.monnaie.texte}`,
      });
      app.setLens(mapLens);
      return;
    }
    if (view.kind === "ied") {
      const c = view.cfg, ind = view.indic, o = data.options;
      const v = valeurs(ind, c);
      const desc = ind === "ied"
        ? `IED ${data.annee} d'une configuration de l'analyse de sensibilité : ${cfgLabel(c)}. ${data.pays_complets.length} pays disposent de toutes les séries.`
        : ind === "iee"
          ? `IEE ${data.annee} : ${o.normalisation[c.n]} ; agrégation entre empreinte CO2, azote et phosphore : ${o.agregation[c.a]}. ${Object.keys(v).length} pays disposent des trois séries.`
          : `IRNR ${data.annee} : empreinte matière totale (RMC, biomasse comprise), ${o.normalisation[c.n]}, repère ${o.seuil_irnr[c.s]}. ${Object.keys(v).length} pays disposent de la série.`;
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
      : "IRNR : empreinte matière totale (RMC, biomasse comprise) normalisée par le repère choisi, de même périmètre. Elle mesure la pression matérielle totale et non le seul objet IRNR du WP : la biomasse, renouvelable, recoupe l'IEE. L'agrégation, les pondérations et l'IBD n'interviennent pas à cet étage.";
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

  // Codes Eurostat d'une dotation : ceux des comptes (population, PIB, 𝒴) et, quand u dépend de l'IED, ceux des termes
  // de l'IED national du pays ou de tous les pays de la zone.
  function codesCellule(a, mon) {
    const m = data.monnaie, p = m.pays[a];
    const comptes = p.codes || [];
    const bio = mon.echelle === "nat" ? p.codes_ied || [] : mon.echelle === "zone" ? m.zone?.codes_ied || [] : [];
    if (!comptes.length && !bio.length) return "";
    const titre = [comptes.length ? `Comptes : ${comptes.join(" ; ")}` : "", bio.length ? `IED : ${bio.join(" ; ")}` : ""]
      .filter(Boolean).join(" — ");
    // Lettres des codes (p, e, b, d…), comme dans le tableau de l'IED ; le détail est au survol.
    const lettres = [...new Set([...comptes, ...bio].map((c) => c.split(" : ").pop().trim()).join("").replace(/\s/g, ""))]
      .sort().join(" ");
    return `<span title="${esc(titre)}">${esc(lettres)}</span>`;
  }

  function tableMonnaie() {
    const m = data.monnaie, mon = view.mon;
    const v = monnaieValeurs(mon, view.cfg);
    const rows = Object.entries(v).map(([a, x]) => ({ a, x, p: data.pays[a] || { nom: a } }))
      .sort((r1, r2) => r2.x.pib - r1.x.pib);
    const body = rows.map((r) => `<tr data-abbr="${r.a}"><th>${esc(r.p.nom)}</th><td>${d2(r.x.u)}</td><td>${eur(r.x.hab)}</td>`
      + `<td>${md(r.x.tot)}</td><td>${pc(r.x.pib)}</td><td>${codesCellule(r.a, mon)}</td></tr>`).join("");
    const tot = rows.reduce((s, r) => s + r.x.tot, 0);
    const pib = rows.reduce((s, r) => s + m.pays[r.a].pib_mio_eur2017 * 1e6, 0);
    const pop = rows.reduce((s, r) => s + m.pays[r.a].population_milliers * 1e3, 0);
    const foot = rows.length > 1 ? `<tr><th>Ensemble des ${rows.length} pays</th><td></td><td>${eur(tot / pop)}</td><td>${md(tot)}</td><td>${pc(tot / pib)}</td><td></td></tr>` : "";
    const zone = mon.echelle === "zone" && m.zone
      ? `<p class="eh-note">IED de zone : ${d2(m.zone.ied[cfgKey(view.cfg)])}, pour la zone formée des ${m.zone.pays.length} pays qui disposent de toutes les séries (${m.zone.pays.join(", ")}) ; ${esc(m.zone.methode)}. Proxy : la zone est un sous-ensemble de disponibilité, non l'UE-27.</p>` : "";
    const nat = mon.echelle === "nat" ? `<p class="eh-note">IED national : un u par pays, pour les ${data.pays_complets.length} pays qui disposent de toutes les séries.</p>` : "";
    const u1 = mon.echelle === "u1" ? `<p class="eh-note">u = 1 : régime neutre, création primaire égale au flux de référence e_base ; elle ne dépend que de β_pub, de la population et de 𝒴.</p>` : "";
    return `<table class="eh-table"><thead><tr><th>Pays</th><th>u</th><th>€2017/hab</th><th>Md€2017</th><th>% PIB</th><th title="Termes portant un code Eurostat : comptes nationaux et, quand u dépend de l'IED, termes de l'IED">Codes</th></tr></thead><tbody>${body}${foot}</tbody></table>
      ${u1}${nat}${zone}
      <p class="eh-note">β_pub = ${eur(m.beta_pub_eur2017)} € constants 2017 par citoyen. 𝒴 : ${esc(m.assiettes[mon.assiette].libelle)}, lissé sur ${m.lissage_y} ans (comptes nationaux par secteur). PIB et 𝒴 convertis en euros constants 2017 par le déflateur de β_pub. Année ${m.annee}.</p>
      <p class="eh-note">${esc(m.texte_harmonisation)}</p>
      <p class="eh-note">${esc(m.texte_echanges)}</p>
      <p class="eh-note">${esc(m.texte_phi)}</p>`;
  }

  function render() {
    if (!root) return;
    if (!data) {
      const msg = echec ? "Données indisponibles : web/data/eh.json n'a pas pu être chargé." : "Chargement des données…";
      root.innerHTML = `<div class="eh-head"><h2>Économie Homéostatique</h2></div><p class="eh-pad">${msg}</p>`;
      return;
    }
    const o = data.options;
    const c = view.cfg;
    const si = data.sous_indicateurs[view.sous];
    const vues = [["ied", "Indices par scénario"], ["rapport", "Rapport au repère"], ...(exo && data.monnaie ? [["monnaie", "Écodotations"]] : []), ["aucune", "Aucune"]]
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
    } else if (view.kind === "monnaie" && data.monnaie) {
      const mon = view.mon, m = data.monnaie;
      const desact = (cond, html) => (cond ? html.replace("<select", "<select disabled") : html);
      const sel = (name, label, entries, value) => `<label class="eh-field"><span>${esc(label)}</span><select data-mon="${name}">${entries
        .map(([k, l]) => `<option value="${k}"${String(k) === String(value) ? " selected" : ""}>${esc(l)}</option>`).join("")}</select></label>`;
      const canaux = Object.entries(CANAUX).map(([k, l]) => `<button type="button" data-canal="${k}" aria-pressed="${mon.canal === k}">${l}</button>`).join("");
      const sansIed = mon.echelle === "u1";
      controls = `<div class="eh-vues eh-indics">${canaux}</div><div class="eh-grid">
        ${sel("echelle", "Échelle de u", Object.entries(ECHELLES), mon.echelle)}
        ${sel("aff", "Affichage", Object.entries(AFFICHAGES), mon.aff)}
        ${desact(sansIed, sel("phi", "Φ", PHI.map((f, k) => [k, f.nom]), mon.phi))}
        ${desact(mon.canal === "eta" || mon.canal === "cit" || mon.aff === "u", sel("assiette", "Assiette 𝒴", Object.entries(m.assiettes).map(([k, a]) => [k, a.libelle]), mon.assiette))}
        ${desact(sansIed, select("n", "Normalisation", o.normalisation, c.n))}
        ${desact(sansIed, select("a", "Agrégation (deux étages)", o.agregation, c.a))}
        ${desact(sansIed, select("p", "Pondérations (IBD, IEE, IRNR)", o.poids, c.p))}
        ${desact(sansIed, select("s", "Repère IRNR", o.seuil_irnr, c.s))}
        ${desact(sansIed, select("b", "IBD supposé, commun à tous les pays", o.ibd, c.b, d1))}
      </div>
      <p class="eh-cfg">${cfgKey(c) === cfgKey(data.reference_indices) ? "Configuration de référence de l'IED." : `<button type="button" data-reset>Revenir à la configuration de référence</button>`}</p>
      ${tableMonnaie()}`;
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
      ${data.monnaie ? `<section class="eh-sec"><h3>Exercice monétaire</h3>
        <label class="eh-dec"><input type="checkbox" data-exo${exo ? " checked" : ""}><i style="border:none"></i><span><b>Afficher les écodotations</b></span></label>
        <p class="eh-note">${esc(data.monnaie.texte)}</p></section>` : ""}
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
      else if (t.dataset.mon) { view.mon = { ...view.mon, [t.dataset.mon]: t.dataset.mon === "phi" ? +t.value : t.value }; }
      else if (t.hasAttribute("data-exo")) {
        exo = t.checked;
        view.kind = exo ? "monnaie" : view.kind === "monnaie" ? "ied" : view.kind;
      }
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
      else if (b.dataset.canal) view.mon = { ...view.mon, canal: b.dataset.canal };
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

  // Lien : #eh=<ied|iee|irnr>.<n><a><p><s><b> | rapport.<sous>.<k> | monnaie.<canal>.<échelle>.<affichage>.<Φ>.<assiette>.<napsb> | aucune
  app.hash.register("eh", {
    get() {
      if (app.mode !== "eh") return null;
      if (view.kind === "ied" && view.cfg) { const c = view.cfg; return `${view.indic}.${c.n}${c.a}${c.p}${c.s}${c.b}`; }
      if (view.kind === "monnaie" && view.cfg) {
        const mn = view.mon;
        return `monnaie.${mn.canal}.${mn.echelle}.${mn.aff}.${mn.phi}.${mn.assiette}.${cfgKey(view.cfg)}`;
      }
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
        } else if (kind === "monnaie" && d.monnaie) {
          const [, canal, echelle, aff, phi, assiette, c5] = String(v).split(".");
          view.mon = {
            canal: CANAUX[canal] ? canal : "dg", echelle: ECHELLES[echelle] ? echelle : "nat",
            aff: AFFICHAGES[aff] ? aff : "pib", phi: PHI[+phi] ? +phi : 0,
            assiette: d.monnaie.assiettes[assiette] ? assiette : "reference",
          };
          if (/^\d{5}$/.test(c5 || "")) {
            const [n, ag, p, s, ib] = c5.split("").map(Number);
            if (scenario({ n, a: ag, p, s, b: ib })) view.cfg = { n, a: ag, p, s, b: ib };
          }
          exo = true;
          view.kind = "monnaie";
        } else if (kind === "aucune") view.kind = "aucune";
        if (app.mode !== "eh") app.setMode("eh");
        else { render(); colour(); }
      });
    },
  });

  app.eh = { get data() { return data; }, view, on };
}
