# HANDOFF
- Done: M0-M7. M7 = `store/` (Cosmos DB with JSON fallback, seeds from golden), live mode (`TACTICLENS_MODE=live`: `POST /explain` with `live:true` runs Foundry Explainer/judge + Azure AI Content Safety in SafetyGate, saves to Cosmos; "Live" toggle in the trace panel), App Insights, Dockerfile, `azure.yaml` + `infra/main.bicep` (keyless managed identity), CI (+Playwright, eval drift check), `deploy.yml`. Details in docs/deploy.md.
- Live URL: https://ca-tacticlens-bwdo4r22di23o.ambitiousocean-8d1c2333.francecentral.azurecontainerapps.io (golden + live verified Oct 25: Foundry run verified on 2nd draft, Content Safety all 0, stored in Cosmos).
- Redeploy: start Docker Desktop, then `azd deploy` (env `tacticlens` already set; azd uses az CLI auth).
- Gotchas: ACR Tasks blocked on the student sub (local Docker build); new Container Apps envs default to Express, which can't pull from ACR, so Bicep sets `environmentMode: 'WorkloadProfiles'`. Scale-to-zero means about 20 s cold start; set `minReplicas: 1` before judging/recording.
- Oct 26: UI pass (lens logo + favicon, how-it-works pipeline guide, live match-stats panel from /events with shot xG). Pushed to public GitHub (main in sync). Live URL NOT yet redeployed with the redesign: run `azd deploy`.
- Next: `azd deploy` + `minReplicas: 1`, then M8 polish (README + architecture diagram + judging map, video, submission text).
- Open: `azd pipeline config` (creates a federated SP in the UCD tenant) not run, so deploy.yml stays skipped until then; UI strings English only; `tone` has no effect; close GitHub issues #1, #5 + M6/M7.
- Usage (Oct 25, M7 session): weekly 3% -> 5%; session 6% -> 16%.
