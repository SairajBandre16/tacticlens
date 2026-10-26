# Deploying TacticLens to Azure

One command, keyless: `azd up` provisions everything in `infra/main.bicep` into an existing resource group and
deploys the container. The Foundry/AI Services account (`tacticlens-ai-sb`, project `tacticlens`, deployment
`gpt-5-mini`) is created beforehand and referenced as `existing`.

```sh
azd config set auth.useAzCliAuth true        # reuse `az login`
azd env new tacticlens --location francecentral
azd env set AZURE_RESOURCE_GROUP tacticlens-rg
azd up                                        # needs Docker running locally (see gotchas)
```

## What gets created
| Resource | Purpose |
|---|---|
| User-assigned managed identity | AcrPull on the registry; Cognitive Services User + Azure AI User on the AI Services account; Cosmos DB Built-in Data Contributor |
| Container Registry (Basic) | the app image |
| Container Apps environment (workload profiles, Consumption) + app | public HTTPS ingress on port 8000, scale 1-2 (one warm replica), readiness probe on `/api/health` |
| Cosmos DB (serverless, local auth disabled) | db `tacticlens`, containers `moments` and `explanations`, both partitioned on `/match_id` |
| Log Analytics + Application Insights | container logs, request telemetry (`azure-monitor-opentelemetry`) |

## Runtime modes
- Every GET endpoint serves golden data, so the Match Center never waits on Azure.
- `TACTICLENS_MODE=live` (the default in the cloud) enables `POST /api/matches/{id}/explain` with `live: true`:
  Explainer + judge on Foundry, SafetyGate on Azure AI Content Safety (blocks severity >= 4), and the result is
  stored in Cosmos DB. Capped by `TACTICLENS_LIVE_LIMIT` (default 300 uncached runs per replica); every model
  and Content Safety call is cached on disk by input hash.
- Moments are read from Cosmos DB (seeded from `data/golden/` on first read). Any Cosmos error falls back to the
  JSON files.

## Gotchas (Azure for Students)
- **ACR Tasks are blocked** (`TasksOperationsNotAllowed`), so `remoteBuild` is off and the image builds locally
  (or on the GitHub runner).
- **New Container Apps environments default to Express mode**, which fails ACR image pulls even with a valid
  managed identity or admin credential. `environmentMode: 'WorkloadProfiles'` (API `2026-03-02-preview`) is set
  explicitly to avoid it.
- Region policy allows only switzerlandnorth, norwayeast, austriaeast, francecentral, germanywestcentral.

## CI/CD
`.github/workflows/ci.yml` runs pytest (with the Playwright smoke test) and checks that the eval table matches the
committed golden explanations. `.github/workflows/deploy.yml` runs `azd deploy` after CI passes on `main`. It
stays skipped until `azd pipeline config` has created the federated credential and the `AZURE_*` repo variables.
