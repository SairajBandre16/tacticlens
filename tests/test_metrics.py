"""Metrics (xG, xT, win probability, flow) and the moment detector on golden data."""
import json

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from tacticlens.contracts import load_schema
from tacticlens.metrics.clock import ev_clock
from tacticlens.metrics import flow, winprob, xg as xg_mod, xt as xt_mod
from tacticlens.metrics.pipeline import load_golden, load_models, match_metrics
from tacticlens.moments.detector import detect, top
from tacticlens.sim.golden import GOLDEN, GOLDEN_DIR, run_spec
from tacticlens.sim.realism import league_sample

IDS = [s.match_id for s in GOLDEN]


@pytest.fixture(scope="module")
def models():
    return load_models()


@pytest.fixture(scope="module")
def golden(models):
    out = {}
    for mid in IDS:
        meta, events = load_golden(mid)
        mm = match_metrics(meta, events, models)
        out[mid] = (meta, events, mm, detect(meta, events, mm))
    return out


def test_xg_geometry_and_monotonicity(models):
    xg = models[0]
    d1, a1 = xg_mod.shot_geometry(95, 50)
    d2, a2 = xg_mod.shot_geometry(80, 50)
    assert d1 < d2 and a1 > a2
    assert xg_mod.shot_geometry(90, 30) == pytest.approx(xg_mod.shot_geometry(90, 70))
    assert xg.shot(94, 50, False, False, False) > xg.shot(80, 50, False, False, False) > xg.shot(70, 20, False, False, False)
    assert xg.shot(94, 50, True, False, False) < xg.shot(94, 50, False, False, False)
    assert xg.shot(94, 50, False, True, False) < xg.shot(94, 50, False, False, False)


def test_xg_training_is_deterministic_and_recovers_signs():
    res = league_sample(150, seed=5, fast=True)
    X, y, _, _ = xg_mod.shot_table(res)
    a, b = xg_mod.train(X, y), xg_mod.train(X, y)
    assert a.coef == b.coef
    assert a.coef[0] < 0 and a.coef[2] < 0  # farther and headed shots score less


def test_set_piece_heuristic_matches_simulator():
    r = run_spec(GOLDEN[5])
    sp = xg_mod.set_piece_shots(r.events)
    shots = [e for e in r.events if e["type"] == "shot"]
    agree = sum((e["id"] in sp) == rec.set_piece for e, rec in zip(shots, r.shots))
    assert agree / len(shots) >= 0.9


def test_xt_grid_shape_and_gradient(models):
    g = models[1].grid
    assert g.shape == (12, 8) and (g >= 0).all() and (g <= 1).all()
    assert g[-1].mean() > 5 * g[0].mean()
    assert g[11, 3] > g[11, 0]  # central beats the corner flag
    small = xt_mod.fit([r.events for r in league_sample(10, seed=3)])
    assert np.array_equal(small, xt_mod.fit([r.events for r in league_sample(10, seed=3)]))


def test_wp_probabilities_and_game_state(models):
    wp = models[2]
    p = wp.predict([winprob.state_features(m, 1, 0, 0, 1.0, 0.5, 0.0) for m in (10, 50, 88)])
    assert np.allclose(p.sum(axis=1), 1)
    assert p[0, 0] < p[1, 0] < p[2, 0] and p[2, 0] > 0.85  # a 1-0 lead firms up with time
    up = wp.one(winprob.state_features(60, 0, 0, 1, 0, 0, 0))
    down = wp.one(winprob.state_features(60, 0, 0, -1, 0, 0, 0))
    assert up["home"] > down["home"]  # man advantage helps


def test_event_state_matches_training_snapshots(models):
    """Features rebuilt from events equal the fast-mode snapshot features (xG up to set-piece tagging)."""
    xg = models[0]
    r = run_spec(GOLDEN[0])
    X, _, _ = winprob.snapshots([r], xg)
    shot_xg = xg_mod.event_xg(xg, r.events)
    st = winprob.MatchState(r.home.id, r.home.style.quality - r.away.style.quality)
    i = 0
    for row, m in zip(X, winprob.SNAPSHOT_MINUTES):
        while i < len(r.events) and ev_clock(r.events[i]) < m:
            st.update(r.events[i], shot_xg)
            i += 1
        f = st.features(m)
        assert f[:4] == list(row[:4]) and f[5] == pytest.approx(row[5])
        assert f[4] == pytest.approx(row[4], abs=0.15)


@pytest.mark.parametrize("mid", IDS)
def test_golden_metrics_files_are_current(mid, golden):
    _, _, mm, moments = golden[mid]
    on_disk = json.loads((GOLDEN_DIR / mid / "metrics.json").read_text(encoding="utf-8"))
    assert on_disk == json.loads(json.dumps(mm)), "stale: run python -m tacticlens.metrics golden"
    saved = json.loads((GOLDEN_DIR / mid / "moments.json").read_text(encoding="utf-8"))
    assert saved == [m.model_dump(mode="json") for m in moments], "stale: run python -m tacticlens.metrics golden"


@pytest.mark.parametrize("mid", IDS)
def test_golden_final_wp_matches_result(mid, golden):
    meta, _, mm, _ = golden[mid]
    h, a = meta["score"]["home"], meta["score"]["away"]
    want = "home" if h > a else "draw" if h == a else "away"
    last = mm["wp"][-1]
    assert max(("home", "draw", "away"), key=last.get) == want


def test_momentum_and_press_index(golden):
    for _, _, mm, _ in golden.values():
        assert all(-1 <= v <= 1 for v in mm["momentum"])
    pi = golden["GM04"][2]["pressure_index"][0]  # Kestrel's press collapses after 58'
    assert np.mean(pi[45:58]) > 2 * np.mean(pi[68:88])
    p0, _, _ = flow.window_ppda(golden["GM04"][1], "KES", 0, 58)
    assert p0 is not None and p0 > 0


@pytest.mark.parametrize("mid", IDS)
def test_moments_are_valid_and_grounded(mid, golden):
    meta, events, _, moments = golden[mid]
    v = Draft202012Validator(load_schema("moment"))
    ids = {e["id"] for e in events}
    ev_ids = [e.id for m in moments for e in m.evidence]
    assert len(ev_ids) == len(set(ev_ids))
    for m in moments:
        v.validate(m.model_dump(mode="json"))
        assert m.t_start <= m.t_end
        assert all(i in ids for e in m.evidence for i in e.event_ids)
    goals = [m for m in moments if m.kind == "goal"]
    assert len(goals) == meta["score"]["home"] + meta["score"]["away"]
    assert len(top(moments)) == min(8, len(moments))


def test_story_moments_are_detected(golden):
    def kinds(mid):
        return {(m.kind, next(e.value for e in m.evidence if e.label == "Minute")) for m in golden[mid][3]}
    assert any(k == "red_card" and mi == 34 for k, mi in kinds("GM02"))
    assert any(k == "press_collapse" and 50 <= mi <= 66 for k, mi in kinds("GM04"))
    assert any(k == "sub_effect" and 60 <= mi <= 66 for k, mi in kinds("GM01"))
    late = [m for m in golden["GM01"][3] if m.kind == "goal"][-1]
    assert late in top(golden["GM01"][3], 3)  # the late winner ranks near the top
