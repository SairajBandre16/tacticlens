"""Expected threat (xT) on the 12x8 zone grid, solved by value iteration from simulated event data.

xT(z) = P(shoot|z) * P(goal|shot,z) + P(move|z) * sum_z' T(z->z') * xT(z')
where T only counts successful moves (a failed move ends the possession with value 0).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..sim.engine import COLS, ROWS, ZH, ZW

MOVES = ("pass", "dribble", "free_kick", "corner", "clearance")


def zone(x: float, y: float) -> int:
    c = min(int(x / ZW), COLS - 1)
    r = min(int(y / ZH), ROWS - 1)
    return c * ROWS + r


def fit(event_lists: list[list[dict]], iters: int = 100, tol: float = 1e-7) -> np.ndarray:
    """Return xT as a (COLS, ROWS) array."""
    n = COLS * ROWS
    shots, goals, moves = np.zeros(n), np.zeros(n), np.zeros(n)
    trans = np.zeros((n, n))
    for events in event_lists:
        for e in events:
            if e["type"] == "shot":
                z = zone(e["x"], e["y"])
                shots[z] += 1
                goals[z] += e["outcome"] == "goal"
            elif e["type"] in MOVES and e["end_x"] is not None:
                z = zone(e["x"], e["y"])
                moves[z] += 1
                if e["outcome"] == "success":
                    trans[z, zone(e["end_x"], e["end_y"])] += 1
    total = shots + moves
    with np.errstate(invalid="ignore", divide="ignore"):
        p_shot = np.nan_to_num(shots / total)
        p_move = np.nan_to_num(moves / total)
        p_goal = np.nan_to_num(goals / shots)
        T = np.nan_to_num(trans / moves[:, None])
    xt = np.zeros(n)
    for _ in range(iters):
        new = p_shot * p_goal + p_move * (T @ xt)
        if np.max(np.abs(new - xt)) < tol:
            xt = new
            break
        xt = new
    return xt.reshape(COLS, ROWS)


class XTGrid:
    def __init__(self, grid: np.ndarray):
        self.grid = np.asarray(grid, dtype=float)

    def value(self, x: float, y: float) -> float:
        z = zone(x, y)
        return float(self.grid[z // ROWS, z % ROWS])

    def added(self, e: dict) -> float:
        """xT added by a successful move; 0 for anything else."""
        if e["type"] not in MOVES or e["outcome"] != "success" or e["end_x"] is None:
            return 0.0
        return self.value(e["end_x"], e["end_y"]) - self.value(e["x"], e["y"])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [[round(float(v), 5) for v in col] for col in self.grid]
        path.write_text(json.dumps({"cols": COLS, "rows": ROWS, "grid": rows}) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "XTGrid":
        return cls(np.array(json.loads(path.read_text(encoding="utf-8"))["grid"]))
