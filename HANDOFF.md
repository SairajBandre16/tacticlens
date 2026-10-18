# HANDOFF
- Done: M0, M1, M2. M2 = `src/tacticlens/metrics/` (xg, xt, winprob, flow, clock, pipeline, report) + `moments/detector.py`. CLI `python -m tacticlens.metrics [train|golden|all]` (~1 min). Models in data/models/ (xg.json, xt.json, wp.pkl, eval.json). Golden outputs: data/golden/GMxx/{metrics.json, moments.json}. docs/evaluation.md + docs/img/calibration.svg. `pytest -q` = 67 passed.
- Results: xG AUC 0.84, log loss 0.244 vs oracle 0.243 (coefficients match simulator). WP log loss 0.650 vs logreg 0.662 vs base rates 1.062. All 6 golden final WPs match the result; story moments detected (GM02 red 34', GM04 press collapse 60', GM01 sub effect 62').
- Next: M3 counterfactual rollouts (N=200, remove_event / press_intensity / undo_sub) from a moment's state + full evidence packs (extend detector evidence; ids `<moment>.eN`).
- Gotcha: sim `minute` overlaps in first-half stoppage (46'-47' then 2nd half restarts at 45'). Always use `metrics.clock.ev_clock(e)` / `rec_clock` for ordering and windows; metrics arrays are indexed by clock minute.
- Gotcha: MatchResult now has `half_time` and `reds` = (minute, side, t). No RNG change, golden events unchanged.
- Gotcha: wp.pkl is a pickled sklearn 1.9.1 model; if sklearn version changes, rerun `python -m tacticlens.metrics all`. Tests fail if metrics/moments files are stale.
- For M3: rollouts need to restart MatchSim from a mid-match state (score, minute, players on, style); engine has no snapshot/restore yet, so add one (keep RNG streams untouched for normal runs).
- Open: window moments (press_collapse, sub_effect, momentum_shift) are generic too; tune thresholds in detector.py constants if the demo shows noise.
- Usage: start of M2 session 0% (5h window) / 16% week. End: fill in from `/usage`.
