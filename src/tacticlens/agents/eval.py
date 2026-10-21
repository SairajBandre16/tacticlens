"""Eval harness: grounding, number accuracy, fallback rate, and verifier catch rate on injected faults."""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

from ..sim.golden import GOLDEN_DIR
from .explainer import FAULTS, KILL_ENV, OfflineExplainer, inject, offline_sentences
from .state import PERSONAS, EvidencePack
from .verifier import verify
from .workflow import run_match

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs"
START, END = "<!-- agents-eval:start -->", "<!-- agents-eval:end -->"
GOLDEN_FAULT_RATE = 0.2  # simulated LLM drift for the offline backend, so retries show up in the trace
GOLDEN_SEED = 4


def load(match_id: str, golden_dir: Path = GOLDEN_DIR) -> tuple[dict, list[dict]]:
    d = golden_dir / match_id
    return (json.loads((d / "match.json").read_text(encoding="utf-8")),
            json.loads((d / "moments.json").read_text(encoding="utf-8")))


def match_ids(golden_dir: Path = GOLDEN_DIR) -> list[str]:
    return [m["match_id"] for m in json.loads((golden_dir / "index.json").read_text(encoding="utf-8"))]


def _dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def build_golden(backend=None, golden_dir: Path = GOLDEN_DIR) -> dict[str, tuple[list[dict], dict]]:
    backend = backend or OfflineExplainer(fault_rate=GOLDEN_FAULT_RATE, seed=GOLDEN_SEED)
    out = {}
    for mid in match_ids(golden_dir):
        meta, moments = load(mid, golden_dir)
        explanations, trace = run_match(meta, moments, backend)
        _dump(golden_dir / mid / "explanations.json", explanations)
        _dump(golden_dir / mid / "trace.json", trace)
        out[mid] = (explanations, trace)
    return out


def score(runs: dict[str, tuple[list[dict], dict]], golden_dir: Path = GOLDEN_DIR) -> dict:
    """Draft-level stats come from verifier trace entries; shipped-level stats re-verify the final text."""
    c = Counter()
    for mid, (explanations, trace) in runs.items():
        meta, moments = load(mid, golden_dir)
        packs = {m["id"]: EvidencePack(m, meta) for m in moments}
        c["moments"] += len(moments)
        c["moments_covered"] += len({e["moment_id"] for e in explanations if e["verified"]})
        for e in explanations:
            c["explanations"] += 1
            c["degraded"] += e["degraded"]
            c["verified"] += e["verified"]
            rep = verify(e["sentences"], packs[e["moment_id"]])
            c["ship_sentences"] += rep.n_sentences
            c["ship_cited_ok"] += rep.n_cited_ok
            c["ship_numbers"] += rep.n_numbers
            c["ship_numbers_ok"] += rep.n_numbers_ok
        for personas in trace["moments"].values():
            for steps in personas.values():
                checks = [s for s in steps if s["agent"] == "verifier"]
                c["drafts"] += len(checks)
                c["first_pass"] += bool(checks) and checks[0]["action"] == "verified"
                for s in checks:
                    c["draft_sentences"] += s["stats"]["sentences"]
                    c["draft_cited_ok"] += s["stats"]["cited_ok"]
                    c["draft_numbers"] += s["stats"]["numbers"]
                    c["draft_numbers_ok"] += s["stats"]["numbers_ok"]
    return dict(c)


def fault_table(golden_dir: Path = GOLDEN_DIR) -> dict[str, tuple[int, int]]:
    applied, caught = Counter(), Counter()
    for mid in match_ids(golden_dir):
        meta, moments = load(mid, golden_dir)
        for m in moments:
            pack = EvidencePack(m, meta)
            for persona in PERSONAS:
                clean = offline_sentences(pack, persona)
                for fault in FAULTS:
                    if bad := inject(clean, fault, pack):
                        applied[fault] += 1
                        caught[fault] += not verify(bad, pack).ok
    return {f: (caught[f], applied[f]) for f in FAULTS}


def kill_switch_check(golden_dir: Path = GOLDEN_DIR) -> tuple[int, int]:
    mid = match_ids(golden_dir)[0]
    meta, moments = load(mid, golden_dir)
    os.environ[KILL_ENV] = "1"
    try:
        explanations, _ = run_match(meta, moments, OfflineExplainer())
    finally:
        os.environ.pop(KILL_ENV, None)
    return sum(e["degraded"] and e["verified"] for e in explanations), len(explanations)


def _pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}% ({a}/{b})" if b else "n/a"


def evaluation_section(backend_name: str, s: dict, faults: dict[str, tuple[int, int]], kill: tuple[int, int]) -> str:
    lines = [START, "## Agents workflow: grounding and verifier (M4)", "",
             f"Explainer backend: **{backend_name}**. The offline backend is a deterministic stand-in for the "
             f"Foundry agent, with {GOLDEN_FAULT_RATE:.0%} simulated drift on first drafts (halving per retry) so "
             "the retry and fallback paths run. Live Foundry numbers replace this table in M7.", "",
             "| Metric | Value |", "|---|---|",
             f"| Golden moments with a verified or template-fallback explanation | {_pct(s['moments_covered'], s['moments'])} |",
             f"| Explanations (moments x 4 personas, en) | {s['explanations']} |",
             f"| Shipped: sentences citing valid evidence (grounding rate) | {_pct(s['ship_cited_ok'], s['ship_sentences'])} |",
             f"| Shipped: numbers backed by cited evidence (number accuracy) | {_pct(s['ship_numbers_ok'], s['ship_numbers'])} |",
             f"| Drafts: grounding rate before verification | {_pct(s['draft_cited_ok'], s['draft_sentences'])} |",
             f"| Drafts: number accuracy before verification | {_pct(s['draft_numbers_ok'], s['draft_numbers'])} |",
             f"| First draft passed verifier | {_pct(s['first_pass'], s['explanations'])} |",
             f"| Mean Explainer attempts per explanation | {s['drafts'] / max(s['explanations'], 1):.2f} |",
             f"| Template fallback rate | {_pct(s['degraded'], s['explanations'])} |",
             f"| Kill switch (`{KILL_ENV}=1`): verified template fallbacks | {_pct(*kill)} |", "",
             "### Verifier catch rate on injected faults", "",
             "Each clean offline draft (every golden moment x persona) is corrupted with one known fault.", "",
             "| Fault | Caught |", "|---|---|"]
    lines += [f"| {f.replace('_', ' ')} | {_pct(*faults[f])} |" for f in FAULTS]
    return "\n".join(lines + ["", END]) + "\n"


def upsert(md: str, section: str) -> str:
    if START in md and END in md:
        return re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", lambda _: section, md, flags=re.S)
    return md.rstrip("\n") + "\n\n" + section


def keep_section(old_md: str, new_md: str) -> str:
    """Used by the metrics CLI so regenerating docs/evaluation.md keeps this section."""
    m = re.search(re.escape(START) + r".*?" + re.escape(END) + r"\n?", old_md, flags=re.S)
    return upsert(new_md, m.group(0)) if m else new_md


def write_report(backend_name: str, runs: dict, golden_dir: Path = GOLDEN_DIR) -> dict:
    s = score(runs, golden_dir)
    faults, kill = fault_table(golden_dir), kill_switch_check(golden_dir)
    path = DOCS / "evaluation.md"
    md = path.read_text(encoding="utf-8") if path.exists() else "# Evaluation\n"
    path.write_text(upsert(md, evaluation_section(backend_name, s, faults, kill)), encoding="utf-8")
    return {"score": s, "faults": faults, "kill": kill}
