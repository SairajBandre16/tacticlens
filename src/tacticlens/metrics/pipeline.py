"""Train xG / xT / win-probability models, evaluate them, and compute golden-match metrics.

CLI: python -m tacticlens.metrics [train|golden|all]
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from ..sim.golden import GOLDEN_DIR
from ..sim.realism import league_sample
from . import flow, winprob, xg as xg_mod, xt as xt_mod
from .winprob import WPModel
from .xg import XGModel
from .xt import XTGrid

ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = ROOT / "data" / "models"
N_TRAIN_MATCHES = 3000
N_XT_MATCHES = 300
TRAIN_SEED, XT_SEED = 2027, 2028


def _bins(pred: np.ndarray, obs: np.ndarray, edges: list[float], extra: np.ndarray | None = None) -> list[dict]:
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        k = (pred >= lo) & (pred < hi if hi < 1 else pred <= hi)
        if k.sum() == 0:
            continue
        row = {"lo": lo, "hi": hi, "n": int(k.sum()), "pred": round(float(pred[k].mean()), 4),
               "obs": round(float(obs[k].mean()), 4)}
        if extra is not None:
            row["true"] = round(float(extra[k].mean()), 4)
        rows.append(row)
    return rows


def train_all(n_matches: int = N_TRAIN_MATCHES, n_xt: int = N_XT_MATCHES, out_dir: Path = MODELS_DIR) -> dict:
    """Train all three models (held-out = every 5th match) and return the evaluation dict."""
    results = league_sample(n_matches, seed=TRAIN_SEED, fast=True)
    ev: dict = {"n_matches": n_matches}

    # xG
    X, y, p_true, mi = xg_mod.shot_table(results)
    test = mi % 5 == 0
    xg = xg_mod.train(X[~test], y[~test])
    p = xg.predict(X[test])
    ev["xg"] = {
        "n_train": int((~test).sum()), "n_test": int(test.sum()), "goal_rate": round(float(y[test].mean()), 4),
        "log_loss": round(log_loss(y[test], p), 4), "brier": round(brier_score_loss(y[test], p), 4),
        "auc": round(roc_auc_score(y[test], p), 4),
        "log_loss_true": round(log_loss(y[test], p_true[test]), 4),
        "mae_vs_true": round(float(np.abs(p - p_true[test]).mean()), 4),
        "coef": dict(zip(xg_mod.FEATURES, xg.coef)),
        "calibration": _bins(p, y[test], [0, 0.03, 0.06, 0.1, 0.15, 0.2, 0.3, 0.45, 1.0], p_true[test]),
    }

    # xT (needs coordinates, so full-mode matches)
    full = league_sample(n_xt, seed=XT_SEED, fast=False)
    xt = XTGrid(xt_mod.fit([r.events for r in full]))
    ev["xt"] = {"n_matches": n_xt, "max": round(float(xt.grid.max()), 4),
                "own_box": round(float(xt.grid[0].mean()), 4), "opp_box": round(float(xt.grid[-1, 2:6].mean()), 4)}

    # Win probability
    Xw, yw, mw = winprob.snapshots(results, xg)
    tw = mw % 5 == 0
    wp = WPModel(winprob.train(Xw[~tw], yw[~tw]))
    base = LogisticRegression(max_iter=2000).fit(Xw[~tw], yw[~tw])
    pw, pb = wp.predict(Xw[tw]), base.predict_proba(Xw[tw])
    onehot = np.eye(3)[yw[tw]]
    minute = Xw[tw][:, 0]
    phases = {}
    for lo, hi in ((0, 30), (30, 60), (60, 96)):
        k = (minute >= lo) & (minute < hi)
        phases[f"{lo}-{hi}"] = round(log_loss(yw[tw][k], pw[k], labels=[0, 1, 2]), 4)
    prior = np.bincount(yw[~tw], minlength=3) / (~tw).sum()
    ev["wp"] = {
        "n_train": int((~tw).sum()), "n_test": int(tw.sum()),
        "log_loss": round(log_loss(yw[tw], pw), 4),
        "log_loss_logreg": round(log_loss(yw[tw], pb), 4),
        "log_loss_prior": round(log_loss(yw[tw], np.tile(prior, (tw.sum(), 1))), 4),
        "brier": round(float(((pw - onehot) ** 2).sum(axis=1).mean()), 4),
        "brier_logreg": round(float(((pb - onehot) ** 2).sum(axis=1).mean()), 4),
        "by_phase": phases,
        "outcome_rates": dict(zip(winprob.CLASSES, [round(float(v), 4) for v in prior])),
        "calibration_home": _bins(pw[:, 0], onehot[:, 0], [i / 10 for i in range(11)]),
        "calibration_draw": _bins(pw[:, 1], onehot[:, 1], [i / 10 for i in range(11)]),
    }

    xg.save(out_dir / "xg.json")
    xt.save(out_dir / "xt.json")
    wp.save(out_dir / "wp.pkl")
    (out_dir / "eval.json").write_text(json.dumps(ev, indent=1) + "\n", encoding="utf-8")
    return ev


def load_models(models_dir: Path = MODELS_DIR) -> tuple[XGModel, XTGrid, WPModel]:
    return (XGModel.load(models_dir / "xg.json"), XTGrid.load(models_dir / "xt.json"),
            WPModel.load(models_dir / "wp.pkl"))


def load_golden(match_id: str, golden_dir: Path = GOLDEN_DIR) -> tuple[dict, list[dict]]:
    d = golden_dir / match_id
    return (json.loads((d / "match.json").read_text(encoding="utf-8")),
            json.loads((d / "events.json").read_text(encoding="utf-8")))


def match_metrics(meta: dict, events: list[dict], models: tuple[XGModel, XTGrid, WPModel]) -> dict:
    xg, xt, wp = models
    teams = (meta["home"]["id"], meta["away"]["id"])
    q_diff = meta["home"]["style"]["quality"] - meta["away"]["style"]["quality"]
    shot_xg = xg_mod.event_xg(xg, events)
    timeline, per_event = winprob.event_wp(wp, events, teams[0], q_diff, shot_xg)
    thr = flow.threat(events, teams, xt, shot_xg)
    pp = flow.ppda_and_pressure(events, teams)
    xt_added = {e["id"]: round(xt.added(e), 4) for e in events if xt.added(e) != 0.0}
    shooter = {e["id"]: e["team"] for e in events if e["type"] == "shot"}
    return {
        "match_id": meta["match_id"], "teams": list(teams),
        "xg_total": [round(sum(v for k, v in shot_xg.items() if shooter[k] == t), 3) for t in teams],
        "shot_xg": shot_xg, "xt_added": xt_added,
        "wp": timeline,
        "event_wp": {e["id"]: {"before": b, "after": a} for e, (b, a) in zip(events, per_event)
                     if e["type"] in ("goal", "shot", "card", "sub")},
        "threat": [[round(v, 4) for v in s] for s in thr],
        "momentum": flow.momentum(thr),
        "ppda": pp["ppda"], "pressure_index": pp["pressure_index"],
    }


def build_golden_metrics(models=None, golden_dir: Path = GOLDEN_DIR) -> dict[str, dict]:
    models = models or load_models()
    index = json.loads((golden_dir / "index.json").read_text(encoding="utf-8"))
    out = {}
    for row in index:
        meta, events = load_golden(row["match_id"], golden_dir)
        mm = match_metrics(meta, events, models)
        (golden_dir / row["match_id"] / "metrics.json").write_text(
            json.dumps(mm, separators=(",", ":")) + "\n", encoding="utf-8")
        out[row["match_id"]] = mm
    return out
