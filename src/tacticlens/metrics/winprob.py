"""In-play win probability (home / draw / away): gradient boosting on match-state snapshots.

Training snapshots come from fast-mode simulated matches; the same features are rebuilt from event
streams for the golden matches, so the model sees identical inputs in both settings.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from .clock import ev_clock, rec_clock
from .xg import XGModel, features as xg_features

FEATURES = ("minute", "goal_diff", "goals_total", "man_adv", "xg_diff", "quality_diff")
CLASSES = ("home", "draw", "away")
SNAPSHOT_MINUTES = tuple(range(0, 96, 3))


def state_features(minute: float, gh: int, ga: int, man_adv: int, xg_h: float, xg_a: float,
                   q_diff: float) -> list[float]:
    return [min(float(minute), 95.0), gh - ga, gh + ga, man_adv, xg_h - xg_a, q_diff]


def outcome(score: tuple[int, int]) -> int:
    return 0 if score[0] > score[1] else 1 if score[0] == score[1] else 2


def snapshots(results, xg: XGModel, minutes=SNAPSHOT_MINUTES):
    """(X, y, match_index) with one row per (match, clock minute); state counts events before it."""
    X, y, m = [], [], []
    for i, r in enumerate(results):
        q = r.home.style.quality - r.away.style.quality
        shot_xg = xg.predict(np.array([xg_features(s.x, s.y, s.header, s.under_pressure, s.set_piece)
                                       for s in r.shots])) if r.shots else []
        ht = r.half_time
        goals = [(g.side, rec_clock(g.minute, g.t, ht)) for g in r.goals]
        reds = [(s, rec_clock(mm, t, ht)) for mm, s, t in r.reds]
        shots = [(s.side, rec_clock(s.minute, s.t, ht), p) for s, p in zip(r.shots, shot_xg)]
        for mi in minutes:
            gh = sum(1 for s, c in goals if s == "home" and c < mi)
            ga = sum(1 for s, c in goals if s == "away" and c < mi)
            man = sum(1 for s, c in reds if s == "away" and c < mi) - sum(1 for s, c in reds if s == "home" and c < mi)
            xh = sum(p for s, c, p in shots if s == "home" and c < mi)
            xa = sum(p for s, c, p in shots if s == "away" and c < mi)
            X.append(state_features(mi, gh, ga, man, xh, xa, q))
            y.append(outcome(r.score))
            m.append(i)
    return np.array(X), np.array(y), np.array(m)


def train(X: np.ndarray, y: np.ndarray) -> HistGradientBoostingClassifier:
    clf = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.08, max_leaf_nodes=15,
                                         min_samples_leaf=40, l2_regularization=1.0,
                                         early_stopping=False, random_state=0)
    clf.fit(X, y)
    return clf


class WPModel:
    def __init__(self, clf: HistGradientBoostingClassifier):
        self.clf = clf

    def predict(self, X) -> np.ndarray:
        return self.clf.predict_proba(np.asarray(X, dtype=float))

    def one(self, feats: list[float]) -> dict[str, float]:
        p = self.predict([feats])[0]
        return {k: round(float(v), 4) for k, v in zip(CLASSES, p)}

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(self.clf, protocol=4))

    @classmethod
    def load(cls, path: Path) -> "WPModel":
        return cls(pickle.loads(path.read_bytes()))


class MatchState:
    """Running match state built from an event stream (home/away by team id)."""

    def __init__(self, home_id: str, q_diff: float):
        self.home_id, self.q_diff = home_id, q_diff
        self.gh = self.ga = self.man = 0
        self.xg_h = self.xg_a = 0.0

    def update(self, e: dict, xg: dict[str, float]) -> None:
        home = e["team"] == self.home_id
        if e["type"] == "goal":
            if home:
                self.gh += 1
            else:
                self.ga += 1
        elif e["type"] == "card" and e["outcome"] in ("red", "second_yellow"):
            self.man += -1 if home else 1
        elif e["type"] == "shot":
            if home:
                self.xg_h += xg.get(e["id"], 0.0)
            else:
                self.xg_a += xg.get(e["id"], 0.0)

    def features(self, minute: float) -> list[float]:
        return state_features(minute, self.gh, self.ga, self.man, self.xg_h, self.xg_a, self.q_diff)


def event_wp(model: WPModel, events: list[dict], home_id: str, q_diff: float,
             xg: dict[str, float]) -> tuple[list[dict], list[tuple[dict, dict]]]:
    """Return (per-minute timeline, per-event (wp_before, wp_after)).

    Clock minute m of the timeline uses all events with clock < m, matching the training snapshots, so
    an event at clock minute m is "before" at m and "after" at m + 1.
    """
    st = MatchState(home_id, q_diff)
    last_min = ev_clock(events[-1]) if events else 90
    rows_min, rows_before, rows_after = [], [], []
    i = 0
    for m in range(0, last_min + 2):
        while i < len(events) and ev_clock(events[i]) < m:
            c = ev_clock(events[i])
            rows_before.append(st.features(c))
            st.update(events[i], xg)
            rows_after.append(st.features(c + 1))
            i += 1
        rows_min.append(st.features(m))

    def as_dicts(rows):
        return [{k: round(float(v), 4) for k, v in zip(CLASSES, p)} for p in model.predict(rows)] if rows else []

    timeline = [{"minute": m, **p} for m, p in enumerate(as_dicts(rows_min))]
    return timeline, list(zip(as_dicts(rows_before), as_dicts(rows_after)))
