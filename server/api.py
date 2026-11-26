#!/usr/bin/env python3
"""europeciv API: the daily challenge played on the server, players and rankings. Stdlib only, one SQLite file.

The browser never sees where a place is before answering: the server draws the day's five places with a secret
key, sends one name at a time, times the answer on its own clock and returns the place with the points.

Scoring (the rules the challenge shows):
  * per place: 1,000 points within 5 km, then 1,000 × e^(−(km − 5)/250): about 680 at 100 km, 310 at 300 km;
  * 30 seconds per place (server clock, 2 s of grace for the network); no answer in time = 0;
  * the day's score is the five places (max 5,000). Only a player's first game of the day is ranked; ties go to the
    faster total time;
  * the month: each player's 20 best days of the month added up (playing often pays, a missed day costs little);
  * teams (city = urban area, country, sub-region of Europe, from the home town a player gives): the mean of the
    team's 5 best players, ranked once at least 3 players count (a big city cannot win by numbers alone, one lucky
    player cannot carry a village). A game counts for the team the player belonged to when it started.

Run:   api.py serve [--port 8661] [--data DIR] [--db FILE] [--secret FILE] [--trust-proxy]
       api.py admin players | ban P | unban P | reset P [DAY] | rename P NEW | game P [DAY] | pin [DAY] | top [DAY]
In development `uv run python -m pipeline serve` mounts this module under /api/ (data from web/data).
"""

from __future__ import annotations

import argparse
import os
import hashlib
import hmac
import json
import math
import re
import secrets
import sqlite3
import sys
import threading
import time
import unicodedata
from collections import defaultdict, deque
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
ROUNDS = 5
LIMIT_S = 30
GRACE_S = 2
BEST_DAYS = 20
TEAM_TOP = 5
TEAM_MIN = 3
RECENT_DAYS = 120  # a commune is not drawn again within this many days
MAX_BODY = 4096
TEAMS = ("villes", "departements", "regions")
ORIGIN_OK = re.compile(r"^(https://mathieuastruc\.com|http://(localhost|127\.0\.0\.1)(:\d+)?)$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
  id INTEGER PRIMARY KEY, pseudo TEXT NOT NULL, pkey TEXT NOT NULL UNIQUE, token_hash TEXT NOT NULL UNIQUE,
  commune TEXT, created REAL NOT NULL, ip TEXT, banned INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS games (
  id TEXT PRIMARY KEY, day TEXT NOT NULL, player INTEGER REFERENCES players(id), aav TEXT, dep TEXT, region TEXT,
  round INTEGER NOT NULL DEFAULT 0, started REAL, finished REAL, created REAL NOT NULL, ip TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_ranked_game ON games(day, player) WHERE player IS NOT NULL;
CREATE INDEX IF NOT EXISTS games_day ON games(day);
CREATE TABLE IF NOT EXISTS days (day TEXT PRIMARY KEY, picks TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS guesses (
  game TEXT NOT NULL REFERENCES games(id), round INTEGER NOT NULL, x REAL, y REAL, km REAL, pts INTEGER NOT NULL,
  ms INTEGER NOT NULL, PRIMARY KEY (game, round));
"""


# Scored for a continent: full marks within 5 km, then halved every ~170 km (100 km: 684, 300 km: 309, 1,000 km: 19).
FULL_KM, DECAY_KM = 5, 250


def points(km: float) -> int:
    return 1000 if km <= FULL_KM else round(1000 * math.exp(-(km - FULL_KM) / DECAY_KM))


def fold(s: str) -> str:
    """Lower case, no accents, letters and digits only: the key two pseudos may not share."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


# Pseudos are public: a short blocklist (whole words, and longer stems anywhere), plus reserved names.
BLOCK_WORDS = {"con", "cons", "pd", "fdp", "ntm", "tg", "nazi", "nazis", "hitler", "pute", "putes", "merde", "bite", "cul"}
BLOCK_STEMS = ("connard", "connasse", "salope", "encule", "nique", "negre", "bougnoul", "batard", "pedophile", "pedo",
               "fuck", "shit", "bitch", "nigger", "nigga", "retard", "salaud", "enfoire", "pouffiasse", "tapette",
               "youpin", "bicot", "raton", "chinetoque", "hitler", "heil", "jihad", "terroris")
RESERVED = {"admin", "administrator", "administrateur", "moderator", "moderateur", "modo", "europeciv", "franceciv", "official", "officiel", "support", "mathieuastruc", "anonymous", "anonyme"}
PSEUDO_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ0-9][A-Za-zÀ-ÖØ-öø-ÿ0-9 _.'-]{1,18}[A-Za-zÀ-ÖØ-öø-ÿ0-9]$")


def check_pseudo(raw) -> tuple[str | None, str | None]:
    """(pseudo, None) or (None, reason)."""
    if not isinstance(raw, str):
        return None, "Missing name."
    p = re.sub(r"\s+", " ", raw).strip()
    if not 3 <= len(p) <= 20:
        return None, "Names are 3 to 20 characters long."
    if not PSEUDO_RE.match(p) or not re.search(r"[A-Za-zÀ-ÿ]", p):
        return None, "Letters, digits, spaces and - _ . ' only, with at least one letter."
    key = fold(p)
    words = set(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", p).encode("ascii", "ignore").decode().lower()))
    if key in RESERVED or words & BLOCK_WORDS or any(s in key for s in BLOCK_STEMS):
        return None, "This name is not allowed."
    return p, None


class Places:
    """Places, cities (urban areas), countries and sub-regions, from the site's public data files."""

    def __init__(self, data: Path):
        c = json.loads((data / "communes.json").read_text())
        col = {k: i for i, k in enumerate(c["columns"])}
        self.communes = {r[col["code"]]: {"name": r[col["name"]], "dep": r[col["dep"]], "aav": r[col["aav"]]}
                         for r in c["rows"]}
        self.villes = {x["id"]: x["name"] for x in json.loads((data / "cities.json").read_text())}
        self.deps = {}
        for s in json.loads((data / "states.json").read_text()):
            self.deps[s["abbr"]] = {"name": s["name"], "region": s.get("region")}
        pool = json.loads((data / "defi.json").read_text())
        pc = {k: i for i, k in enumerate(pool["columns"])}
        self.pool = {t: [{"code": r[pc["code"]], "name": r[pc["name"]], "dep": r[pc["dep"]], "pop": r[pc["pop"]],
                          "x": r[pc["x"]], "y": r[pc["y"]]} for r in rows] for t, rows in pool["tiers"].items()}
        self.pattern = pool["pattern"]
        self.start = pool["start"]
        self.km_per_unit = pool["km_per_unit"]

    def team_of(self, code: str | None) -> dict:
        c = self.communes.get(code or "")
        if not c:
            return {"aav": None, "dep": None, "region": None}
        return {"aav": c["aav"], "dep": c["dep"], "region": (self.deps.get(c["dep"]) or {}).get("region")}

    def team_label(self, kind: str, key: str) -> str:
        if kind == "villes":
            return self.villes.get(key, key)
        if kind == "departements":
            return f"{(self.deps.get(key) or {}).get('name', key)} ({key})"
        return key


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Api:
    LIMITS = {"per_minute": 120, "signups": 5, "anon_games": 50}  # per address (and per day for the last two)

    def __init__(self, db: Path, secret: bytes, data: Path, now=time.time, limits: dict | None = None):
        self.limits = {**self.LIMITS, **(limits or {})}
        self.db_path = str(db)
        self.secret = secret
        self.places = Places(data)
        self.now = now
        self.lock = threading.Lock()
        self._picks: dict[str, list[dict]] = {}  # day → draw as played (stored)
        self._drawn: dict[str, list[dict]] = {}  # day → draw computed from the pool (not stored)
        self._boards: dict[tuple, tuple[float, list]] = {}  # rankings, a few seconds old at most
        self._hits: dict[str, deque] = defaultdict(deque)
        con = self.connect()
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(SCHEMA)
        finally:
            con.close()

    # --- plumbing -------------------------------------------------------------------------------------------------
    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def today(self) -> str:
        return datetime.fromtimestamp(self.now(), PARIS).date().isoformat()

    def day_number(self, day: str) -> int:
        return (date.fromisoformat(day) - date.fromisoformat(self.places.start)).days

    def ip_key(self, ip: str, day: str) -> str:
        """The caller's address, keyed by the day: enough to count per address, useless once the day is over."""
        return hmac.new(self.secret, f"ip|{day}|{ip}".encode(), hashlib.sha256).hexdigest()[:16]

    def rate_limit(self, ip: str) -> None:
        per_minute = self.limits["per_minute"]
        if len(self._hits) > 20_000:  # forget idle addresses
            for k in [k for k, v in self._hits.items() if not v or v[-1] < self.now() - 60]:
                del self._hits[k]
        q, t = self._hits[ip], self.now()
        while q and q[0] < t - 60:
            q.popleft()
        if len(q) >= per_minute:
            raise ApiError(429, "Too many requests, try again in a minute.")
        q.append(t)

    def picks(self, day: str, con: sqlite3.Connection | None = None) -> list[dict]:
        """The day's communes: drawn with the secret key, slot by slot, none drawn in the previous RECENT_DAYS.
        A day's draw is stored the first time it is asked for (names and positions), so a new pool (data update)
        never changes the communes of a day already played; only days not yet drawn use it."""
        if day in self._picks:
            return self._picks[day]
        own = con is None
        con = con or self.connect()
        try:
            stored = {r["day"]: json.loads(r["picks"]) for r in con.execute("SELECT day, picks FROM days")}
        finally:
            if own:
                con.close()
                con = None
        if day in stored:
            self._picks[day] = stored[day]
            return stored[day]
        drawn = self._drawn
        d = date.fromisoformat(self.places.start)
        target = max(date.fromisoformat(day), d)
        recent: deque = deque()
        while d <= target:
            key = d.isoformat()
            if key in stored:
                drawn[key] = stored[key]
            elif key not in drawn:
                taken = {c for _, codes in recent for c in codes}
                out = []
                for slot, tier in enumerate(self.places.pattern):
                    rows = self.places.pool[tier]
                    for k in range(2000):
                        h = hmac.new(self.secret, f"defi|{key}|{slot}|{k}".encode(), hashlib.sha256).digest()
                        row = rows[int.from_bytes(h[:8], "big") % len(rows)]
                        if row["code"] not in taken:
                            break
                    taken.add(row["code"])
                    out.append(row)
                drawn[key] = out
            recent.append((key, [r["code"] for r in drawn[key]]))
            while recent and date.fromisoformat(recent[0][0]) <= d - timedelta(days=RECENT_DAYS):
                recent.popleft()
            d += timedelta(days=1)
        out = drawn[target.isoformat()]
        if day <= self.today():
            # Inside the caller's transaction when there is one (a POST holds the write lock), else on our own.
            own = con is None
            con = con or self.connect()
            try:
                con.execute("INSERT OR IGNORE INTO days (day, picks, created) VALUES (?, ?, ?)",
                            (day, json.dumps(out, ensure_ascii=False), self.now()))
                if own:
                    con.commit()
                row = con.execute("SELECT picks FROM days WHERE day = ?", (day,)).fetchone()
                out = json.loads(row["picks"]) if row else out
            finally:
                if own:
                    con.close()
        self._picks[day] = out
        return out

    def player_from(self, con, headers) -> sqlite3.Row | None:
        auth = headers.get("Authorization") or headers.get("authorization") or ""
        if not auth.startswith("Bearer "):
            return None
        h = hashlib.sha256(auth[7:].strip().encode()).hexdigest()
        p = con.execute("SELECT * FROM players WHERE token_hash = ?", (h,)).fetchone()
        if p is None:
            raise ApiError(401, "Unknown player: please sign up again.")
        if p["banned"]:
            raise ApiError(403, "This player was removed from the rankings.")
        return p

    # --- entry point ----------------------------------------------------------------------------------------------
    def handle(self, method: str, path: str, query: str, headers, body: bytes, ip: str) -> tuple[int, dict]:
        try:
            self.rate_limit(ip)
            if method == "POST":
                origin = headers.get("Origin") or headers.get("origin")
                if origin and not ORIGIN_OK.match(origin):
                    raise ApiError(403, "Origin refused.")
                if len(body) > MAX_BODY:
                    raise ApiError(413, "Request too large.")
                try:
                    data = json.loads(body or b"{}")
                except ValueError:
                    raise ApiError(400, "JSON invalide.") from None
                if not isinstance(data, dict):
                    raise ApiError(400, "JSON invalide.")
            else:
                data = {k: v[0] for k, v in parse_qs(query).items()}
            route = {
                ("GET", "/api/defi"): self.get_defi,
                ("POST", "/api/joueur"): self.post_joueur,
                ("POST", "/api/joueur/commune"): self.post_commune,
                ("POST", "/api/defi/start"): self.post_start,
                ("POST", "/api/defi/guess"): self.post_guess,
                ("POST", "/api/defi/next"): self.post_next,
                ("GET", "/api/classement"): self.get_classement,
            }.get((method, path.rstrip("/") or "/"))
            if route is None:
                raise ApiError(404, "Inconnu.")
            con = self.connect()
            try:
                if method != "POST":
                    return 200, route(con, data, headers, ip)
                with self.lock:
                    con.execute("BEGIN IMMEDIATE")
                    try:
                        out = route(con, data, headers, ip)
                    except BaseException:
                        con.rollback()
                        raise
                    con.commit()
                    return 200, out
            finally:
                con.close()
        except ApiError as e:
            return e.status, {"error": e.message}

    # --- players --------------------------------------------------------------------------------------------------
    def me(self, con, p) -> dict | None:
        if p is None:
            return None
        team = self.places.team_of(p["commune"])
        com = self.places.communes.get(p["commune"] or "")
        today = self.today()
        days = {r["day"] for r in con.execute(
            "SELECT day FROM games WHERE player = ? AND finished IS NOT NULL", (p["id"],))}
        streak, d = 0, date.fromisoformat(today)
        if today not in days:
            d -= timedelta(days=1)
        while d.isoformat() in days:
            streak += 1
            d -= timedelta(days=1)
        return {
            "pseudo": p["pseudo"],
            "commune": {"code": p["commune"], "name": com["name"]} if com else None,
            "ville": self.places.villes.get(team["aav"]) if team["aav"] else None,
            "departement": self.places.team_label("departements", team["dep"]) if team["dep"] else None,
            "region": team["region"],
            "streak": streak,
            "played_today": today in days,
        }

    def post_joueur(self, con, data, headers, ip):
        pseudo, why = check_pseudo(data.get("pseudo"))
        if why:
            raise ApiError(400, why)
        commune = data.get("commune") or None
        if commune is not None and commune not in self.places.communes:
            raise ApiError(400, "Commune inconnue.")
        today = self.today()
        ipk = self.ip_key(ip, today)
        n = con.execute("SELECT COUNT(*) FROM players WHERE ip = ?", (ipk,)).fetchone()[0]
        if n >= self.limits["signups"]:
            raise ApiError(429, "Trop d'inscriptions depuis cette connexion aujourd'hui.")
        if con.execute("SELECT 1 FROM players WHERE pkey = ?", (fold(pseudo),)).fetchone():
            raise ApiError(409, "This name is already taken.")
        token = secrets.token_urlsafe(24)
        con.execute("INSERT INTO players (pseudo, pkey, token_hash, commune, created, ip) VALUES (?, ?, ?, ?, ?, ?)",
                    (pseudo, fold(pseudo), hashlib.sha256(token.encode()).hexdigest(), commune, self.now(), ipk))
        p = con.execute("SELECT * FROM players WHERE pkey = ?", (fold(pseudo),)).fetchone()
        return {"token": token, "me": self.me(con, p)}

    def post_commune(self, con, data, headers, ip):
        p = self.player_from(con, headers)
        if p is None:
            raise ApiError(401, "Inscrivez-vous d'abord.")
        commune = data.get("commune") or None
        if commune is not None and commune not in self.places.communes:
            raise ApiError(400, "Commune inconnue.")
        con.execute("UPDATE players SET commune = ? WHERE id = ?", (commune, p["id"]))
        return {"me": self.me(con, con.execute("SELECT * FROM players WHERE id = ?", (p["id"],)).fetchone())}

    # --- the game -------------------------------------------------------------------------------------------------
    def get_defi(self, con, data, headers, ip):
        today = self.today()
        p = self.player_from(con, headers)
        return {"day": today, "n": self.day_number(today) + 1, "rounds": ROUNDS, "limit_s": LIMIT_S,
                "rules": {"best_days": BEST_DAYS, "team_top": TEAM_TOP, "team_min": TEAM_MIN}, "me": self.me(con, p)}

    def state(self, con, g) -> dict:
        """What the browser may know about a game: the current name, and the answers already given."""
        picks = self.picks(g["day"], con)
        rows = {r["round"]: r for r in con.execute("SELECT * FROM guesses WHERE game = ? ORDER BY round", (g["id"],))}
        results = []
        for r, row in rows.items():
            c = picks[r]
            dep = self.places.deps.get(c["dep"]) or {}
            results.append({"round": r, "name": c["name"], "dep": c["dep"], "dep_name": dep.get("name", c["dep"]),
                            "pop": c["pop"], "x": c["x"], "y": c["y"], "km": row["km"], "pts": row["pts"], "ms": row["ms"],
                            "guess": [row["x"], row["y"]] if row["x"] is not None else None, "timeout": row["km"] is None})
        cur = g["round"]
        phase = "done" if g["finished"] else "reveal" if cur in rows else "guess"
        out = {"game": g["id"], "day": g["day"], "n": self.day_number(g["day"]) + 1, "ranked": g["player"] is not None,
               "round": cur, "rounds": ROUNDS, "phase": phase, "limit_s": LIMIT_S, "results": results,
               "total": sum(x["pts"] for x in results), "ms": sum(x["ms"] for x in results)}
        if phase == "guess":
            out["name"] = picks[cur]["name"]
            out["remaining_ms"] = max(0, int((g["started"] + LIMIT_S - self.now()) * 1000))
        if phase == "done" and g["player"] is not None:
            board = self.day_players(con, g["day"])
            pos = next((k + 1 for k, row in enumerate(board) if row["game"] == g["id"]), None)
            out["rank"] = {"pos": pos, "of": len(board)}
        return out

    def expire(self, con, g) -> sqlite3.Row:
        """A round whose time ran out (tab closed, network gone) is scored 0 when the game is next touched."""
        if g["finished"] or g["started"] is None or self.now() <= g["started"] + LIMIT_S + GRACE_S:
            return g
        self.record(con, g, None, None)
        return con.execute("SELECT * FROM games WHERE id = ?", (g["id"],)).fetchone()

    def record(self, con, g, x, y) -> None:
        r = g["round"]
        elapsed = self.now() - g["started"]
        if x is None or elapsed > LIMIT_S + GRACE_S:
            km, pts, ms, x, y = None, 0, LIMIT_S * 1000, None, None
        else:
            c = self.picks(g["day"], con)[r]
            km = round(math.hypot(x - c["x"], y - c["y"]) * self.places.km_per_unit, 1)
            pts, ms = points(km), min(LIMIT_S * 1000, int(elapsed * 1000))
        con.execute("INSERT INTO guesses (game, round, x, y, km, pts, ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (g["id"], r, x, y, km, pts, ms))
        finished = self.now() if r == ROUNDS - 1 else None
        con.execute("UPDATE games SET started = NULL, finished = ? WHERE id = ?", (finished, g["id"]))
        if finished:
            self._boards.clear()

    def game(self, con, gid) -> sqlite3.Row:
        g = con.execute("SELECT * FROM games WHERE id = ?", (str(gid or ""),)).fetchone() if gid else None
        if g is None:
            raise ApiError(404, "Partie introuvable.")
        return self.expire(con, g)

    def post_start(self, con, data, headers, ip):
        today = self.today()
        p = None if data.get("unranked") else self.player_from(con, headers)
        if p is not None:
            g = con.execute("SELECT * FROM games WHERE day = ? AND player = ?", (today, p["id"])).fetchone()
            if g is not None:
                return self.state(con, self.expire(con, g))
        elif data.get("game"):
            g = con.execute("SELECT * FROM games WHERE id = ? AND player IS NULL AND day = ?",
                            (str(data["game"]), today)).fetchone()
            if g is not None and not data.get("new"):
                return self.state(con, self.expire(con, g))
        ipk = self.ip_key(ip, today)
        if p is None:
            n = con.execute("SELECT COUNT(*) FROM games WHERE day = ? AND ip = ? AND player IS NULL", (today, ipk)).fetchone()[0]
            if n >= self.limits["anon_games"]:
                raise ApiError(429, "Trop de parties depuis cette connexion aujourd'hui.")
        team = self.places.team_of(p["commune"]) if p is not None else {"aav": None, "dep": None, "region": None}
        gid = secrets.token_urlsafe(18)
        con.execute("INSERT INTO games (id, day, player, aav, dep, region, round, started, created, ip) "
                    "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
                    (gid, today, p["id"] if p is not None else None, team["aav"], team["dep"], team["region"],
                     self.now(), self.now(), ipk))
        return self.state(con, con.execute("SELECT * FROM games WHERE id = ?", (gid,)).fetchone())

    def post_guess(self, con, data, headers, ip):
        g = self.game(con, data.get("game"))
        if g["finished"]:
            return self.state(con, g)
        if data.get("round") != g["round"]:
            return self.state(con, g)  # a late or repeated answer: the browser catches up
        if con.execute("SELECT 1 FROM guesses WHERE game = ? AND round = ?", (g["id"], g["round"])).fetchone():
            return self.state(con, g)
        x, y = data.get("x"), data.get("y")
        if x is not None or y is not None:
            if not all(isinstance(v, (int, float)) and math.isfinite(v) and -1e5 < v < 1e5 for v in (x, y)):
                raise ApiError(400, "Position invalide.")
            x, y = float(x), float(y)
        self.record(con, g, x, y)
        return self.state(con, con.execute("SELECT * FROM games WHERE id = ?", (g["id"],)).fetchone())

    def post_next(self, con, data, headers, ip):
        g = self.game(con, data.get("game"))
        answered = con.execute("SELECT 1 FROM guesses WHERE game = ? AND round = ?", (g["id"], g["round"])).fetchone()
        if not g["finished"] and answered and g["round"] < ROUNDS - 1:
            con.execute("UPDATE games SET round = round + 1, started = ? WHERE id = ?", (self.now(), g["id"]))
            g = con.execute("SELECT * FROM games WHERE id = ?", (g["id"],)).fetchone()
        return self.state(con, g)

    # --- rankings -------------------------------------------------------------------------------------------------
    def day_games(self, con, days: list[str]):
        """Ranked games of those days that count: finished, or from a day already over (unanswered rounds = 0)."""
        today = self.today()
        marks = ",".join("?" * len(days))
        q = (f"SELECT g.id, g.day, g.player, g.aav, g.dep, g.region, g.finished, p.pseudo, "
             f"COALESCE(SUM(x.pts), 0) AS total, COALESCE(SUM(x.ms), 0) + (? - COUNT(x.round)) * ? AS ms "
             f"FROM games g JOIN players p ON p.id = g.player LEFT JOIN guesses x ON x.game = g.id "
             f"WHERE g.day IN ({marks}) AND p.banned = 0 GROUP BY g.id")
        rows = con.execute(q, (ROUNDS, LIMIT_S * 1000, *days)).fetchall()
        return [r for r in rows if r["finished"] is not None or r["day"] < today]

    BOARD_TTL = 10.0

    def cached(self, key: tuple, build):
        hit = self._boards.get(key)
        if hit and self.now() - hit[0] < self.BOARD_TTL:
            return hit[1]
        out = build()
        if len(self._boards) > 200:
            self._boards.clear()
        self._boards[key] = (self.now(), out)
        return out

    def day_players(self, con, day: str) -> list[dict]:
        return self.cached(("day", day, self.today()), lambda: self._day_players(con, day))

    def _day_players(self, con, day: str) -> list[dict]:
        rows = sorted(self.day_games(con, [day]), key=lambda r: (-r["total"], r["ms"], r["id"]))
        return [{"game": r["id"], "player": r["player"], "pseudo": r["pseudo"], "aav": r["aav"], "dep": r["dep"],
                 "region": r["region"], "points": r["total"], "time_s": round(r["ms"] / 1000, 1)} for r in rows]

    def month_players(self, con, month: str) -> list[dict]:
        return self.cached(("month", month, self.today()), lambda: self._month_players(con, month))

    def _month_players(self, con, month: str) -> list[dict]:
        y, m = map(int, month.split("-"))
        d, days = date(y, m, 1), []
        while d.month == m:
            days.append(d.isoformat())
            d += timedelta(days=1)
        per = defaultdict(list)
        info = {}
        for r in self.day_games(con, days):
            per[r["player"]].append(r["total"])
            if r["player"] not in info or r["day"] > info[r["player"]]["day"]:
                info[r["player"]] = {"pseudo": r["pseudo"], "aav": r["aav"], "dep": r["dep"], "region": r["region"],
                                     "day": r["day"]}
        out = []
        for pid, totals in per.items():
            best = sorted(totals, reverse=True)[:BEST_DAYS]
            i = info[pid]
            out.append({"player": pid, "pseudo": i["pseudo"], "aav": i["aav"], "dep": i["dep"], "region": i["region"],
                        "points": sum(best), "days": len(totals), "average": round(sum(totals) / len(totals))})
        out.sort(key=lambda r: (-r["points"], -r["average"], r["pseudo"].lower()))
        return out

    def teams(self, players: list[dict], kind: str) -> list[dict]:
        field = {"villes": "aav", "departements": "dep", "regions": "region"}[kind]
        groups = defaultdict(list)
        for r in players:
            if r[field]:
                groups[r[field]].append(r["points"])
        out = []
        for key, pts in groups.items():
            if len(pts) < TEAM_MIN:
                continue
            top = sorted(pts, reverse=True)[:TEAM_TOP]
            out.append({"key": key, "name": self.places.team_label(kind, key), "points": round(sum(top) / len(top)),
                        "players": len(pts)})
        out.sort(key=lambda r: (-r["points"], -r["players"], r["name"]))
        return out

    def get_classement(self, con, data, headers, ip):
        kind = data.get("type", "joueurs")
        periode = data.get("periode", "jour")
        if kind not in ("joueurs", *TEAMS) or periode not in ("jour", "mois"):
            raise ApiError(400, "Classement inconnu.")
        today = self.today()
        p = self.player_from(con, headers)
        if periode == "jour":
            day = data.get("jour") or today
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or day > today:
                raise ApiError(400, "Jour invalide.")
            players, label = self.day_players(con, day), day
        else:
            month = data.get("mois") or today[:7]
            if not re.fullmatch(r"\d{4}-\d{2}", month) or month > today[:7]:
                raise ApiError(400, "Mois invalide.")
            players, label = self.month_players(con, month), month
        me = None
        if kind == "joueurs":
            rows = [{"rank": k + 1, "name": r["pseudo"], "ville": self.places.villes.get(r["aav"]) if r["aav"] else None,
                     "points": r["points"], **({"time_s": r["time_s"]} if "time_s" in r else {"days": r["days"]}),
                     "_player": r["player"]} for k, r in enumerate(players)]
            if p is not None:
                me = next((r for r in rows if r["_player"] == p["id"]), None)
        else:
            rows = [{"rank": k + 1, **r} for k, r in enumerate(self.teams(players, kind))]
            if p is not None:
                team = self.places.team_of(p["commune"])
                key = team[{"villes": "aav", "departements": "dep", "regions": "region"}[kind]]
                me = next((r for r in rows if r["key"] == key), None)
        clean = lambda r: {k: v for k, v in r.items() if not k.startswith("_")}
        return {"type": kind, "periode": periode, "label": label, "count": len(rows),
                "rows": [clean(r) for r in rows[:50]], "me": clean(me) if me else None,
                "rules": {"best_days": BEST_DAYS, "team_top": TEAM_TOP, "team_min": TEAM_MIN}}


# --- HTTP ---------------------------------------------------------------------------------------------------------
def make_handler(api: Api, trust_proxy: bool):
    class Handler(BaseHTTPRequestHandler):
        server_version = "europeciv-api"
        sys_version = ""

        def _send(self, status: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _ip(self) -> str:
            if trust_proxy:
                return self.headers.get("CF-Connecting-IP") or (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip() or self.client_address[0]
            return self.client_address[0]

        def _go(self, method: str):
            u = urlsplit(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self._send(413, {"error": "Request too large."})
            body = self.rfile.read(n) if n else b""
            status, payload = api.handle(method, u.path, u.query, self.headers, body, self._ip())
            self._send(status, payload)

        def do_GET(self):
            self._go("GET")

        def do_POST(self):
            self._go("POST")

        def log_message(self, fmt, *args):  # no addresses in the logs
            sys.stderr.write(f"{self.command} {urlsplit(self.path).path} {args[1] if len(args) > 1 else ''}\n")

    return Handler


def load_secret(path: Path) -> bytes:
    if not path.exists():  # created owner-only from the start (never readable by others, even for an instant)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    return path.read_text().strip().encode()


def main(argv=None):
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="europeciv API")
    ap.add_argument("command", choices=["serve", "admin"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--port", type=int, default=8661)
    ap.add_argument("--data", type=Path, default=here / "data")
    ap.add_argument("--db", type=Path, default=here / "var" / "europeciv.sqlite3")
    ap.add_argument("--secret", type=Path, default=here / "var" / "secret")
    ap.add_argument("--trust-proxy", action="store_true", help="take the caller's address from CF-Connecting-IP")
    a = ap.parse_args(argv)
    a.db.parent.mkdir(parents=True, exist_ok=True)
    api = Api(a.db, load_secret(a.secret), a.data)
    if a.command == "serve":
        srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(api, a.trust_proxy))
        print(f"europeciv API on 127.0.0.1:{a.port}", flush=True)
        srv.serve_forever()
        return
    cmd, *rest = a.args or ["players"]
    con = api.connect()
    with con:
        if cmd == "players":
            for r in con.execute("SELECT id, pseudo, commune, banned, datetime(created, 'unixepoch') c FROM players ORDER BY id"):
                print(f"{r['id']:>5}  {r['pseudo']:<20} {r['commune'] or '-':<6} {'BANNI' if r['banned'] else ''} {r['c']}")
        elif cmd in ("ban", "unban") and rest:
            n = con.execute("UPDATE players SET banned = ? WHERE pkey = ?", (int(cmd == "ban"), fold(rest[0]))).rowcount
            print(f"{cmd}: {n} joueur(s)")
        elif cmd == "reset" and rest:
            # Delete a player's game of a day (today by default) so they can play it again (e.g. after a bug).
            day = rest[1] if len(rest) > 1 else api.today()
            p = con.execute("SELECT id FROM players WHERE pkey = ?", (fold(rest[0]),)).fetchone()
            g = p and con.execute("SELECT id FROM games WHERE day = ? AND player = ?", (day, p["id"])).fetchone()
            if g:
                con.execute("DELETE FROM guesses WHERE game = ?", (g["id"],))
                con.execute("DELETE FROM games WHERE id = ?", (g["id"],))
            print(f"reset {rest[0]} {day}: {'game deleted' if g else 'no game'}")
        elif cmd == "rename" and len(rest) == 2:
            new, why = check_pseudo(rest[1])
            if why:
                print(why)
            else:
                n = con.execute("UPDATE players SET pseudo = ?, pkey = ? WHERE pkey = ?", (new, fold(new), fold(rest[0]))).rowcount
                print(f"rename: {n} joueur(s)")
        elif cmd == "pin":
            # Store a day's draw now (today by default), before a pool update.
            day = rest[0] if rest else api.today()
            print(day, [c["name"] for c in api.picks(day)])
        elif cmd == "game" and rest:
            # A player's game of a day, round by round (distances and points only).
            day = rest[1] if len(rest) > 1 else api.today()
            p = con.execute("SELECT id FROM players WHERE pkey = ?", (fold(rest[0]),)).fetchone()
            g = p and con.execute("SELECT id FROM games WHERE day = ? AND player = ?", (day, p["id"])).fetchone()
            for r in (con.execute("SELECT round, km, pts, ms FROM guesses WHERE game = ? ORDER BY round", (g["id"],)) if g else []):
                print(f"  round {r['round'] + 1}: {'time out' if r['km'] is None else str(r['km']) + ' km'}, {r['pts']} pts, {r['ms'] / 1000:.1f} s")
            if not g:
                print("aucune partie")
        elif cmd == "top":
            for r in api.day_players(con, rest[0] if rest else api.today())[:20]:
                print(f"{r['points']:>5}  {r['time_s']:>6}s  {r['pseudo']}")
        else:
            ap.error("admin players | ban P | unban P | reset P [DAY] | rename P NEW | game P [DAY] | pin [DAY] | top [DAY]")


if __name__ == "__main__":
    main()
