import json

from fastapi.testclient import TestClient

from tacticlens.agents.workflow import run_match
from tacticlens.api.app import app
from tacticlens.sim.golden import GOLDEN_DIR
from tacticlens.store import CosmosStore, JsonStore, get_store

client = TestClient(app)
META = json.loads((GOLDEN_DIR / "GM01" / "match.json").read_text(encoding="utf-8"))


class FakeContainer:
    def __init__(self, rows=None, fail=False):
        self.rows, self.fail = list(rows or []), fail

    def query_items(self, query, parameters, partition_key):
        if self.fail:
            raise ConnectionError("cosmos down")
        return [dict(r, _etag="x") for r in self.rows if r["match_id"] == partition_key]

    def upsert_item(self, item):
        if self.fail:
            raise ConnectionError("cosmos down")
        self.rows = [r for r in self.rows if r["id"] != item["id"]] + [item]


def cosmos(tmp_path, fail=False):
    s = object.__new__(CosmosStore)  # skip the real client; containers are fakes
    s.moments_c, s.expl_c = FakeContainer(fail=fail), FakeContainer(fail=fail)
    s.fallback = JsonStore(local_dir=tmp_path)
    return s


def test_default_store_is_json():
    assert get_store().name == "json"
    assert client.get("/api/health").json()["store"] == "json"


def test_cosmos_seeds_from_golden_then_reads_back(tmp_path):
    s, golden = cosmos(tmp_path), JsonStore().moments("GM01")
    assert s.moments("GM01") == sorted(golden, key=lambda m: (m["t_start"], m["id"]))
    assert len(s.moments_c.rows) == len(golden)
    assert all(not k.startswith("_") for m in s.moments("GM01") for k in m)  # Cosmos system fields stripped


def test_cosmos_failure_falls_back_to_json(tmp_path):
    s = cosmos(tmp_path, fail=True)
    assert s.moments("GM01") == JsonStore().moments("GM01")
    exp = {"moment_id": "GM01-m01", "persona_key": "casual.en"}
    doc_id = s.save_explanation("GM01", exp, [], "foundry")
    assert "/" not in doc_id and list((tmp_path / "GM01").glob("*.json"))


class FakeSafety:
    def __init__(self, sev=None, fail=False):
        self.sev, self.fail = sev or {}, fail

    async def analyze_text(self, text):
        if self.fail:
            raise TimeoutError("slow")
        return self.sev


def _gate(safety):
    m = JsonStore().moments("GM01")[0]
    exps, tr = run_match(META, [m], personas=("casual",), safety=safety)
    return exps[0], tr["moments"][m["id"]]["casual"][-1]


def test_safety_gate_blocks_on_medium_severity():
    exp, step = _gate(FakeSafety({"Hate": 0, "Violence": 4}))
    assert step["action"] == "blocked" and exp["degraded"] and "Violence severity 4" in exp["verifier_notes"][-1]


def test_safety_gate_passes_low_severity_and_survives_outage():
    exp, step = _gate(FakeSafety({"Violence": 2}))
    assert step["action"] == "passed" and step["severity"] == {"Violence": 2} and not exp["degraded"]
    _, step = _gate(FakeSafety(fail=True))
    assert step["action"] == "passed" and "unavailable" in step["error"]


def test_live_explain_refused_in_golden_mode():
    r = client.post("/api/matches/GM01/explain", json={"moment_id": JsonStore().moments("GM01")[0]["id"], "live": True})
    assert r.status_code == 409
