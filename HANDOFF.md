# HANDOFF
- Done: M0-M4 + Azure setup (#1). Budget `tacticlens-monthly` (20/month, 50/80/100% alerts) live. az CLI 2.91 + azd 1.37 installed, `az login` done (UCD tenant).
- Azure: subscription policy allows ONLY switzerlandnorth, norwayeast, austriaeast, francecentral, germanywestcentral. Everything is in **francecentral**: RG `tacticlens-rg`, AIServices/Foundry resource `tacticlens-ai-sb`, project `tacticlens`, deployment `gpt-5-mini` (GlobalStandard, 50k TPM). Roles Foundry User + Cognitive Services User on the account for the user.
- One AIServices resource also serves Speech (francecentral), Content Safety and Translator: endpoint `https://tacticlens-ai-sb.cognitiveservices.azure.com/`, keyless (Entra ID). No extra resources needed for M5/M7.
- `.env` written (git-ignored); code does NOT auto-load it — export vars or load in the CLI. Smoke test: live FoundryExplainer on GM01-M01/casual verified on first pass, no fallback.
- Gotcha: shells started before the install lack az on PATH -> DefaultAzureCredential fails ("Azure CLI not found on path") and the workflow silently falls back to templates. Prepend `C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin`. Use `.venv` (Python 3.11); system python is 3.10.
- Next: M5 personalization + Speech (Thu 22). Optional first: `python -m tacticlens.agents golden --live` to regenerate golden explanations with gpt-5-mini (overwrites data/golden + eval section; review diff before commit).
- Usage: run `/usage` and record here.
- Repo: github.com/SairajBandre16/tacticlens (public, MIT, CI green). Issues: #1 Azure setup (now done, close it), #2-4 Copilot infra, #5-9 M5-M8.
