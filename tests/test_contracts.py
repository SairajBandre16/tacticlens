"""Contracts: schemas are valid, fixtures validate, pydantic models mirror the schemas."""
import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from tacticlens import contracts as c

FIXTURES = Path(__file__).parent / "fixtures"
NAMES = sorted(c.MODELS)

# (schema name, $defs key or None for the root) -> model
NESTED = {
    ("event", None): c.Event,
    ("moment", None): c.Moment,
    ("moment", "WinProb"): c.WinProb,
    ("moment", "Evidence"): c.Evidence,
    ("moment", "Counterfactual"): c.Counterfactual,
    ("explanation", None): c.Explanation,
    ("explanation", "Sentence"): c.Sentence,
    ("overlay_cue", None): c.OverlayCue,
    ("overlay_cue", "A11y"): c.A11y,
    ("persona", None): c.Persona,
}


def fixtures(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def validator(name):
    return Draft202012Validator(c.load_schema(name))


def test_every_schema_has_model_and_fixture():
    stems = {p.name.removesuffix(".schema.json") for p in c.CONTRACTS_DIR.glob("*.schema.json")}
    assert stems == set(c.MODELS)
    assert all((FIXTURES / f"{n}.json").exists() for n in stems)


@pytest.mark.parametrize("name", NAMES)
def test_schema_is_valid(name):
    Draft202012Validator.check_schema(c.load_schema(name))


@pytest.mark.parametrize("name", NAMES)
def test_fixtures_validate_and_roundtrip(name):
    v, model = validator(name), c.MODELS[name]
    items = fixtures(name)
    assert items
    for item in items:
        v.validate(item)
        dumped = model.model_validate(item).model_dump(mode="json")
        v.validate(dumped)  # pydantic output is schema-valid too
        assert model.model_validate(dumped).model_dump(mode="json") == dumped


@pytest.mark.parametrize("key", list(NESTED), ids=lambda k: f"{k[0]}.{k[1] or 'root'}")
def test_model_mirrors_schema_fields(key):
    name, sub = key
    schema = c.load_schema(name)
    node = schema if sub is None else schema["$defs"][sub]
    model: type[BaseModel] = NESTED[key]
    assert set(model.model_fields) == set(node["properties"])
    required = {f for f, info in model.model_fields.items() if info.is_required()}
    assert required == set(node.get("required", []))


BAD = {
    "event": lambda d: d.update(x=150),
    "moment": lambda d: d.update(kind="own_goal"),
    "explanation": lambda d: d["sentences"][0].update(evidence_ids=[]),
    "overlay_cue": lambda d: d.update(unknown_field=1),
    "persona": lambda d: d.update(tone=3),
}


@pytest.mark.parametrize("name", NAMES)
def test_invalid_rejected_by_schema_and_model(name):
    bad = copy.deepcopy(fixtures(name)[0])
    BAD[name](bad)
    assert not validator(name).is_valid(bad)
    with pytest.raises(ValidationError):
        c.MODELS[name].model_validate(bad)


def test_persona_key_is_stable():
    p = c.Persona(mode="casual", lang="hi", fav_club="NBU", analogy="cricket", tone=2, stats_density=0)
    assert p.key == "casual.hi.cricket.t2.d0.NBU.-"
    assert c.Persona.model_validate(p.model_dump()).key == p.key
    assert p.model_copy(update={"player_lock": True}).key == p.key + ".lock"
