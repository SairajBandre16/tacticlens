# HANDOFF
- Done: M0 scaffold. Layout, pyproject (py3.11, `.venv`), 5 contracts + pydantic models (`src/tacticlens/contracts.py`), fixtures, CI stub. `pytest -q` = 27 passed.
- Next: M1 simulator + realism report (docs/realism.md), 6 golden matches.
- Gotcha: home folder `C:/Users/91810` is also a git repo; TacticLens now has its own nested repo (branch `main`). No remote yet.
- Gotcha: system Python is 3.10; use `.venv\Scripts\python` (3.11). Install: `pip install -e .[dev]`.
- Contract additions beyond spec: Event.related_player_id (receiver / sub-on / fouled), Sentence.en_text, WinProb {home,draw,away}, Persona.key format `mode.lang.analogy.tN.dN.club.player`.
- Open decision: Event.outcome enum may need extending in M1 (contract change = schema + model + fixtures + tests together).
- Usage: not measured this session (run `/usage`, record here).
