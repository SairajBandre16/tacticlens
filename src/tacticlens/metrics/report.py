"""docs/evaluation.md and its inline-SVG figure (no plotting library)."""
from __future__ import annotations

from ..contracts import Moment
from ..moments.detector import top

COLORS = {"model": "#2563eb", "true": "#d97706", "draw": "#059669"}


def _panel(x0: float, y0: float, size: float, title: str, series: list[tuple[str, str, list[tuple[float, float]]]],
           vmax: float = 1.0) -> list[str]:
    def px(v: float) -> float:
        return x0 + size * v / vmax

    def py(v: float) -> float:
        return y0 + size - size * v / vmax

    out = [f'<rect x="{x0}" y="{y0}" width="{size}" height="{size}" fill="none" stroke="#9ca3af"/>',
           f'<line x1="{px(0)}" y1="{py(0)}" x2="{px(vmax)}" y2="{py(vmax)}" stroke="#9ca3af" stroke-dasharray="4 4"/>',
           f'<text x="{x0 + size / 2}" y="{y0 - 10}" text-anchor="middle" font-size="14" font-weight="600">{title}</text>',
           f'<text x="{x0 + size / 2}" y="{y0 + size + 32}" text-anchor="middle" font-size="12">predicted</text>',
           f'<text x="{x0 - 34}" y="{y0 + size / 2}" text-anchor="middle" font-size="12" '
           f'transform="rotate(-90 {x0 - 34} {y0 + size / 2})">observed</text>']
    for i in range(5):
        v = vmax * i / 4
        out.append(f'<text x="{px(v)}" y="{y0 + size + 15}" text-anchor="middle" font-size="10">{v:.2g}</text>')
        out.append(f'<text x="{x0 - 6}" y="{py(v) + 3}" text-anchor="end" font-size="10">{v:.2g}</text>')
    for k, (name, color, pts) in enumerate(series):
        pts = [(min(a, vmax), min(b, vmax)) for a, b in pts]
        out.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="'
                   + " ".join(f"{px(a):.1f},{py(b):.1f}" for a, b in pts) + '"/>')
        out += [f'<circle cx="{px(a):.1f}" cy="{py(b):.1f}" r="3.5" fill="{color}"/>' for a, b in pts]
        out.append(f'<text x="{x0 + 8}" y="{y0 + 18 + 16 * k}" font-size="12" fill="{color}">{name}</text>')
    return out


def _heatmap(x0: float, y0: float, w: float, h: float, grid: list[list[float]]) -> list[str]:
    cols, rows = len(grid), len(grid[0])
    vmax = max(max(c) for c in grid)
    cw, ch = w / cols, h / rows
    out = [f'<text x="{x0 + w / 2}" y="{y0 - 10}" text-anchor="middle" font-size="14" font-weight="600">'
           f'xT by zone (attacking left to right)</text>']
    for c, col in enumerate(grid):
        for r, v in enumerate(col):
            a = (v / vmax) ** 0.5
            out.append(f'<rect x="{x0 + c * cw:.1f}" y="{y0 + r * ch:.1f}" width="{cw:.1f}" height="{ch:.1f}" '
                       f'fill="#2563eb" fill-opacity="{a:.3f}" stroke="#e5e7eb"/>')
    out.append(f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="none" stroke="#6b7280"/>')
    out.append(f'<text x="{x0 + w / 2}" y="{y0 + h + 18}" text-anchor="middle" font-size="11">'
               f'max {vmax:.3f} in front of goal; own third ~0.01</text>')
    return out


def figure_svg(ev: dict, xt_grid: list[list[float]]) -> str:
    xg = ev["xg"]["calibration"]
    wp = ev["wp"]
    body = _panel(60, 40, 240, "xG calibration (held-out shots)",
                  [("xG model", COLORS["model"], [(b["pred"], b["obs"]) for b in xg]),
                   ("simulator truth", COLORS["true"], [(b["pred"], b["true"]) for b in xg])], vmax=0.7)
    body += _panel(400, 40, 240, "Win-probability calibration",
                   [("P(home win)", COLORS["model"], [(b["pred"], b["obs"]) for b in wp["calibration_home"]]),
                    ("P(draw)", COLORS["draw"], [(b["pred"], b["obs"]) for b in wp["calibration_draw"]])])
    body += _heatmap(720, 40, 288, 192, xt_grid)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1040 330" font-family="system-ui, sans-serif" '
            'role="img" aria-label="Calibration of the xG and win-probability models, and the xT grid">\n'
            '<rect width="1040" height="330" fill="#ffffff"/>\n' + "\n".join(body) + "\n</svg>\n")


def _table(header: list[str], rows: list[list]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + \
           ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


def evaluation_md(ev: dict, golden: list[tuple[dict, dict, list[Moment]]]) -> str:
    xg, wp = ev["xg"], ev["wp"]
    true_coef = {"distance_m": -0.16, "angle_rad": 0.6, "header": -0.9, "under_pressure": -0.4,
                 "set_piece": "0 (direct free kicks x0.7)"}
    L = ["# Model evaluation", "",
         f"Trained on {ev['n_matches']:,} fast-mode simulated league matches (seeded); every 5th match is held out.",
         "Regenerate with `python -m tacticlens.metrics all` (models in `data/models/`, numbers in `data/models/eval.json`).",
         "", "![Calibration plots and xT grid](img/calibration.svg)", "",
         "## Expected goals (logistic regression)", "",
         "Features: shot distance, goal-mouth angle, header, under pressure, set piece. "
         "Because the data is synthetic, the simulator's hidden per-shot scoring probability is an oracle we can "
         "compare against.", ""]
    L += _table(["metric", "value"], [
        ["held-out shots", f"{xg['n_test']:,}"], ["goal rate", xg["goal_rate"]],
        ["log loss (model)", xg["log_loss"]], ["log loss (oracle: simulator truth)", xg["log_loss_true"]],
        ["Brier score", xg["brier"]], ["ROC AUC", xg["auc"]],
        ["mean abs. error vs truth", xg["mae_vs_true"]]])
    L += ["", "Learned coefficients next to the simulator's (team-quality terms are hidden from the model):", ""]
    L += _table(["feature", "learned", "simulator"], [[k, v, true_coef[k]] for k, v in xg["coef"].items()])
    L += ["", "Calibration (held-out):", ""]
    L += _table(["xG bin", "shots", "mean xG", "goal rate", "true prob."],
                [[f"{b['lo']}-{b['hi']}", b["n"], b["pred"], b["obs"], b["true"]] for b in xg["calibration"]])
    x = ev["xt"]
    L += ["", "## Expected threat (value iteration)", "",
          f"12x8 zone grid fitted on {x['n_matches']} full-mode matches: move/shot probabilities and a "
          f"successful-move transition matrix, iterated to convergence. Max zone value {x['max']}, "
          f"own penalty area {x['own_box']}, opponent's central box zones {x['opp_box']}.", "",
          "## Win probability (gradient boosting)", "",
          "Features at each minute: minute, goal difference, total goals, man advantage, xG difference so far, "
          "pre-match team-quality difference. One snapshot every 3 minutes per match.", ""]
    L += _table(["metric", "gradient boosting", "multinomial logreg", "base rates"], [
        ["log loss", wp["log_loss"], wp["log_loss_logreg"], wp["log_loss_prior"]],
        ["Brier (3-class)", wp["brier"], wp["brier_logreg"], "-"]])
    L += ["", "Log loss by match phase (it should fall as the match resolves):", ""]
    L += _table(["minutes", "log loss"], [[k, v] for k, v in wp["by_phase"].items()])
    L += ["", "Calibration of P(home win), held-out snapshots:", ""]
    L += _table(["bin", "n", "predicted", "observed"],
                [[f"{b['lo']:.1f}-{b['hi']:.1f}", b["n"], b["pred"], b["obs"]] for b in wp["calibration_home"]])
    L += ["", "## Golden matches: final win probability and top-8 moments", "",
          "Importance = kind base + effect size + win-probability swing (window moments get a small WP weight so "
          "goals inside their window do not dominate).", "",
          "Counterfactuals (top 5 moments per match, at most 3 of one kind): the match is replayed to the moment, "
          "then 200 rest-of-match rollouts run as played and 200 with one change, paired by seed. The interval is a "
          "bootstrap 80% interval of the mean paired difference. A near-zero effect is a real answer: in the "
          "simulator a substitution only matters when it changes team style.", ""]
    for meta, mm, moments in golden:
        last = mm["wp"][-1]
        L += [f"### {meta['match_id']} {meta['title']}: {meta['home']['name']} {meta['score']['home']}-"
              f"{meta['score']['away']} {meta['away']['name']}", "",
              f"xG {mm['xg_total'][0]}-{mm['xg_total'][1]}; final WP home/draw/away "
              f"{last['home']:.2f}/{last['draw']:.2f}/{last['away']:.2f}.", ""]
        rows = []
        for m in sorted(top(moments), key=lambda m: m.t_start):
            e = {x.label: x.value for x in m.evidence}
            who = next((v for k, v in e.items() if k in ("Team", "Pressing team", "Team taking control")), "")
            rows.append([f"{int(e['Minute'])}'", m.kind, who, f"{m.importance:.2f}",
                         f"{m.wp_before.home:.2f}/{m.wp_before.draw:.2f}/{m.wp_before.away:.2f}",
                         f"{m.wp_after.home:.2f}/{m.wp_after.draw:.2f}/{m.wp_after.away:.2f}"])
        L += _table(["min", "kind", "team", "importance", "WP before (H/D/A)", "WP after"], rows) + [""]
        cfs = [(m, c) for m in moments for c in m.counterfactuals]
        if cfs:
            L += ["What-if rollouts (change in home win probability, mean and 80% interval):", ""]
            L += _table(["min", "kind", "what if", "rollouts", "mean", "80% interval"], [
                [f"{int(next(e.value for e in m.evidence if e.label == 'Minute'))}'", m.kind, c.description,
                 c.n_rollouts, f"{c.wp_delta_mean:+.3f}", f"{c.wp_delta_p10:+.3f} to {c.wp_delta_p90:+.3f}"]
                for m, c in cfs]) + [""]
    return "\n".join(L).rstrip() + "\n"
