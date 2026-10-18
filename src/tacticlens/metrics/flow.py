"""Per-minute game-flow metrics from an event stream: threat, momentum, PPDA and pressure index.

All windows are trailing and minute-based, so the value at minute m only uses events up to m.
"""
from __future__ import annotations

import math

from .clock import ev_clock
from .xt import XTGrid

DEF_ACTIONS = ("tackle", "interception", "foul")
WINDOW = 10           # minutes, for PPDA and pressure index
HALF_LIFE = 4.0       # minutes, momentum smoothing
MOMENTUM_SCALE = 0.05  # threat/minute difference that maps to tanh(1) ~ 0.76


def _n_minutes(events: list[dict]) -> int:
    return (ev_clock(events[-1]) if events else 90) + 1


def threat(events: list[dict], teams: tuple[str, str], xt: XTGrid, xg: dict[str, float]) -> list[list[float]]:
    """Threat per team per minute: positive xT added by moves + xG of shots."""
    n = _n_minutes(events)
    out = [[0.0] * n, [0.0] * n]
    for e in events:
        s = teams.index(e["team"])
        if e["type"] == "shot":
            out[s][ev_clock(e)] += xg.get(e["id"], 0.0)
        else:
            out[s][ev_clock(e)] += max(0.0, xt.added(e))
    return out


def momentum(thr: list[list[float]]) -> list[float]:
    """Smoothed home-minus-away threat, squashed to [-1, 1]; positive = home on top."""
    a = 1.0 - 0.5 ** (1.0 / HALF_LIFE)
    eh = ea = 0.0
    out = []
    for h, w in zip(*thr):
        eh, ea = eh + a * (h - eh), ea + a * (w - ea)
        out.append(round(math.tanh((eh - ea) / MOMENTUM_SCALE), 4))
    return out


def ppda_and_pressure(events: list[dict], teams: tuple[str, str]) -> dict[str, list]:
    """Trailing-window PPDA (lower = more intense press) and pressures per minute, per team."""
    n = _n_minutes(events)
    opp_passes = [[0] * n, [0] * n]   # passes allowed by team s in the opponent's own 60%
    def_act = [[0] * n, [0] * n]      # team s defensive actions in the opponent's 60%
    pressures = [[0] * n, [0] * n]
    for e in events:
        s = teams.index(e["team"])
        m = ev_clock(e)
        if e["type"] == "pass" and e["x"] <= 60:
            opp_passes[1 - s][m] += 1
        elif e["type"] in DEF_ACTIONS and e["x"] >= 40:
            def_act[s][m] += 1
        elif e["type"] == "pressure":
            pressures[s][m] += 1
    out: dict[str, list] = {"ppda": [[], []], "pressure_index": [[], []]}
    for s in (0, 1):
        for m in range(n):
            lo = max(0, m - WINDOW + 1)
            p, d = sum(opp_passes[s][lo:m + 1]), sum(def_act[s][lo:m + 1])
            out["ppda"][s].append(round(p / d, 2) if d else None)
            out["pressure_index"][s].append(round(sum(pressures[s][lo:m + 1]) / (m + 1 - lo), 3))
    return out


def window_ppda(events: list[dict], team: str, lo: int, hi: int) -> tuple[float | None, int, int]:
    """PPDA of `team` for clock minutes [lo, hi): (ppda, opponent passes, defensive actions)."""
    p = sum(1 for e in events if lo <= ev_clock(e) < hi and e["team"] != team and e["type"] == "pass"
            and e["x"] <= 60)
    d = sum(1 for e in events if lo <= ev_clock(e) < hi and e["team"] == team and e["type"] in DEF_ACTIONS
            and e["x"] >= 40)
    return (round(p / d, 2) if d else None), p, d
