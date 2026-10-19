"""Monte-Carlo counterfactuals: re-simulate the rest of a golden match from a moment with one thing changed.

The golden match is replayed (same seed, same beats) until the moment, which reproduces its exact state:
score, players on the pitch, team styles, pending beats and planned subs. From that snapshot N rollouts
continue the match with fresh random streams, once as played (factual) and once with the change.
Rollout i uses the same seed in both arms (common random numbers), so the paired difference isolates the
change. The 80% interval is a bootstrap interval of the mean paired difference.

Moments are mapped to the events they are about through their first evidence item (see detector.py).
"""
from __future__ import annotations

import copy
import random
from dataclasses import replace
from typing import Callable

import numpy as np

from ..contracts import Counterfactual, Evidence, Moment
from ..moments.detector import top
from ..sim.engine import MatchSim
from ..sim.golden import GOLDEN, GoldenSpec
from ..sim.teams import make_team

N_ROLLOUTS = 200
TOP_N = 5
MAX_PER_KIND = 3
N_BOOT = 2000
INTERVAL = (10, 90)
MOMENTUM_PRESS_BOOST = 0.25  # press intensity added for the side losing control in a momentum shift
PRESS_LOOKBACK = 900.0       # seconds before a press collapse at which the earlier press level is read

CHANGE_FOR = {"goal": "remove_event", "red_card": "remove_event", "big_chance": "convert_chance",
              "press_collapse": "press_intensity", "momentum_shift": "press_intensity", "sub_effect": "undo_sub"}


def spec_for(match_id: str) -> GoldenSpec:
    return next(s for s in GOLDEN if s.match_id == match_id)


def replay(spec: GoldenSpec, n_events: int) -> MatchSim:
    """Golden match replayed until its first `n_events` events exist (pauses between two actions)."""
    sim = MatchSim(make_team(spec.home), make_team(spec.away), spec.seed, spec.match_id, spec.beats)
    sim.advance(lambda s: len(s.events) >= n_events)
    return sim


def rollouts(sim: MatchSim, n: int, seed: int) -> np.ndarray:
    """Final results of n continuations of `sim` (left untouched): 0 home win, 1 draw, 2 away win."""
    events, sim.events = sim.events, []
    base = copy.deepcopy(sim)
    sim.events = events
    base.fast = True
    out = np.empty(n, dtype=int)
    for i in range(n):
        s = copy.deepcopy(base)
        s.rng = random.Random(seed * 1000 + i)
        s.advance()
        h, a = s.score
        out[i] = 0 if h > a else 1 if h == a else 2
    return out


class _Setup:
    """Snapshot of a moment plus the change to apply to a copy of it."""

    def __init__(self, sim: MatchSim, change: str, apply: Callable[[MatchSim], None], description: str):
        self.sim, self.change, self.apply, self.description = sim, change, apply, description


def _names(sim: MatchSim) -> dict[str, str]:
    return {p.id: p.name for t in (sim.home, sim.away) for p in t.players}


def _side_of_club(sim: MatchSim, club: str) -> int:
    return 0 if sim.home.name == club else 1


def _setup(moment: Moment, events: list[dict], spec: GoldenSpec) -> _Setup:
    index = {e["id"]: i for i, e in enumerate(events)}
    first = moment.evidence[0]
    change = CHANGE_FOR[moment.kind]

    if moment.kind in ("goal", "big_chance", "red_card"):
        i = index[first.event_ids[0]]
        if moment.kind == "goal":
            i += 1  # the goal event follows the shot
        sim = replay(spec, i + 1)
        e = events[i]
        s = 0 if e["team"] == sim.home.id else 1
        who, club = _names(sim)[e["player_id"]], sim.sides[s].team.name
        if moment.kind == "goal":
            def apply(c: MatchSim) -> None:
                c.score[s] -= 1
                c.goals.pop()
            return _Setup(sim, change, apply, f"What if {who}'s goal for {club} had not gone in")
        if moment.kind == "big_chance":
            def apply(c: MatchSim) -> None:
                c.score[s] += 1
            return _Setup(sim, change, apply, f"What if {who} had scored this chance for {club}")

        def apply(c: MatchSim) -> None:
            st = c.sides[s]
            st.on.append(next(p for p in st.team.players if p.id == e["player_id"]))
            st._pools()
            c.reds.pop()
        return _Setup(sim, change, apply, f"What if {who} had stayed on the pitch for {club}")

    if moment.kind == "sub_effect":
        subs = [events[index[x]] for x in first.event_ids]
        i = index[subs[0]["id"]]
        while events[i - 1]["type"] == "sub":  # subs made in the same stoppage (either side)
            i -= 1
        sim = replay(spec, i)  # paused just before the change is made
        s = 0 if subs[0]["team"] == sim.home.id else 1
        side, minute, names = sim._side_name(s), subs[0]["minute"], _names(sim)

        def apply(c: MatchSim) -> None:
            n0 = len(c.beats) + len(c.sub_plan)
            c.beats = [b for b in c.beats if not (b.kind == "sub" and b.side == side and b.minute <= minute)]
            c.sub_plan = [(m, x) for m, x in c.sub_plan if not (x == s and m <= minute)]
            assert len(c.beats) + len(c.sub_plan) < n0, "substitution not found in the snapshot"
        off = ", ".join(names[x["player_id"]] for x in subs)
        on = ", ".join(names[x["related_player_id"]] for x in subs)
        return _Setup(sim, change, apply,
                      f"What if {sim.sides[s].team.name} had kept {off} on instead of bringing on {on}")

    # press_collapse / momentum_shift: the club is the first evidence value
    n = next(i for i, e in enumerate(events) if e["t"] >= moment.t_start)
    sim = replay(spec, n)
    s = _side_of_club(sim, str(first.value))
    if moment.kind == "momentum_shift":
        s = 1 - s  # the side losing control presses harder
        club = sim.sides[s].team.name

        def apply(c: MatchSim) -> None:
            st = c.sides[s].style
            st["press_intensity"] = min(1.0, st["press_intensity"] + MOMENTUM_PRESS_BOOST)
        return _Setup(sim, change, apply, f"What if {club} had pressed harder from this point")

    n_early = next(i for i, e in enumerate(events) if e["t"] >= moment.t_start - PRESS_LOOKBACK)
    target = replay(spec, n_early).sides[s].style["press_intensity"]
    side, club = sim._side_name(s), sim.sides[s].team.name
    if target <= sim.sides[s].style["press_intensity"] + 0.01:  # emergent collapse (fatigue): press harder
        target = min(1.0, sim.sides[s].style["press_intensity"] + MOMENTUM_PRESS_BOOST)

    def apply(c: MatchSim) -> None:
        st = c.sides[s].style
        st["press_intensity"] = max(st["press_intensity"], target)
        c.beats = [replace(b, style=tuple((k, v) for k, v in b.style if k != "press_intensity"))
                   if b.side == side else b for b in c.beats]
    return _Setup(sim, change, apply, f"What if {club} had kept pressing at their earlier intensity")


def counterfactual(moment: Moment, events: list[dict], spec: GoldenSpec, n: int = N_ROLLOUTS
                   ) -> tuple[Counterfactual, dict]:
    """One counterfactual for a moment plus the home/away win chances behind it (as played vs changed)."""
    setup = _setup(moment, events, spec)
    seed = spec.seed * 100 + int(moment.id.rsplit("M", 1)[1])
    changed = copy.deepcopy(setup.sim)
    setup.apply(changed)
    fact, cf = rollouts(setup.sim, n, seed), rollouts(changed, n, seed)
    d = (cf == 0).astype(float) - (fact == 0)
    boot = d[np.random.default_rng(seed).integers(0, n, (N_BOOT, n))].mean(axis=1)
    lo, hi = np.percentile(boot, INTERVAL)
    c = Counterfactual(id=f"{moment.id}-CF1", change=setup.change, description=setup.description,
                       n_rollouts=n, seed=seed, wp_delta_mean=round(float(d.mean()), 4),
                       wp_delta_p10=round(float(lo), 4), wp_delta_p90=round(float(hi), 4))
    chances = {"home": (float((fact == 0).mean()), float((cf == 0).mean())),
               "away": (float((fact == 2).mean()), float((cf == 2).mean()))}
    return c, chances


def _evidence(moment: Moment, c: Counterfactual, chances: dict, clubs: dict[str, str]) -> list[Evidence]:
    k = len(moment.evidence)
    pct = lambda v: round(100 * v, 1)  # noqa: E731
    items = [(f"What-if: {clubs['home']} win chance as played", pct(chances["home"][0]), "%"),
             (f"What-if: {clubs['home']} win chance with the change", pct(chances["home"][1]), "%"),
             (f"What-if: {clubs['away']} win chance as played", pct(chances["away"][0]), "%"),
             (f"What-if: {clubs['away']} win chance with the change", pct(chances["away"][1]), "%"),
             (f"What-if: change in {clubs['home']} win chance", pct(c.wp_delta_mean), "pp"),
             (f"What-if: change in {clubs['home']} win chance, 80% interval low", pct(c.wp_delta_p10), "pp"),
             (f"What-if: change in {clubs['home']} win chance, 80% interval high", pct(c.wp_delta_p90), "pp"),
             ("What-if: simulated rest-of-match rollouts per scenario", c.n_rollouts, None)]
    return [Evidence(id=f"{moment.id}.e{k + j}", label=lab, value=val, unit=unit)
            for j, (lab, val, unit) in enumerate(items, 1)]


def pick(moments: list[Moment], n: int = TOP_N) -> list[Moment]:
    """The n most important moments, at most MAX_PER_KIND of one kind so the story beats get a what-if."""
    out: list[Moment] = []
    for m in top(moments, len(moments)):
        if len(out) < n and sum(x.kind == m.kind for x in out) < MAX_PER_KIND:
            out.append(m)
    return out


def attach(meta: dict, events: list[dict], moments: list[Moment], top_n: int = TOP_N,
           n: int = N_ROLLOUTS) -> list[Moment]:
    """Moments with a counterfactual (and its evidence) added to the top_n picked by `pick`."""
    spec = spec_for(meta["match_id"])
    clubs = {s: meta[s]["name"] for s in ("home", "away")}
    chosen = {m.id for m in pick(moments, top_n)}
    out = []
    for m in moments:
        if m.id in chosen:
            c, chances = counterfactual(m, events, spec, n)
            m = m.model_copy(update={"counterfactuals": [c], "evidence": m.evidence + _evidence(m, c, chances, clubs)})
        out.append(m)
    return out
