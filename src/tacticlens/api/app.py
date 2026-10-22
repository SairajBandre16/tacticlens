"""FastAPI app: golden-mode match data, personalized cards, overlay cues, SSE replay, what-if and agent re-runs.

Golden mode reads only data/golden/ and never calls Azure. Personalization and overlays run per request
(deterministic and cheap). A what-if for a moment without a precomputed counterfactual is simulated on
demand (~5 s, N=200 rollouts) and cached to data/cache/whatif/.
"""
from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from ..agents.explainer import ExplainerKilled, OfflineExplainer
from ..agents.workflow import run_match_async
from ..contracts import Moment, Persona
from ..counterfactual.rollouts import _evidence, counterfactual, spec_for
from ..personalize.persona import index_explanations, personalize
from ..render.overlays import render
from ..sim.golden import GOLDEN_DIR

ROOT = Path(__file__).resolve().parents[3]
WEB_DIR = ROOT / "web"
WHATIF_CACHE = ROOT / "data" / "cache" / "whatif"
MAX_GAP_S = 1.5  # longest real-time pause between two replayed events

app = FastAPI(title="TacticLens", version="0.1.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)


def _read(mid: str, name: str, default=None):
    p = GOLDEN_DIR / mid / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


@lru_cache(maxsize=None)
def index() -> list[dict]:
    return json.loads((GOLDEN_DIR / "index.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=16)
def match(mid: str) -> dict:
    """Everything golden for one match, loaded once."""
    if mid not in {m["match_id"] for m in index()}:
        raise HTTPException(404, f"unknown match {mid}")
    loc = _read(mid, "localized.json", {})
    return {
        "meta": _read(mid, "match.json"), "moments": _read(mid, "moments.json"), "events": _read(mid, "events.json"),
        "metrics": _read(mid, "metrics.json"), "audio": _read(mid, "audio.json", {}),
        "explanations": index_explanations(_read(mid, "explanations.json"), loc.get("explanations", [])),
        "trace": _read(mid, "trace.json", {}), "loc_trace": loc.get("trace", {}), "loc_backend": loc.get("backend"),
    }


def moment(mid: str, moment_id: str) -> dict:
    m = next((x for x in match(mid)["moments"] if x["id"] == moment_id), None)
    if m is None:
        raise HTTPException(404, f"unknown moment {moment_id}")
    return m


def persona_q(mode: Literal["analyst", "casual", "beginner", "audio"] = "casual",
              lang: Literal["en", "hi", "es", "ar", "ja"] = "en", fav_club: str | None = None,
              fav_player: str | None = None, player_lock: bool = False,
              analogy: Literal["none", "cricket"] = "none", tone: int = Query(1, ge=0, le=2),
              stats_density: int = Query(1, ge=0, le=2)) -> Persona:
    try:
        return Persona(mode=mode, lang=lang, fav_club=fav_club or None, fav_player=fav_player or None,
                       player_lock=player_lock, analogy=analogy, tone=tone, stats_density=stats_density)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors()) from exc


def cards_for(mid: str, persona: Persona) -> list[dict]:
    d = match(mid)
    return personalize(d["moments"], d["meta"], persona, d["explanations"], d["audio"])


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "mode": "golden", "matches": len(index())}


@app.get("/api/matches")
def matches() -> list[dict]:
    return index()


@app.get("/api/matches/{mid}")
def match_detail(mid: str) -> dict:
    d = match(mid)
    mt = d["metrics"]
    periods = [{"period": e["period"], "t0": e["t"], "minute0": e["minute"]}
               for i, e in enumerate(d["events"]) if i == 0 or e["period"] != d["events"][i - 1]["period"]]
    return {"meta": d["meta"], "moments": d["moments"], "wp": mt["wp"], "momentum": mt["momentum"],
            "xg_total": mt["xg_total"], "teams": mt["teams"], "audio": d["audio"], "periods": periods}


@app.get("/api/matches/{mid}/events")
def events(mid: str) -> list[dict]:
    return match(mid)["events"]


@app.get("/api/matches/{mid}/replay")
async def replay(mid: str, from_t: float = Query(0.0, ge=0), speed: float = Query(8.0, gt=0, le=2000)):
    """Server-sent events: one `ev` message per match event, paced by match time / speed, then `end`."""
    evs = [e for e in match(mid)["events"] if e["t"] >= from_t]

    async def stream():
        prev = from_t
        for e in evs:
            await asyncio.sleep(min((e["t"] - prev) / speed, MAX_GAP_S))
            prev = e["t"]
            yield f"event: ev\nid: {e['id']}\ndata: {json.dumps(e)}\n\n"
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/matches/{mid}/cards")
def cards(mid: str, persona: Persona = Depends(persona_q)) -> dict:
    return {"persona": persona.key, "cards": cards_for(mid, persona)}


@app.get("/api/matches/{mid}/overlays")
def overlays(mid: str, persona: Persona = Depends(persona_q)) -> dict:
    cues = render(cards_for(mid, persona), match(mid)["moments"], mid)
    return {"persona": persona.key, "cues": cues}


@app.get("/api/matches/{mid}/trace/{moment_id}")
def trace(mid: str, moment_id: str, mode: str = "casual", lang: str = "en") -> dict:
    d, _ = match(mid), moment(mid, moment_id)
    return {"backend": d["trace"].get("backend"), "explain": d["trace"].get("moments", {}).get(moment_id, {}).get(mode, []),
            "localize_backend": d["loc_backend"], "localize": d["loc_trace"].get(moment_id, {}).get(lang, [])}


def _whatif_live(mid: str, moment_id: str) -> dict:
    path = WHATIF_CACHE / f"{moment_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    d = match(mid)
    m = Moment(**moment(mid, moment_id))
    c, chances = counterfactual(m, d["events"], spec_for(mid))
    clubs = {s: d["meta"][s]["name"] for s in ("home", "away")}
    out = {"counterfactual": c.model_dump(), "evidence": [e.model_dump() for e in _evidence(m, c, chances, clubs)]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out), encoding="utf-8")
    return out


@app.get("/api/matches/{mid}/whatif/{moment_id}")
async def whatif(mid: str, moment_id: str, live: bool = False) -> dict:
    """The precomputed counterfactual, or (live=true) one simulated now for any other moment."""
    m = moment(mid, moment_id)
    if m["counterfactuals"]:
        ev = [e for e in m["evidence"] if e["label"].startswith("What-if")]
        return {"source": "precomputed", "counterfactual": m["counterfactuals"][0], "evidence": ev}
    if not live:
        return {"source": "none", "counterfactual": None, "evidence": []}
    return {"source": "live", **await run_in_threadpool(_whatif_live, mid, moment_id)}


class KilledExplainer(OfflineExplainer):
    """UI kill switch: every Explainer call fails, so the Verifier retries and then hands off to the template."""
    name = "killed"

    async def explain(self, pack, persona, notes, attempt):
        raise ExplainerKilled("kill switch (UI)")


class ExplainRequest(BaseModel):
    moment_id: str
    mode: Literal["analyst", "casual", "beginner", "audio"] = "casual"
    kill: bool = False


@app.post("/api/matches/{mid}/explain")
async def explain(mid: str, req: ExplainRequest) -> dict:
    """Re-run the agent workflow for one moment and persona (offline backend) and return its trace."""
    d, m = match(mid), moment(mid, req.moment_id)
    backend = KilledExplainer() if req.kill else OfflineExplainer()
    exps, tr = await run_match_async(d["meta"], [m], backend, personas=(req.mode,))
    return {"backend": backend.name, "explanation": exps[0], "trace": tr["moments"][m["id"]][req.mode]}


app.mount("/golden", StaticFiles(directory=GOLDEN_DIR), name="golden")
app.mount("/", StaticFiles(directory=WEB_DIR, html=True, check_dir=False), name="web")
