"""CLI: python -m tacticlens.metrics [train|golden|all]

train  - train xG / xT / WP models into data/models/ (about a minute)
golden - golden-match metrics.json + moments.json (with counterfactuals, ~1.5 min), docs/evaluation.md
all    - both
"""
import json
import sys

from ..agents.eval import keep_section
from ..counterfactual.rollouts import attach
from ..moments.detector import detect
from .pipeline import MODELS_DIR, ROOT, build_golden_metrics, load_golden, load_models, train_all
from .report import evaluation_md, figure_svg

DOCS = ROOT / "docs"


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "all"
    if cmd in ("train", "all"):
        ev = train_all()
        print("xG log loss", ev["xg"]["log_loss"], "| WP log loss", ev["wp"]["log_loss"])
    if cmd in ("golden", "all"):
        ev = json.loads((MODELS_DIR / "eval.json").read_text(encoding="utf-8"))
        models = load_models()
        golden = []
        for match_id, mm in build_golden_metrics(models).items():
            meta, events = load_golden(match_id)
            moments = attach(meta, events, detect(meta, events, mm))
            body = ",\n".join(m.model_dump_json() for m in moments)
            (ROOT / "data" / "golden" / match_id / "moments.json").write_text(f"[\n{body}\n]\n", encoding="utf-8")
            golden.append((meta, mm, moments))
            print(match_id, len(moments), "moments")
        (DOCS / "img").mkdir(parents=True, exist_ok=True)
        (DOCS / "img" / "calibration.svg").write_text(figure_svg(ev, models[1].grid.tolist()), encoding="utf-8")
        path = DOCS / "evaluation.md"
        old = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(keep_section(old, evaluation_md(ev, golden)), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
