"""Counterfactual rollouts: resumable simulator, determinism, sign of effect, saved evidence packs."""
import json

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from tacticlens.contracts import Moment, load_schema
from tacticlens.counterfactual.rollouts import (MAX_PER_KIND, N_ROLLOUTS, TOP_N, counterfactual, pick, replay,
                                                rollouts, spec_for)
from tacticlens.metrics.pipeline import load_golden
from tacticlens.sim.golden import GOLDEN, GOLDEN_DIR, run_spec

IDS = [s.match_id for s in GOLDEN]


@pytest.fixture(scope="module")
def saved():
    out = {}
    for mid in IDS:
        meta, events = load_golden(mid)
        ms = json.loads((GOLDEN_DIR / mid / "moments.json").read_text(encoding="utf-8"))
        out[mid] = (meta, events, [Moment(**m) for m in ms])
    return out


def _cf(saved, mid, kind, i=0):
    return [m for m in saved[mid][2] if m.kind == kind and m.counterfactuals][i]


def test_paused_sim_resumes_to_the_same_match():
    spec = spec_for("GM02")
    sim = replay(spec, 500)
    _, events = load_golden("GM02")
    assert len(sim.events) >= 500 and sim.events == events[:len(sim.events)]
    sim.advance()
    full = run_spec(spec)
    assert sim.result().score == full.score and sim.events == full.events


def test_rollouts_are_deterministic_and_leave_the_snapshot_alone():
    sim = replay(spec_for("GM05"), 1200)
    n_events, score = len(sim.events), list(sim.score)
    a, b = rollouts(sim, 15, 7), rollouts(sim, 15, 7)
    assert np.array_equal(a, b) and set(a) <= {0, 1, 2}
    assert len(sim.events) == n_events and sim.score == score and not sim.fast


def test_saved_counterfactual_is_reproducible(saved):
    meta, events, _ = saved["GM02"]
    m = _cf(saved, "GM02", "red_card")
    c, _ = counterfactual(m.model_copy(update={"counterfactuals": []}), events, spec_for("GM02"))
    assert c == m.counterfactuals[0]


def test_sign_of_effect(saved):
    # Removing a goal hurts the scorer (home goal -> home win chance falls, away goal -> rises).
    for mid in IDS:
        meta = saved[mid][0]
        for m in saved[mid][2]:
            for c in m.counterfactuals:
                assert c.wp_delta_p10 <= c.wp_delta_mean <= c.wp_delta_p90
                if m.kind == "goal":
                    home = m.evidence[1].value == meta["home"]["name"]
                    assert (c.wp_delta_mean <= 0) if home else (c.wp_delta_mean >= 0)
    late = [m for m in saved["GM01"][2] if m.kind == "goal" and m.counterfactuals][-1]  # 88' winner
    assert late.counterfactuals[0].wp_delta_p90 < -0.5
    assert _cf(saved, "GM02", "red_card").counterfactuals[0].wp_delta_p90 < 0  # Redmere keep 11: Harbor less likely
    assert _cf(saved, "GM04", "press_collapse").counterfactuals[0].wp_delta_p10 > 0  # Kestrel keep pressing


@pytest.mark.parametrize("mid", IDS)
def test_saved_packs(mid, saved):
    _, events, moments = saved[mid]
    v = Draft202012Validator(load_schema("moment"))
    with_cf = [m for m in moments if m.counterfactuals]
    assert {m.id for m in with_cf} == {m.id for m in pick(moments, TOP_N)}
    assert len(with_cf) == min(TOP_N, len(moments))
    assert max(sum(m.kind == k for m in with_cf) for k in {m.kind for m in with_cf}) <= MAX_PER_KIND
    for m in moments:
        v.validate(m.model_dump(mode="json"))
        assert [e.id for e in m.evidence] == [f"{m.id}.e{k}" for k in range(1, len(m.evidence) + 1)]
        for c in m.counterfactuals:
            assert c.n_rollouts == N_ROLLOUTS and c.id == f"{m.id}-CF1" and c.description.startswith("What if")
            ev = {e.label: e.value for e in m.evidence}
            delta = next(v for k, v in ev.items() if k.startswith("What-if: change in") and "interval" not in k)
            assert delta == round(100 * c.wp_delta_mean, 1)
