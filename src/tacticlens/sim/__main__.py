"""CLI: python -m tacticlens.sim [golden|realism|all]"""
import sys
from pathlib import Path

from .golden import GOLDEN, GOLDEN_DIR, build_golden, run_spec
from .realism import write_report

DOCS = Path(__file__).resolve().parents[3] / "docs"


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "all"
    built = build_golden(GOLDEN_DIR) if cmd in ("golden", "all") else [(s, run_spec(s)) for s in GOLDEN]
    rows = []
    for spec, r in built:
        c = r.counters
        rows.append((spec.match_id, spec.title,
                     {"score": f"{r.home.name} {r.score[0]}-{r.score[1]} {r.away.name}",
                      "shots": f"{c['shots'][0]}-{c['shots'][1]}",
                      "passes": f"{c['passes'][0]}-{c['passes'][1]}", "cards": len(r.cards)}))
        print(spec.match_id, rows[-1][2]["score"], f"({spec.title})")
    if cmd in ("realism", "all"):
        summary = write_report(DOCS / "realism.md", golden=rows)
        print("realism:", "PASS" if all(v["ok"] for v in summary.values()) else "FAIL")


if __name__ == "__main__":
    main(sys.argv[1:])
