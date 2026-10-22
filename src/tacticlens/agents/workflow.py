"""Explanation workflow on Microsoft Agent Framework (graph API).

Spotter -> EvidenceBuilder -> (per persona) Explainer <-> Verifier -> [TemplateFallback] -> Localizer
-> AccessibilityDescriber -> SafetyGate -> output. Every handoff is logged on the Draft's trace.
"""
import asyncio
import re
from dataclasses import dataclass, replace
from typing_extensions import Never

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

from ..contracts import Explanation
from .explainer import OfflineExplainer
from .state import MAX_ATTEMPTS, PERSONAS, Draft, EvidencePack, MatchInput, Result
from .templates import template_sentences
from .verifier import FORBIDDEN_RE, REAL_RE, verify

# Offline stand-in for Azure AI Content Safety (wired in M7).
UNSAFE_RE = re.compile(r"\b(kill|hate|idiot|stupid|disgrace|damn|hell)\b", re.I)


@dataclass(frozen=True)
class MomentJob:
    pack: EvidencePack
    personas: tuple[str, ...]
    trace: tuple[dict, ...]


class Spotter(Executor):
    def __init__(self):
        super().__init__(id="spotter")

    @handler
    async def spot(self, match: MatchInput, ctx: WorkflowContext[MomentJob]) -> None:
        ranked = sorted(match.moments, key=lambda m: -m["importance"])[:match.top_n]
        for m in sorted(ranked, key=lambda m: m["t_start"]):
            entry = {"step": 1, "agent": "spotter", "action": "selected",
                     "detail": f"{m['kind']} importance {m['importance']:.2f}"}
            await ctx.send_message(MomentJob(EvidencePack(m, match.meta), match.personas, (entry,)))


class EvidenceBuilder(Executor):
    def __init__(self):
        super().__init__(id="evidence_builder")

    @handler
    async def build(self, job: MomentJob, ctx: WorkflowContext[Draft]) -> None:
        n_whatif = len(job.pack.by_prefix("What-if"))
        for persona in job.personas:
            draft = Draft(job.pack, persona, trace=job.trace)
            await ctx.send_message(draft.log("evidence_builder", "packed",
                                             detail=f"{len(job.pack.items)} evidence items ({n_whatif} what-if)"))


class Explainer(Executor):
    def __init__(self, backend):
        super().__init__(id="explainer")
        self.backend = backend

    @handler
    async def explain(self, draft: Draft, ctx: WorkflowContext[Draft]) -> None:
        attempt = draft.attempts + 1
        try:
            sentences = await self.backend.explain(draft.pack, draft.persona_key, draft.notes, attempt)
            out = replace(draft, attempts=attempt, status="drafted", sentences=tuple(sentences))
            out = out.log("explainer", "drafted", attempt=attempt, backend=self.backend.name,
                          detail=f"{len(sentences)} sentences")
        except Exception as exc:  # any backend failure is a rejected draft, never a crash
            out = replace(draft, attempts=attempt, status="drafted", sentences=(),
                          notes=draft.notes + (f"attempt {attempt}: explainer error ({type(exc).__name__})",))
            out = out.log("explainer", "error", attempt=attempt, backend=self.backend.name,
                          detail=f"{type(exc).__name__}: {exc}")
        await ctx.send_message(out)


class Verifier(Executor):
    def __init__(self, backend):
        super().__init__(id="verifier")
        self.backend = backend

    @handler
    async def check(self, draft: Draft, ctx: WorkflowContext[Draft]) -> None:
        rep = verify(draft.sentences, draft.pack)
        judge_notes = None
        if rep.ok:
            try:
                judge_notes = await self.backend.judge(list(draft.sentences), draft.pack)
            except Exception as exc:
                judge_notes = None
                rep.notes.append(f"llm judge unavailable ({type(exc).__name__})")
            if judge_notes:
                for note in judge_notes:
                    rep.fail(note)
        status = "verified" if rep.ok else "rejected"
        notes = draft.notes + tuple(f"attempt {draft.attempts}: {n}" for n in rep.notes)
        if rep.ok and judge_notes is None:
            notes += ("llm judge skipped (offline backend); deterministic checks passed",)
        out = replace(draft, status=status, notes=notes)
        nxt = ("localizer" if rep.ok else "explainer (regenerate)" if draft.attempts < MAX_ATTEMPTS
               else "template_fallback")
        await ctx.send_message(out.log("verifier", status, attempt=draft.attempts, next=nxt,
                                       notes=rep.notes[:4], stats=rep.stats()))


class TemplateFallback(Executor):
    def __init__(self):
        super().__init__(id="template_fallback")

    @handler
    async def fallback(self, draft: Draft, ctx: WorkflowContext[Draft]) -> None:
        sentences = template_sentences(draft.pack)
        rep = verify(sentences, draft.pack)
        out = replace(draft, status="fallback" if rep.ok else "rejected", sentences=tuple(sentences),
                      notes=draft.notes + (f"template fallback after {draft.attempts} attempts",))
        await ctx.send_message(out.log("template_fallback", "used", verified=rep.ok, stats=rep.stats()))


class Localizer(Executor):
    def __init__(self):
        super().__init__(id="localizer")

    @handler
    async def localize(self, draft: Draft, ctx: WorkflowContext[Draft]) -> None:
        lang = PERSONAS[draft.persona_key].lang
        await ctx.send_message(draft.log("localizer", "passthrough", lang=lang,
                                         detail="verified English source; hi/es by the Localizer agent (personalize.localize)"))


class AccessibilityDescriber(Executor):
    def __init__(self):
        super().__init__(id="accessibility_describer")

    @handler
    async def describe(self, draft: Draft, ctx: WorkflowContext[Draft]) -> None:
        detail = ("audio persona: sentences read as speech text" if draft.persona_key == "audio"
                  else "aria text = sentence text")
        await ctx.send_message(draft.log("accessibility_describer", "passthrough", detail=detail))


class SafetyGate(Executor):
    def __init__(self):
        super().__init__(id="safety_gate")

    @handler
    async def gate(self, draft: Draft, ctx: WorkflowContext[Never, Result]) -> None:
        text = " ".join(s["text"] for s in draft.sentences)
        hit = UNSAFE_RE.search(text) or FORBIDDEN_RE.search(text) or REAL_RE.search(text)
        if hit:
            draft = replace(draft, status="fallback", sentences=tuple(template_sentences(draft.pack)),
                            notes=draft.notes + (f"safety gate blocked '{hit.group(0)}'",))
        draft = draft.log("safety_gate", "blocked" if hit else "passed", engine="offline blocklist")
        exp = Explanation(moment_id=draft.pack.moment["id"], persona_key=draft.persona_key,
                          lang=PERSONAS[draft.persona_key].lang, sentences=list(draft.sentences),
                          verified=draft.status in ("verified", "fallback"), verifier_notes=list(draft.notes),
                          degraded=draft.status != "verified")
        await ctx.yield_output(Result(exp.model_dump(exclude_none=True), draft.trace))


def build_workflow(backend):
    spotter, builder = Spotter(), EvidenceBuilder()
    explainer, verifier, fallback = Explainer(backend), Verifier(backend), TemplateFallback()
    localizer, a11y, safety = Localizer(), AccessibilityDescriber(), SafetyGate()
    return (WorkflowBuilder(name="tacticlens-explain", start_executor=spotter, output_from=[safety])
            .add_edge(spotter, builder)
            .add_edge(builder, explainer)
            .add_edge(explainer, verifier)
            .add_edge(verifier, explainer, condition=lambda d: d.status == "rejected" and d.attempts < MAX_ATTEMPTS)
            .add_edge(verifier, fallback, condition=lambda d: d.status == "rejected" and d.attempts >= MAX_ATTEMPTS)
            .add_edge(verifier, localizer, condition=lambda d: d.status == "verified")
            .add_edge(fallback, localizer)
            .add_edge(localizer, a11y)
            .add_edge(a11y, safety)
            .build())


async def run_match_async(meta: dict, moments: list[dict], backend=None, personas: tuple[str, ...] = tuple(PERSONAS),
                          top_n: int | None = None) -> tuple[list[dict], dict]:
    backend = backend or OfflineExplainer()
    result = await build_workflow(backend).run(MatchInput(meta, moments, personas, top_n))
    order = {p: i for i, p in enumerate(personas)}
    t_start = {m["id"]: m["t_start"] for m in moments}
    results: list[Result] = sorted(result.get_outputs(), key=lambda r: (
        t_start[r.explanation["moment_id"]], r.explanation["moment_id"], order[r.explanation["persona_key"]]))
    trace: dict[str, dict] = {}
    for r in results:
        trace.setdefault(r.explanation["moment_id"], {})[r.explanation["persona_key"]] = list(r.trace)
    return [r.explanation for r in results], {"backend": backend.name, "moments": trace}


def run_match(meta: dict, moments: list[dict], backend=None, **kw) -> tuple[list[dict], dict]:
    return asyncio.run(run_match_async(meta, moments, backend, **kw))
