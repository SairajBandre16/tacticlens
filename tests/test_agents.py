"""Agents workflow: verifier checks, template fallback, retries, kill switch, committed golden explanations."""
import json

import pytest
from jsonschema import Draft202012Validator

from tacticlens.agents.eval import keep_section, load, match_ids, upsert
from tacticlens.agents.explainer import FAULTS, KILL_ENV, OfflineExplainer, inject, offline_sentences
from tacticlens.agents.state import MAX_ATTEMPTS, PERSONAS, EvidencePack
from tacticlens.agents.templates import template_sentences
from tacticlens.agents.verifier import verify
from tacticlens.agents.workflow import run_match
from tacticlens.contracts import load_schema
from tacticlens.sim.golden import GOLDEN_DIR

IDS = match_ids()


@pytest.fixture(scope="module")
def packs():
    out = []
    for mid in IDS:
        meta, moments = load(mid)
        out += [EvidencePack(m, meta) for m in moments]
    return out


@pytest.fixture(scope="module")
def goal_pack(packs):
    return next(p for p in packs if p.moment["kind"] == "goal" and p.moment["counterfactuals"])


def test_templates_and_offline_drafts_pass_verifier(packs):
    for p in packs:
        assert verify(template_sentences(p), p).ok, p.moment["id"]
        for persona in PERSONAS:
            rep = verify(offline_sentences(p, persona), p)
            assert rep.ok, (p.moment["id"], persona, rep.notes)


@pytest.mark.parametrize("fault", FAULTS)
def test_verifier_catches_each_fault(packs, fault):
    applied = 0
    for p in packs:
        for persona in PERSONAS:
            if bad := inject(offline_sentences(p, persona), fault, p):
                applied += 1
                assert not verify(bad, p).ok, (fault, p.moment["id"], persona)
    assert applied > 0


def test_number_rules(goal_pack):
    p = goal_pack
    xg = p.by_label("Shot xG")
    ok = [{"text": f"The shot was worth {xg['value']:.2f} xG.", "evidence_ids": [xg["id"]]}]
    assert verify(ok, p).ok
    uncited = [{"text": f"The shot was worth {xg['value']:.2f} xG.", "evidence_ids": [p.by_label("Minute")["id"]]}]
    assert not verify(uncited, p).ok  # number exists in the pack but not in the cited item
    pct = [{"text": f"It was {xg['value']:.2f}%.", "evidence_ids": [xg["id"]]}]
    assert not verify(pct, p).ok  # unit-aware: % needs a % item
    words = [{"text": "Seventeen players were involved.", "evidence_ids": [xg["id"]]}]
    assert not verify(words, p).ok


def test_workflow_retries_then_verifies_deterministically(packs):
    meta, moments = load(IDS[0])
    a = run_match(meta, moments[:3], OfflineExplainer(fault_rate=1.0))
    b = run_match(meta, moments[:3], OfflineExplainer(fault_rate=1.0))
    assert a == b
    explanations, trace = a
    assert len(explanations) == 3 * len(PERSONAS)
    for e in explanations:
        steps = trace["moments"][e["moment_id"]][e["persona_key"]]
        verdicts = [s["action"] for s in steps if s["agent"] == "verifier"]
        assert verdicts[0] == "rejected" and len(verdicts) <= MAX_ATTEMPTS
        assert e["verified"]
        assert [s["agent"] for s in steps][-3:] == ["localizer", "accessibility_describer", "safety_gate"]


def test_kill_switch_falls_back_with_trace(monkeypatch):
    monkeypatch.setenv(KILL_ENV, "1")
    meta, moments = load(IDS[0])
    explanations, trace = run_match(meta, moments[:2], OfflineExplainer(), personas=("casual",))
    for e in explanations:
        assert e["degraded"] and e["verified"]
        agents = [s["agent"] for s in trace["moments"][e["moment_id"]]["casual"]]
        assert agents.count("explainer") == MAX_ATTEMPTS and "template_fallback" in agents


def test_golden_explanations_cover_every_moment():
    validator = Draft202012Validator(load_schema("explanation"))
    for mid in IDS:
        meta, moments = load(mid)
        explanations = json.loads((GOLDEN_DIR / mid / "explanations.json").read_text(encoding="utf-8"))
        trace = json.loads((GOLDEN_DIR / mid / "trace.json").read_text(encoding="utf-8"))
        packs = {m["id"]: EvidencePack(m, meta) for m in moments}
        assert {(m["id"], p) for m in moments for p in PERSONAS} == {
            (e["moment_id"], e["persona_key"]) for e in explanations}
        for e in explanations:
            validator.validate(e)
            assert e["verified"]
            assert verify(e["sentences"], packs[e["moment_id"]]).ok
        assert set(trace["moments"]) == set(packs)


def test_eval_section_survives_metrics_rewrite():
    section = "<!-- agents-eval:start -->\nX\n<!-- agents-eval:end -->\n"
    doc = upsert("# Evaluation\n", section)
    assert keep_section(doc, "# Evaluation v2\n").endswith(section)
    assert upsert(doc, section.replace("X", "Y")).count("agents-eval:start") == 1
