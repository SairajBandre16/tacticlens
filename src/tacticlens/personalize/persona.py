"""Persona engine: pick and rank moments for a viewer, then assemble one card per moment.

Deterministic and cheap, so the API can run it per request over the golden (or live) explanations.
"""
from __future__ import annotations

from ..agents.state import EvidencePack
from ..agents.templates import Facts
from ..contracts import Persona
from .checks import numbers
from .cricket import analogy_sentence

FAV_BOOST = 1.25


def player_name(meta: dict, player_id: str | None) -> str | None:
    return next((p["name"] for s in ("home", "away") for p in meta[s]["players"] if p["id"] == player_id), None)


def club_name(meta: dict, club_id: str | None) -> str | None:
    return next((meta[s]["name"] for s in ("home", "away") if meta[s]["id"] == club_id), None)


def involves(moment: dict, name: str | None) -> bool:
    return bool(name) and any(isinstance(e["value"], str) and name in e["value"] for e in moment["evidence"])


def subject_club(moment: dict, meta: dict) -> str | None:
    team = Facts(EvidencePack(moment, meta)).team
    return team["value"] if team else None


def select_moments(moments: list[dict], meta: dict, persona: Persona, top_n: int | None = None) -> list[dict]:
    """Rank by importance (favourite club boosted); player-lock keeps only the favourite player's moments."""
    club, player = club_name(meta, persona.fav_club), player_name(meta, persona.fav_player)
    pool = [m for m in moments if involves(m, player)] if persona.player_lock and player else list(moments)

    def score(m: dict) -> float:
        return m["importance"] * (FAV_BOOST if club and subject_club(m, meta) == club else 1.0)

    ranked = sorted(pool, key=lambda m: (-score(m), m["t_start"]))[:top_n]
    return sorted(ranked, key=lambda m: m["t_start"])


def _trim(sentences: list[dict], density: int) -> list[dict]:
    """stats_density 0: keep the headline plus sentences with at most one number, three sentences max."""
    if density > 0 or len(sentences) <= 1:
        return sentences
    rest = [s for s in sentences[1:] if len(numbers(s.get("en_text") or s["text"])) <= 1]
    return (sentences[:1] + rest)[:3]


def build_card(moment: dict, meta: dict, persona: Persona, explanations: dict[tuple[str, str, str], dict],
               audio: dict | None = None) -> dict:
    """One personalized card. explanations is keyed by (moment_id, mode, lang); English is the fallback."""
    mid = moment["id"]
    exp = explanations.get((mid, persona.mode, persona.lang))
    shown_lang = persona.lang if exp else "en"
    exp = exp or explanations[(mid, persona.mode, "en")]
    sentences = _trim([dict(s) for s in exp["sentences"]], persona.stats_density)
    analogy = None
    if persona.analogy == "cricket":
        analogy = analogy_sentence(EvidencePack(moment, meta), shown_lang)
        if analogy:
            sentences.insert(1, analogy)
    club, player = club_name(meta, persona.fav_club), player_name(meta, persona.fav_player)
    return {
        "moment_id": mid, "kind": moment["kind"], "t_start": moment["t_start"], "persona": persona.key,
        "mode": persona.mode, "lang": shown_lang, "sentences": sentences,
        "verified": exp["verified"], "degraded": exp["degraded"] or shown_lang != persona.lang,
        "analogy": bool(analogy), "fav_club": bool(club) and subject_club(moment, meta) == club,
        "fav_player": involves(moment, player),
        "audio": (audio or {}).get(mid, {}).get(shown_lang) if persona.mode == "audio" else None,
    }


def index_explanations(*groups: list[dict]) -> dict[tuple[str, str, str], dict]:
    return {(e["moment_id"], e["persona_key"], e["lang"]): e for g in groups for e in g}


def personalize(moments: list[dict], meta: dict, persona: Persona, explanations: dict, audio: dict | None = None,
                top_n: int | None = None) -> list[dict]:
    """Cards for every selected moment that has an explanation for this persona mode."""
    return [build_card(m, meta, persona, explanations, audio) for m in select_moments(moments, meta, persona, top_n)
            if (m["id"], persona.mode, "en") in explanations]
