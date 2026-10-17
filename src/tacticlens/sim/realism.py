"""Realism report: league-average match stats from simulated events vs real-football targets."""
from __future__ import annotations

import itertools
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

from .engine import MatchResult, simulate
from .teams import CLUBS, make_team


@dataclass(frozen=True)
class Target:
    key: str
    label: str
    lo: float
    hi: float
    fmt: str = "{:.1f}"


TARGETS = [
    Target("goals", "Goals per match", 2.0, 3.5, "{:.2f}"),
    Target("shots", "Shots per team", 9, 16),
    Target("on_target", "Shots on target per team", 3, 6),
    Target("passes", "Passes per team", 350, 600, "{:.0f}"),
    Target("pass_acc", "Pass accuracy (%)", 75, 88),
    Target("fouls", "Fouls per match", 18, 26),
    Target("cards", "Cards per match", 2, 5),
    Target("corners", "Corners per team", 3.5, 6.5),
    Target("dom_poss", "Dominant-side possession (%)", 50, 65),
]


def match_stats(events: list[dict], home_id: str, away_id: str) -> dict[str, float]:
    """Per-match stats computed from Event dicts (per-team values are averaged over both teams)."""
    c = {t: {"passes": 0, "ok": 0, "shots": 0, "on": 0, "goals": 0, "corners": 0} for t in (home_id, away_id)}
    fouls = cards = 0
    for e in events:
        tm, ty = c[e["team"]], e["type"]
        if ty == "pass":
            tm["passes"] += 1
            tm["ok"] += e["outcome"] == "success"
        elif ty == "shot":
            tm["shots"] += 1
            tm["on"] += e["outcome"] in ("goal", "saved")
        elif ty == "goal":
            tm["goals"] += 1
        elif ty == "corner":
            tm["corners"] += 1
        elif ty == "foul":
            fouls += 1
        elif ty == "card":
            cards += 1
    h, a = c[home_id], c[away_id]
    passes = h["passes"] + a["passes"]
    return {
        "goals": h["goals"] + a["goals"],
        "shots": (h["shots"] + a["shots"]) / 2,
        "on_target": (h["on"] + a["on"]) / 2,
        "passes": passes / 2,
        "pass_acc": 100.0 * (h["ok"] + a["ok"]) / max(1, passes),
        "fouls": fouls,
        "cards": cards,
        "corners": (h["corners"] + a["corners"]) / 2,
        "dom_poss": 100.0 * max(h["passes"], a["passes"]) / max(1, passes),
        "home_poss": 100.0 * h["passes"] / max(1, passes),
    }


def league_sample(n_matches: int, seed: int = 2026, fast: bool = False) -> list[MatchResult]:
    """Round-robin fixtures of the fictional league, repeated until n_matches."""
    rng = random.Random(seed)
    pairs = list(itertools.permutations(sorted(CLUBS), 2))
    out = []
    for i in range(n_matches):
        h, a = pairs[i % len(pairs)]
        out.append(simulate(make_team(h), make_team(a), rng.randrange(1 << 30), f"R{i:04d}", fast=fast))
    return out


def summarize(results: list[MatchResult]) -> dict[str, dict[str, float]]:
    rows = [match_stats(r.events, r.home.id, r.away.id) for r in results]
    out = {}
    for t in TARGETS:
        vals = sorted(r[t.key] for r in rows)
        q = statistics.quantiles(vals, n=10) if len(vals) >= 10 else [vals[0]] * 9
        mean = statistics.fmean(vals)
        out[t.key] = {"mean": mean, "p10": q[0], "p90": q[-1], "ok": t.lo <= mean <= t.hi}
    return out


def render_report(summary: dict, n: int, golden: list[tuple[str, str, dict]] | None = None) -> str:
    lines = ["# Simulator realism report", "",
             f"League sample: {n} full-mode matches between the 8 fictional clubs (seeded, reproducible).",
             "Regenerate with `python -m tacticlens.sim realism`.", "",
             "Engine: possession-chain simulator on a 12x8 zone grid. Each action (pass, dribble, shot, clearance) is",
             "sampled from zone- and style-dependent probabilities (press_intensity, tempo, directness, width, quality);",
             "pressing, fouls, cards, corners, free kicks, substitutions and fatigue are modelled. Shot outcomes come",
             "from a hidden ground-truth scoring function that the xG model (M2) has to learn. Fast mode skips",
             "coordinates and Event objects but replays the identical random stream, so a seed gives the same match.", "",
             "| Metric | Target | Mean | p10 - p90 | Pass |", "|---|---|---|---|---|"]
    for t in TARGETS:
        s = summary[t.key]
        f = t.fmt.format
        lines.append(f"| {t.label} | {f(t.lo)} - {f(t.hi)} | {f(s['mean'])} | {f(s['p10'])} - {f(s['p90'])} | "
                     f"{'yes' if s['ok'] else 'NO'} |")
    verdict = all(summary[t.key]["ok"] for t in TARGETS)
    lines += ["", f"**Overall: {'PASS' if verdict else 'FAIL'}** (league mean of every metric inside its target band)."]
    if golden:
        lines += ["", "## Golden matches", "", "| Match | Story | Score | Shots H-A | Passes H-A | Cards |",
                  "|---|---|---|---|---|---|"]
        for mid, story, st in golden:
            lines.append(f"| {mid} | {story} | {st['score']} | {st['shots']} | {st['passes']} | {st['cards']} |")
    return "\n".join(lines) + "\n"


def write_report(path: Path, n: int = 300, golden=None) -> dict:
    summary = summarize(league_sample(n))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(summary, n, golden), encoding="utf-8")
    return summary
