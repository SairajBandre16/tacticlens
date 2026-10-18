"""Expected goals: logistic regression on shot geometry, trained on simulated shots.

The model is stored as plain JSON coefficients so it loads without pickle and applies with numpy.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

FEATURES = ("distance_m", "angle_rad", "header", "under_pressure", "set_piece")


def shot_geometry(x: float, y: float) -> tuple[float, float]:
    """Distance (m) and goal-mouth angle (rad) from attacker-perspective coordinates (0-100)."""
    dx, dy = (100.0 - x) * 1.05, (y - 50.0) * 0.68
    half_goal = 3.66
    angle = math.atan2(2 * half_goal * dx, dx * dx + dy * dy - half_goal * half_goal)
    if angle < 0:
        angle += math.pi
    return math.hypot(dx, dy), angle


def features(x: float, y: float, header: bool, under_pressure: bool, set_piece: bool) -> list[float]:
    d, a = shot_geometry(x, y)
    return [d, a, float(header), float(under_pressure), float(set_piece)]


@dataclass
class XGModel:
    coef: list[float]
    intercept: float

    def predict(self, X: np.ndarray) -> np.ndarray:
        z = np.asarray(X, dtype=float) @ np.asarray(self.coef) + self.intercept
        return 1.0 / (1.0 + np.exp(-z))

    def shot(self, x: float, y: float, header: bool, under_pressure: bool, set_piece: bool) -> float:
        return float(self.predict(np.array([features(x, y, header, under_pressure, set_piece)]))[0])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"features": FEATURES, "coef": self.coef, "intercept": self.intercept},
                                   indent=1) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "XGModel":
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(d["coef"], d["intercept"])


def shot_table(results) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(X, y, p_true, match_index) from MatchResult shot records (works in fast mode)."""
    X, y, p, m = [], [], [], []
    for i, r in enumerate(results):
        for s in r.shots:
            X.append(features(s.x, s.y, s.header, s.under_pressure, s.set_piece))
            y.append(s.outcome == "goal")
            p.append(s.p_true)
            m.append(i)
    return np.array(X), np.array(y, dtype=int), np.array(p), np.array(m)


def train(X: np.ndarray, y: np.ndarray) -> XGModel:
    lr = LogisticRegression(C=10.0, max_iter=2000)
    lr.fit(X, y)
    return XGModel([round(float(c), 6) for c in lr.coef_[0]], round(float(lr.intercept_[0]), 6))


def set_piece_shots(events: list[dict]) -> set[str]:
    """Shot ids that come within 3 actions of the shooting team's corner or free kick (as in the sim)."""
    out, last_sp = set(), {}
    for i, e in enumerate(events):
        if e["type"] in ("corner", "free_kick"):
            last_sp[e["team"]] = i
        elif e["type"] == "shot" and e["team"] in last_sp and i - last_sp[e["team"]] <= 6:
            out.add(e["id"])
    return out


def event_xg(model: XGModel, events: list[dict]) -> dict[str, float]:
    """xG per shot event id."""
    sp = set_piece_shots(events)
    return {e["id"]: round(model.shot(e["x"], e["y"], e["body_part"] == "head", e["under_pressure"],
                                      e["id"] in sp), 4)
            for e in events if e["type"] == "shot"}
