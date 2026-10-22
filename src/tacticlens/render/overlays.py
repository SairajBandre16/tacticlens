"""Renderer: personalized cards -> broadcast overlay cues (OverlayCue contract).

Plain deterministic code. Every number on a cue is copied from the moment's evidence, never computed here,
so overlays stay as grounded as the explanations. Cue times are match seconds (same clock as events).
"""
from __future__ import annotations

from ..contracts import OverlayCue

LOWER_THIRD_S = 25.0
BUG_S = 15.0
KIND_LABEL = {"goal": "Goal", "big_chance": "Big chance", "red_card": "Red card", "momentum_shift": "Momentum shift",
              "press_collapse": "Press collapse", "sub_effect": "Substitution effect"}
PLAYER_LABELS = ("Shooter", "Player sent off")
STAT_LABELS = ("Shot xG", "Pressures per minute, 15 min after", "Threat per minute, 15 min after",
               "Players left on the pitch", "Momentum at peak")


def _ev(moment: dict, label: str) -> dict | None:
    return next((e for e in moment["evidence"] if e["label"] == label), None)


def _ev_prefix(moment: dict, prefix: str) -> dict | None:
    return next((e for e in moment["evidence"] if e["label"].startswith(prefix)), None)


def _minute(moment: dict) -> int:
    m = _ev(moment, "Minute")
    return int(m["value"]) if m else int(moment["t_start"] // 60)


def _fmt(e: dict) -> str:
    unit = e["unit"] or ""
    unit = "" if unit.startswith("index") else unit
    return f"{e['value']}{'' if unit in ('%', '') else ' '}{unit}".strip()


def cues_for_card(card: dict, moment: dict, match_id: str) -> list[dict]:
    """Up to five cues for one card: lower third always, then stat bug / win-prob swing / player tag / press map."""
    mid, t0 = moment["id"], float(moment["t_start"])
    persona, lang, minute = card["persona"], card["lang"], _minute(moment)
    kind = KIND_LABEL[moment["kind"]]
    sentences = card["sentences"]
    headline = sentences[0]["text"]
    speech = " ".join(s["text"] for s in sentences)
    base = {"match_id": match_id, "persona_key": persona, "lang": lang}
    cues = [{**base, "cue_id": f"{mid}.{persona}.lower_third", "in_t": t0, "out_t": t0 + LOWER_THIRD_S,
             "template": "lower_third",
             "payload": {"moment_id": mid, "kind": moment["kind"], "title": f"{minute}' {kind}", "text": headline,
                         "en_text": sentences[0].get("en_text") or headline,
                         "evidence_ids": sentences[0]["evidence_ids"]},
             "a11y": {"aria_label": f"Minute {minute}, {kind}: {headline}", "speech_text": speech}}]

    stat = next((e for lab in STAT_LABELS if (e := _ev(moment, lab))), None)
    if stat:
        cues.append({**base, "cue_id": f"{mid}.{persona}.stat_bug", "in_t": t0, "out_t": t0 + BUG_S,
                     "template": "stat_bug",
                     "payload": {"moment_id": mid, "label": stat["label"], "value": stat["value"],
                                 "unit": stat["unit"], "evidence_ids": [stat["id"]]},
                     "a11y": {"aria_label": f"{stat['label']}: {_fmt(stat)}",
                              "speech_text": f"{stat['label']}: {_fmt(stat)}"}})

    before, after = _ev_prefix(moment, "Win probability for "), _ev_prefix(moment, "Win probability change for ")
    later = [e for e in moment["evidence"] if e["label"].startswith("Win probability for ") and e is not before]
    if before and later:
        club = before["label"].removeprefix("Win probability for ").removesuffix(" before")
        aft = later[0]
        text = f"{club} win probability {before['value']}% to {aft['value']}%"
        cues.append({**base, "cue_id": f"{mid}.{persona}.wp_swing", "in_t": t0 + 5, "out_t": t0 + 5 + BUG_S,
                     "template": "wp_swing",
                     "payload": {"moment_id": mid, "club": club, "before": before["value"], "after": aft["value"],
                                 "delta_pp": after["value"] if after else None,
                                 "evidence_ids": [e["id"] for e in (before, aft, after) if e]},
                     "a11y": {"aria_label": text, "speech_text": text}})

    player = next((e for lab in PLAYER_LABELS if (e := _ev(moment, lab))), None)
    team = _ev(moment, "Team")
    if player:
        text = f"{player['value']}, {team['value']}" if team else str(player["value"])
        cues.append({**base, "cue_id": f"{mid}.{persona}.player_tag", "in_t": t0, "out_t": t0 + BUG_S,
                     "template": "player_tag",
                     "payload": {"moment_id": mid, "player": player["value"], "club": team["value"] if team else None,
                                 "event_ids": player["event_ids"],
                                 "evidence_ids": [e["id"] for e in (player, team) if e]},
                     "a11y": {"aria_label": text, "speech_text": text}})

    if moment["kind"] == "press_collapse":
        pre, post = _ev(moment, "PPDA, 15 min before"), _ev(moment, "PPDA, 15 min after")
        club = _ev(moment, "Pressing team")
        if pre and post and club:
            text = f"{club['value']} pressing: PPDA {pre['value']} before, {post['value']} after"
            cues.append({**base, "cue_id": f"{mid}.{persona}.pressing_map", "in_t": t0, "out_t": t0 + LOWER_THIRD_S,
                         "template": "pressing_map",
                         "payload": {"moment_id": mid, "club": club["value"], "ppda_before": pre["value"],
                                     "ppda_after": post["value"],
                                     "evidence_ids": [club["id"], pre["id"], post["id"]]},
                         "a11y": {"aria_label": text, "speech_text": text}})
    return [OverlayCue(**c).model_dump() for c in cues]


def render(cards: list[dict], moments: list[dict], match_id: str) -> list[dict]:
    """All cues for a persona's cards, sorted by in_t (validated against the OverlayCue contract)."""
    by_id = {m["id"]: m for m in moments}
    cues = [c for card in cards for c in cues_for_card(card, by_id[card["moment_id"]], match_id)]
    return sorted(cues, key=lambda c: (c["in_t"], c["cue_id"]))
