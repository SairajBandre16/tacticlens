import pytest
from fastapi.testclient import TestClient

from tacticlens.api.app import app
from tacticlens.contracts import OverlayCue

client = TestClient(app)


def test_health_and_matches():
    assert client.get("/api/health").json()["mode"] == "golden"
    assert len(client.get("/api/matches").json()) == 6
    assert client.get("/api/matches/NOPE").status_code == 404


def test_match_detail_has_periods_and_wp():
    d = client.get("/api/matches/GM01").json()
    assert [p["period"] for p in d["periods"]] == [1, 2]
    assert d["wp"][0]["minute"] == 0 and len(d["moments"]) == 11


def test_events_carry_shot_xg_matching_total():
    evs = client.get("/api/matches/GM01/events").json()
    xg_total = client.get("/api/matches/GM01").json()["xg_total"]
    sums = [sum(e["xg"] or 0 for e in evs if e["team"] == t) for t in ("NBU", "KES")]
    assert all(e["xg"] is not None for e in evs if e["type"] == "shot")
    assert sums == pytest.approx(xg_total, abs=0.01)


def test_cards_localized_with_english_beside():
    r = client.get("/api/matches/GM01/cards", params={"mode": "casual", "lang": "hi"}).json()
    assert r["persona"].startswith("casual.hi")
    s = r["cards"][0]["sentences"][0]
    assert s["en_text"] and s["back_translation"] and s["text"] != s["en_text"]


def test_bad_persona_rejected():
    assert client.get("/api/matches/GM01/cards", params={"mode": "pundit"}).status_code == 422


def test_overlays_follow_contract_and_evidence():
    d = client.get("/api/matches/GM01").json()
    evidence = {e["id"]: e for m in d["moments"] for e in m["evidence"]}
    cues = client.get("/api/matches/GM01/overlays", params={"mode": "analyst"}).json()["cues"]
    assert {c["template"] for c in cues} >= {"lower_third", "stat_bug", "wp_swing", "player_tag"}
    for c in cues:
        OverlayCue(**c)
        assert c["out_t"] > c["in_t"] and c["a11y"]["aria_label"]
        assert all(i in evidence for i in c["payload"]["evidence_ids"])
        if c["template"] == "stat_bug":
            assert c["payload"]["value"] == evidence[c["payload"]["evidence_ids"][0]]["value"]
    assert [c["in_t"] for c in cues] == sorted(c["in_t"] for c in cues)


def test_pressing_map_cue_for_press_collapse():
    cues = client.get("/api/matches/GM04/overlays", params={"mode": "analyst"}).json()["cues"]
    assert any(c["template"] == "pressing_map" for c in cues)


def test_replay_sse_streams_events_then_end():
    with client.stream("GET", "/api/matches/GM01/replay", params={"from_t": 5850, "speed": 2000}) as r:
        body = "".join(r.iter_text())
    assert body.count("event: ev") >= 1 and body.rstrip().endswith("data: {}")


def test_whatif_precomputed_and_none():
    r = client.get("/api/matches/GM01/whatif/GM01-M05").json()
    assert r["source"] == "precomputed" and r["counterfactual"]["n_rollouts"] == 200 and len(r["evidence"]) == 8
    assert client.get("/api/matches/GM01/whatif/GM01-M01").json()["source"] == "none"


def test_trace_and_kill_switch_falls_back_to_template():
    t = client.get("/api/matches/GM01/trace/GM01-M05", params={"mode": "casual", "lang": "hi"}).json()
    assert t["explain"][0]["agent"] == "spotter" and t["localize"][0]["agent"] == "localizer"
    r = client.post("/api/matches/GM01/explain", json={"moment_id": "GM01-M05", "kill": True}).json()
    agents = [s["agent"] for s in r["trace"]]
    assert agents.count("explainer") == 3 and "template_fallback" in agents
    assert r["explanation"]["degraded"] and r["explanation"]["verified"]
