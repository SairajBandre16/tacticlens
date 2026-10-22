# HANDOFF
- Done: M0-M6. M6 = `src/tacticlens/api/app.py` (FastAPI, golden mode: cards via `personalize()`, overlays, SSE `/replay`, trace, what-if precomputed or `?live=true` (~6 s, cached in data/cache/whatif/), `POST /explain` with kill switch) + `render/overlays.py` (OverlayCue from evidence only) + `web/` (vanilla ES modules: pitch replay, lane-stacked timeline, WP chart, persona cards with English beside hi/es + back-translation + evidence chips, compare A/B, what-if chart, overlay JSON download, agent trace + kill/re-run).
- Run: `.venv/Scripts/python.exe -m tacticlens.api` then http://127.0.0.1:8000/#GM01. Keys: Space play, arrows ±30 s, [ ] prev/next moment. `?dir=rtl` previews RTL.
- Tests: tests/test_api.py (fast) + tests/test_web_smoke.py (Playwright desktop 1366 + mobile 390; skips if Playwright/Chromium missing). New extra: `pip install -e .[e2e] && python -m playwright install chromium`.
- Gotcha: system `python` is 3.10 without deps; always use `.venv/Scripts/python.exe`.
- Next: M7 cloud (Container Apps via azd, managed identity, Cosmos store, live mode). Dockerfile/CI can go to Copilot; CI must install the e2e extra to run the smoke test.
- Open: UI strings are English only (Translator for UI strings not wired); `tone` persona field has no effect yet; close issues #1, #5 (and M6 issue) on GitHub.
- Usage (Oct 22, M6 session): weekly 41% -> 48% (past the 45% lean-mode line in PLAN.md); session 12%.
