"""Fictional clubs, deterministic rosters and team style parameters."""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field, replace

STYLE_KEYS = ("press_intensity", "tempo", "directness", "width", "quality")


@dataclass(frozen=True)
class TeamStyle:
    """All values in 0..1. quality is overall technical level (passing, finishing, keeping)."""
    press_intensity: float = 0.5
    tempo: float = 0.5
    directness: float = 0.5
    width: float = 0.5
    quality: float = 0.5

    def with_(self, **changes: float) -> "TeamStyle":
        return replace(self, **changes)


@dataclass(frozen=True)
class Player:
    id: str
    name: str
    number: int
    pos: str  # GK | DF | MF | FW


@dataclass(frozen=True)
class Team:
    id: str
    name: str
    style: TeamStyle
    players: tuple[Player, ...] = field(repr=False)

    @property
    def starters(self) -> tuple[Player, ...]:
        return self.players[:11]

    @property
    def bench(self) -> tuple[Player, ...]:
        return self.players[11:]

    def player(self, number: int) -> Player:
        return next(p for p in self.players if p.number == number)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "style": asdict(self.style),
                "players": [asdict(p) for p in self.players]}


# 4-3-3 starting XI then a 7-player bench.
SHIRTS = [(1, "GK"), (2, "DF"), (3, "DF"), (4, "DF"), (5, "DF"), (6, "MF"), (8, "MF"), (10, "MF"),
          (7, "FW"), (9, "FW"), (11, "FW"),
          (13, "GK"), (14, "DF"), (15, "DF"), (16, "MF"), (17, "MF"), (18, "FW"), (19, "FW")]

_FIRST = ["Arin", "Bastian", "Caio", "Dario", "Elio", "Femi", "Gael", "Hugo", "Ilan", "Jari", "Kofi",
          "Luca", "Mateo", "Niko", "Omar", "Pavel", "Rafa", "Soren", "Tomas", "Umar", "Viktor", "Wen",
          "Yusuf", "Zane", "Aleks", "Bruno", "Cyril", "Dev", "Emre", "Felix", "Idris", "Joon", "Kenji",
          "Leon", "Milan", "Nils", "Otto", "Remi", "Sami", "Teo", "Arjun", "Rohan", "Iker", "Diego"]
_SUR_A = ["Hal", "Mor", "Bren", "Cal", "Dun", "Fal", "Gar", "Hol", "Kel", "Lin", "Nor", "Os", "Pen",
          "Quil", "Rav", "Sel", "Tor", "Wyn", "Ald", "Brom", "Cor", "Dray", "Ev", "Ferr", "Gul", "Im"]
_SUR_B = ["wick", "more", "vane", "ley", "ton", "by", "ridge", "stone", "vale", "holt", "croft",
          "mere", "worth", "brook", "den", "hame", "iva", "aro", "enko", "ssen", "ier", "ando"]

# id -> (name, style)
CLUBS: dict[str, tuple[str, TeamStyle]] = {
    "NBU": ("Northbridge United", TeamStyle(0.70, 0.65, 0.40, 0.60, 0.72)),
    "KES": ("Kestrel Town", TeamStyle(0.80, 0.70, 0.55, 0.50, 0.58)),
    "HAR": ("Harbor Athletic", TeamStyle(0.45, 0.50, 0.60, 0.70, 0.55)),
    "RED": ("Redmere FC", TeamStyle(0.40, 0.40, 0.70, 0.45, 0.52)),
    "GRY": ("Greyhaven Rovers", TeamStyle(0.75, 0.60, 0.50, 0.55, 0.56)),
    "THV": ("Thornvale City", TeamStyle(0.55, 0.55, 0.45, 0.50, 0.57)),
    "ELM": ("Elmstead Wanderers", TeamStyle(0.30, 0.35, 0.65, 0.40, 0.32)),
    "CPB": ("Copperbay FC", TeamStyle(0.50, 0.45, 0.35, 0.65, 0.50)),
}


def _roster(club_id: str) -> tuple[Player, ...]:
    rng = random.Random(f"roster:{club_id}")
    players = []
    for number, pos in SHIRTS:
        name = f"{rng.choice(_FIRST)} {rng.choice(_SUR_A)}{rng.choice(_SUR_B)}"
        players.append(Player(f"{club_id}-{number:02d}", name, number, pos))
    return tuple(players)


def make_team(club_id: str, style: TeamStyle | None = None) -> Team:
    name, default_style = CLUBS[club_id]
    return Team(club_id, name, style or default_style, _roster(club_id))
