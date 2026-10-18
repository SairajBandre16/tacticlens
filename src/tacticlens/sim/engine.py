"""Possession-chain match simulator on a 12x8 zone grid.

Coordinates follow the Event contract: 0-100 on both axes, the acting team attacks towards x=100.
Defensive events (pressure, tackle, interception, foul) are therefore mirrored for the defending team.

Two random streams keep fast mode and full mode identical: `rng` drives every decision (and shot
locations), `crng` only jitters coordinates inside zones. Fast mode skips coordinates and Event
construction but consumes `rng` exactly like full mode, so the same seed gives the same match.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Literal

from .teams import STYLE_KEYS, Player, Team

COLS, ROWS = 12, 8
ZW, ZH = 100.0 / COLS, 100.0 / ROWS
HALF = 2700.0

Side = Literal["home", "away"]

# Base probability of shooting per zone (col 0 = own goal line). Rows 2-5 are central.
_SHOT_COL = [0, 0, 0, 0, 0, 0, 0, 0, 0.004, 0.022, 0.10, 0.25]
_SHOT_ROW = [0.25, 0.5, 0.9, 1.0, 1.0, 0.9, 0.5, 0.25]
SHOT_P = [[_SHOT_COL[c] * _SHOT_ROW[r] for r in range(ROWS)] for c in range(COLS)]
# How hard the defending side presses by ball column (attacker's perspective): high press = attacker deep.
PRESS_ZONE = [1.0, 1.0, 1.0, 0.95, 0.85, 0.75, 0.7, 0.65, 0.6, 0.6, 0.65, 0.7]

# Player pick weights per (pitch band, position).
_BAND_W = [{"GK": 1, "DF": 6, "MF": 3, "FW": 1}, {"GK": 0, "DF": 2, "MF": 5, "FW": 2},
           {"GK": 0, "DF": 1, "MF": 4, "FW": 6}]
_SHOOT_W = {"GK": 0, "DF": 1, "MF": 3, "FW": 7}
_HEAD_W = {"GK": 0, "DF": 4, "MF": 1, "FW": 4}


@dataclass(frozen=True)
class Beat:
    """Scripted story beat applied at `minute`. Style values are absolute (0..1)."""
    minute: int
    side: Side
    kind: Literal["red_card", "sub", "style"]
    off: int | None = None  # shirt numbers for subs
    on: int | None = None
    style: tuple[tuple[str, float], ...] = ()
    note: str = ""

    def to_dict(self) -> dict:
        return {"minute": self.minute, "side": self.side, "kind": self.kind, "off": self.off,
                "on": self.on, "style": dict(self.style), "note": self.note}


@dataclass(frozen=True)
class GoalRec:
    t: float
    minute: int
    side: Side
    player_id: str
    set_piece: bool


@dataclass(frozen=True)
class ShotRec:
    t: float
    minute: int
    side: Side
    x: float
    y: float
    header: bool
    under_pressure: bool
    set_piece: bool
    outcome: str
    p_true: float


@dataclass
class MatchResult:
    match_id: str
    home: Team
    away: Team
    seed: int
    score: tuple[int, int]
    goals: list[GoalRec]
    shots: list[ShotRec]
    cards: list[tuple[int, Side, str, str]]  # minute, side, player_id, outcome
    reds: list[tuple[int, Side, float]]  # minute, side, t
    subs: list[tuple[int, Side, str, str]]  # minute, side, off, on
    counters: dict[str, list[int]]  # per side [home, away]
    duration: float
    events: list[dict] | None = None
    half_time: float = 0.0  # t at the end of the first half

    def score_at(self, minute: int) -> tuple[int, int]:
        h = sum(1 for g in self.goals if g.side == "home" and g.minute < minute)
        a = sum(1 for g in self.goals if g.side == "away" and g.minute < minute)
        return h, a


class _SideState:
    def __init__(self, team: Team, idx: int, home: bool):
        self.team, self.idx = team, idx
        self.style = {k: getattr(team.style, k) for k in STYLE_KEYS}
        if home:
            self.style["quality"] = min(1.0, self.style["quality"] + 0.03)
        self.on: list[Player] = list(team.starters)
        self.bench: list[Player] = list(team.bench)
        self.yellows: set[str] = set()
        self.pending_red = False
        self.reserved: set[int | None] = set()  # shirt numbers used by scripted subs
        self._pools()

    def _pools(self) -> None:
        def pool(w: dict[str, int]) -> list[str]:
            return [p.id for p in self.on for _ in range(w[p.pos])] or [self.on[0].id]
        self.band = [pool(w) for w in _BAND_W]
        self.shooters, self.headers = pool(_SHOOT_W), pool(_HEAD_W)
        self.gk = next((p.id for p in self.on if p.pos == "GK"), self.on[0].id)

    def send_off(self, pid: str) -> None:
        self.on = [p for p in self.on if p.id != pid]
        self._pools()

    def substitute(self, off: Player, on: Player) -> None:
        self.on = [on if p.id == off.id else p for p in self.on]
        self.bench = [p for p in self.bench if p.id != on.id]
        self._pools()


def _clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


def p_goal_true(x: float, y: float, header: bool, under_pressure: bool, q_att: float = 0.5,
                q_def: float = 0.5, man_adv: int = 0) -> float:
    """Ground-truth scoring probability used by the simulator (the xG model must learn it)."""
    dx, dy = (100.0 - x) * 1.05, (y - 50.0) * 0.68
    d = math.hypot(dx, dy)
    half_goal = 3.66
    angle = math.atan2(2 * half_goal * dx, dx * dx + dy * dy - half_goal * half_goal)
    if angle < 0:
        angle += math.pi
    logit = -0.1 - 0.16 * d + 0.6 * angle
    logit += -0.9 * header - 0.4 * under_pressure + 1.2 * (q_att - 0.5) - 0.8 * (q_def - 0.5)
    logit += 0.15 * man_adv
    return 1.0 / (1.0 + math.exp(-logit))


class MatchSim:
    def __init__(self, home: Team, away: Team, seed: int, match_id: str = "M000",
                 beats: tuple[Beat, ...] | list[Beat] = (), fast: bool = False):
        self.home, self.away, self.seed, self.match_id, self.fast = home, away, seed, match_id, fast
        self.rng = random.Random(seed)
        self.crng = random.Random(seed * 7919 + 17)
        self.sides = [_SideState(home, 0, True), _SideState(away, 1, False)]
        self.beats = sorted(beats, key=lambda b: b.minute)
        for b in self.beats:
            if b.kind == "sub":
                self.sides[0 if b.side == "home" else 1].reserved |= {b.off, b.on}
        self.events: list[dict] = []
        self.goals: list[GoalRec] = []
        self.shots: list[ShotRec] = []
        self.cards: list = []
        self.reds: list = []
        self.subs: list = []
        self.score = [0, 0]
        self.counters = {k: [0, 0] for k in ("passes", "passes_ok", "shots", "on_target", "fouls",
                                              "cards", "corners", "tackles", "interceptions",
                                              "pressures", "dribbles", "clearances", "free_kicks")}
        self.t = 0.0
        self.period = 1
        self.p_start = 0.0
        self.poss, self.col, self.row = 0, 5, 3
        self.bx, self.by = 50.0, 50.0
        self.n_actions = 0
        self.sp_until = -1  # set-piece window (action index)
        self.from_cross = False
        self._plan_subs()

    # ---------- helpers ----------
    @property
    def minute(self) -> int:
        m = int((self.t - self.p_start) // 60)
        return m if self.period == 1 else 45 + m

    def _side_name(self, idx: int) -> Side:
        return "home" if idx == 0 else "away"

    def _pick(self, pool: list[str]) -> str:
        return pool[int(self.rng.random() * len(pool))]

    def _emit(self, side: int, etype: str, pid: str | None, x: float, y: float, *, end=None,
              outcome=None, up=False, body=None, rel=None) -> None:
        if self.fast:
            return
        ev = {"id": f"{self.match_id}-E{len(self.events) + 1:05d}", "match_id": self.match_id,
              "t": round(self.t, 1), "period": self.period, "minute": self.minute,
              "team": self.sides[side].team.id, "player_id": pid, "related_player_id": rel,
              "type": etype, "x": round(x, 1), "y": round(y, 1),
              "end_x": round(end[0], 1) if end else None, "end_y": round(end[1], 1) if end else None,
              "outcome": outcome, "under_pressure": up, "body_part": body, "xg": None}
        self.events.append(ev)

    def _zone_xy(self, col: int, row: int) -> tuple[float, float]:
        if self.fast:
            return 0.0, 0.0
        cr = self.crng.random
        return (col + 0.1 + 0.8 * cr()) * ZW, (row + 0.1 + 0.8 * cr()) * ZH

    def _turnover(self, col: int, row: int) -> None:
        """Defending side wins the ball at attacker-perspective zone (col, row)."""
        self.poss = 1 - self.poss
        self.col, self.row = 11 - col, 7 - row
        self.bx, self.by = 100.0 - self.bx, 100.0 - self.by
        self.from_cross = False

    def _set_ball(self, side: int, col: int, row: int, xy: tuple[float, float] | None = None) -> None:
        self.poss, self.col, self.row = side, col, row
        self.bx, self.by = xy if xy else self._zone_xy(col, row)
        self.from_cross = False

    def _dead(self, lo: float, hi: float) -> None:
        self.t += lo + (hi - lo) * self.rng.random()

    def _man_adv(self, a: int) -> int:
        return len(self.sides[a].on) - len(self.sides[1 - a].on)

    # ---------- substitutions and beats ----------
    def _plan_subs(self) -> None:
        r = self.rng.random
        self.sub_plan: list[tuple[int, int]] = []  # (minute, side)
        for s in (0, 1):
            scripted = sum(1 for b in self.beats if b.kind == "sub" and b.side == self._side_name(s))
            n = max(0, 3 + int(r() * 3) - scripted)
            self.sub_plan += [(55 + int(r() * 31), s) for _ in range(n)]
        self.sub_plan.sort()

    def _do_sub(self, s: int, off: Player | None = None, on: Player | None = None) -> None:
        st = self.sides[s]
        if off is None:  # automatic sub: never touch players reserved by a scripted sub beat
            cands = ([p for p in st.on if p.pos in ("MF", "FW") and p.number not in st.reserved]
                     or [p for p in st.on if p.pos != "GK" and p.number not in st.reserved])
            if not cands:
                return
            off = cands[int(self.rng.random() * len(cands))]
        if on is None:
            free = [p for p in st.bench if p.number not in st.reserved]
            same = [p for p in free if p.pos == off.pos] or [p for p in free if p.pos != "GK"]
            if not same:
                return
            on = same[int(self.rng.random() * len(same))]
        if off not in st.on or on not in st.bench:
            return
        st.substitute(off, on)
        self.subs.append((self.minute, self._side_name(s), off.id, on.id))
        self._emit(s, "sub", off.id, 50.0, 0.0, rel=on.id)
        self._dead(20, 35)

    def _apply_due(self) -> None:
        m = self.minute
        while self.beats and self.beats[0].minute <= m:
            b = self.beats.pop(0)
            s = 0 if b.side == "home" else 1
            st = self.sides[s]
            if b.kind == "red_card":
                st.pending_red = True
            elif b.kind == "sub":
                team = st.team
                self._do_sub(s, team.player(b.off) if b.off else None, team.player(b.on) if b.on else None)
            for k, v in b.style:
                st.style[k] = v
        while self.sub_plan and self.sub_plan[0][0] <= m and self.period == 2:
            _, s = self.sub_plan.pop(0)
            self._do_sub(s)

    # ---------- main loop ----------
    def run(self) -> MatchResult:
        r = self.rng.random
        for period in (1, 2):
            self.period = period
            self.p_start = self.t
            stoppage = 60 + 180 * r() if period == 1 else 120 + 300 * r()
            end = self.p_start + HALF + stoppage
            self._kickoff(0 if period == 1 else 1)
            while self.t < end:
                self._apply_due()
                self._step()
            if period == 1:
                half_time = self.t
        return MatchResult(self.match_id, self.home, self.away, self.seed, tuple(self.score),
                           self.goals, self.shots, self.cards, self.reds, self.subs, self.counters,
                           round(self.t, 1), None if self.fast else self.events, half_time)

    def _kickoff(self, side: int) -> None:
        self._set_ball(side, 5, 3 + int(self.rng.random() * 2), (50.0, 50.0))

    def _step(self) -> None:
        r = self.rng.random
        a = self.poss
        A, D = self.sides[a], self.sides[1 - a]
        col, row = self.col, self.row
        self.n_actions += 1
        if D.pending_red:
            D.pending_red = False
            self._foul(1 - a, forced_red=True)
            return
        minute = self.minute
        fatigue = 1.0 - 0.25 * max(0.0, (minute - 60) / 30.0)
        press = D.style["press_intensity"] * fatigue
        up = False
        if r() < 0.05 + 0.40 * press * PRESS_ZONE[col]:
            up = True
            D_pid = self._pick(D.band[0 if col >= 8 else 1 if col >= 4 else 2])
            self.counters["pressures"][1 - a] += 1
            self._emit(1 - a, "pressure", D_pid, 100.0 - self.bx, 100.0 - self.by)
            if r() < 0.04 + 0.05 * press:
                self._foul(1 - a, D_pid)
                return
        qa, qd = A.style["quality"], D.style["quality"]
        man = self._man_adv(a)
        ps = SHOT_P[col][row] * (1.0 + 0.9 * (qa - qd) + 0.15 * man) * (2.2 if self.from_cross else 1.0)
        if ps > 0 and r() < ps:
            self._shot(a, up, header=self.from_cross and r() < 0.7, set_piece=self.n_actions <= self.sp_until)
            return
        if col <= 1 and up and r() < 0.35:
            self._clearance(a, up)
            return
        if r() < 0.045 + 0.05 * (col >= 6):
            self._dribble(a, up)
            return
        self._pass(a, up)

    # ---------- actions ----------
    def _advance_time(self, base: float, tempo: float) -> None:
        self.t += base * (0.55 + self.rng.expovariate(1.0) * (1.25 - 0.7 * tempo))

    def _pass(self, a: int, up: bool, etype: str = "pass") -> None:
        r, g = self.rng.random, self.rng.gauss
        A, D = self.sides[a], self.sides[1 - a]
        st = A.style
        col, row = self.col, self.row
        band = 0 if col <= 3 else 1 if col <= 7 else 2
        pid = self._pick(A.band[band])
        mu = (0.35 + 1.9 * st["directness"]) * (0.4 if col >= 9 else 1.0)
        tc = _clamp(col + int(round(g(mu, 1.1 + 0.9 * st["directness"]))), 0, 11)
        tr = _clamp(row + int(round(g(0.0, 0.9 + 1.4 * st["width"]))), 0, 7)
        if col >= 8 and st["width"] > r() * 1.6 and row in (2, 3, 4, 5):
            tr = 0 if row <= 3 else 7  # switch to the flank
        dist = math.hypot(tc - col, 0.8 * (tr - row))
        cross = col >= 8 and row in (0, 1, 6, 7) and tc >= 10 and 2 <= tr <= 5
        if cross:
            p_ok = 0.36 + 0.2 * (st["quality"] - 0.5)
        else:
            p_ok = (0.955 + 0.16 * (st["quality"] - 0.5) - 0.05 * (D.style["quality"] - 0.5)
                    - 0.026 * dist - 0.11 * up - 0.06 * (tc >= 9) - 0.035 * D.style["press_intensity"]
                    + 0.02 * self._man_adv(a) + 0.03 * (tc < col))
        ok = r() < p_ok
        rel = self._pick(A.band[0 if tc <= 3 else 1 if tc <= 7 else 2]) if ok else None
        sx, sy = self.bx, self.by
        ex, ey = self._zone_xy(tc, tr)
        if etype == "pass":
            self.counters["passes"][a] += 1
            self.counters["passes_ok"][a] += ok
        self._emit(a, etype, pid, sx, sy, end=(ex, ey), outcome="success" if ok else "fail", up=up,
                   body="foot", rel=rel)
        self._advance_time(2.9 if dist > 3 else 2.2, st["tempo"])
        if ok:
            self.col, self.row, self.bx, self.by = tc, tr, ex, ey
            self.from_cross = cross
            return
        self.bx, self.by = ex, ey
        if r() < 0.6 or tc < 9:
            if r() < 0.7:
                dpid = self._pick(D.band[0 if tc >= 8 else 1 if tc >= 4 else 2])
                self.counters["interceptions"][1 - a] += 1
                self._emit(1 - a, "interception", dpid, 100.0 - ex, 100.0 - ey, outcome="success")
                self._turnover(tc, tr)
            else:  # throw-in to the defending side
                self._dead(8, 18)
                self._turnover(tc, 0 if tr <= 3 else 7)
                self.bx, self.by = self._zone_xy(self.col, self.row)
        elif r() < 0.2:
            self._dead(15, 30)
            self._corner(a)
        else:  # goal kick
            self._dead(15, 30)
            self._set_ball(1 - a, 1, 3 + int(r() * 2))

    def _dribble(self, a: int, up: bool) -> None:
        r = self.rng.random
        A, D = self.sides[a], self.sides[1 - a]
        col = self.col
        pid = self._pick(A.band[0 if col <= 3 else 1 if col <= 7 else 2])
        ok = r() < 0.6 + 0.3 * (A.style["quality"] - D.style["quality"]) - 0.1 * up
        nc = _clamp(col + 1, 0, 11) if ok else col
        nr = _clamp(self.row + int(round(self.rng.gauss(0, 0.8))), 0, 7)
        ex, ey = self._zone_xy(nc, nr)
        self.counters["dribbles"][a] += 1
        self._emit(a, "dribble", pid, self.bx, self.by, end=(ex, ey), outcome="success" if ok else "fail", up=up)
        self._advance_time(2.4, A.style["tempo"])
        if ok:
            self.col, self.row, self.bx, self.by = nc, nr, ex, ey
            self.from_cross = False
            return
        dpid = self._pick(D.band[0 if col >= 8 else 1 if col >= 4 else 2])
        if r() < 0.25:
            self._foul(1 - a, dpid)
            return
        self.counters["tackles"][1 - a] += 1
        self._emit(1 - a, "tackle", dpid, 100.0 - self.bx, 100.0 - self.by, outcome="success")
        self._turnover(col, self.row)

    def _clearance(self, a: int, up: bool) -> None:
        r = self.rng.random
        A = self.sides[a]
        pid = self._pick(A.band[0])
        tc, tr = 5 + int(r() * 4), int(r() * 8)
        ex, ey = self._zone_xy(tc, tr)
        self.counters["clearances"][a] += 1
        keep = r() < 0.4
        self._emit(a, "clearance", pid, self.bx, self.by, end=(ex, ey), outcome="success" if keep else "fail",
                   up=up, body="head" if r() < 0.4 else "foot")
        self._advance_time(3.0, A.style["tempo"])
        self.bx, self.by = ex, ey
        if keep:
            self.col, self.row = tc, tr
        else:
            self._turnover(tc, tr)

    def _foul(self, d: int, pid: str | None = None, forced_red: bool = False) -> None:
        """Defending side `d` fouls; the attacking side gets a free kick at the ball position."""
        r = self.rng.random
        D, a = self.sides[d], 1 - d
        if pid is None:
            dfs = [p.id for p in D.on if p.pos == "DF"] or [p.id for p in D.on]
            pid = dfs[int(r() * len(dfs))]
        victim = self._pick(self.sides[a].band[0 if self.col <= 3 else 1 if self.col <= 7 else 2])
        if self.col >= 10 and 2 <= self.row <= 5:  # keep fouls outside the box (no penalties modelled)
            self.col = 9
            self.bx = min(self.bx, 9.9 * ZW)
        self.counters["fouls"][d] += 1
        self._emit(d, "foul", pid, 100.0 - self.bx, 100.0 - self.by, rel=victim)
        card = None
        if forced_red:
            card = "red"
        elif r() < (0.05 if pid in D.yellows else 0.16):  # booked players tread carefully
            card = "second_yellow" if pid in D.yellows else "yellow"
        elif r() < 0.0015:
            card = "red"
        if card:
            self.counters["cards"][d] += 1
            self.cards.append((self.minute, self._side_name(d), pid, card))
            self._emit(d, "card", pid, 100.0 - self.bx, 100.0 - self.by, outcome=card)
            if card == "yellow":
                D.yellows.add(pid)
            else:
                self.reds.append((self.minute, self._side_name(d), round(self.t, 1)))
                D.send_off(pid)
        self._dead(20, 40 if not card else 70)
        self._free_kick(a)

    def _free_kick(self, a: int) -> None:
        r = self.rng.random
        A = self.sides[a]
        self.counters["free_kicks"][a] += 1
        self.sp_until = self.n_actions + 3
        if self.col >= 9 and 2 <= self.row <= 5 and r() < 0.45:
            pid = self._pick(A.shooters)
            self._emit(a, "free_kick", pid, self.bx, self.by, end=(100.0, 50.0), outcome="success", body="foot")
            self._shot(a, False, header=False, set_piece=True, direct_fk=True, pid=pid)
            return
        if self.col >= 8 and r() < 0.6:  # delivered into the box like a cross
            self.row = 0 if self.row <= 3 else 7
        self._pass(a, False, etype="free_kick")

    def _corner(self, a: int) -> None:
        r = self.rng.random
        A, D = self.sides[a], self.sides[1 - a]
        self.counters["corners"][a] += 1
        self.sp_until = self.n_actions + 3
        top = r() < 0.5
        cx, cy = 99.5, 0.5 if top else 99.5
        pid = self._pick(A.band[2])
        ok = r() < 0.4 + 0.15 * (A.style["quality"] - D.style["quality"])
        ex, ey = self._zone_xy(10 + int(r() * 2), 2 + int(r() * 4))
        self._emit(a, "corner", pid, cx, cy, end=(ex, ey), outcome="success" if ok else "fail", body="foot")
        self._advance_time(2.5, 0.5)
        self.bx, self.by = ex, ey
        if ok:
            self.col, self.row = 10 + int(r() * 2), 2 + int(r() * 4)
            if r() < 0.55:
                self._shot(a, r() < 0.5, header=r() < 0.75, set_piece=True)
                return
            self.from_cross = False
            return
        dpid = self._pick(D.headers)
        self.counters["clearances"][1 - a] += 1
        self._emit(1 - a, "clearance", dpid, 100.0 - ex, 100.0 - ey, end=self._zone_xy(5, 3), body="head",
                   outcome="success")
        if r() < 0.5:
            self._set_ball(1 - a, 3 + int(r() * 3), int(r() * 8))
        else:
            self._set_ball(a, 7 + int(r() * 2), int(r() * 8))

    def _shot(self, a: int, up: bool, *, header: bool, set_piece: bool, direct_fk: bool = False,
              pid: str | None = None) -> None:
        r = self.rng.random
        A, D = self.sides[a], self.sides[1 - a]
        col, row = self.col, self.row
        if header:
            x, y = 88.0 + 8.0 * r(), 36.0 + 28.0 * r()
            pid = pid or self._pick(A.headers)
        else:
            x, y = (col + r()) * ZW, (row + r()) * ZH
            pid = pid or self._pick(A.shooters)
        p = p_goal_true(x, y, header, up, A.style["quality"], D.style["quality"], self._man_adv(a))
        if direct_fk:
            p *= 0.7
        u = r()
        if u < p:
            outcome = "goal"
        else:
            v = r()
            blocked = 0.0 if direct_fk else 0.24 + 0.1 * up
            outcome = ("blocked" if v < blocked else "saved" if v < blocked + 0.29
                       else "post" if v < blocked + 0.32 else "off_target")
        self.counters["shots"][a] += 1
        self.counters["on_target"][a] += outcome in ("goal", "saved")
        self.shots.append(ShotRec(round(self.t, 1), self.minute, self._side_name(a), round(x, 1), round(y, 1),
                                  header, up, set_piece, outcome, p))
        end = (100.0, 45.0 + 10.0 * r()) if outcome in ("goal", "saved") else (100.0, y)
        if not direct_fk and not self.fast:
            self.bx, self.by = x, y
        self._emit(a, "shot", pid, x, y, end=end, outcome=outcome, up=up, body="head" if header else "foot")
        self.t += 1.0
        self.from_cross = False
        if outcome == "goal":
            self.score[a] += 1
            self.goals.append(GoalRec(round(self.t, 1), self.minute, self._side_name(a), pid, set_piece))
            self._emit(a, "goal", pid, x, y, body="head" if header else "foot")
            self._dead(55, 85)
            self._kickoff(1 - a)
        elif outcome == "saved":
            if r() < 0.25:
                self._dead(15, 25)
                self._corner(a)
            else:
                self._dead(5, 12)
                self._set_ball(1 - a, 0, 3 + int(r() * 2))
        elif outcome == "blocked":
            u = r()
            if u < 0.28:
                self._dead(15, 25)
                self._corner(a)
            elif u < 0.7:
                self._set_ball(a, 9, _clamp(row + int(round(self.rng.gauss(0, 1))), 0, 7))
            else:
                self._set_ball(1 - a, 2, 7 - row)
        else:
            self._dead(18, 30)
            self._set_ball(1 - a, 1, 3 + int(r() * 2))


def simulate(home: Team, away: Team, seed: int, match_id: str = "M000",
             beats: tuple[Beat, ...] | list[Beat] = (), fast: bool = False) -> MatchResult:
    return MatchSim(home, away, seed, match_id, beats, fast).run()
