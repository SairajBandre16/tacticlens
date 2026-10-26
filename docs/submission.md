# Submission kit

Copy-ready text for the hackathon form, plus the script the demo video was made from.

## Links
- Repository: https://github.com/SairajBandre16/tacticlens
- Live demo: https://ca-tacticlens-bwdo4r22di23o.ambitiousocean-8d1c2333.francecentral.azurecontainerapps.io
- Video: https://youtu.be/srW510kqPf0 (1:49, public)
- Categories: Grand Prize; Best Use of Microsoft Foundry; Best Multi-Agent System

## Project name and tagline
**TacticLens**: grounded, personalized match storytelling. Every number is checked, and every fan can follow the story their way.

## What it does
TacticLens is a match-intelligence engine on Azure. It turns a stream of football events into short stories about the key moments of a match, and it tells each story in the way the viewer needs it. An analyst gets the numbers. A casual fan gets the story. A beginner gets the terms explained. A blind or low-vision fan gets an audio description. Each version is available in English, Hindi or Spanish, and the English source sits beside every translation. The engine also answers "what if?" questions, such as "what if that goal had not gone in?". It replays the rest of the match 200 times with that one change and reports how the win chance would move. Broadcasters get the same stories as overlay cues in JSON, ready for on-screen graphics.

## The problem it solves
A scoreline does not explain a game, and one commentary cannot fit every fan. Generative AI can write personalized commentary at scale, but it invents numbers, and a wrong statistic on a broadcast damages trust. TacticLens lets the AI write only from computed evidence. Each sentence must cite the evidence it uses, and a deterministic verifier rejects any claim or number that the evidence does not back. If the AI cannot produce a verified draft, the system uses a verified template instead. Viewers therefore never see an unchecked number.

## How we built it (technology)
- **Simulation and models (Python):** a possession-chain simulator generates fictional matches with team styles and scripted story beats. It passes 9 of 9 realism checks against real-football ranges. We trained our own xG (logistic regression, ROC AUC 0.84), expected-threat (value iteration) and win-probability (gradient boosting) models on 3,000 simulated matches. A moment detector ranks goals, big chances, red cards, momentum shifts, press collapses and substitution effects. Each moment gets an evidence pack.
- **Counterfactual engine:** Monte-Carlo rollouts (N = 200, seeded) from the state of a moment, with one change. It reports the mean change in win chance and an 80% interval.
- **Multi-agent workflow (Microsoft Agent Framework + Microsoft Foundry):** Spotter → EvidenceBuilder → Explainer agent ⇄ Verifier (deterministic checks, then an LLM judge, up to 2 regenerations) → TemplateFallback → Localizer agent → AccessibilityDescriber → SafetyGate (Azure AI Content Safety). The workflow logs every handoff, retry and fallback, and the app shows them in an Agent trace panel. A kill switch shows the fallback path live.
- **Personalization and accessibility:** four personas, three languages (numeral and entity checks, with an Azure AI Translator back-translation check), a cricket analogy pack, favourite club and player, player-lock mode, Azure AI Speech audio descriptions, ARIA live captions, keyboard control, reduced motion and RTL layouts.
- **Platform:** FastAPI with server-sent-event replay on Azure Container Apps (azd + Bicep, keyless managed identity), Azure Cosmos DB, Application Insights, and GitHub Actions (tests, a Playwright smoke test, an eval drift check). The frontend is vanilla JS and SVG with no build step.
- **Results:** 100% of shipped sentences cite valid evidence (763 of 763), and 100% of shipped numbers are backed by evidence (1,448 of 1,448). The verifier catches 100% of injected faults in all 8 fault classes. All demo moments get a verified or template-fallback explanation.

## Testing instructions
No login is needed. The first load can take about 20 seconds while the app starts.
1. Press **Play**. Events stream onto the pitch, and the score, match stats and win-probability chart update live.
2. Click an icon on the **Key moments** timeline. Overlay cues appear on the pitch, and the matching story card is highlighted. Click an evidence id such as `e3` to see the number it backs.
3. In **Story**, set **Language** to Hindi to see the English source and a back-translation check beside each sentence. Set **Viewer** to Audio description to get a playable audio track.
4. Open **Compare** to see two viewers side by side, and **What if?** to see the counterfactual for the selected moment.
5. Open **Agent trace**, turn on **Kill the Explainer agent**, and click **Re-run agents**. The trace shows the retries and then the verified template fallback. Choose **Live** to run the workflow on Microsoft Foundry and Content Safety.

All data is synthetic, and all clubs and players are fictional.

## Video script (target 105 s, hard cap 120 s)
The published video follows this script: screen captures of the Match Center at 1920 × 1080, an Azure AI Speech voiceover (en-US-AndrewMultilingualNeural), burned-in subtitles, no music and no real logos.

| Time | On screen | Voice-over |
|---|---|---|
| 0:00–0:10 | The Match Center loaded on "Late comeback"; slowly hover the logo and the how-it-works strip | "A scoreline doesn't explain a game, and one commentary doesn't fit every fan. TacticLens turns match events into stories that every fan can trust." |
| 0:10–0:30 | Press Play at 64×; the stats and win-probability chart move; while it plays, click the 88' goal on the timeline; the goal burst and the overlay cues appear | "We simulate fictional matches and train our own xG and win-probability models. A detector finds the moments that mattered, and the overlays are JSON a broadcaster can use." |
| 0:30–0:55 | In Story, click the evidence id `e3`; switch to Compare with Analyst in English beside Beginner in Hindi; point at the English source and the back-translation check | "Agents on Microsoft Foundry write each story, and every sentence cites its evidence. The same moment reads differently for an analyst and for a beginner in Hindi, with the English source alongside." |
| 0:55–1:05 | Set Viewer to Audio description and play the clip for 3 seconds | "Blind and low-vision fans get an audio description from Azure AI Speech." |
| 1:05–1:20 | Open What if? on the 38' goal and show the interval chart | "What if that goal hadn't gone in? We replay the rest of the match two hundred times and show the change in win chance with its uncertainty." |
| 1:20–1:35 | Open Agent trace, turn on the kill switch, click Re-run, and show the retries and the template fallback | "A verifier checks every number. If the AI can't produce a verified draft, the system falls back to a verified template. No fan sees an unchecked number." |
| 1:35–1:45 | The README architecture diagram, then the live URL | "Microsoft Foundry, Agent Framework, Content Safety, Speech, Cosmos DB and Container Apps. TacticLens: every story checked, every fan included." |
