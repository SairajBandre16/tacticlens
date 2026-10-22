import asyncio
import json
import re

import pytest

from tacticlens.agents.eval import load, match_ids
from tacticlens.agents.state import EvidencePack
from tacticlens.agents.verifier import verify
from tacticlens.contracts import Explanation, Persona
from tacticlens.personalize.checks import check_sentence, numbers
from tacticlens.personalize.cricket import PACK, analogy_sentence
from tacticlens.personalize.glossary import localize_name, match_names, name_table
from tacticlens.personalize.localize import localize_moment
from tacticlens.personalize.persona import index_explanations, personalize, player_name, select_moments
from tacticlens.personalize.speech import audio_name, ssml
from tacticlens.sim.golden import GOLDEN_DIR
from tacticlens.sim.teams import CLUBS, make_team

LATIN = re.compile(r"[A-Za-z]")


@pytest.fixture(scope="module")
def gm01():
    meta, moments = load("GM01")
    exps = json.loads((GOLDEN_DIR / "GM01" / "explanations.json").read_text(encoding="utf-8"))
    return meta, moments, exps


# --- glossary + checks -----------------------------------------------------------------------------------

def test_every_club_and_player_has_a_devanagari_name():
    for cid, (club, _) in CLUBS.items():
        assert not LATIN.search(localize_name(club, "hi")), club
        for p in make_team(cid).players:
            assert not LATIN.search(localize_name(p.name, "hi")), p.name
            assert localize_name(p.name, "es") == p.name


def test_vowel_initial_surname_part_joins_as_vowel_sign():
    assert localize_name("Omar Osiva", "hi") == "ओमार ओसिवा"


def test_numbers_normalise_scripts_and_decimal_commas():
    assert numbers("xG ०.१२, ६४ प्रतिशत") == {0.12, 64.0}
    assert numbers("un xG de 0,12 y 2-1") == {0.12, 2.0, 1.0}


def test_check_sentence_catches_number_and_name_drift(gm01):
    meta = gm01[0]
    home = meta["home"]["name"]
    src = f"{home} win chance jumped to 64%, up 12 points."
    good = f"{localize_name(home, 'hi')} की जीत की संभावना 64% हो गई, 12 अंक ऊपर।"
    assert check_sentence(src, good, "hi", meta) == []
    assert any("dropped" in n for n in check_sentence(src, good.replace("12", "बारह"), "hi", meta))
    assert any("added" in n for n in check_sentence(src, good.replace("64%", "65%, 64%"), "hi", meta))
    assert any("must appear" in n for n in check_sentence(src, good.replace(localize_name(home, "hi"), home), "hi", meta))
    assert any("English" in n for n in check_sentence(src, src, "es", meta))


# --- localizer pipeline (fake agent + fake Translator: no Azure) -------------------------------------------

class FakeLocalizer:
    name = "fake"

    def __init__(self, drop_number_on_attempt: tuple[int, ...] = ()):
        self.calls, self.bad = 0, drop_number_on_attempt

    async def translate(self, items, lang, names):
        self.calls += 1
        out = {}
        for it in items:
            text = it["text"]
            for n in sorted(names, key=len, reverse=True):
                text = text.replace(n, names[n])
            if self.calls in self.bad:
                text = re.sub(r"\d", "", text)
            out[it["key"]] = ("अनुवाद: " if lang == "hi" else "Traducción: ") + text
        return out


class FakeRest:
    def __init__(self, ok: bool = True):
        self.ok, self.calls = ok, []

    async def translate(self, texts, to, frm="en"):
        self.calls.append((frm, to, len(texts)))
        if to == "en":
            return [re.sub(r"^\S+: ", "", t) for t in texts]
        if not self.ok:
            return ["" for _ in texts]
        clean = [re.sub(r'<mstrans:dictionary translation="([^"]*)">[^<]*</mstrans:dictionary>', r"\1", t)
                 for t in texts]
        return [("अनुवाद: " if to == "hi" else "Traducción: ") + t for t in clean]


def _moment_exps(gm01, kind="goal"):
    meta, moments, exps = gm01
    mid = next(m["id"] for m in moments if m["kind"] == kind)
    return meta, [e for e in exps if e["moment_id"] == mid]


def test_localizer_happy_path_keeps_evidence_and_adds_back_translation(gm01):
    meta, exps = _moment_exps(gm01)
    out, trace = asyncio.run(localize_moment(exps, meta, "hi", FakeLocalizer(), FakeRest()))
    assert len(out) == len(exps)
    for src, loc in zip(exps, out):
        Explanation.model_validate(loc)
        assert loc["lang"] == "hi" and loc["degraded"] == src["degraded"]
        for s, ls in zip(src["sentences"], loc["sentences"]):
            assert ls["evidence_ids"] == s["evidence_ids"] and ls["en_text"] == s["text"]
            assert ls["back_translation"]
    done = trace[-1]
    assert done["english_fallback"] == 0 and done["agent_ok"] == sum(len(e["sentences"]) for e in exps)


def test_localizer_regenerates_then_falls_back(gm01):
    meta, exps = _moment_exps(gm01)
    agent = FakeLocalizer(drop_number_on_attempt=(1,))
    out, trace = asyncio.run(localize_moment(exps, meta, "es", agent, FakeRest()))
    assert agent.calls == 2 and trace[-1]["english_fallback"] == 0

    out, trace = asyncio.run(localize_moment(exps, meta, "es", FakeLocalizer((1, 2)), FakeRest()))
    assert trace[-1]["translator_ok"] > 0 and trace[-1]["english_fallback"] == 0

    out, trace = asyncio.run(localize_moment(exps, meta, "hi", FakeLocalizer((1, 2)), FakeRest(ok=False)))
    numeric = sum(bool(numbers(s["text"])) for e in exps for s in e["sentences"])
    assert trace[-1]["english_fallback"] == numeric > 0
    assert all(e["degraded"] for e, src in zip(out, exps)
               if any(numbers(s["text"]) for s in src["sentences"]))


# --- cricket pack + persona engine -------------------------------------------------------------------------

def test_cricket_analogies_cover_every_kind_and_pass_the_verifier():
    seen = set()
    for mid in match_ids():
        meta, moments = load(mid)
        for m in moments:
            pack = EvidencePack(m, meta)
            s = analogy_sentence(pack, "en")
            assert s, m["kind"]
            assert verify([s], pack).ok, (m["id"], verify([s], pack).notes)
            seen.add(m["kind"])
            assert analogy_sentence(pack, "hi")["en_text"] == s["text"]
    assert {"goal", "red_card", "momentum_shift"} <= seen
    assert all(set(v) == {"en", "hi", "es"} for v in PACK.values())


def test_player_lock_and_favourite_club(gm01):
    meta, moments, exps = gm01
    scorer = next(e["value"] for m in moments for e in m["evidence"] if e["label"] == "Shooter")
    pid = next(p["id"] for s in ("home", "away") for p in meta[s]["players"] if p["name"] == scorer)
    assert player_name(meta, pid) == scorer
    locked = select_moments(moments, meta, Persona(mode="casual", lang="en", fav_player=pid, player_lock=True))
    assert locked and all(any(scorer in str(e["value"]) for e in m["evidence"]) for m in locked)
    cards = personalize(moments, meta, Persona(mode="casual", lang="en", fav_club=meta["away"]["id"]),
                        index_explanations(exps), top_n=3)
    assert len(cards) == 3 and [c["t_start"] for c in cards] == sorted(c["t_start"] for c in cards)


def test_card_falls_back_to_english_and_trims_for_low_density(gm01):
    meta, moments, exps = gm01
    idx = index_explanations(exps)
    m = next(m for m in moments if m["kind"] == "goal")
    card = personalize([m], meta, Persona(mode="analyst", lang="ja", stats_density=0, analogy="cricket"), idx)[0]
    assert card["lang"] == "en" and card["degraded"] and card["analogy"]
    assert len(card["sentences"]) <= 4
    assert all(s["evidence_ids"] for s in card["sentences"])


def test_golden_localized_files_cover_every_explanation_in_hi_and_es():
    for mid in match_ids():
        path = GOLDEN_DIR / mid / "localized.json"
        assert path.exists(), f"{mid}: run python -m tacticlens.personalize localize --live"
        loc = json.loads(path.read_text(encoding="utf-8"))
        en = json.loads((GOLDEN_DIR / mid / "explanations.json").read_text(encoding="utf-8"))
        keys = {(e["moment_id"], e["persona_key"], e["lang"]) for e in loc["explanations"]}
        assert keys == {(e["moment_id"], e["persona_key"], lang) for e in en for lang in ("hi", "es")}
        for e in loc["explanations"]:
            Explanation.model_validate(e)
            assert all(s.get("en_text") for s in e["sentences"])


def test_golden_audio_has_en_and_hi():
    for mid in match_ids():
        audio = json.loads((GOLDEN_DIR / mid / "audio.json").read_text(encoding="utf-8"))
        assert audio
        for langs in audio.values():
            assert {"en", "hi"} <= set(langs)
            assert all((GOLDEN_DIR / mid / rel).stat().st_size > 1000 for rel in langs.values())


def test_ssml_escapes_and_audio_names_are_stable(gm01):
    meta = gm01[0]
    assert "&amp;" in ssml("A & B", "en") and "hi-IN-SwaraNeural" in ssml("x", "hi")
    assert audio_name("hello", "en") == audio_name("hello", "en") != audio_name("hello", "hi")
    assert set(name_table(meta, "es").values()) == set(match_names(meta))
