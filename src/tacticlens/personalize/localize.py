"""Localizer: verified English explanations -> hi / es, with numeral + entity checks and English back-translation.

Per (moment, language) every persona's sentences go to the Localizer agent in one call. Each sentence must keep
the same numbers and the glossary form of every name. Failures get one regeneration with the checker's notes,
then Azure Translator with dictionary markup, then the English sentence (marked degraded). Translator also
back-translates every accepted sentence so the UI can show it beside the original.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from ..contracts import Explanation
from .checks import check_back_translation, check_sentence
from .glossary import LANG_NAMES, TERMS, name_table, names_in

ROOT = Path(__file__).resolve().parents[3]
LLM_CACHE = ROOT / "data" / "cache" / "llm"

INSTRUCTIONS = """You are the Localizer for a football match-intelligence app about synthetic matches.
Translate each item's English text into the target language. Reply with JSON only:
{"items": [{"key": "<same key>", "text": "<translation>"}]}
Rules:
- One output item per input item, same keys, one sentence each.
- Keep every number exactly: Western digits 0-9, same decimals, same scorelines. Never add or drop a number.
- Write club and player names exactly as given in "names". Use the "glossary" terms for football vocabulary.
- Keep the register of each item's persona: analyst = precise; casual = lively; beginner = plain and friendly;
  audio = spoken, present tense, no symbols.
- Do not add facts, opinions, betting language or certainty words."""


class FoundryLocalizer:
    """Localizer agent on Microsoft Foundry (Agent Framework). Calls are cached on disk by input hash."""
    name = "foundry"

    def __init__(self, endpoint: str | None = None, model: str | None = None, cache_dir: Path = LLM_CACHE):
        from agent_framework.foundry import FoundryChatClient  # optional extra: pip install .[azure]
        from azure.identity import DefaultAzureCredential

        self.model = model or os.environ["AZURE_AI_MODEL_DEPLOYMENT"]
        client = FoundryChatClient(project_endpoint=endpoint or os.environ["AZURE_AI_PROJECT_ENDPOINT"],
                                   model=self.model, credential=DefaultAzureCredential())
        self.agent = client.as_agent(name="Localizer", instructions=INSTRUCTIONS)
        self.cache_dir = cache_dir

    async def translate(self, items: list[dict], lang: str, names: dict[str, str]) -> dict[str, str]:
        from ..agents.explainer import _parse_json
        from .azure_rest import digest

        prompt = json.dumps({"target_language": LANG_NAMES[lang], "names": names, "glossary": TERMS[lang],
                             "items": items}, ensure_ascii=False, sort_keys=True)
        path = self.cache_dir / f"{digest(self.model, INSTRUCTIONS, prompt)}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = _parse_json((await self.agent.run(prompt)).text)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return {str(i.get("key")): str(i.get("text", "")) for i in data.get("items", [])}


def _markup(text: str, names: dict[str, str]) -> str:
    """Translator input with names pinned by <mstrans:dictionary> (so 'Harbor Athletic' is never translated)."""
    out = escape(text)
    for name in sorted(names, key=len, reverse=True):
        if name in text:
            out = out.replace(escape(name), f"<mstrans:dictionary translation={quoteattr(names[name])}>"
                                            f"{escape(name)}</mstrans:dictionary>")
    return out


def _entry(trace: list[dict], agent: str, action: str, **detail) -> None:
    trace.append({"step": len(trace) + 1, "agent": agent, "action": action, **detail})


async def localize_moment(explanations: list[dict], meta: dict, lang: str, localizer=None, rest=None
                          ) -> tuple[list[dict], list[dict]]:
    """Localize every persona explanation of one moment into `lang`. Returns (explanations, trace)."""
    names = name_table(meta, lang)
    src = {f"{e['persona_key']}.{i}": s["text"] for e in explanations for i, s in enumerate(e["sentences"])}
    persona_of = {k: k.rsplit(".", 1)[0] for k in src}
    accepted: dict[str, tuple[str, str]] = {}  # key -> (text, engine)
    notes: dict[str, list[str]] = {}
    trace: list[dict] = []

    def take(cands: dict[str, str], engine: str) -> None:
        for k, text in cands.items():
            if k in src and k not in accepted:
                problems = check_sentence(src[k], text, lang, meta)
                if problems:
                    notes[k] = problems
                else:
                    accepted[k] = (text, engine)
                    notes.pop(k, None)

    if localizer:
        for attempt in (1, 2):
            todo = [k for k in src if k not in accepted]
            if not todo:
                break
            items = [{"key": k, "persona": persona_of[k], "text": src[k],
                      **({"fix": notes[k]} if k in notes else {})} for k in todo]
            used = {n: names[n] for k in todo for n in names_in(src[k], meta)}
            try:
                take(await localizer.translate(items, lang, used), "agent")
                _entry(trace, "localizer", "drafted", attempt=attempt, backend=localizer.name, lang=lang,
                       detail=f"{sum(k in accepted for k in todo)}/{len(todo)} sentences passed checks")
            except Exception as exc:  # agent failure falls through to Translator, never a crash
                _entry(trace, "localizer", "error", attempt=attempt, backend=localizer.name, lang=lang,
                       detail=f"{type(exc).__name__}: {exc}")
        if failed := [k for k in src if k not in accepted]:
            _entry(trace, "numeral_entity_check", "rejected", lang=lang, notes=[f"{k}: {notes.get(k, ['no output'])[0]}"
                                                                                  for k in failed][:4])
    if rest and (todo := [k for k in src if k not in accepted]):
        try:
            out = await rest.translate([_markup(src[k], names) for k in todo], to=lang)
            take(dict(zip(todo, out)), "translator")
            _entry(trace, "translator_fallback", "used", lang=lang,
                   detail=f"{sum(k in accepted for k in todo)}/{len(todo)} sentences passed checks")
        except Exception as exc:
            _entry(trace, "translator_fallback", "error", lang=lang, detail=f"{type(exc).__name__}: {exc}")

    back: dict[str, str] = {}
    if rest and accepted:
        keys = list(accepted)
        try:
            back = dict(zip(keys, await rest.translate([accepted[k][0] for k in keys], to="en", frm=lang)))
            drift = [f"{k}: {n}" for k in keys for n in check_back_translation(src[k], back[k])]
            _entry(trace, "back_translator", "checked", lang=lang, drift=drift[:4],
                   detail=f"{len(keys)} sentences back-translated, {len(drift)} drift notes")
        except Exception as exc:
            _entry(trace, "back_translator", "error", lang=lang, detail=f"{type(exc).__name__}: {exc}")

    english = [k for k in src if k not in accepted]
    _entry(trace, "localizer", "done", lang=lang, agent_ok=sum(e == "agent" for _, e in accepted.values()),
           translator_ok=sum(e == "translator" for _, e in accepted.values()), english_fallback=len(english))

    out = []
    for e in explanations:
        sentences, fell_back = [], []
        for i, s in enumerate(e["sentences"]):
            k = f"{e['persona_key']}.{i}"
            text = accepted[k][0] if k in accepted else s["text"]
            if k not in accepted:
                fell_back.append(f"s{i + 1}: {(notes.get(k) or ['no translation'])[0]}")
            sentences.append({"text": text, "evidence_ids": s["evidence_ids"], "en_text": s["text"],
                              **({"back_translation": back[k]} if k in back else {})})
        loc_notes = [f"{lang}: English shown for {n}" for n in fell_back]
        out.append(Explanation(moment_id=e["moment_id"], persona_key=e["persona_key"], lang=lang,
                               sentences=sentences, verified=e["verified"],
                               verifier_notes=list(e.get("verifier_notes", [])) + loc_notes,
                               degraded=e["degraded"] or bool(fell_back)).model_dump(exclude_none=True))
    return out, trace


async def localize_match(meta: dict, explanations: list[dict], langs=("hi", "es"), localizer=None, rest=None,
                         concurrency: int = 6) -> tuple[list[dict], dict]:
    by_moment: dict[str, list[dict]] = {}
    for e in explanations:
        by_moment.setdefault(e["moment_id"], []).append(e)
    gate = asyncio.Semaphore(concurrency)

    async def one(mid: str, lang: str):
        async with gate:
            return mid, lang, await localize_moment(by_moment[mid], meta, lang, localizer, rest)

    results = await asyncio.gather(*(one(mid, lang) for mid in by_moment for lang in langs))
    out, trace = [], {}
    for mid, lang, (exps, tr) in results:
        out += exps
        trace.setdefault(mid, {})[lang] = tr
    return out, trace
