# HANDOFF
- Done: M0-M3. M3 = `counterfactual/rollouts.py` (replay golden match to a moment, 200 paired rollouts as played vs changed, bootstrap 80% interval) attached to top 5 moments/match (max 3 per kind). `MatchSim.advance(stop)` makes the sim resumable. `pytest -q` = 77 passed.
- Regenerate: `python -m tacticlens.metrics golden` (~1.5 min) writes moments.json with counterfactuals + docs/evaluation.md what-if tables.
- Evidence packs: ids `<moment>.eN`; evidence[0] names the subject (detector convention, rollouts rely on it); the 8 "What-if: ..." items are appended last. Win-chance items are per-club %, deltas in pp.
- Contract change: counterfactual `change` gains `convert_chance` (big chances). Moment→change map in `CHANGE_FOR`.
- Gotcha: wp_delta_* is HOME win chance only (schema); removing a late winner for the away side shows a small home delta because the result becomes a draw. Use the away/home win-chance evidence in explanations.
- Gotcha: undo_sub effects are ~0 (players have no individual quality; only scripted style beats matter). That is an honest answer, not a bug.
- Next: M4 agents workflow (start in plan mode per PLAN.md; check MS Agent Framework docs first).
- Usage: end of M3 session 5% (5h window) / 20% week (resets Oct 24 06:59 Dublin).
