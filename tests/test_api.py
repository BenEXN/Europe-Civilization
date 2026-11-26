"""server/api.py: the daily challenge on the server, players and rankings (fake clock, temporary database)."""

import importlib.util
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pipeline.core.paths import WEB_DATA

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("franceciv_api", ROOT / "server" / "api.py")
api_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api_mod)

NEEDED = ["communes.json", "cities.json", "states.json", "defi.json"]


class Clock:
    def __init__(self, iso="2026-11-27T10:00:00"):
        self.t = datetime.fromisoformat(iso).replace(tzinfo=ZoneInfo("Europe/Paris")).timestamp()

    def __call__(self):
        return self.t


@unittest.skipUnless(all((WEB_DATA / f).exists() for f in NEEDED), "web data not built")
class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.places = api_mod.Places(WEB_DATA)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.api = api_mod.Api(Path(self.tmp.name) / "t.sqlite3", b"test-secret", WEB_DATA, now=self.clock)
        self.api.places = self.places
        self.ip = "203.0.113.7"

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, method, path, body=None, token=None, query="", ip=None, origin=None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if origin:
            headers["Origin"] = origin
        return self.api.handle(method, path, query, headers, json.dumps(body or {}).encode(), ip or self.ip)

    def join(self, pseudo, commune=None, ip=None):
        st, out = self.call("POST", "/api/joueur", {"pseudo": pseudo, "commune": commune}, ip=ip)
        self.assertEqual(st, 200, out)
        return out["token"]

    def play(self, token=None, offsets=(0, 0, 0, 0, 0), unranked=False):
        st, s = self.call("POST", "/api/defi/start", {"unranked": unranked}, token=token)
        self.assertEqual(st, 200, s)
        picks = self.api.picks(s["day"])
        for r, off in enumerate(offsets):
            self.assertEqual(s["phase"], "guess")
            self.assertEqual(s["name"], picks[r]["name"])
            self.clock.t += 5
            st, s = self.call("POST", "/api/defi/guess", {"game": s["game"], "round": r, "x": picks[r]["x"] + off,
                                                          "y": picks[r]["y"]}, token=token)
            self.assertEqual(st, 200, s)
            if r < 4:
                self.assertEqual(s["phase"], "reveal")
                st, s = self.call("POST", "/api/defi/next", {"game": s["game"]}, token=token)
        self.assertEqual(s["phase"], "done")
        return s

    def test_points_curve(self):
        p = api_mod.points
        self.assertEqual(p(0), 1000)
        self.assertEqual(p(5), 1000)
        self.assertTrue(670 < p(100) < 700)
        self.assertTrue(300 < p(300) < 315)
        self.assertLess(p(1000), 25)

    def test_pseudos(self):
        ok = api_mod.check_pseudo
        self.assertEqual(ok("  Jean   Dupont ")[0], "Jean Dupont")
        self.assertEqual(ok("Élodie_42")[0], "Élodie_42")
        for bad in ["ab", "x" * 21, "1234", "<script>", "admin", "Gros con", "SaLoPe99", "-abc", "a​b"]:
            self.assertIsNone(ok(bad)[0], bad)
        self.assertIsNotNone(ok("Conflans")[0])  # "con" is only blocked as a word

    def test_picks_are_secret_stable_and_fresh(self):
        a = self.api.picks("2026-12-01")
        self.assertEqual([c["code"] for c in a], [c["code"] for c in self.api.picks("2026-12-01")])
        self.assertEqual([c["name"] for c in a[:2]], [c["name"] for c in a[:2]])
        other = api_mod.Api(Path(self.tmp.name) / "o.sqlite3", b"another-secret", WEB_DATA, now=self.clock)
        self.assertNotEqual([c["code"] for c in a], [c["code"] for c in other.picks("2026-12-01")])
        seen, d0 = [], date(2027, 1, 1)
        for d in range(60):
            seen += [c["code"] for c in self.api.picks((d0 + timedelta(days=d)).isoformat())]
        self.assertEqual(len(seen), len(set(seen)), "a commune came back within 60 days")

    def test_a_played_day_keeps_its_draw_when_the_pool_changes(self):
        today = self.api.today()
        before = [c["code"] for c in self.api.picks(today)]
        # a new pool (data update), as after a server restart
        fresh = api_mod.Api(Path(self.tmp.name) / "t.sqlite3", b"test-secret", WEB_DATA, now=self.clock)
        fresh.places = self.places
        fresh.places.pool = {t: list(reversed(rows)) for t, rows in self.places.pool.items()}
        try:
            self.assertEqual([c["code"] for c in fresh.picks(today)], before)  # stored: unchanged
            tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
            self.assertEqual(len(fresh.picks(tomorrow)), 5)  # not stored yet: drawn from the new pool
        finally:
            fresh.places.pool = {t: list(reversed(rows)) for t, rows in fresh.places.pool.items()}

    def test_rankings_refresh_when_a_game_ends(self):
        a, b = self.join("Alice"), self.join("Bruno", ip="198.51.100.9")
        self.play(a)
        st, board = self.call("GET", "/api/classement", query="type=joueurs&periode=jour")
        self.assertEqual(board["count"], 1)
        self.play(b, offsets=(0, 0, 0, 0, 50))
        st, board = self.call("GET", "/api/classement", query="type=joueurs&periode=jour")
        self.assertEqual(board["count"], 2)  # the cache dropped when Bruno finished

    def test_game_flow_and_hidden_answers(self):
        st, s = self.call("POST", "/api/defi/start")
        self.assertEqual(st, 200)
        self.assertNotIn("x", json.dumps(s["results"]))  # nothing answered, nothing revealed
        text = json.dumps(s)
        for c in self.api.picks(s["day"])[1:]:
            self.assertNotIn(c["name"], text)
        s = self.play(offsets=(0, 35, 175, 700, 3500))
        pts = [r["pts"] for r in s["results"]]
        self.assertEqual(pts[0], 1000)
        self.assertTrue(pts[0] > pts[1] > pts[2] > pts[3] > pts[4])
        self.assertFalse(s["ranked"])

    def test_timeout_scores_zero(self):
        st, s = self.call("POST", "/api/defi/start")
        self.clock.t += api_mod.LIMIT_S + api_mod.GRACE_S + 1
        c = self.api.picks(s["day"])[0]
        st, s = self.call("POST", "/api/defi/guess", {"game": s["game"], "round": 0, "x": c["x"], "y": c["y"]})
        self.assertEqual(s["results"][0]["pts"], 0)
        self.assertTrue(s["results"][0]["timeout"])

    def test_one_ranked_game_a_day(self):
        tok = self.join("Mathilde", "FR_69123")
        first = self.play(tok, offsets=(0, 0, 0, 0, 0))
        self.assertEqual(first["total"], 5000)
        self.assertEqual(first["rank"], {"pos": 1, "of": 1})
        st, again = self.call("POST", "/api/defi/start", {}, token=tok)
        self.assertEqual(again["game"], first["game"])  # the same game, already done
        replay = self.play(tok, offsets=(9999, 9999, 9999, 9999, 9999), unranked=True)
        self.assertFalse(replay["ranked"])
        st, board = self.call("GET", "/api/classement", query="type=joueurs&periode=jour", token=tok)
        self.assertEqual(board["rows"][0]["points"], 5000)
        self.assertEqual(board["me"]["rank"], 1)

    def test_pseudo_taken_and_registration_limit(self):
        self.join("Paul")
        st, out = self.call("POST", "/api/joueur", {"pseudo": "paul"})
        self.assertEqual(st, 409)
        for k in range(4):
            self.join(f"Joueur{k}")
        st, out = self.call("POST", "/api/joueur", {"pseudo": "Joueur9"})
        self.assertEqual(st, 429)
        self.join("Joueur9", ip="198.51.100.1")

    def test_rankings_daily_tiebreak_and_teams(self):
        lyon = [self.join(f"Lyonnais{k}", "FR_69123", ip=f"10.0.0.{k}") for k in range(4)]
        brest = [self.join(f"Berliner{k}", "DE_11000000", ip=f"10.0.1.{k}") for k in range(2)]
        for k, tok in enumerate(lyon):
            self.play(tok, offsets=(k * 30, 0, 0, 0, 0))
        for tok in brest:
            self.play(tok)
        st, villes = self.call("GET", "/api/classement", query="type=villes&periode=jour")
        names = [r["name"] for r in villes["rows"]]
        self.assertIn("Lyon", names)
        self.assertNotIn("Berlin", names)  # two players: not ranked yet
        st, players = self.call("GET", "/api/classement", query="type=joueurs&periode=jour")
        self.assertEqual(players["rows"][0]["ville"] in ("Lyon", "Berlin"), True)
        self.assertEqual(players["count"], 6)
        st, deps = self.call("GET", "/api/classement", query="type=departements&periode=jour")
        self.assertEqual(deps["rows"][0]["name"], "France (FR)")
        st, regs = self.call("GET", "/api/classement", query="type=regions&periode=mois")
        self.assertEqual(regs["rows"][0]["name"], "Western Europe")

    def test_month_counts_best_days(self):
        tok = self.join("Assidu", "FR_75056")
        for d in range(22):
            self.clock.t = Clock(f"2026-12-{d + 1:02d}T09:00:00").t
            self.play(tok, offsets=(0, 0, 0, 0, 3500 if d < 2 else 0))
        st, m = self.call("GET", "/api/classement", query="type=joueurs&periode=mois&mois=2026-12", token=tok)
        self.assertEqual(m["me"]["points"], 20 * 5000)
        self.assertEqual(m["me"]["days"], 22)
        st, me = self.call("GET", "/api/defi", token=tok)
        self.assertEqual(me["me"]["streak"], 22)

    def test_guards(self):
        st, out = self.call("POST", "/api/joueur", {"pseudo": "Eve"}, origin="https://evil.example")
        self.assertEqual(st, 403)
        st, out = self.call("POST", "/api/defi/guess", {"game": "nope", "round": 0, "x": 1, "y": 1})
        self.assertEqual(st, 404)
        st, s = self.call("POST", "/api/defi/start")
        st, out = self.call("POST", "/api/defi/guess", {"game": s["game"], "round": 0, "x": "1e999", "y": 2})
        self.assertEqual(st, 400)
        st, out = self.call("GET", "/api/classement", query="type=x")
        self.assertEqual(st, 400)
        st, out = self.call("GET", "/api/defi", token="forged")
        self.assertEqual(st, 401)


if __name__ == "__main__":
    unittest.main()
