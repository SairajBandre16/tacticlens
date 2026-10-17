"""Simulator: determinism, fast/full parity, contract validity, story beats, golden data, realism."""
import json

import pytest
from jsonschema import Draft202012Validator

from tacticlens.contracts import Event, load_schema
from tacticlens.sim.engine import Beat, simulate
from tacticlens.sim.golden import GOLDEN, GOLDEN_DIR, run_spec
from tacticlens.sim.realism import TARGETS, league_sample, match_stats, summarize
from tacticlens.sim.teams import CLUBS, make_team

NBU, KES = make_team("NBU"), make_team("KES")


@pytest.fixture(scope="module")
def golden_runs():
    return {s.match_id: run_spec(s) for s in GOLDEN}


def test_same_seed_same_match():
    a, b = simulate(NBU, KES, 7, "T1"), simulate(NBU, KES, 7, "T1")
    assert a.events == b.events
    assert simulate(NBU, KES, 8, "T1").events != a.events


def test_fast_mode_matches_full_mode():
    for seed in range(5):
        full, fast = simulate(NBU, KES, seed), simulate(NBU, KES, seed, fast=True)
        assert fast.events is None
        assert (fast.score, fast.goals, fast.shots, fast.cards, fast.subs, fast.counters) == \
               (full.score, full.goals, full.shots, full.cards, full.subs, full.counters)


def test_events_follow_contract_and_invariants(golden_runs):
    r = golden_runs["GM01"]
    v = Draft202012Validator(load_schema("event"))
    for e in r.events:
        v.validate(e)
    events = [Event.model_validate(e) for e in r.events]
    assert len({e.id for e in events}) == len(events)
    assert all(b.t >= a.t for a, b in zip(events, events[1:]))
    rosters = {t.id: {p.id for p in t.players} for t in (r.home, r.away)}
    for e in events:
        assert e.player_id in rosters[e.team]
        assert (e.minute < 45 + 10) if e.period == 1 else (e.minute >= 45)
    goals = [e for e in events if e.type == "goal"]
    assert len(goals) == sum(r.score)
    for g in goals:  # every goal event is preceded by a scoring shot by the same player
        shot = next(e for e in reversed(events[:events.index(g)]) if e.type == "shot")
        assert shot.outcome == "goal" and shot.player_id == g.player_id


def test_sent_off_and_subbed_players_stop_playing(golden_runs):
    for r in golden_runs.values():
        gone, entered = {}, {}
        events = [Event.model_validate(e) for e in r.events]
        for e in events:
            if e.type == "sub":
                gone[e.player_id], entered[e.related_player_id] = e.t, e.t
            elif e.type == "card" and e.outcome in ("red", "second_yellow"):
                gone[e.player_id] = e.t
        for e in events:
            if e.type in ("sub", "card"):
                continue
            for pid in (e.player_id, e.related_player_id):
                if pid in gone:
                    assert e.t <= gone[pid], (r.match_id, e.id)
                if pid in entered:
                    assert e.t >= entered[pid], (r.match_id, e.id)


def test_story_beats_fire(golden_runs):
    reds = [e for e in golden_runs["GM02"].events if e.get("outcome") == "red"]
    assert len(reds) == 1 and reds[0]["minute"] >= 34 and reds[0]["team"] == "RED"
    subs = [e for e in golden_runs["GM01"].events if e["type"] == "sub" and e["player_id"] == "NBU-08"]
    assert subs and subs[0]["minute"] == 64 and subs[0]["related_player_id"] == "NBU-17"


def test_style_beat_changes_play():
    base = simulate(NBU, KES, 3, fast=True)
    calm = simulate(NBU, KES, 3, beats=[Beat(0, "away", "style", style=(("press_intensity", 0.0),))], fast=True)
    assert calm.counters["pressures"][1] < base.counters["pressures"][1] * 0.6


@pytest.mark.parametrize("spec", GOLDEN, ids=lambda s: s.match_id)
def test_golden_seed_fits_story_and_files_are_current(spec, golden_runs):
    r = golden_runs[spec.match_id]
    assert spec.criterion(r)
    assert spec.criterion(run_spec(spec, fast=True))
    meta = json.loads((GOLDEN_DIR / spec.match_id / "match.json").read_text(encoding="utf-8"))
    events = json.loads((GOLDEN_DIR / spec.match_id / "events.json").read_text(encoding="utf-8"))
    assert (meta["score"]["home"], meta["score"]["away"]) == r.score and meta["seed"] == spec.seed
    assert events == r.events, "golden data is stale: run python -m tacticlens.sim golden"


def test_realism_targets_on_small_sample():
    results = league_sample(56, seed=99)
    s = summarize(results)
    assert all(s[t.key]["ok"] for t in TARGETS), {k: round(v["mean"], 2) for k, v in s.items()}
    st = match_stats(results[0].events, results[0].home.id, results[0].away.id)
    assert st["goals"] == sum(results[0].score)


BANNED = ["premier league", "arsenal", "chelsea", "liverpool", "manchester", "tottenham", "everton",
          "newcastle", "aston villa", "west ham", "brighton", "fulham", "brentford", "wolves", "crystal palace",
          "nottingham", "bournemouth", "leicester", "southampton", "ipswich", "burnley", "leeds", "sunderland"]


def test_only_fictional_names():
    names = " ".join([n for n, _ in CLUBS.values()] + [p.name for c in CLUBS for p in make_team(c).players]).lower()
    golden = " ".join(p.read_text(encoding="utf-8").lower() for p in GOLDEN_DIR.glob("*/match.json"))
    for word in BANNED:
        assert word not in names and word not in golden, word
    all_names = [p.name for c in CLUBS for p in make_team(c).players]
    assert len(set(all_names)) == len(all_names)
