# TacticLens — sureshot plan (Sat Oct 17 -> Tue Oct 27, 2026)

Times are Dublin. Ireland's clocks go back on Sun Oct 25 (you gain an hour).

## 0. Hard facts
- Submission closes Oct 27 23:59 PT = **06:59 Wed Oct 28 Dublin**. We submit by **18:00 Tue Oct 27** and never plan to use the last night.
- Registration closes Oct 20 12:00 PT = **20:00 Tue Oct 20 Dublin**. You said you registered: confirm you got the Innovation Studio invite (check spam). If not, fix it before Tue 20:00.
- Judging runs to Nov 10: the live demo link must stay free to access and working until then.
- Needed to submit: public GitHub repo, English pitch (what/tech/problem), public video link under 2 minutes (YouTube/Vimeo etc.), live or test link plus testing instructions. Video: no third-party trademarks, no copyrighted music. Non-English material needs English translation (we show English beside every translated output).
- Judging: Stage 1 pass/fail (fits theme, visibly uses the Microsoft/Azure tech), Stage 2 five criteria at 20% each (see section 8).

## 1. Scope tiers (cut from the bottom, never from the top)
**P0 — must ship (this alone is a credible Grand Prize entry):**
simulator + realism report; xG/xT/win-probability models with calibration plot; moment detector; grounded explanations with verifier and template fallback; counterfactual "what if" for top moments (precomputed); personas analyst/casual/beginner; languages en + hi + es with English shown alongside; cricket analogy pack; audio for en + hi; overlay JSON; web Match Center; deployed on Container Apps using Foundry; eval table; README; video; submission.
**P1 — strongly wanted:** audio-description persona with Speech and ARIA live captions; player-lock mode; Cosmos DB store; Arabic with RTL; Content Safety gate; Azure Translator back-translation check; GitHub Actions running tests + eval.
**P2 — only if ahead:** Japanese; Fabric Real-Time; OpenTelemetry dashboards; live custom-persona generation beyond cache.

## 2. How Claude limits work (so the plan respects them)
- Two limits run at once: a rolling 5-hour window that starts at your first prompt, and a weekly cap. Check both with `/usage` in Claude Code (also Settings > Usage on claude.ai).
- It is ONE pool: claude.ai chat, Claude Desktop and Claude Code all draw from it. **Do your brainstorming here once, then stop chatting; build in Claude Code only.**
- Context size is the hidden cost: past roughly 150k tokens every turn gets expensive. Short sessions beat marathon ones.
- Your plan tier is unknown to me, so the plan measures instead of guessing (rule in 2.3).

### 2.1 Token hygiene (all already baked into CLAUDE.md)
1. One milestone per session, then `/clear`. Never carry a 200k-token context into the next milestone.
2. CLAUDE.md holds the architecture, so no session starts with exploration. HANDOFF.md carries state between sessions.
3. Deterministic code first, LLM calls last; cache every LLM/Speech output on disk by input hash (also protects Azure spend and demo reliability).
4. Run tests with `pytest -q -x`; never paste long logs.
5. Default model: Claude Sonnet 5.5 (`/model`). Switch to Opus 5.5 only for the M4 agent design and for a bug that survived two Sonnet attempts. Use Haiku 5.5 for mechanical chores (fixtures, docstrings, doc tables).
6. Ask for MS Learn doc lookups before writing Azure/Agent Framework code, so you don't burn sessions on hallucinated APIs and rewrites.
7. No subagents or parallel agents (each starts cold and re-reads context).
8. Start your first prompt of the day deliberately: the 5-hour window starts then. Heavy milestones go at the start of a window.

### 2.2 Offload to GitHub Copilot (saves Claude usage AND ticks the judged hero tech)
Check Copilot access today (it is typically free for verified students through GitHub Education — verify). Use Copilot Agent Mode, with the Azure MCP server enabled, for: `infra/` (azd + Bicep for Container Apps, Cosmos DB, Foundry/Speech/Content Safety wiring, managed identity), Dockerfile, `.github/workflows/`, PR descriptions/reviews, README polish. Drive repo chores with `gh` (issues per milestone, PRs). Mention all of this in the README: judges score GitHub Copilot Agent Mode, Azure MCP and GitHub CLI use.

### 2.3 Measure and adapt
- Run `/usage` at the start and end of each Claude session and write the % consumed into HANDOFF.md.
- After M2 you will know your real burn. Decision rule: if weekly usage is already above ~45% after M2, switch to LEAN MODE: drop all P1 except Cosmos DB and Content Safety, Sonnet only, let Copilot write more of the tests, and keep M6 to one session.
- Safety valve: paid plans can continue on usage credits at API rates once you hit a limit. Optional; if you enable it, set a low monthly spend cap.

### 2.4 If you hit a limit mid-milestone (do not stop working)
Switch to non-Claude work until the window resets: Azure/Foundry provisioning, Copilot tasks, manual QA of the running app, reading MS Learn docs, recording and re-recording the video, README and architecture diagram, reviewing evaluation output, drafting the submission text, checking the realism report by eye. Keep a running list of these in HANDOFF.md so you always have useful work queued.

## 3. Tonight (Sat Oct 17, ~2 h) — setup, minimal Claude usage
1. Confirm hackathon registration + Innovation Studio invite.
2. Azure subscription with credits (check Azure for Students with your UCD email) and set a **budget alert**. Create a Foundry project and deploy one small, cheap chat model; note endpoint + deployment name. Create AI Speech and Content Safety resources (free tiers where available).
3. Create the public GitHub repo `tacticlens` (MIT license), enable Copilot, put `CLAUDE.md` and `PLAN.md` in the root, create `HANDOFF.md` (one line: "M0 not started").
4. In VS Code, start Claude Code in the repo and run the M0 prompt (small).

## 4. Day-by-day
| Date | Milestone | Claude Code session | Non-Claude work |
|---|---|---|---|
| Sat 17 | Setup + M0 scaffold | light | Azure, repo, Copilot access |
| Sun 18 | M1 simulator + realism report | heavy | eyeball golden matches; confirm invite |
| Mon 19 | M2 metrics, models, moment detector | heavy | record `/usage` burn; apply rule 2.3 |
| Tue 20 | M3 counterfactuals + evidence packs | medium | **registration closes 20:00**; Copilot: deploy hello-world to Container Apps via `azd` |
| Wed 21 | M4 agents on Foundry + verifier + eval | heavy | Copilot: managed identity to Foundry; create GitHub issues |
| Thu 22 | M5 personalization + Speech | medium | review hi/es output with a fluent friend if possible; cricket analogy sanity check |
| Fri 23 | M6a Match Center: pitch replay, timeline, WP chart, persona switcher | medium | Copilot: Cosmos DB + CI workflow |
| Sat 24 | M6b what-if panel, overlay viewer, agent trace, a11y, Playwright smoke | medium | manual QA on phone + desktop |
| Sun 25 | M7 cloud live mode + eval in CI; **FEATURE FREEZE at night** | light/medium | verify public URL from another network |
| Mon 26 | M8 bug fixes only, README, docs, video draft, dry-run of the submission form | light | record video take 1 |
| Tue 27 | Final video, submission by **18:00** | none | submit, then verify repo is public + link works logged out |
| Wed 28 | Do not touch. Deadline 06:59. | | |

Weekday sessions assume 3–4 focused hours around your lectures. If a day is lost, merge M3 into M2/M4 (cut counterfactual UI polish first, never the verifier).

## 5. Session prompt template (paste, change the milestone)
> Read CLAUDE.md and HANDOFF.md. Implement milestone M<N> only, to its definition of done. Don't read or edit files outside what M<N> needs. Check Microsoft docs before using any Azure/Agent Framework API. Run `pytest -q -x` and fix failures. Then commit and rewrite HANDOFF.md in at most 10 lines including the current `/usage` percentages.

Milestone-specific extra line:
- M1: "Show me the realism table and the 6 golden match scorelines when done."
- M2: "Save the calibration plot and metrics table to docs/evaluation.md."
- M4: "Start in plan mode: propose the workflow and the verifier checks in under 40 lines, wait for my OK, then implement."
- M6: "Use the golden data and contracts only; no new dependencies; mobile + desktop layouts."

## 6. Demo insurance
- Golden mode: every demo match has precomputed explanations, counterfactuals, localizations and audio committed in `data/golden/`. The app works with Azure fully offline; live mode is a bonus that the video shows once.
- Container Apps with at least one warm replica during judging, plus the budget alert. Keep the URL free of login.
- Agent failure demo: a visible "Agent trace" panel and a switch that kills the Explainer to show retry then template fallback (this is what the Multi-Agent criterion wants).
- Test the public URL on mobile data before submitting.

## 7. Video script (target 105 s, hard cap 120)
- 0:00–0:10 Problem: scores don't explain the game; fans, analysts and broadcasters need different stories. Show the Match Center.
- 0:10–0:35 Live replay of a synthetic match; a moment fires; overlay appears with win-probability swing.
- 0:35–0:70 Same moment, three personas side by side: analyst card, casual caption, Hindi version with a cricket analogy and English alongside; press play for the audio description.
- 0:70–0:90 "What if?": counterfactual distribution for the moment; point at the evidence links and the green "verified" badge.
- 0:90–0:105 Architecture slide: simulator -> Foundry agents -> verifier -> overlays on Azure, built with Copilot Agent Mode and Claude Code. Close on the live URL.
No music with rights issues (use silence or your own track), no logos, fictional clubs only.

## 8. Judging criteria -> proof
| Criterion (20% each) | Proof in repo/video |
|---|---|
| Technological Implementation | Simulator + realism report, trained models + calibration plot, typed code, tests, CI, IaC |
| Agentic Design & Innovation | Distinct agent roles, shared state, verifier loop, fallbacks, trace panel, counterfactual engine |
| Real-World Impact | Broadcaster overlay JSON contract, localization, accessibility, grounded outputs, deployed on Azure |
| UX & Presentation | Polished Match Center, persona compare view, clear <2 min video, real backend + frontend balance |
| Category adherence | README states target categories: Grand Prize, Best Use of Microsoft Foundry, plus Best Multi-Agent System as a second shot |

## 9. Submission checklist (Tue Oct 27)
- [ ] Repo is public, MIT license, README with architecture diagram and judging mapping, no secrets (run a secret scan).
- [ ] Demo video under 2:00, public URL, plays logged out, no trademarks or copyrighted music.
- [ ] Live URL works logged out; testing instructions written (golden mode and live mode).
- [ ] Pitch text: what it is, Azure/Microsoft tech used (Foundry, Agent Framework, Container Apps, Speech, Content Safety, Cosmos DB, Copilot Agent Mode, Azure MCP, GitHub CLI), problem solved.
- [ ] Project is new work started after Sep 29, fictional data only.
- [ ] Submitted on the Hackathon platform by 18:00 Dublin; screenshot the confirmation.

## 10. Cut order if time or usage runs short
Japanese -> Fabric -> OpenTelemetry -> Arabic/RTL -> player-lock live mode -> Cosmos DB (use local JSON) -> Translator check -> audio-description Speech (keep captions) -> counterfactual UI polish. Never cut: verifier, golden mode, personas, English-beside-translation, deployment, video.