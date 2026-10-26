// TacticLens on Azure Container Apps. Deploy with `azd up` into an existing resource group.
// Keyless throughout: one user-assigned managed identity pulls the image and calls Foundry, Speech/Translator,
// Content Safety (the existing AI Services account) and Cosmos DB.
targetScope = 'resourceGroup'

@minLength(1)
param environmentName string
param location string = resourceGroup().location
@description('Existing AI Services (Foundry) account in this resource group.')
param aiServicesName string = 'tacticlens-ai-sb'
param aiProjectName string = 'tacticlens'
param modelDeployment string = 'gpt-5-mini'
@allowed(['golden', 'live'])
param tacticlensMode string = 'live'
@description('Image set by azd after the first deploy; empty means the placeholder image.')
param apiImage string = ''
@description('Signed-in user (set by azd); gets Cosmos data access for local runs.')
param principalId string = ''

var tags = { 'azd-env-name': environmentName }
var token = uniqueString(subscription().id, resourceGroup().id, environmentName)
var roles = {
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  azureAiUser: '53ca6127-db72-4b80-b1b0-d745d6d5456d'
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-tacticlens-${token}'
  location: location
  tags: tags
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-tacticlens-${token}'
  location: location
  tags: tags
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-tacticlens-${token}'
  location: location
  tags: tags
  kind: 'web'
  properties: { Application_Type: 'web', WorkspaceResourceId: logs.id }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'crtacticlens${token}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, roles.acrPull)
  scope: registry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}

// --- existing Foundry / AI Services account: keyless access for the app identity ---------------------------
resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aiServicesName
}

resource aiRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for r in [roles.cognitiveServicesUser, roles.azureAiUser]: {
  name: guid(aiServices.id, identity.id, r)
  scope: aiServices
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', r)
  }
}]

// --- Cosmos DB (serverless, Entra ID only): moment/evidence store ----------------------------------------
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: 'cosmos-tacticlens-${token}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [{ locationName: location, failoverPriority: 0 }]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    capabilities: [{ name: 'EnableServerless' }]
    disableLocalAuth: true
  }
}

resource db 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmos
  name: 'tacticlens'
  properties: { resource: { id: 'tacticlens' } }
}

resource containers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for c in ['moments', 'explanations']: {
  parent: db
  name: c
  properties: { resource: { id: c, partitionKey: { paths: ['/match_id'], kind: 'Hash' } } }
}]

var cosmosDataContributor = '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'

resource cosmosAppRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmos
  name: guid(cosmosDataContributor, identity.id, cosmos.id)
  properties: { principalId: identity.properties.principalId, roleDefinitionId: cosmosDataContributor, scope: cosmos.id }
}

resource cosmosUserRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = if (!empty(principalId)) {
  parent: cosmos
  name: guid(cosmosDataContributor, principalId, cosmos.id)
  properties: { principalId: principalId, roleDefinitionId: cosmosDataContributor, scope: cosmos.id }
}

// --- Container Apps ---------------------------------------------------------------------------------------
// environmentMode is explicit: new environments on this subscription otherwise default to *Express*, which
// fails managed-identity (and admin) image pulls from ACR.
resource env 'Microsoft.App/managedEnvironments@2026-03-02-preview' = {
  name: 'cae-wp-tacticlens-${token}'
  location: location
  tags: tags
  properties: {
    environmentMode: 'WorkloadProfiles'
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: { customerId: logs.properties.customerId, sharedKey: logs.listKeys().primarySharedKey }
    }
  }
}

resource api 'Microsoft.App/containerApps@2026-01-01' = {
  name: 'ca-tacticlens-${token}'
  location: location
  tags: union(tags, { 'azd-service-name': 'api' })
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  dependsOn: [acrPull]
  properties: {
    managedEnvironmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'auto', allowInsecure: false }
      registries: [{ server: registry.properties.loginServer, identity: identity.id }]
    }
    template: {
      containers: [{
        name: 'api'
        image: empty(apiImage) ? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' : apiImage
        resources: { cpu: json('1.0'), memory: '2Gi' }
        env: [
          { name: 'TACTICLENS_MODE', value: tacticlensMode }
          { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
          { name: 'AZURE_AI_PROJECT_ENDPOINT', value: 'https://${aiServicesName}.services.ai.azure.com/api/projects/${aiProjectName}' }
          { name: 'AZURE_AI_MODEL_DEPLOYMENT', value: modelDeployment }
          { name: 'AZURE_AI_SERVICES_ENDPOINT', value: aiServices.properties.endpoint }
          { name: 'AZURE_COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
          { name: 'AZURE_COSMOS_DATABASE', value: 'tacticlens' }
          { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
        ]
        // the placeholder image listens on 80, so probe only our own image
        probes: empty(apiImage) ? [] : [{ type: 'Readiness', httpGet: { path: '/api/health', port: 8000 }, periodSeconds: 10 }]
      }]
      scale: { minReplicas: 1, maxReplicas: 2 }  // one warm replica through judging (no cold start)
    }
  }
}

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.properties.loginServer
output AZURE_COSMOS_ENDPOINT string = cosmos.properties.documentEndpoint
output SERVICE_API_NAME string = api.name
output SERVICE_API_URI string = 'https://${api.properties.configuration.ingress.fqdn}'
