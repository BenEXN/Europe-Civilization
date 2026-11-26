// The daily challenge, played against the API (server/api.py): the server draws the day's five places, sends one
// name at a time, times each answer (30 s) and only then says where the place was. Players may sign up with a
// nickname and, if they like, their home town, which puts them in the rankings of its city (urban area), country
// and region.
//
//   mode "challenge" (Esc or the close button leaves), top-bar button, #defi in the URL, "mapclick" taken while the
//   mode is on, a world overlay for the guess, the answer pin and the line between them.
//   Stored on the device: the player's nickname and token ("europeciv-joueur"), an unranked game in progress.
import { icon } from "../../ui/icon.js";
import { esc, int } from "../../format.js";
import { drawPin } from "../../render/overlays.js";
import { copyText } from "../../app/share.js";

const PLAYER_KEY = "europeciv-joueur";
const GAME_KEY = "europeciv-defi-partie";
const API = new URL("api/", document.baseURI).href;

/** Points for a guess `km` away (the server's rule, for display). */
export const points = (km) => (km <= 5 ? 1000 : Math.round(1000 * Math.exp(-(km - 5) / 250)));  // = server/api.py

const store = {
  get(k) { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch { return null; } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
};
// Search key for place names: lower case, accents off, the Latin letters that do not decompose spelled out (Łódź →
// lodz, Tromsø → tromso, Straße → strasse); Greek and Cyrillic letters are kept as they are.
const FOLD = { ł: "l", ø: "o", æ: "ae", œ: "oe", ß: "ss", đ: "d", ð: "d", þ: "th", ħ: "h", ı: "i" };
const fold = (s) => String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
  .replace(/[łøæœßđðþħı]/g, (c) => FOLD[c]).replace(/[^\p{L}\p{N}]+/gu, " ").trim();
const longDate = (day) => new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
  .format(new Date(day + "T12:00:00Z"));
const monthName = (m) => new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" })
  .format(new Date(m + "-15T12:00:00Z"));
const kmText = (km) => (km == null ? "out of time" : km < 10 ? `${km.toFixed(1)} km` : `${int(Math.round(km))} km`);
const ordinal = (n) => {
  const t = n % 100, u = n % 10;
  return `${n}${t >= 11 && t <= 13 ? "th" : u === 1 ? "st" : u === 2 ? "nd" : u === 3 ? "rd" : "th"}`;
};

export function install(app) {
  let info = null; // GET /api/defi
  let game = null; // the server's state of the current game
  let view = "intro"; // intro | game | board
  const board = { type: "joueurs", periode: "jour", data: null, loading: false };
  let el = null;
  let prevLens = null;
  let session = 0;
  let busy = false;
  let error = "";
  let timer = 0;
  let deadline = 0;
  let pick = null; // the home town chosen in the sign-up form {code, name, dep}
  let communes = null;

  const player = () => store.get(PLAYER_KEY);

  async function call(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    const p = player();
    if (p?.token) headers.Authorization = `Bearer ${p.token}`;
    let res;
    try {
      res = await fetch(API + path, { method, headers, body: body ? JSON.stringify(body) : undefined, cache: "no-store" });
    } catch {
      throw new Error("The challenge server is not responding. Check your connection and try again.");
    }
    let data = null;
    try { data = await res.json(); } catch { /* not JSON */ }
    if (res.status === 401 && p) store.set(PLAYER_KEY, null); // a token the server forgot: sign up again
    if (!res.ok) throw Object.assign(new Error(data?.error || `Error ${res.status}`), { status: res.status });
    return data;
  }

  // --- the panel ------------------------------------------------------------------------------------------------
  function hud() {
    if (el) return el;
    el = document.createElement("section");
    el.className = "panel defi";
    el.setAttribute("role", "region");
    el.setAttribute("aria-label", "Daily challenge");
    el.addEventListener("click", onClick);
    el.addEventListener("input", (e) => { if (e.target.id === "df-commune") suggest(e.target.value); });
    el.addEventListener("submit", (e) => { e.preventDefault(); signUp(); });
    document.body.appendChild(el);
    return el;
  }

  function onClick(e) {
    const b = e.target.closest("[data-act]");
    if (!b || busy) return;
    const act = b.dataset.act;
    if (act === "close") app.setMode(null);
    else if (act === "play") play();
    else if (act === "anon") play({ unranked: true });
    else if (act === "next") next();
    else if (act === "share") share(b);
    else if (act === "board") openBoard();
    else if (act === "back") { view = game ? "game" : "intro"; render(); }
    else if (act === "tab") { board.type = b.dataset.v; loadBoard(); }
    else if (act === "period") { board.periode = b.dataset.v; loadBoard(); }
    else if (act === "pick") { keepPseudo(() => { pick = communes?.byCode.get(b.dataset.code) || null; }); }
    else if (act === "unpick") { keepPseudo(() => { pick = null; }); el.querySelector("#df-commune")?.focus(); }
    else if (act === "logout") { store.set(PLAYER_KEY, null); info = info && { ...info, me: null }; render(); }
    else if (act === "go") flyToTeam(b.dataset.kind, b.dataset.key);
    else if (act === "retry") { error = ""; render(); start(); }
  }

  // Re-rendering the sign-up form would lose what was typed in the nickname field.
  function keepPseudo(fn) {
    const typed = el.querySelector("#df-pseudo")?.value || "";
    fn();
    render();
    const input = el.querySelector("#df-pseudo");
    if (input) input.value = typed;
  }

  const head = () => `<div class="df-head">
      <span class="df-title">Daily challenge${info ? ` #${info.n}` : ""}</span>
      ${game && view === "game" ? `<span class="df-score"><b>${int(game.total)}</b> pts</span>` : ""}
      <button type="button" class="icon-btn df-close" data-act="close" aria-label="Leave the challenge (Esc)">${icon("close", null, { size: 12 })}</button>
    </div>`;

  function render() {
    const root = hud();
    root.hidden = false;
    clearInterval(timer);
    setSearch(true);
    if (error) {
      root.innerHTML = `${head()}<p class="df-error">${esc(error)}</p>
        <div class="df-actions"><button type="button" class="btn df-primary" data-act="retry">Try again</button></div>`;
      return;
    }
    if (!info) {
      root.innerHTML = `${head()}<p class="df-help">Loading the challenge…</p>`;
      return;
    }
    if (view === "board") return renderBoard(root);
    if (view === "intro" || !game) return renderIntro(root);
    renderGame(root);
  }

  function renderIntro(root) {
    const me = info.me;
    const rules = `<p class="df-rules">Five places, thirty seconds each. Click where you think each one is: up to
      1,000 points a place within 5 km, fewer the further off you are (about 680 at 100 km, 310 at 300 km).</p>`;
    if (me) {
      const where = me.ville || me.departement;
      root.innerHTML = `${head()}${rules}
        <div class="df-me"><span>Playing as <b>${esc(me.pseudo)}</b>${where ? ` (${esc(where)})` : ""}.</span>
          ${me.streak > 1 ? `<span class="df-streak">${me.streak} days in a row</span>` : ""}</div>
        <div class="df-actions">
          <button type="button" class="btn df-primary" data-act="play">${me.played_today ? "See today's game" : "Play"}</button>
          <button type="button" class="btn" data-act="board">Rankings</button>
        </div>
        <p class="df-foot">One ranked game a day.
          <button type="button" class="linkish" data-act="logout">Switch player</button></p>`;
      root.querySelector(".df-primary")?.focus({ preventScroll: true });
      return;
    }
    root.innerHTML = `${head()}${rules}
      <form class="df-form" autocomplete="off">
        <label class="df-field"><span>Your nickname</span>
          <input id="df-pseudo" name="pseudo" maxlength="20" minlength="3" required spellcheck="false" placeholder="3 to 20 characters"></label>
        <div class="df-field"><span>Your home town <small>optional, for your city's ranking</small></span>
          ${pick ? `<div class="df-picked">${esc(pick.name)} (${esc(pick.dep)}) <button type="button" class="linkish" data-act="unpick">change</button></div>`
            : `<input id="df-commune" placeholder="Start typing…" spellcheck="false" aria-autocomplete="list" aria-controls="df-sugg">
               <div id="df-sugg" class="df-sugg" role="listbox"></div>`}
        </div>
        <p class="df-formerr" role="alert"></p>
        <div class="df-actions">
          <button type="submit" class="btn df-primary">Sign up and play</button>
          <button type="button" class="btn" data-act="board">Rankings</button>
        </div>
      </form>
      <p class="df-foot">No email, no password: your nickname stays on this device. The rankings show your nickname and
        your city, never your home town. <button type="button" class="linkish" data-act="anon">Play unranked</button></p>`;
  }

  function renderGame(root) {
    const g = game;
    const pips = `<div class="df-pips" aria-hidden="true">${Array.from({ length: g.rounds }, (_, k) => {
      const r = g.results[k];
      const cls = r ? (r.pts >= 800 ? "good" : r.pts >= 400 ? "mid" : "low") : k === g.round ? "now" : "";
      return `<span class="df-pip ${cls}"></span>`;
    }).join("")}</div>`;
    if (g.phase === "done") {
      const rows = g.results.map((r) => `<tr><td>${esc(r.name)} <small>${esc(r.dep)}</small></td><td>${kmText(r.km)}</td><td>${int(r.pts)}</td></tr>`).join("");
      const rank = g.rank?.pos ? `<div class="df-rank">${ordinal(g.rank.pos)} of ${int(g.rank.of)} today</div>` : "";
      root.innerHTML = `${head()}
        <div class="df-total"><b>${int(g.total)}</b> points out of ${int(1000 * g.rounds)}</div>${rank}
        ${g.ranked ? "" : `<p class="df-help">Unranked game.</p>`}
        <table class="df-table"><thead><tr><th>Place</th><th>Off by</th><th>Points</th></tr></thead><tbody>${rows}</tbody></table>
        <div class="df-actions">
          <button type="button" class="btn df-primary" data-act="share">${icon("share", null, { size: 14 })}<span>Copy my result</span></button>
          <button type="button" class="btn" data-act="board">Rankings</button>
        </div>
        <p class="df-foot">A new challenge tomorrow, the same for everyone.
          ${g.ranked ? `<button type="button" class="linkish" data-act="anon">Play again unranked</button>` : ""}</p>`;
      root.querySelector(".df-primary")?.focus({ preventScroll: true });
      return;
    }
    if (g.phase === "guess") {
      root.innerHTML = `${head()}${pips}
        <div class="df-round">Place ${g.round + 1} of ${g.rounds}</div>
        <div class="df-name">${esc(g.name)}</div>
        <div class="df-clock" aria-hidden="true"><span class="df-bar"></span></div>
        <div class="df-help"><span class="df-secs"></span> Click on the map where you think it is.</div>`;
      setSearch(false);
      deadline = performance.now() + g.remaining_ms;
      tick();
      timer = setInterval(tick, 200);
      return;
    }
    const r = g.results[g.round];
    const last = g.round === g.rounds - 1;
    root.innerHTML = `${head()}${pips}
      <div class="df-round">Place ${g.round + 1} of ${g.rounds}</div>
      <div class="df-name">${esc(r.name)}</div>
      <div class="df-sub">${esc(r.dep_name)} (${esc(r.dep)}), ${int(r.pop)} residents</div>
      <div class="df-result"><span class="df-km">${r.km == null ? "Out of time" : `${kmText(r.km)} off`}</span><span class="df-pts">+${int(r.pts)} points</span></div>
      <div class="df-actions"><button type="button" class="btn df-primary" data-act="next">${last ? "See my score" : "Next place"}</button></div>`;
    root.querySelector(".df-primary")?.focus({ preventScroll: true });
  }

  function tick() {
    const left = Math.max(0, deadline - performance.now());
    const bar = el?.querySelector(".df-bar");
    if (bar) bar.style.transform = `scaleX(${left / (game.limit_s * 1000)})`;
    const secs = el?.querySelector(".df-secs");
    if (secs) secs.textContent = `${Math.ceil(left / 1000)} s.`;
    el?.querySelector(".df-clock")?.classList.toggle("late", left < 8000);
    if (left <= 0 && game?.phase === "guess") {
      clearInterval(timer);
      answer(null, null);
    }
  }

  // The search box would find the place on the map: off while a name is on screen.
  function setSearch(on) {
    const input = document.getElementById("search-input");
    if (input) input.disabled = !on;
    document.body.classList.toggle("defi-round", !on);
  }

  // --- sign-up --------------------------------------------------------------------------------------------------
  async function loadCommunes() {
    if (communes) return communes;
    const d = await app.loadData("communes");
    const col = Object.fromEntries((d?.columns || []).map((c, k) => [c, k]));
    const list = (d?.rows || []).map((r) => ({ code: r[col.code], name: r[col.name], dep: r[col.dep], pop: r[col.pop] || 0, n: fold(r[col.name]) }));
    communes = { list, byCode: new Map(list.map((c) => [c.code, c])) };
    return communes;
  }

  async function suggest(q) {
    const box = el?.querySelector("#df-sugg");
    if (!box) return;
    const f = fold(q);
    if (f.length < 2) { box.innerHTML = ""; return; }
    const { list } = await loadCommunes();
    const starts = [], has = [];
    for (const c of list) {
      if (c.n.startsWith(f)) starts.push(c);
      else if (c.n.includes(f)) has.push(c);
    }
    const out = [...starts.sort((a, b) => b.pop - a.pop), ...has.sort((a, b) => b.pop - a.pop)].slice(0, 6);
    box.innerHTML = out.map((c) => `<button type="button" role="option" class="df-opt" data-act="pick" data-code="${esc(c.code)}">${esc(c.name)} <small>${esc(c.dep)}</small></button>`).join("")
      || `<div class="df-none">No place found</div>`;
  }

  async function signUp() {
    const form = el.querySelector(".df-form");
    const pseudo = form?.querySelector("#df-pseudo")?.value || "";
    const errEl = form?.querySelector(".df-formerr");
    busy = true;
    try {
      const out = await call("POST", "joueur", { pseudo, commune: pick?.code || null });
      store.set(PLAYER_KEY, { pseudo: out.me.pseudo, token: out.token });
      info = { ...info, me: out.me };
      busy = false;
      play();
    } catch (err) {
      busy = false;
      if (errEl) errEl.textContent = err.message;
    }
  }

  // --- the game -------------------------------------------------------------------------------------------------
  async function start() {
    const my = session;
    try {
      info = await call("GET", "defi");
    } catch (err) {
      if (my !== session) return;
      if (err.status === 401) { // the stored player is gone (call() forgot it): ask again, anonymously
        try { info = await call("GET", "defi"); } catch (e2) { error = e2.message; }
      } else error = err.message;
    }
    if (my !== session || app.mode !== "challenge") return;
    view = "intro";
    game = null;
    // An unranked game left half way through today comes back as it was.
    const saved = store.get(GAME_KEY);
    if (info && !info.me && saved?.day === info.day && saved?.game) {
      try {
        const g = await call("POST", "defi/start", { game: saved.game });
        if (my !== session) return;
        if (g.phase !== "done") { setGame(g); view = "game"; }
      } catch { /* gone: start fresh */ }
    }
    render();
    frameLand();
  }

  function setGame(g) {
    game = g;
    if (!g.ranked) store.set(GAME_KEY, g.phase === "done" ? null : { day: g.day, game: g.game });
  }

  async function play({ unranked = false } = {}) {
    const my = session;
    busy = true;
    try {
      const g = await call("POST", "defi/start", unranked ? { unranked: true, new: true } : {});
      if (my !== session) return;
      setGame(g);
      view = "game";
      error = "";
    } catch (err) {
      error = err.message;
    }
    busy = false;
    render();
    if (game?.phase === "done") frameAll();
    else if (game?.phase === "reveal") frameGuess();
    else frameLand();
    app.requestDraw();
  }

  async function answer(x, y) {
    if (!game || game.phase !== "guess" || busy) return;
    busy = true;
    clearInterval(timer);
    const my = session;
    try {
      const g = await call("POST", "defi/guess", { game: game.game, round: game.round, x, y });
      if (my !== session) return;
      // The fifth answer ends the game on the server; show where that place was before the score.
      setGame(g.phase === "done" ? { ...g, phase: "reveal", round: g.rounds - 1, final: true } : g);
      if (g.phase === "done" && g.ranked && info?.me) info.me.played_today = true;
    } catch (err) {
      error = err.message;
    }
    busy = false;
    render();
    frameGuess();
    app.requestDraw();
  }

  async function next() {
    if (!game || game.phase !== "reveal" || busy) return;
    if (game.final) {
      game = { ...game, phase: "done", final: false };
      render();
      frameAll();
      app.requestDraw();
      return;
    }
    busy = true;
    const my = session;
    try {
      const g = await call("POST", "defi/next", { game: game.game });
      if (my !== session) return;
      setGame(g);
    } catch (err) {
      error = err.message;
    }
    busy = false;
    render();
    frameLand();
    app.requestDraw();
  }

  async function share(btn) {
    const g = game;
    const link = `${location.origin}${location.pathname}defi/`; // its own page: a link preview that says what it is
    const rank = g.rank?.pos ? `, ${ordinal(g.rank.pos)} of ${int(g.rank.of)}` : "";
    const text = `Europeciv, daily challenge #${g.n} (${longDate(g.day)})\n${int(g.total)} points out of ${int(1000 * g.rounds)}${rank}\n`
      + `${g.results.map((r) => kmText(r.km)).join(", ")}\n${link}`;
    const ok = await copyText(text);
    const span = btn.querySelector("span");
    if (span) span.textContent = ok ? "Result copied" : "Copy the text below";
    if (!ok && !el.querySelector(".df-copy")) {
      const ta = document.createElement("textarea");
      ta.className = "df-copy";
      ta.readOnly = true;
      ta.rows = 4;
      ta.value = text;
      el.querySelector(".df-actions")?.after(ta);
      ta.select();
    }
  }

  // --- rankings -------------------------------------------------------------------------------------------------
  // The API's team types keep their names: villes = cities (urban areas), departements = countries, regions = the
  // region the server gives each country.
  const TABS = [["joueurs", "Players"], ["villes", "Cities"], ["departements", "Countries"], ["regions", "Regions"]];

  function openBoard() {
    view = "board";
    loadBoard();
  }

  async function loadBoard() {
    board.loading = true;
    board.data = null;
    render();
    const my = session;
    try {
      board.data = await call("GET", `classement?type=${board.type}&periode=${board.periode}`);
    } catch (err) {
      board.data = { error: err.message };
    }
    if (my !== session) return;
    board.loading = false;
    if (view === "board") render();
  }

  function renderBoard(root) {
    const d = board.data;
    const team = board.type !== "joueurs";
    const tabs = `<div class="df-tabs" role="tablist">${TABS.map(([v, l]) =>
      `<button type="button" role="tab" aria-selected="${board.type === v}" class="df-tab${board.type === v ? " on" : ""}" data-act="tab" data-v="${v}">${l}</button>`).join("")}</div>
      <div class="df-periods">${[["jour", "Today"], ["mois", "This month"]].map(([v, l]) =>
      `<button type="button" class="df-period${board.periode === v ? " on" : ""}" data-act="period" data-v="${v}">${l}</button>`).join("")}</div>`;
    let body = "";
    if (!d) body = `<p class="df-help">Loading…</p>`;
    else if (d.error) body = `<p class="df-error">${esc(d.error)}</p>`;
    else {
      const extra = (r) => (team ? int(r.players) : r.time_s != null ? `${r.time_s} s` : int(r.days));
      const name = (r) => (team && board.type !== "regions"
        ? `<button type="button" class="linkish" data-act="go" data-kind="${board.type}" data-key="${esc(r.key)}">${esc(r.name)}</button>`
        : esc(r.name)) + (!team && r.ville ? ` <small>${esc(r.ville)}</small>` : "");
      const line = (r, me) => `<tr class="${me ? "me" : ""}"><td>${r.rank}</td><td>${name(r)}</td><td>${int(r.points)}</td><td>${extra(r)}</td></tr>`;
      const isMe = (r) => d.me && r.rank === d.me.rank && r.name === d.me.name;
      const rows = d.rows.map((r) => line(r, isMe(r))).join("") + (d.me && !d.rows.some(isMe) ? line(d.me, true) : "");
      const what = board.periode === "jour" ? "today" : `in ${monthName(d.label)}`;
      const unit = { villes: "city", departements: "country", regions: "region" }[board.type];
      const empty = team ? `No ranking ${what}: a ${unit} needs at least ${d.rules.team_min} players to be ranked.`
        : `Nobody is ranked ${what} yet.`;
      const cols = team ? ["", "Name", "Points", "Players"] : ["", "Player", "Points", board.periode === "jour" ? "Time" : "Days"];
      body = rows ? `<div class="df-scroll"><table class="df-table df-board"><thead><tr>${cols.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`
        : `<p class="df-help">${empty}</p>`;
      const rule = team ? `A team's points: the average of its ${d.rules.team_top} best players, once it has ${d.rules.team_min} players.`
        : board.periode === "mois" ? `Monthly points: each player's ${d.rules.best_days} best days, added up.` : "Ties go to the faster player.";
      body += `<p class="df-foot">${rule}</p>`;
    }
    root.innerHTML = `${head()}${tabs}${body}
      <div class="df-actions"><button type="button" class="btn" data-act="back">Back</button></div>`;
  }

  function flyToTeam(kind, key) {
    if (kind === "villes") {
      const c = app.cityById.get(key);
      if (c?.cell != null) frameBox([[app.w.grid.cx(c.cell), app.w.grid.cy(c.cell)]], 40);
      return;
    }
    const idx = app.w.raw.states.findIndex((s) => s.abbr === key);
    const b = idx >= 0 ? app.highlightBounds({ states: new Set([idx]) }) : null;
    if (b) app.fitBounds(b.x0, b.y0, b.x1, b.y1, { padTop: hudBottom(), padBottom: 40, ms: 800 });
  }

  // --- camera ---------------------------------------------------------------------------------------------------
  const hudBottom = () => (el && !el.hidden ? el.getBoundingClientRect().bottom + 16 : 90);
  const unitsPerKm = () => 1 / (app.data.world?.km_per_unit || 1 / 3.5);
  let land = null;
  function frameLand(ms = 750) {
    if (!land) {
      const g = app.w.grid, own = app.w.raw.owner;
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (let i = 0; i < g.size; i++) {
        if (own[i] < 0) continue;
        const x = g.cx(i), y = g.cy(i);
        x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
      }
      land = { x0, y0, x1, y1 };
    }
    app.fitBounds(land.x0, land.y0, land.x1, land.y1, { padTop: hudBottom(), padBottom: 24, padLeft: 24, padRight: 24, ms });
  }
  // The answer is shown at a regional zoom (about 60 km across at least), never down in the city art: closer
  // zooms cost a lot of sprites for nothing, and the flight back out to Europe would have to repaint them all.
  function frameBox(pts, padKm) {
    const pad = Math.max(padKm, 30) * unitsPerKm();
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const [x, y] of pts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
    if (isFinite(x0)) app.fitBounds(x0 - pad, y0 - pad, x1 + pad, y1 + pad, { padTop: hudBottom(), padBottom: 60, padLeft: 30, padRight: 30, ms: 800, maxScale: 1.1 });
  }
  function frameGuess() {
    const r = game?.results[game.round];
    if (r) frameBox([[r.x, r.y], ...(r.guess ? [r.guess] : [])], 40);
  }
  function frameAll() {
    if (game?.results.length) frameBox(game.results.flatMap((r) => [[r.x, r.y], ...(r.guess ? [r.guess] : [])]), 30);
  }

  // --- wiring ---------------------------------------------------------------------------------------------------
  app.registerMode("challenge", {
    enter() {
      session++;
      app.clearSelection();
      prevLens = app.state.lens?.id || null;
      if (prevLens) app.setLens(null);
      app.state.highlight = null;
      info = null;
      game = null;
      error = "";
      view = "intro";
      render();
      start();
    },
    exit() {
      session++;
      clearInterval(timer);
      setSearch(true);
      busy = false;
      if (el) { el.hidden = true; el.innerHTML = ""; }
      game = null;
      if (prevLens) app.setLens(prevLens);
      prevLens = null;
      app.requestDraw();
    },
  });

  // While the challenge is on, a click on the map is an answer (and never selects a city or a country).
  app.on("mapclick", (ev) => {
    if (app.mode !== "challenge") return false;
    if (view === "game" && game?.phase === "guess") {
      const [x, y] = app.cam.toWorld(ev.x, ev.y);
      answer(Math.round(x), Math.round(y));
    }
    return true;
  });
  document.addEventListener("keydown", (e) => {
    if (app.mode !== "challenge" || !game || e.target?.closest?.("input, textarea, button")) return;
    if (e.key === "Enter" && view === "game" && game.phase === "reveal") { e.preventDefault(); next(); }
  });

  app.registerOverlay({
    id: "defi",
    z: 60,
    space: "world",
    draw(ctx, cam) {
      if (app.mode !== "challenge" || !game || view !== "game") return;
      const s = cam.scale;
      const shown = game.phase === "done" ? game.results : game.phase === "reveal" ? [game.results[game.round]] : [];
      for (const r of shown) {
        if (!r) continue;
        if (r.guess) {
          const [gx, gy] = r.guess;
          ctx.save();
          ctx.setLineDash([8 / s, 6 / s]);
          ctx.lineCap = "round";
          ctx.lineWidth = 4 / s;
          ctx.strokeStyle = "rgba(20,14,4,.8)";
          ctx.beginPath(); ctx.moveTo(gx, gy); ctx.lineTo(r.x, r.y); ctx.stroke();
          ctx.lineWidth = 2 / s;
          ctx.strokeStyle = "#f6e7bf";
          ctx.stroke();
          ctx.restore();
          ctx.save();
          ctx.translate(gx, gy);
          ctx.scale(1 / s, 1 / s);
          ctx.beginPath(); ctx.arc(0, 0, 7, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(246,231,191,.9)"; ctx.fill();
          ctx.lineWidth = 2; ctx.strokeStyle = "rgba(20,14,4,.9)"; ctx.stroke();
          ctx.beginPath(); ctx.arc(0, 0, 2.4, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(20,14,4,.9)"; ctx.fill();
          ctx.restore();
        }
        drawPin(ctx, r.x, r.y, r.name, s);
      }
    },
  });

  app.ui?.addTopButton?.({
    id: "btn-defi", icon: "target", label: "Daily challenge", title: "The daily challenge: find five places on the map, with rankings",
    onClick: () => app.setMode(app.mode === "challenge" ? null : "challenge"),
  });
  app.hash.register("defi", {
    get: () => (app.mode === "challenge" ? "1" : null),
    set(v) {
      if (v != null && app.mode !== "challenge") app.setMode("challenge");
      else if (v == null && app.mode === "challenge") app.setMode(null);
    },
  });
  app.challenge = {
    points,
    get game() { return game; },
    get view() { return view; },
    get info() { return info; },
    answer: (x, y) => answer(x, y),
    next: () => next(),
    play: (o) => play(o),
    openBoard: (type = "joueurs", periode = "jour") => { board.type = type; board.periode = periode; openBoard(); },
  };
}
