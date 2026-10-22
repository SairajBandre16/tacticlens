"""Deterministic checks on a localized sentence: same numbers, same entities, real target language."""
from __future__ import annotations

import re

from ..agents.verifier import REAL_RE
from .glossary import fold, localize_name, names_in

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def numbers(text: str) -> set[float]:
    """Numbers in any of our languages: Devanagari digits and decimal commas are normalised first."""
    text = text.translate(DEVANAGARI_DIGITS)
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)
    return {round(float(t), 4) for t in NUM_RE.findall(text)}


def check_sentence(src: str, loc: str, lang: str, meta: dict) -> list[str]:
    """Problems with one localized sentence (empty list = pass)."""
    notes = []
    if not loc.strip():
        return ["empty translation"]
    if lang == "hi" and not DEVANAGARI_RE.search(loc):
        notes.append("not in Devanagari script")
    if lang != "en" and loc.strip() == src.strip():
        notes.append("text left in English")
    want, got = numbers(src), numbers(loc)
    if missing := want - got:
        notes.append(f"numbers dropped: {sorted(missing)}")
    if extra := got - want:
        notes.append(f"numbers added: {sorted(extra)}")
    for name in names_in(src, meta):
        target = localize_name(name, lang)
        if fold(target) not in fold(loc):
            notes.append(f"name '{name}' must appear as '{target}'")
    if m := REAL_RE.search(loc):
        notes.append(f"real-world name '{m.group(0)}'")
    return notes


def check_back_translation(src: str, back: str) -> list[str]:
    """Back-translation drift notes (informational: the translator, not the Localizer, wrote it)."""
    notes = []
    if numbers(src) != numbers(back):
        notes.append(f"back-translation numbers differ: {sorted(numbers(back) ^ numbers(src))}")
    if m := REAL_RE.search(back):
        notes.append(f"back-translation has real-world name '{m.group(0)}'")
    return notes
