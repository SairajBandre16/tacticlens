"""Deterministic grounding checks. Every number and name must trace back to cited evidence."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .state import EvidencePack

MAX_SENTENCES = 6
MAX_WORDS = 40

NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty".split()) if i >= 2}  # "one" is too often not a count

SCORE_RE = re.compile(r"(?<![\d.])(\d{1,2})\s?[-–]\s?(\d{1,2})(?!\d|\.\d)")
PCT_RE = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*(?:%|per\s?cent\b)", re.I)
PP_RE = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)[\s-]*(?:pp\b|percentage[\s-]points?\b|points?\b)", re.I)
NUM_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w])")
WORD_RE = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.I)

UP_RE = re.compile(r"\b(rose|rise[sn]?|rising|jump(?:ed|s)?|climb(?:ed|s)?|boost(?:ed|s)?|increase[ds]?|"
                   r"lift(?:ed|s)?|surge[ds]?|soar(?:ed|s)?)\b", re.I)
DOWN_RE = re.compile(r"\b(fell|fall(?:s|en|ing)?|drop(?:ped|s)?|slump(?:ed|s)?|decrease[ds]?|dip(?:ped|s)?|"
                     r"slid(?:e|es)?|plunge[ds]?|sank|sink(?:s)?)\b", re.I)
HEDGE_RE = re.compile(r"\b(would|could|might|estimate[ds]?|simulat\w*|likely|about|around|roughly)\b", re.I)
COUNTERFACTUAL_RE = re.compile(r"\b(what if|would have|had not|hadn't|without (?:that|this|the))\b", re.I)
FORBIDDEN_RE = re.compile(r"\b(guarantee[ds]?|certainly|definitely|sure to|bet(?:s|ting)?|odds|bookmakers?|"
                          r"wagers?)\b", re.I)

# Real-world names that must never appear (synthetic data only).
REAL_NAMES = ["Premier League", "Arsenal", "Chelsea", "Liverpool", "Manchester", "Man City", "Man United",
              "Tottenham", "Spurs", "Everton", "Newcastle", "Aston Villa", "Brighton", "Brentford", "Fulham",
              "Wolves", "Wolverhampton", "West Ham", "Crystal Palace", "Bournemouth", "Nottingham Forest",
              "Leicester", "Southampton", "Ipswich", "Leeds", "Burnley", "Sunderland", "Haaland", "Salah",
              "Saka", "Bellingham", "De Bruyne", "Rashford", "Messi", "Ronaldo", "Mbappe", "Mbappé", "Kane",
              "Odegaard", "Ødegaard", "Palmer", "Foden", "Rice"]
REAL_RE = re.compile(r"\b(" + "|".join(re.escape(n) for n in REAL_NAMES) + r")\b")


@dataclass
class Report:
    ok: bool = True
    notes: list[str] = field(default_factory=list)
    n_sentences: int = 0
    n_numbers: int = 0
    n_numbers_ok: int = 0
    n_cited_ok: int = 0

    def fail(self, note: str) -> None:
        self.ok = False
        self.notes.append(note)

    def stats(self) -> dict:
        return {"sentences": self.n_sentences, "cited_ok": self.n_cited_ok,
                "numbers": self.n_numbers, "numbers_ok": self.n_numbers_ok}


def _decimals(token: str) -> int:
    return len(token.split(".")[1]) if "." in token else 0


def _matches(token: str, values: list[float]) -> bool:
    n, d = abs(float(token)), _decimals(token)
    tol = 0.5 * 10 ** -d + 1e-9
    return any(abs(abs(v) - n) <= tol for v in values)


def _label_numbers(items: list[dict]) -> list[float]:
    return [float(t) for e in items for t in NUM_RE.findall(e["label"])]


def _numeric(items: list[dict], unit: str | None = None) -> list[float]:
    return [float(e["value"]) for e in items
            if isinstance(e["value"], (int, float)) and (unit is None or e["unit"] == unit)]


def _check_numbers(text: str, cited: list[dict], rep: Report, i: int) -> None:
    strings = {str(e["value"]) for e in cited if isinstance(e["value"], str)}
    labels = _label_numbers(cited)
    rest = text
    for m in SCORE_RE.finditer(text):
        rep.n_numbers += 1
        if f"{m.group(1)}-{m.group(2)}" in strings:
            rep.n_numbers_ok += 1
        else:
            rep.fail(f"s{i}: scoreline '{m.group(0)}' not in cited evidence")
    rest = SCORE_RE.sub(" ", rest)
    for regex, unit in ((PCT_RE, "%"), (PP_RE, "pp")):
        for m in regex.finditer(rest):
            rep.n_numbers += 1
            if _matches(m.group(1), _numeric(cited, unit) + labels):
                rep.n_numbers_ok += 1
            else:
                rep.fail(f"s{i}: '{m.group(0).strip()}' not backed by a cited {unit} item")
        rest = regex.sub(" ", rest)
    values = _numeric(cited) + labels
    for tok in NUM_RE.findall(rest) + [str(NUMBER_WORDS[w.lower()]) for w in WORD_RE.findall(rest)]:
        rep.n_numbers += 1
        if _matches(tok, values):
            rep.n_numbers_ok += 1
        else:
            rep.fail(f"s{i}: number {tok} not backed by cited evidence")


def _check_direction(text: str, cited: list[dict], rep: Report, i: int) -> None:
    up, down = bool(UP_RE.search(text)), bool(DOWN_RE.search(text))
    if up == down:
        return
    deltas = _numeric(cited, "pp")
    by_label = {e["label"]: e["value"] for e in cited}
    for label, before in by_label.items():
        if label.endswith(" before") and isinstance(before, (int, float)):
            after = by_label.get(label[:-len(" before")] + " after")
            if isinstance(after, (int, float)):
                deltas.append(after - before)
    if deltas and all(d == 0 for d in deltas):
        rep.fail(f"s{i}: direction word but the cited change is zero")
    elif any((d > 0) != up for d in deltas if d != 0):
        rep.fail(f"s{i}: direction word ('{'up' if up else 'down'}') contradicts cited change")


def _check_entities(text: str, pack: EvidencePack, rep: Report, i: int) -> None:
    if m := REAL_RE.search(text):
        rep.fail(f"s{i}: real-world club or player name is not allowed")
    for club in pack.foreign_clubs:
        if re.search(rf"\b{re.escape(club.split()[0])}\b", text):
            rep.fail(f"s{i}: club '{club}' is not in this match")
    for player in pack.foreign_players:
        if re.search(rf"\b{re.escape(player.split()[-1])}\b", text) and not any(
                player.split()[-1] in p for p in pack.players):
            rep.fail(f"s{i}: player '{player}' is not in this match")


def verify(sentences: list[dict] | tuple[dict, ...], pack: EvidencePack) -> Report:
    rep = Report(n_sentences=len(sentences))
    if not 1 <= len(sentences) <= MAX_SENTENCES:
        rep.fail(f"need 1-{MAX_SENTENCES} sentences, got {len(sentences)}")
    for i, s in enumerate(sentences, 1):
        text, ids = (s.get("text") or "").strip(), list(s.get("evidence_ids") or [])
        if not text:
            rep.fail(f"s{i}: empty text")
            continue
        if len(text.split()) > MAX_WORDS:
            rep.fail(f"s{i}: longer than {MAX_WORDS} words")
        unknown = [e for e in ids if e not in pack.items]
        if not ids:
            rep.fail(f"s{i}: cites no evidence")
        elif unknown:
            rep.fail(f"s{i}: unknown evidence ids {unknown}")
        else:
            rep.n_cited_ok += 1
        cited = [pack.items[e] for e in ids if e in pack.items]
        _check_numbers(text, cited, rep, i)
        _check_direction(text, cited, rep, i)
        _check_entities(text, pack, rep, i)
        what_if = any(e["label"].startswith("What-if") for e in cited)
        if COUNTERFACTUAL_RE.search(text) and not what_if:
            rep.fail(f"s{i}: counterfactual claim without a cited What-if item")
        if what_if and not HEDGE_RE.search(text):
            rep.fail(f"s{i}: What-if sentence must be hedged (would/about/simulated)")
        if m := FORBIDDEN_RE.search(text):
            rep.fail(f"s{i}: forbidden certainty/betting word '{m.group(0)}'")
    return rep
