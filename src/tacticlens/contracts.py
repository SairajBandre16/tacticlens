"""Pydantic v2 models mirroring contracts/*.schema.json (the schemas are the source of truth)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"

Lang = Literal["en", "hi", "es", "ar", "ja"]
EventType = Literal[
    "pass", "shot", "tackle", "interception", "dribble", "foul", "card", "sub",
    "clearance", "corner", "free_kick", "goal", "pressure",
]
Outcome = Literal[
    "success", "fail", "goal", "saved", "off_target", "blocked", "post",
    "yellow", "second_yellow", "red",
]
MomentKind = Literal["goal", "big_chance", "red_card", "momentum_shift", "press_collapse", "sub_effect"]
CounterfactualChange = Literal["remove_event", "press_intensity", "undo_sub"]
OverlayTemplate = Literal["lower_third", "stat_bug", "wp_swing", "pressing_map", "player_tag"]
PersonaMode = Literal["analyst", "casual", "beginner", "audio"]
Analogy = Literal["none", "cricket"]


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Event(_Contract):
    id: str = Field(min_length=1)
    match_id: str = Field(min_length=1)
    t: float = Field(ge=0)
    period: int = Field(ge=1, le=4)
    minute: int = Field(ge=0, le=130)
    team: str = Field(min_length=1)
    player_id: str | None = None
    related_player_id: str | None = None
    type: EventType
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    end_x: float | None = Field(default=None, ge=0, le=100)
    end_y: float | None = Field(default=None, ge=0, le=100)
    outcome: Outcome | None = None
    under_pressure: bool
    body_part: Literal["foot", "head", "other"] | None = None
    xg: float | None = Field(default=None, ge=0, le=1)


class WinProb(_Contract):
    home: float = Field(ge=0, le=1)
    draw: float = Field(ge=0, le=1)
    away: float = Field(ge=0, le=1)


class Evidence(_Contract):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    value: float | str
    unit: str | None = None
    event_ids: list[str] = Field(default_factory=list)


class Counterfactual(_Contract):
    id: str = Field(min_length=1)
    change: CounterfactualChange
    description: str
    n_rollouts: int = Field(ge=1)
    seed: int
    wp_delta_mean: float = Field(ge=-1, le=1)
    wp_delta_p10: float = Field(ge=-1, le=1)
    wp_delta_p90: float = Field(ge=-1, le=1)


class Moment(_Contract):
    id: str = Field(min_length=1)
    match_id: str = Field(min_length=1)
    t_start: float = Field(ge=0)
    t_end: float = Field(ge=0)
    kind: MomentKind
    importance: float = Field(ge=0, le=1)
    wp_before: WinProb
    wp_after: WinProb
    evidence: list[Evidence]
    counterfactuals: list[Counterfactual] = Field(default_factory=list)


class Sentence(_Contract):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    en_text: str | None = None


class Explanation(_Contract):
    moment_id: str = Field(min_length=1)
    persona_key: str = Field(min_length=1)
    lang: Lang
    sentences: list[Sentence] = Field(min_length=1)
    verified: bool
    verifier_notes: list[str] = Field(default_factory=list)
    degraded: bool


class A11y(_Contract):
    aria_label: str = Field(min_length=1)
    speech_text: str = Field(min_length=1)


class OverlayCue(_Contract):
    cue_id: str = Field(min_length=1)
    match_id: str = Field(min_length=1)
    in_t: float = Field(ge=0)
    out_t: float = Field(ge=0)
    template: OverlayTemplate
    persona_key: str = Field(min_length=1)
    lang: Lang
    payload: dict[str, Any]
    a11y: A11y


class Persona(_Contract):
    mode: PersonaMode
    lang: Lang
    fav_club: str | None = None
    fav_player: str | None = None
    analogy: Analogy = "none"
    tone: int = Field(default=1, ge=0, le=2)
    stats_density: int = Field(default=1, ge=0, le=2)

    @property
    def key(self) -> str:
        """Stable cache/persona key, e.g. 'analyst.en.none.t1.d2.NBU.-'."""
        return ".".join([
            self.mode, self.lang, self.analogy, f"t{self.tone}", f"d{self.stats_density}",
            self.fav_club or "-", self.fav_player or "-",
        ])


# schema file stem -> top-level model
MODELS: dict[str, type[_Contract]] = {
    "event": Event,
    "moment": Moment,
    "explanation": Explanation,
    "overlay_cue": OverlayCue,
    "persona": Persona,
}


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    return json.loads((CONTRACTS_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
