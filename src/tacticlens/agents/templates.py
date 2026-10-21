"""Evidence lookup shared by the offline Explainer, plus the deterministic template fallback."""
from __future__ import annotations

from .state import EvidencePack

SUBJECT_LABELS = ("Team", "Team taking control", "Pressing team")


class Facts:
    """Named views over one moment's evidence pack. Every accessor returns an evidence item (or None)."""

    def __init__(self, pack: EvidencePack):
        self.pack = pack
        self.kind = pack.moment["kind"]
        g = pack.by_label
        self.minute = g("Minute")
        self.team = next((g(lab) for lab in SUBJECT_LABELS if g(lab)), None)
        self.shooter, self.xg, self.dist = g("Shooter"), g("Shot xG"), g("Distance to goal")
        self.outcome, self.pressure, self.actions = g("Shot outcome"), g("Under pressure"), g("Actions in the move")
        self.score_after, self.score_before = g("Score after goal"), g("Score at the start of the moment")
        self.sent_off, self.players_left, self.minutes_left = (
            g("Player sent off"), g("Players left on the pitch"), g("Minutes left to play"))
        self.mom_start, self.mom_peak, self.duration = g("Momentum at start"), g("Momentum at peak"), g("Swing duration")
        self.press_before = g("Pressures per minute, 15 min before")
        self.press_after = g("Pressures per minute, 15 min after")
        self.ppda_before, self.ppda_after = g("PPDA, 15 min before"), g("PPDA, 15 min after")
        self.threat_before = g("Threat per minute, 15 min before")
        self.threat_after = g("Threat per minute, 15 min after")
        self.on, self.off = g("Players on"), g("Players off")
        wp = pack.by_prefix("Win probability for ")
        self.wp_club = wp[0]["label"][len("Win probability for "):].rsplit(" ", 1)[0] if wp else None
        self.wp_before = g(f"Win probability for {self.wp_club} before") if wp else None
        self.wp_after = g(f"Win probability for {self.wp_club} after") if wp else None
        self.wp_change = g(f"Win probability change for {self.wp_club}") if wp else None
        change = [e for e in pack.by_prefix("What-if: change in ") if "interval" not in e["label"]]
        self.wi_change = change[0] if change else None
        self.wi_club = change[0]["label"][len("What-if: change in "):-len(" win chance")] if change else None
        self.wi_played = g(f"What-if: {self.wi_club} win chance as played") if change else None
        self.wi_with = g(f"What-if: {self.wi_club} win chance with the change") if change else None
        self.wi_low = g(f"What-if: change in {self.wi_club} win chance, 80% interval low") if change else None
        self.wi_high = g(f"What-if: change in {self.wi_club} win chance, 80% interval high") if change else None
        n = pack.by_prefix("What-if: simulated")
        self.wi_n = n[0] if n else None
        cfs = pack.moment.get("counterfactuals") or []
        self.wi_desc = cfs[0]["description"] if cfs else None

    @staticmethod
    def v(item: dict):
        value = item["value"]
        return value.replace("_", " ") if isinstance(value, str) else value


def S(text: str, *items: dict | None) -> dict:
    return {"text": text, "evidence_ids": [e["id"] for e in items if e]}


def headline(f: Facts) -> dict | None:
    v, m = f.v, f.minute
    if f.kind == "goal" and f.shooter and f.score_after:
        return S(f"{v(f.shooter)} scored for {v(f.team)} in minute {v(m):.0f}, making it {v(f.score_after)}.",
                 f.shooter, f.team, m, f.score_after)
    if f.kind == "big_chance" and f.shooter:
        return S(f"{v(f.shooter)} had a big chance for {v(f.team)} in minute {v(m):.0f}.", f.shooter, f.team, m)
    if f.kind == "red_card" and f.sent_off:
        return S(f"{v(f.sent_off)} of {v(f.team)} was sent off in minute {v(m):.0f}.", f.sent_off, f.team, m)
    if f.kind == "momentum_shift" and f.team:
        return S(f"{v(f.team)} took control of the game from minute {v(m):.0f}.", f.team, m)
    if f.kind == "press_collapse" and f.team:
        return S(f"The {v(f.team)} press faded from minute {v(m):.0f}.", f.team, m)
    if f.kind == "sub_effect" and f.on:
        return S(f"{v(f.team)} made a change in minute {v(m):.0f}: {v(f.on)} on for {v(f.off)}.",
                 f.team, m, f.on, f.off)
    if m:
        return S(f"A key moment came in minute {v(m):.0f}.", m)
    return None


def detail(f: Facts) -> dict | None:
    v = f.v
    if f.kind in ("goal", "big_chance") and f.xg and f.dist:
        return S(f"The shot was worth {v(f.xg):.2f} xG from {v(f.dist):.1f} metres.", f.xg, f.dist)
    if f.kind == "red_card" and f.players_left and f.minutes_left:
        return S(f"{v(f.team)} played the last {v(f.minutes_left):.0f} minutes with {v(f.players_left):.0f} players.",
                 f.team, f.minutes_left, f.players_left)
    if f.kind == "momentum_shift" and f.mom_start and f.mom_peak:
        return S(f"The momentum index went from {v(f.mom_start):.2f} to {v(f.mom_peak):.2f}.", f.mom_start, f.mom_peak)
    if f.kind == "press_collapse" and f.press_before and f.press_after:
        return S(f"Pressures per minute went from {v(f.press_before):.1f} to {v(f.press_after):.1f}.",
                 f.press_before, f.press_after)
    if f.kind == "sub_effect" and f.threat_before and f.threat_after:
        return S(f"Threat per minute went from {v(f.threat_before):.3f} to {v(f.threat_after):.3f}.",
                 f.threat_before, f.threat_after)
    return None


def win_chance(f: Facts) -> dict | None:
    if not (f.wp_before and f.wp_after):
        return None
    return S(f"{f.wp_club} win chance went from {f.v(f.wp_before):.0f}% to {f.v(f.wp_after):.0f}%.",
             f.wp_before, f.wp_after)


def what_if(f: Facts) -> dict | None:
    if not (f.wi_with and f.wi_played and f.wi_n):
        return None
    lead = f"{f.wi_desc}? " if f.wi_desc else ""
    return S(f"{lead}Across {f.v(f.wi_n):.0f} simulated rollouts, {f.wi_club} win chance would be about "
             f"{f.v(f.wi_with):.0f}% instead of {f.v(f.wi_played):.0f}%.", f.wi_with, f.wi_played, f.wi_n)


def template_sentences(pack: EvidencePack) -> list[dict]:
    """Plain, persona-neutral fallback built only from evidence. Must always pass the verifier."""
    f = Facts(pack)
    out = [s for s in (headline(f), detail(f), win_chance(f), what_if(f)) if s and s["evidence_ids"]]
    if not out:  # last resort: restate the first evidence item verbatim
        e = pack.moment["evidence"][0]
        out = [S(f"{e['label']}: {e['value']}{' ' + e['unit'] if e['unit'] else ''}.", e)]
    return out
