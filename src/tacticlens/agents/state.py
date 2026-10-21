"""Messages passed between workflow executors, personas, and the evidence pack."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import cached_property

from ..contracts import Persona
from ..sim.teams import CLUBS, make_team

MAX_ATTEMPTS = 3  # first draft + 2 regenerations, then template fallback

PERSONAS: dict[str, Persona] = {
    "analyst": Persona(mode="analyst", lang="en", tone=0, stats_density=2),
    "casual": Persona(mode="casual", lang="en", tone=1, stats_density=1),
    "beginner": Persona(mode="beginner", lang="en", tone=2, stats_density=0),
    "audio": Persona(mode="audio", lang="en", tone=1, stats_density=1),
}


@dataclass(frozen=True)
class MatchInput:
    """Start message: one golden match and the moments to explain."""
    meta: dict
    moments: list[dict]
    personas: tuple[str, ...] = tuple(PERSONAS)
    top_n: int | None = None


@dataclass(frozen=True)
class EvidencePack:
    moment: dict
    meta: dict

    @cached_property
    def items(self) -> dict[str, dict]:
        return {e["id"]: e for e in self.moment["evidence"]}

    def by_label(self, label: str) -> dict | None:
        return next((e for e in self.moment["evidence"] if e["label"] == label), None)

    def by_prefix(self, prefix: str) -> list[dict]:
        return [e for e in self.moment["evidence"] if e["label"].startswith(prefix)]

    @cached_property
    def clubs(self) -> tuple[str, str]:
        return self.meta["home"]["name"], self.meta["away"]["name"]

    @cached_property
    def players(self) -> set[str]:
        return {p["name"] for side in ("home", "away") for p in self.meta[side]["players"]}

    @cached_property
    def foreign_clubs(self) -> set[str]:
        return {name for name, _ in CLUBS.values()} - set(self.clubs)

    @cached_property
    def foreign_players(self) -> set[str]:
        ids = {self.meta["home"]["id"], self.meta["away"]["id"]}
        return {p.name for cid in CLUBS if cid not in ids for p in make_team(cid).players} - self.players

    def prompt_view(self) -> dict:
        """Compact JSON the Explainer sees: only evidence, no raw events."""
        m = self.moment
        return {"moment_id": m["id"], "kind": m["kind"], "home": self.clubs[0], "away": self.clubs[1],
                "evidence": [{k: e[k] for k in ("id", "label", "value", "unit")} for e in m["evidence"]],
                "what_if": [c["description"] for c in m.get("counterfactuals", [])]}


@dataclass(frozen=True)
class Draft:
    """One persona's explanation as it moves through the workflow."""
    pack: EvidencePack
    persona_key: str
    status: str = "pending"  # pending | drafted | verified | rejected | fallback
    attempts: int = 0
    sentences: tuple[dict, ...] = ()
    notes: tuple[str, ...] = ()
    trace: tuple[dict, ...] = field(default=())

    def log(self, agent: str, action: str, **detail) -> Draft:
        entry = {"step": len(self.trace) + 1, "agent": agent, "action": action, **detail}
        return replace(self, trace=self.trace + (entry,))


@dataclass(frozen=True)
class Result:
    explanation: dict
    trace: tuple[dict, ...]
