"""Explainer backends. Offline = deterministic stand-in (golden mode). Foundry = Agent Framework agent (live mode)."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from .state import EvidencePack
from .templates import Facts, S, detail, headline, what_if
from .verifier import DOWN_RE, HEDGE_RE, NUM_RE, SCORE_RE, UP_RE

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = ROOT / "data" / "cache" / "llm"
KILL_ENV = "TACTICLENS_KILL_EXPLAINER"

FAULTS = ("fabricated_number", "bad_evidence_id", "missing_citation", "wrong_direction",
          "foreign_club", "real_name", "unhedged_what_if", "certainty_claim")


class ExplainerKilled(RuntimeError):
    pass


def _h(*parts) -> float:
    """Stable value in [0, 1) from any parts (no Python hash randomisation)."""
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16) / 2**32


def _pick(options: list[str], *key) -> str:
    return options[int(_h(*key) * len(options))]


# --- fault injection (simulated LLM drift; used by the offline backend and the eval harness) ---------------

def inject(sentences: list[dict], fault: str, pack: EvidencePack) -> list[dict] | None:
    """Corrupt one sentence with a known failure. None when the fault does not apply to this draft."""
    out = [dict(s, evidence_ids=list(s["evidence_ids"])) for s in sentences]
    first = out[0]
    if fault == "fabricated_number":
        for s in out:
            text = SCORE_RE.sub(lambda m: m.group(0).replace("-", "\x00"), s["text"])
            if m := NUM_RE.search(text):
                fake = f"{float(m.group(0)) + 7.3:.1f}"
                s["text"] = (text[:m.start()] + fake + text[m.end():]).replace("\x00", "-")
                return out
        return None
    if fault == "bad_evidence_id":
        first["evidence_ids"].append(f"{pack.moment['id']}.e99")
    elif fault == "missing_citation":
        first["evidence_ids"] = []
    elif fault == "wrong_direction":
        swap = {"rose": "fell", "fell": "rose", "jumped": "dropped", "dropped": "jumped", "lifted": "cut"}
        for s in out:
            m = UP_RE.search(s["text"]) or DOWN_RE.search(s["text"])
            if m and m.group(0).lower() in swap:
                s["text"] = s["text"][:m.start()] + swap[m.group(0).lower()] + s["text"][m.end():]
                return out
        return None
    elif fault in ("foreign_club", "real_name"):
        new = sorted(pack.foreign_clubs)[0] if fault == "foreign_club" else "Arsenal"
        for s in out:
            for club in pack.clubs:
                if club in s["text"]:
                    s["text"] = s["text"].replace(club, new, 1)
                    return out
        return None
    elif fault == "unhedged_what_if":
        for s in out:
            if any(pack.items.get(e, {}).get("label", "").startswith("What-if") for e in s["evidence_ids"]):
                s["text"] = re.sub(r"\s+", " ", HEDGE_RE.sub("", s["text"])).replace(" ,", ",")
                return out
        return None
    elif fault == "certainty_claim":
        first["text"] = first["text"].rstrip(".") + ", and the result was guaranteed from there."
    else:
        raise ValueError(fault)
    return out


# --- offline backend -------------------------------------------------------------------------------------

def _win_line(f: Facts, persona: str, key: tuple) -> dict | None:
    if not (f.wp_before and f.wp_after and f.wp_change):
        return None
    club, b, a, c = f.wp_club, f.v(f.wp_before), f.v(f.wp_after), f.v(f.wp_change)
    if persona == "analyst":
        if abs(c) < 0.05:
            return S(f"{club} win probability held at {a:.1f}%.", f.wp_change, f.wp_after)
        verb = "rose" if c > 0 else "fell"
        return S(f"{club} win probability {verb} by {abs(c):.1f} pp, from {b:.1f}% to {a:.1f}%.",
                 f.wp_change, f.wp_before, f.wp_after)
    if persona == "beginner":
        return S(f"Our model now gives {club} a {a:.0f}% chance of winning, compared with {b:.0f}% before.",
                 f.wp_before, f.wp_after)
    if persona == "audio":
        if round(a) == round(b):
            return S(f"{club} still has a {a:.0f} per cent chance of winning.", f.wp_after)
        return S(f"{club} now has a {a:.0f} per cent chance of winning, {'up' if c > 0 else 'down'} from "
                 f"{b:.0f} per cent.", f.wp_before, f.wp_after)
    if abs(c) < 1:
        return S(f"{club} win chance barely moved, staying near {a:.0f}%.", f.wp_after, f.wp_change)
    up = ["{club} win chance jumped to {a:.0f}%, up {d:.0f} points.", "{club} hopes rose by {d:.0f} points to {a:.0f}%."]
    down = ["{club} win chance dropped to {a:.0f}%, down {d:.0f} points.",
            "{club} hopes fell by {d:.0f} points to {a:.0f}%."]
    return S(_pick(up if c > 0 else down, *key).format(club=club, a=a, d=abs(c)), f.wp_after, f.wp_change)


def _extra(f: Facts, persona: str) -> dict | None:
    v = f.v
    if persona == "beginner" and f.xg:
        return S(f"xG measures chance quality; this one was {v(f.xg):.2f}, and higher means a better chance.", f.xg)
    if persona == "analyst" and f.actions and f.pressure:
        return S(f"The move had {v(f.actions):.0f} actions, and the shooter was under pressure: {v(f.pressure)}.",
                 f.actions, f.pressure)
    if persona == "analyst" and f.ppda_before and f.ppda_after:
        return S(f"PPDA went from {v(f.ppda_before):.1f} to {v(f.ppda_after):.1f}.", f.ppda_before, f.ppda_after)
    return None


def _what_if_lines(f: Facts, persona: str) -> list[dict]:
    if not (f.wi_with and f.wi_played and f.wi_n):
        return []
    if persona == "analyst":
        out = [what_if(f)]
        if f.wi_change and f.wi_low and f.wi_high:
            out.append(S(f"The simulated change is {f.v(f.wi_change):+.1f} pp, with an 80% interval from "
                         f"{f.v(f.wi_low):.1f} to {f.v(f.wi_high):.1f} pp.", f.wi_change, f.wi_low, f.wi_high))
        return out
    if persona == "beginner":
        return [S(f"If that had not happened, our simulations suggest {f.wi_club} would have about a "
                  f"{f.v(f.wi_with):.0f}% chance instead of {f.v(f.wi_played):.0f}%.", f.wi_with, f.wi_played)]
    if persona == "audio":
        return []  # audio stays short; the what-if panel is visual
    lead = f"{f.wi_desc}? " if f.wi_desc else ""
    return [S(f"{lead}{f.wi_club} would be about {f.v(f.wi_with):.0f}% to win, not {f.v(f.wi_played):.0f}%.",
              f.wi_with, f.wi_played)]


def _audio_headline(f: Facts) -> dict | None:
    v, m = f.v, f.minute
    if f.kind == "goal" and f.shooter and f.score_after:
        return S(f"Minute {v(m):.0f}. {v(f.shooter)} scores for {v(f.team)}, and the score is now {v(f.score_after)}.",
                 m, f.shooter, f.team, f.score_after)
    return headline(f)


def offline_sentences(pack: EvidencePack, persona: str, attempt: int = 1) -> list[dict]:
    f = Facts(pack)
    key = (pack.moment["id"], persona, attempt)
    head = _audio_headline(f) if persona == "audio" else headline(f)
    parts = [head]
    if persona in ("analyst", "casual", "audio"):
        parts.append(detail(f))
    parts += [_extra(f, persona), _win_line(f, persona, key)]
    parts += _what_if_lines(f, persona)
    return [s for s in parts if s and s["evidence_ids"]][:6]


class OfflineExplainer:
    """Deterministic stand-in for the LLM. fault_rate simulates drift so the retry path is exercised."""
    name = "offline"

    def __init__(self, fault_rate: float = 0.0, seed: int = 0):
        self.fault_rate, self.seed = fault_rate, seed

    async def explain(self, pack: EvidencePack, persona: str, notes: tuple[str, ...], attempt: int) -> list[dict]:
        if os.environ.get(KILL_ENV) == "1":
            raise ExplainerKilled(f"{KILL_ENV}=1")
        sentences = offline_sentences(pack, persona, attempt)
        key = (self.seed, pack.moment["id"], persona, attempt)
        if _h(*key) < self.fault_rate * 0.5 ** (attempt - 1):
            for k in range(len(FAULTS)):
                fault = FAULTS[(int(_h("fault", *key) * len(FAULTS)) + k) % len(FAULTS)]
                if bad := inject(sentences, fault, pack):
                    return bad
        return sentences

    async def judge(self, sentences: list[dict], pack: EvidencePack) -> list[str] | None:
        return None  # no LLM offline; the deterministic checks are the whole verifier


# --- live backend: Microsoft Agent Framework on Foundry --------------------------------------------------

INSTRUCTIONS = """You explain one football moment from a synthetic match. Reply with JSON only:
{"sentences": [{"text": "...", "evidence_ids": ["<id>", ...]}]}
Rules: 2-5 sentences, each at most 35 words. Every sentence cites the evidence ids it relies on.
Use only numbers, names and scores that appear in the cited evidence (you may round). Never invent facts.
What-if sentences must cite What-if evidence and be hedged ("would", "about", "simulations suggest").
No betting language, no certainty words, no real clubs or players."""

PERSONA_STYLE = {
    "analyst": "Audience: analysts. Dense, precise, include xG, win-probability deltas in pp and the what-if interval.",
    "casual": "Audience: casual fans. Lively, 2-3 sentences, at most two numbers.",
    "beginner": "Audience: newcomers. Plain words, explain any stat you use, at most two numbers.",
    "audio": "Audience: blind and low-vision fans (audio description). Present tense, say 'per cent', no symbols.",
}

JUDGE_INSTRUCTIONS = """You check grounded explanations. Given evidence and sentences, reply JSON only:
{"unsupported": [{"index": <1-based sentence>, "reason": "..."}]} listing sentences whose claim does not
follow from their cited evidence. Empty list if all are supported."""


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


class FoundryExplainer:
    """Explainer + judge agents on Microsoft Foundry. Every call is cached on disk by input hash."""
    name = "foundry"

    def __init__(self, endpoint: str | None = None, model: str | None = None, cache_dir: Path = CACHE_DIR):
        from agent_framework.foundry import FoundryChatClient  # optional extra: pip install .[azure]
        from azure.identity import DefaultAzureCredential

        self.model = model or os.environ["FOUNDRY_MODEL"]
        client = FoundryChatClient(project_endpoint=endpoint or os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                                   model=self.model, credential=DefaultAzureCredential())
        self.explainer = client.as_agent(name="Explainer", instructions=INSTRUCTIONS)
        self.judge_agent = client.as_agent(name="VerifierJudge", instructions=JUDGE_INSTRUCTIONS)
        self.cache_dir = cache_dir

    async def _run(self, agent, instructions: str, prompt: str) -> dict:
        key = hashlib.sha256(f"{self.model}\n{instructions}\n{prompt}".encode()).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        data = _parse_json((await agent.run(prompt)).text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return data

    async def explain(self, pack: EvidencePack, persona: str, notes: tuple[str, ...], attempt: int) -> list[dict]:
        if os.environ.get(KILL_ENV) == "1":
            raise ExplainerKilled(f"{KILL_ENV}=1")
        prompt = json.dumps({"persona": PERSONA_STYLE[persona], "moment": pack.prompt_view(),
                             "fix_these_verifier_notes": list(notes)}, ensure_ascii=False, sort_keys=True)
        data = await self._run(self.explainer, INSTRUCTIONS, prompt)
        return [{"text": str(s.get("text", "")), "evidence_ids": list(s.get("evidence_ids", []))}
                for s in data.get("sentences", [])]

    async def judge(self, sentences: list[dict], pack: EvidencePack) -> list[str] | None:
        prompt = json.dumps({"evidence": pack.prompt_view()["evidence"], "sentences": sentences},
                            ensure_ascii=False, sort_keys=True)
        data = await self._run(self.judge_agent, JUDGE_INSTRUCTIONS, prompt)
        return [f"s{u.get('index')}: judge says unsupported ({u.get('reason', '')})" for u in data.get("unsupported", [])]
