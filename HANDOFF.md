# HANDOFF
- Done: M0-M5. M5 = `src/tacticlens/personalize/`: persona engine (fav club boost, player-lock, stats_density trim, cricket analogy pack en/hi/es), glossary + hi name transliteration, Localizer agent (Foundry gpt-5-mini) -> numeral/entity checks -> Translator fallback -> Translator back-translation, Speech TTS. Report: docs/personalization.md.
- Golden: data/golden/GMxx/localized.json (hi+es for every explanation; 1526/1526 sentences agent-passed, 0 fallback, 0 drift) + audio.json + audio/*.mp3 (audio persona, top-5 moments, en/hi/es, 90 files, ~7.5 MB).
- Contract changes: Persona.player_lock (key gets ".lock"), Sentence.back_translation.
- Env: new AZURE_AI_SERVICES_ENDPOINT (custom domain serves Translator `/translator/text/v3.0/...` and TTS `/tts/cognitiveservices/v1`, plain Entra bearer). AZURE_SPEECH_REGION / AZURE_TRANSLATOR_REGION removed from .env.example. Load .env manually: `set -a; . ./.env; set +a`, and put az on PATH (see M4 gotcha).
- CLI: `python -m tacticlens.personalize [localize|speech] --live` (rebuilds golden), `report` (offline).
- Gotcha: TTS hit one WinError 10060 timeout; `_post` now retries 3x. Live localize takes ~10 min (106 agent calls, concurrency 6).
- Next: M6 Web Match Center (Fri 23). API must load localized.json/audio.json and call `personalize.persona.personalize()` per request.
- Open: close issue #1 (Azure setup) and #5 (M5) on GitHub.
- Usage: weekly 40% at session start (Oct 22); run `/usage` and record end %.
