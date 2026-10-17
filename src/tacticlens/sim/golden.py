"""The 6 golden demo matches: scripted story beats + a seed whose emergent result fits the story.

Seeds were found once with `find_seed` (fast mode) and are pinned here, so builds are instant and
reproducible. Tests re-check every story criterion.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .engine import Beat, MatchResult, simulate
from .teams import make_team

GOLDEN_DIR = Path(__file__).resolve().parents[3] / "data" / "golden"


def _last_goal_minute(r: MatchResult, side: str) -> int:
    return max((g.minute for g in r.goals if g.side == side), default=-1)


def _both_led(r: MatchResult) -> bool:
    h = a = 0
    led = set()
    for g in r.goals:
        h, a = h + (g.side == "home"), a + (g.side == "away")
        if h != a:
            led.add("home" if h > a else "away")
    return led == {"home", "away"}


def _comeback(r: MatchResult) -> bool:
    h70, a70 = r.score_at(70)
    return r.score == (3, 2) and h70 < a70 and _last_goal_minute(r, "home") >= 80 and not r.reds


def _ten_men(r: MatchResult) -> bool:
    return (r.score == (1, 0) and len(r.reds) == 1 and r.reds[0][1] == "away"
            and all(g.minute > r.reds[0][0] for g in r.goals))


def _derby(r: MatchResult) -> bool:
    return r.score == (2, 2) and _both_led(r) and len(r.cards) >= 4 and not r.reds


def _press_collapse(r: MatchResult) -> bool:
    away_late = [g for g in r.goals if g.side == "away" and g.minute >= 60]
    return r.score == (1, 2) and r.score_at(58) == (1, 0) and len(away_late) == 2 and not r.reds


def _rout(r: MatchResult) -> bool:
    return r.score == (4, 0) and not r.reds


def _set_piece(r: MatchResult) -> bool:
    return r.score == (1, 0) and r.goals[0].set_piece and not r.reds


@dataclass(frozen=True)
class GoldenSpec:
    match_id: str
    title: str
    story: str
    home: str
    away: str
    beats: tuple[Beat, ...]
    criterion: Callable[[MatchResult], bool]
    seed: int
    search_from: int


GOLDEN: list[GoldenSpec] = [
    GoldenSpec("GM01", "Late comeback", "Northbridge trail at 70', a tactical sub and a higher press turn it to 3-2.",
               "NBU", "KES",
               (Beat(64, "home", "sub", off=8, on=17, style=(("tempo", 0.85),), note="Tactical sub: fresh legs in midfield"),
                Beat(72, "home", "style", style=(("press_intensity", 0.92), ("directness", 0.6)), note="All-out press")),
               _comeback, seed=10150, search_from=10_000),
    GoldenSpec("GM02", "Ten men", "Redmere lose a defender to a red card on 34'; Harbor break through 1-0.",
               "HAR", "RED", (Beat(34, "away", "red_card", note="Straight red for a last-man foul"),),
               _ten_men, seed=20054, search_from=20_000),
    GoldenSpec("GM03", "Derby draw", "A fierce, high-pressing derby: both sides lead, 2-2, plenty of bookings.",
               "GRY", "THV",
               (Beat(0, "home", "style", style=(("press_intensity", 0.9),), note="Derby intensity"),
                Beat(0, "away", "style", style=(("press_intensity", 0.85),), note="Derby intensity")),
               _derby, seed=30004, search_from=30_000),
    GoldenSpec("GM04", "Press collapse", "Kestrel press high and lead, then their press collapses after 58' and Harbor win 1-2.",
               "KES", "HAR",
               (Beat(0, "home", "style", style=(("press_intensity", 0.95),), note="Ultra-high press"),
                Beat(58, "home", "style", style=(("press_intensity", 0.15), ("tempo", 0.35)), note="Press collapses")),
               _press_collapse, seed=40482, search_from=40_000),
    GoldenSpec("GM05", "The rout", "Northbridge dominate a struggling Elmstead side 4-0.", "NBU", "ELM",
               (), _rout, seed=50001, search_from=50_000),
    GoldenSpec("GM06", "Set-piece special", "A tight game settled by a single set-piece goal, 1-0.", "RED", "THV",
               (), _set_piece, seed=60074, search_from=60_000),
]


def run_spec(spec: GoldenSpec, seed: int | None = None, fast: bool = False) -> MatchResult:
    return simulate(make_team(spec.home), make_team(spec.away), spec.seed if seed is None else seed,
                    spec.match_id, spec.beats, fast=fast)


def find_seed(spec: GoldenSpec, limit: int = 200_000) -> int:
    for seed in range(spec.search_from, spec.search_from + limit):
        if spec.criterion(run_spec(spec, seed, fast=True)):
            return seed
    raise RuntimeError(f"no seed found for {spec.match_id}")


def match_meta(spec: GoldenSpec, r: MatchResult) -> dict:
    return {
        "match_id": spec.match_id, "title": spec.title, "story": spec.story, "seed": r.seed,
        "home": r.home.to_dict(), "away": r.away.to_dict(),
        "beats": [b.to_dict() for b in spec.beats],
        "score": {"home": r.score[0], "away": r.score[1]},
        "goals": [{"t": g.t, "minute": g.minute, "team": (r.home if g.side == "home" else r.away).id,
                   "player_id": g.player_id, "set_piece": g.set_piece} for g in r.goals],
        "duration": r.duration, "n_events": len(r.events or []),
    }


def build_golden(out_dir: Path = GOLDEN_DIR) -> list[tuple[GoldenSpec, MatchResult]]:
    built = []
    for spec in GOLDEN:
        r = run_spec(spec)
        if not spec.criterion(r):
            raise AssertionError(f"{spec.match_id} seed {spec.seed} no longer fits its story")
        d = out_dir / spec.match_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "match.json").write_text(json.dumps(match_meta(spec, r), indent=1, ensure_ascii=False) + "\n",
                                      encoding="utf-8")
        body = ",\n".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) for e in r.events)
        (d / "events.json").write_text(f"[\n{body}\n]\n", encoding="utf-8")
        built.append((spec, r))
    index = [{"match_id": s.match_id, "title": s.title, "story": s.story, "home": s.home, "away": s.away,
              "score": f"{r.score[0]}-{r.score[1]}"} for s, r in built]
    (out_dir / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    return built
