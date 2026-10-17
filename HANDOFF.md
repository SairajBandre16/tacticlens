# HANDOFF
- Done: M0 scaffold; M1 simulator (`src/tacticlens/sim/`: teams, engine, golden, realism, CLI `python -m tacticlens.sim all`). Realism PASS on 300 matches (docs/realism.md). 6 golden matches in data/golden/GM01-06 (match.json + events.json + index.json). `pytest -q` = 41 passed.
- Next: M2 interpret (xG logistic, xT value iteration, WP gradient boosting on ~3,000 fast-sim matches, momentum, PPDA, moment detector) + docs/evaluation.md.
- For M2: `league_sample(n, fast=True)` gives MatchResult with goals/shots/cards/reds/subs/counters, no events (7.6 ms/match). `ShotRec.p_true` = hidden ground-truth scoring prob (compare xG calibration against it). Shots use main RNG for x,y so fast mode has shot coords.
- Gotcha: any engine change shifts RNG streams; re-run `find_seed` per spec, re-pin seeds in golden.py, then `python -m tacticlens.sim all`. Test fails if golden files are stale.
- Gotcha: home folder is also a git repo; TacticLens has its own (branch `main`, no remote). Use `.venv\Scripts\python` (3.11).
- Contract notes: added Event.related_player_id, Sentence.en_text, WinProb{home,draw,away}. Event coords are per acting team (attacks to x=100); defensive events mirrored. No penalties modelled.
- Open: GM04 press-collapse goals are both set pieces (fine, but M2 press_collapse detector should key on PPDA/pressures drop after 58').
- Usage: not measured (run `/usage`, record here).
