# TacticLens — build spec for Claude Code

Project for the Microsoft x Premier League "Inside the Game: Developer Hackathon".
Hard deadline: Oct 27 2026 23:59 PT (= 06:59 on Oct 28, Dublin). Internal target: submit Oct 27 by 18:00 Dublin.
Read PLAN.md for the schedule and HANDOFF.md for where the last session stopped.

## What we are building
An AI match-intelligence engine on Azure that turns SYNTHETIC football events into explained, personalized, accessible match storytelling.
Pipeline (matches the official brief): Ingest -> Interpret -> Explain -> Render -> Personalize.

Three differentiators — protect these, they are how we win:
1. REAL MODELS + COUNTERFACTUALS: xG, xT, win-probability models trained on our own synthetic data, plus a Monte-Carlo "what if?" engine that re-simulates from a match state with one thing changed.
2. GROUNDED EXPLANATIONS: every sentence the AI writes cites evidence IDs; a deterministic verifier rejects any claim or number not backed by evidence.
3. LOCALIZED + ACCESSIBLE PERSONALIZATION: personas (analyst / casual / beginner / audio-description), languages (en, hi, es; ar and ja are stretch), cultural analogy packs (cricket), favourite club/player, player-lock mode. Every non-English output is shown beside its English version.

## Non-negotiable rules
- Synthetic data only. Fictional clubs and players only (e.g. Northbridge United, Kestrel Town, Harbor Athletic, Redmere FC). No Premier League/club logos, names of real players, or third-party trademarks anywhere (app, repo, video).
- The LLM never invents numbers. All figures come from computed evidence; the verifier enforces it.
- Everything must work in "golden mode" with no Azure calls (pre-generated outputs in data/golden/) so the demo never depends on live services.
- No secrets in the repo. Env vars locally, managed identity / Key Vault in Azure. `.env` is git-ignored.
- Public repo, MIT license, English docs.
- `pytest -q` must pass before every commit. Deterministic seeds everywhere.

## Architecture
```
sim (events) -> metrics (xG, xT, WP, momentum, PPDA) -> moments (detector + evidence packs)
   -> counterfactual (rollouts) -> agents workflow (Agent Framework on Microsoft Foundry)
   -> personalize (persona, localize, accessibility, speech) -> render (overlay cues JSON)
   -> api (FastAPI, SSE replay) -> web (Match Center)
```
Agents workflow (Microsoft Agent Framework, Python; check current MS Learn docs before coding — do not guess the API):
- Spotter, EvidenceBuilder, Renderer = plain code (deterministic, cheap).
- Explainer = agent. Produces JSON sentences with evidence_ids.
- Verifier = deterministic checks first, small LLM check second. Up to 2 regenerations, then template fallback.
- Fan-out per persona: Localizer agent, AccessibilityDescriber agent. Then SafetyGate (Azure AI Content Safety).
- Shared state object passed through the workflow; log every handoff and every fallback (shown in the UI "Agent trace" panel).

Azure services (keep to this list): Microsoft Foundry (model deployment + tracing/evals), Container Apps (hosting), Cosmos DB (moment/evidence store; local JSON fallback), AI Speech (TTS), AI Content Safety, AI Translator (UI strings + back-translation check), App Insights. Fabric is a P2 stretch only.

## Contracts (source of truth: contracts/*.schema.json, pydantic v2 models mirror them)
- Event: id, match_id, t (sec), period, minute, team, player_id, type (pass|shot|tackle|interception|dribble|foul|card|sub|clearance|corner|free_kick|goal|pressure), x,y (0-100), end_x,end_y, outcome, under_pressure, body_part, xg (filled by metrics).
- Moment: id, match_id, t_start, t_end, kind (goal|big_chance|red_card|momentum_shift|press_collapse|sub_effect), importance, wp_before, wp_after, evidence[{id,label,value,unit,event_ids}], counterfactuals[].
- Explanation: moment_id, persona_key, lang, sentences[{text, evidence_ids}], verified, verifier_notes, degraded.
- OverlayCue: cue_id, match_id, in_t, out_t, template (lower_third|stat_bug|wp_swing|pressing_map|player_tag), persona_key, lang, payload{}, a11y{aria_label, speech_text}.
- Persona: mode (analyst|casual|beginner|audio), lang, fav_club, fav_player, analogy (none|cricket), tone (0-2), stats_density (0-2).
Changing a contract = update schema + models + fixtures + tests in the same commit.

## Repo layout
```
contracts/  src/tacticlens/{sim,metrics,moments,counterfactual,agents,personalize,render,api,store}/
web/ (static, no build step)  data/golden/  tests/  infra/ (azd+Bicep, owned by Copilot)  docs/  .github/workflows/
```

## Stack choices (do not add heavy deps without asking)
Python 3.11, numpy, pandas, scikit-learn, pydantic v2, FastAPI + uvicorn (SSE), pytest, jsonschema. Frontend: vanilla JS (ES modules) + CSS + SVG pitch, no framework, no build step. Chart: a tiny inline SVG helper (no big chart library).

## Milestones and definition of done
- M0 Scaffold: layout, pyproject, contracts + pydantic models + fixtures, CI stub, `pytest` runs. DoD: `pytest -q` green, schemas validate fixtures.
- M1 Simulator: possession-chain simulator with team style params (press_intensity, tempo, directness, width) on a 12x8 zone grid; scripted story beats (red card at minute X, tactical sub, late comeback); fast mode (no coordinates) for model training. 6 golden matches (3-2 late comeback, red-card 1-0, 2-2 derby, press collapse, 4-0, set-piece 1-0). Realism report vs targets: goals/match 2.0-3.5; shots/team 9-16; on target 3-6; passes/team 350-600; pass accuracy 75-88%; fouls 18-26; cards 2-5; corners 3.5-6.5; dominant-side possession 50-65%. DoD: report passes, written to docs/realism.md.
- M2 Interpret: xG (logistic regression), xT (value iteration on zone grid), win-probability (gradient boosting trained on ~3,000 fast-sim matches), momentum, PPDA/pressure index; moment detector + importance ranking. DoD: calibration plot + metrics in docs/evaluation.md; top-8 moments per golden match look sensible.
- M3 Counterfactuals + evidence: Monte-Carlo rollouts (N=200) from a moment's state with one change (remove the event, change press intensity, undo the substitution); output mean WP delta + 80% interval; precompute for top-5 moments per match. Evidence packs for every moment. DoD: tests on determinism and sign of effect.
- M4 Agents: workflow above on Foundry; verifier; fallbacks; trace log; eval harness (grounding rate, number-accuracy, fallback rate) writing docs/evaluation.md. DoD: 100% of golden-match moments produce a verified or template-fallback explanation; eval table committed.
- M5 Personalize: persona engine, football glossary + name transliteration table (hi, es), cricket analogy pack, localizer with numeral/entity checks, audio-description mode, Speech TTS with cached audio. DoD: same moment renders as 4 persona cards in 3 languages; English back-translation present; audio for at least hi and en.
- M6 Web Match Center: SVG pitch replay with speed control, moment timeline, win-probability chart, persona switcher (side-by-side compare), "What if?" panel, overlay JSON viewer/download, agent trace panel, accessible (ARIA live captions, keyboard, contrast, reduced-motion, RTL). DoD: Playwright smoke test (desktop + mobile) green.
- M7 Cloud: Container Apps deploy via azd, managed identity to Foundry/Speech/Safety, Cosmos DB store, GitHub Actions (tests + eval + deploy), budget alert. DoD: public URL runs golden mode and live mode.
- M8 Polish: README with architecture diagram and judging-criteria mapping, docs/evaluation.md, demo video (<2 min), submission text, final QA.

## Working agreements (to save the user's Claude usage — important)
- One milestone per session. Stop at its DoD. Do not start the next milestone.
- Read only the files you need. No repo-wide exploration sweeps; use Grep/Glob with narrow patterns. Do not re-read files you just edited.
- Do not spawn subagents unless the user asks.
- Keep replies short. Do not paste long logs; run `pytest -q -x` and quote only failures.
- Prefer deterministic code over LLM calls wherever possible; cache every LLM/Speech output to disk keyed by input hash.
- Before using any Microsoft/Azure SDK, check its current docs (WebFetch on learn.microsoft.com) instead of guessing signatures.
- At the end of every session: commit, then rewrite HANDOFF.md (<= 10 lines: done, next step, gotchas, open decisions, `/usage` % consumed).
- Anything infrastructure-as-code, Dockerfile, GitHub Actions, or README polish is allowed to be left for Copilot (see PLAN.md); do not spend Claude usage on it unless asked.