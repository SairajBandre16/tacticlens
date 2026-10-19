"""Key-moment detector and importance ranking over a golden match (events + computed metrics).

Every moment carries an evidence pack built only from computed values (ids <moment>.eN). The first
evidence item names what the moment is about (shooter / player sent off / subbed team with the event ids,
or the club for window moments); counterfactual/rollouts.py relies on that and appends what-if evidence.
"""
from __future__ import annotations

from ..contracts import Evidence, Moment, WinProb
from ..metrics.clock import ev_clock
from ..metrics.flow import window_ppda
from ..metrics.xg import set_piece_shots, shot_geometry

BIG_CHANCE_XG = 0.25
BASE = {"goal": 0.5, "red_card": 0.45, "press_collapse": 0.4, "momentum_shift": 0.3, "sub_effect": 0.3,
        "big_chance": 0.2}
WINDOW = 15                # minutes compared before/after for press collapse and sub effect
PRESS_MIN_BEFORE = 1.4     # pressures per minute a team must sustain before a collapse counts
PRESS_DROP = 0.4           # after-rate must fall below this share of the before-rate
SUB_MIN_GAIN = 0.015       # threat per minute gained after a sub
MOMENTUM_SWING = 0.8       # momentum change (on the -1..1 scale) within MOMENTUM_SPAN minutes
MOMENTUM_SPAN = 10


def _swing(before: dict, after: dict) -> float:
    return max(abs(after[k] - before[k]) for k in ("home", "draw", "away"))


# Point events own their win-probability swing; window moments (press collapse, sub effect, momentum)
# span 10-15 minutes, so goals inside the window would dominate - they get a small WP weight instead.
WP_WEIGHT = {"goal": 0.5, "red_card": 0.5, "big_chance": 0.5}
WINDOW_WP_WEIGHT = 0.15


def _importance(kind: str, before: dict, after: dict, bonus: float = 0.0) -> float:
    w = WP_WEIGHT.get(kind, WINDOW_WP_WEIGHT)
    return round(min(1.0, BASE[kind] + bonus + w * min(1.0, _swing(before, after) / 0.6)), 4)


class _Ctx:
    def __init__(self, meta: dict, events: list[dict], metrics: dict):
        self.meta, self.events, self.m = meta, events, metrics
        self.teams = tuple(metrics["teams"])
        self.names = {p["id"]: p["name"] for side in ("home", "away") for p in meta[side]["players"]}
        self.club = {meta[s]["id"]: meta[s]["name"] for s in ("home", "away")}
        self.minute_t: dict[int, float] = {}
        for e in events:
            self.minute_t.setdefault(ev_clock(e), e["t"])
        self.last_minute = ev_clock(events[-1])
        self.moments: list[dict] = []

    def t_of(self, minute: int) -> float:
        minute = max(0, min(minute, self.last_minute))
        while minute not in self.minute_t:
            minute -= 1
        return self.minute_t[minute]

    def wp_min(self, minute: int) -> dict:
        row = self.m["wp"][max(0, min(minute, len(self.m["wp"]) - 1))]
        return {k: row[k] for k in ("home", "draw", "away")}

    def score_at(self, idx: int) -> str:
        h = sum(1 for e in self.events[:idx + 1] if e["type"] == "goal" and e["team"] == self.teams[0])
        a = sum(1 for e in self.events[:idx + 1] if e["type"] == "goal" and e["team"] == self.teams[1])
        return f"{h}-{a}"

    def add(self, kind: str, t0: float, t1: float, before: dict, after: dict, evidence: list[tuple],
            bonus: float = 0.0, team: str | None = None) -> None:
        swing_team = team or self.teams[0]
        side = "home" if swing_team == self.teams[0] else "away"
        club = self.club[swing_team]
        goals = [e["id"] for e in self.events if e["type"] == "goal" and e["t"] < t0]
        evidence = evidence + [("Minute", self.minute_of(t0), None, []),
                               ("Score at the start of the moment", self.score_at_t(t0), None, goals),
                               (f"Win probability for {club} before", round(100 * before[side], 1), "%", []),
                               (f"Win probability for {club} after", round(100 * after[side], 1), "%", []),
                               (f"Win probability change for {club}",
                                round(100 * (after[side] - before[side]), 1), "pp", [])]
        self.moments.append({"kind": kind, "t_start": t0, "t_end": t1, "before": before, "after": after,
                             "importance": _importance(kind, before, after, bonus), "evidence": evidence})

    def score_at_t(self, t: float) -> str:
        """Score before time t (goals strictly earlier)."""
        n = sum(1 for e in self.events if e["t"] < t)
        return self.score_at(n - 1) if n else "0-0"

    def minute_of(self, t: float) -> int:
        return max((ev_clock(e) for e in self.events if e["t"] <= t), default=0)


def _chain_start(ctx: _Ctx, i: int) -> float:
    """Start of the attacking move that ends with event i (same team, at most 25 s back)."""
    team, t_end = ctx.events[i]["team"], ctx.events[i]["t"]
    j = i
    while j > 0:
        e = ctx.events[j - 1]
        if t_end - e["t"] > 25 or (e["team"] != team and e["type"] != "pressure"):
            break
        j -= 1
    return ctx.events[j]["t"]


def _shots(ctx: _Ctx) -> None:
    sp = set_piece_shots(ctx.events)
    ev = ctx.events
    for i, e in enumerate(ev):
        if e["type"] != "shot":
            continue
        xg = ctx.m["shot_xg"][e["id"]]
        goal = e["outcome"] == "goal"
        if not goal and xg < BIG_CHANCE_XG:
            continue
        wp = ctx.m["event_wp"][ev[i + 1]["id"] if goal else e["id"]]
        chain = [x["id"] for x in ev if _chain_start(ctx, i) <= x["t"] <= e["t"] and x["team"] == e["team"]]
        items = [("Shooter", ctx.names.get(e["player_id"], e["player_id"]), None, [e["id"]]),
                 ("Team", ctx.club[e["team"]], None, [e["id"]]),
                 ("Shot xG", xg, "xG", [e["id"]]),
                 ("Shot outcome", e["outcome"], None, [e["id"]]),
                 ("Distance to goal", round(shot_geometry(e["x"], e["y"])[0], 1), "m", [e["id"]]),
                 ("Body part", e["body_part"], None, [e["id"]]),
                 ("Under pressure", "yes" if e["under_pressure"] else "no", None, [e["id"]]),
                 ("Set piece", "yes" if e["id"] in sp else "no", None, [e["id"]]),
                 ("Actions in the move", len(chain), None, chain)]
        if goal:
            items.append(("Score after goal", ctx.score_at(i + 1), None, [ev[i + 1]["id"]]))
            late = 0.1 if ev_clock(e) >= 80 else 0.0
            ctx.add("goal", _chain_start(ctx, i), ev[i + 1]["t"] + 10, wp["before"], wp["after"], items,
                    bonus=late, team=e["team"])
        else:
            ctx.add("big_chance", _chain_start(ctx, i), e["t"] + 5, wp["before"], wp["after"], items,
                    bonus=0.2 * xg, team=e["team"])


def _reds(ctx: _Ctx) -> None:
    for i, e in enumerate(ctx.events):
        if e["type"] != "card" or e["outcome"] not in ("red", "second_yellow"):
            continue
        foul = ctx.events[i - 1] if i and ctx.events[i - 1]["type"] == "foul" else e
        after_m = min(ev_clock(e) + WINDOW, ctx.last_minute)
        wp = ctx.m["event_wp"][e["id"]]
        items = [("Player sent off", ctx.names.get(e["player_id"], e["player_id"]), None, [e["id"]]),
                 ("Team", ctx.club[e["team"]], None, [e["id"]]),
                 ("Card", e["outcome"].replace("_", " "), None, [e["id"], foul["id"]]),
                 ("Players left on the pitch",
                  11 - sum(1 for x in ctx.events[:i + 1] if x["type"] == "card" and x["team"] == e["team"]
                           and x["outcome"] in ("red", "second_yellow")), None, [e["id"]]),
                 ("Minutes left to play", max(0, 90 - ev_clock(e)), "min", [e["id"]])]
        ctx.add("red_card", foul["t"], ctx.t_of(after_m), wp["before"], wp["after"], items, team=e["team"])


def _rates(ctx: _Ctx, series: list[float], m: int) -> tuple[float, float]:
    lo, hi = max(0, m - WINDOW), min(len(series), m + WINDOW)
    return sum(series[lo:m]) / max(1, m - lo), sum(series[m:hi]) / max(1, hi - m)


def _press_collapse(ctx: _Ctx) -> None:
    for s, team in enumerate(ctx.teams):
        counts = [0] * (ctx.last_minute + 1)
        for e in ctx.events:
            if e["type"] == "pressure" and e["team"] == team:
                counts[ev_clock(e)] += 1
        best = None
        for m in range(WINDOW + 5, ctx.last_minute - 10):
            before, after = _rates(ctx, counts, m)
            if before >= PRESS_MIN_BEFORE and after <= PRESS_DROP * before:
                drop = before - after
                if best is None or drop > best[0]:
                    best = (drop, m, before, after)
        if not best:
            continue
        _, m, before, after = best
        p0, _, _ = window_ppda(ctx.events, team, m - WINDOW, m)
        p1, _, _ = window_ppda(ctx.events, team, m, m + WINDOW)
        ids = [e["id"] for e in ctx.events if e["type"] == "pressure" and e["team"] == team
               and m - WINDOW <= ev_clock(e) < m + WINDOW]
        opp = ctx.teams[1 - s]
        thr0, thr1 = _rates(ctx, ctx.m["threat"][1 - s], m)
        items = [("Pressing team", ctx.club[team], None, []),
                 (f"Pressures per minute, {WINDOW} min before", round(before, 2), "per min", ids),
                 (f"Pressures per minute, {WINDOW} min after", round(after, 2), "per min", ids),
                 (f"PPDA, {WINDOW} min before", p0 if p0 is not None else "n/a", None, []),
                 (f"PPDA, {WINDOW} min after", p1 if p1 is not None else "n/a", None, []),
                 (f"{ctx.club[opp]} threat per minute before", round(thr0, 3), "xT+xG", []),
                 (f"{ctx.club[opp]} threat per minute after", round(thr1, 3), "xT+xG", [])]
        end = min(m + WINDOW, ctx.last_minute)
        ctx.add("press_collapse", ctx.t_of(m), ctx.t_of(end), ctx.wp_min(m), ctx.wp_min(end), items,
                bonus=0.3 * min(1.0, (before - after) / 2.0), team=team)


def _subs(ctx: _Ctx) -> None:
    seen: dict[str, int] = {}
    for e in ctx.events:
        if e["type"] != "sub":
            continue
        if ev_clock(e) - seen.get(e["team"], -99) < 3:  # a double change counts once
            continue
        seen[e["team"]] = ev_clock(e)
        s = ctx.teams.index(e["team"])
        m = ev_clock(e)
        before, after = _rates(ctx, ctx.m["threat"][s], m)
        if after - before < SUB_MIN_GAIN or ctx.last_minute - m < 8:
            continue
        subs = [x for x in ctx.events if x["type"] == "sub" and x["team"] == e["team"] and 0 <= ev_clock(x) - m < 3]
        end = min(m + WINDOW, ctx.last_minute)
        items = [("Team", ctx.club[e["team"]], None, [x["id"] for x in subs]),
                 ("Players on", ", ".join(ctx.names[x["related_player_id"]] for x in subs), None,
                  [x["id"] for x in subs]),
                 ("Players off", ", ".join(ctx.names[x["player_id"]] for x in subs), None, [x["id"] for x in subs]),
                 (f"Threat per minute, {WINDOW} min before", round(before, 3), "xT+xG", []),
                 (f"Threat per minute, {WINDOW} min after", round(after, 3), "xT+xG", [])]
        ctx.add("sub_effect", e["t"], ctx.t_of(end), ctx.wp_min(m), ctx.wp_min(end), items,
                bonus=min(0.3, 6 * (after - before)), team=e["team"])


def _momentum(ctx: _Ctx) -> None:
    mom = ctx.m["momentum"]
    last = -99
    for m in range(MOMENTUM_SPAN, len(mom)):
        window = mom[m - MOMENTUM_SPAN:m + 1]
        lo, hi = min(window), max(window)
        if hi - lo < MOMENTUM_SWING or m - last < 2 * MOMENTUM_SPAN:
            continue
        rising = window.index(lo) < window.index(hi)
        m0 = m - MOMENTUM_SPAN + (window.index(lo) if rising else window.index(hi))
        if mom[m] != (hi if rising else lo):  # wait for the peak of the swing
            continue
        last = m
        team = ctx.teams[0] if rising else ctx.teams[1]
        items = [("Team taking control", ctx.club[team], None, []),
                 ("Momentum at start", mom[m0], "index -1..1 (home +)", []),
                 ("Momentum at peak", mom[m], "index -1..1 (home +)", []),
                 ("Swing duration", m - m0, "min", [])]
        ctx.add("momentum_shift", ctx.t_of(m0), ctx.t_of(m), ctx.wp_min(m0), ctx.wp_min(m + 1), items,
                bonus=0.2 * min(1.0, (hi - lo - MOMENTUM_SWING) / 0.6), team=team)


def detect(meta: dict, events: list[dict], metrics: dict) -> list[Moment]:
    """All detected moments for a match, in time order, with ids <match>-M01.."""
    ctx = _Ctx(meta, events, metrics)
    for f in (_shots, _reds, _press_collapse, _subs, _momentum):
        f(ctx)
    ctx.moments.sort(key=lambda d: (d["t_start"], d["kind"]))
    out = []
    for n, d in enumerate(ctx.moments, 1):
        mid = f"{meta['match_id']}-M{n:02d}"
        ev = [Evidence(id=f"{mid}.e{k}", label=lab, value=val, unit=unit, event_ids=ids)
              for k, (lab, val, unit, ids) in enumerate(d["evidence"], 1)]
        out.append(Moment(id=mid, match_id=meta["match_id"], t_start=d["t_start"], t_end=d["t_end"],
                          kind=d["kind"], importance=d["importance"], wp_before=WinProb(**d["before"]),
                          wp_after=WinProb(**d["after"]), evidence=ev))
    return out


def top(moments: list[Moment], n: int = 8) -> list[Moment]:
    return sorted(moments, key=lambda m: (-m.importance, m.t_start))[:n]
