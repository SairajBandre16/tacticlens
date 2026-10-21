"""CLI: python -m tacticlens.agents [golden|eval] [--live]

golden - run the explanation workflow on every golden match: explanations.json + trace.json, then eval
eval   - re-score the committed golden explanations into docs/evaluation.md
--live - use the Foundry Explainer (needs AZURE_AI_PROJECT_ENDPOINT, AZURE_AI_MODEL_DEPLOYMENT, az login, pip install .[azure])
"""
import json
import sys

from .eval import GOLDEN_DIR, build_golden, match_ids, write_report
from .explainer import FoundryExplainer, OfflineExplainer


def main(argv: list[str]) -> None:
    cmd = next((a for a in argv if not a.startswith("--")), "golden")
    live = "--live" in argv
    if cmd == "golden":
        backend = FoundryExplainer() if live else None
        runs = build_golden(backend)
        name = backend.name if backend else OfflineExplainer.name
    else:
        runs, name = {}, OfflineExplainer.name
        for mid in match_ids():
            d = GOLDEN_DIR / mid
            trace = json.loads((d / "trace.json").read_text(encoding="utf-8"))
            runs[mid] = (json.loads((d / "explanations.json").read_text(encoding="utf-8")), trace)
            name = trace["backend"]
    report = write_report(name, runs)
    s = report["score"]
    print(f"{s['explanations']} explanations | covered {s['moments_covered']}/{s['moments']} moments | "
          f"fallback {s['degraded']} | first-pass {s['first_pass']} | faults caught "
          f"{sum(c for c, _ in report['faults'].values())}/{sum(n for _, n in report['faults'].values())}")


if __name__ == "__main__":
    main(sys.argv[1:])
