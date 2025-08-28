# PowerShell script to generate local.settings.json

# Get values from azd environment
Write-Host "Getting environment values from azd..."
$azdValues = azd env get-values
$COSMOS_ENDPOINT = ($azdValues | Select-String 'COSMOS_ENDPOINT="(.*?)"').Matches.Groups[1].Value
$COSMOS_DATABASE_NAME = ($azdValues | Select-String 'COSMOS_DATABASE_NAME="(.*?)"').Matches.Groups[1].Value
$COSMOS_CONTAINER_NAME = ($azdValues | Select-String 'COSMOS_CONTAINER_NAME="(.*?)"').Matches.Groups[1].Value
$COSMOS_KEY = ($azdValues | Select-String 'COSMOS_KEY="(.*?)"').Matches.Groups[1].Value
$AI_PROJECT_CONNECTION_STRING = ($azdValues | Select-String 'AI_PROJECT_CONNECTION_STRING="(.*?)"').Matches.Groups[1].Value
$AI_FOUNDRY_OPENAI_ENDPOINT = ($azdValues | Select-String 'AI_FOUNDRY_OPENAI_ENDPOINT="(.*?)"').Matches.Groups[1].Value
$AI_FOUNDRY_OPENAI_KEY = ($azdValues | Select-String 'AI_FOUNDRY_OPENAI_KEY="(.*?)"').Matches.Groups[1].Value
$STORAGE_CONNECTION_STRING = ($azdValues | Select-String 'STORAGE_CONNECTION_STRING="(.*?)"').Matches.Groups[1].Value
$STORAGE_CONTAINER_SNIPPETBACKUPS = ($azdValues | Select-String 'STORAGE_CONTAINER_SNIPPETBACKUPS="(.*?)"').Matches.Groups[1].Value
$STORAGE_CONTAINER_SNIPPETINPUT = ($azdValues | Select-String 'STORAGE_CONTAINER_SNIPPETINPUT="(.*?)"').Matches.Groups[1].Value
$EMBEDDING_MODEL_DEPLOYMENT_NAME = ($azdValues | Select-String 'EMBEDDING_MODEL_DEPLOYMENT_NAME="(.*?)"').Matches.Groups[1].Value
$CHAT_MODEL_DEPLOYMENT_NAME = ($azdValues | Select-String 'CHAT_MODEL_DEPLOYMENT_NAME="(.*?)"').Matches.Groups[1].Value
$APP_INSIGHTS_CONNECTION_STRING = ($azdValues | Select-String 'APP_INSIGHTS_CONNECTION_STRING="(.*?)"').Matches.Groups[1].Value

# Provide defaults if values are empty
if (-not $COSMOS_DATABASE_NAME) { $COSMOS_DATABASE_NAME = "dev-snippet-db" }
if (-not $COSMOS_CONTAINER_NAME) { $COSMOS_CONTAINER_NAME = "code-snippets" }
if (-not $STORAGE_CONTAINER_SNIPPETBACKUPS) { $STORAGE_CONTAINER_SNIPPETBACKUPS = "snippet-backups" }
if (-not $STORAGE_CONTAINER_SNIPPETINPUT) { $STORAGE_CONTAINER_SNIPPETINPUT = "snippet-input" }
if (-not $EMBEDDING_MODEL_DEPLOYMENT_NAME) { $EMBEDDING_MODEL_DEPLOYMENT_NAME = "text-embedding-3-small" }
if (-not $CHAT_MODEL_DEPLOYMENT_NAME) { $CHAT_MODEL_DEPLOYMENT_NAME = "gpt-4o" }
if (-not $STORAGE_CONNECTION_STRING) { $STORAGE_CONNECTION_STRING = "UseDevelopmentStorage=true" }

# Create the JSON content
$jsonContent = @"
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "$STORAGE_CONNECTION_STRING",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "PYTHON_ENABLE_WORKER_EXTENSIONS": "True",
    "COSMOS_ENDPOINT": "$COSMOS_ENDPOINT",
    "COSMOS_KEY": "$COSMOS_KEY",
    "COSMOS_DATABASE_NAME": "$COSMOS_DATABASE_NAME",
    "COSMOS_CONTAINER_NAME": "$COSMOS_CONTAINER_NAME",
    "COSMOS_VECTOR_TOP_K": "30",
    "BLOB_CONTAINER_NAME": "$STORAGE_CONTAINER_SNIPPETBACKUPS",
    "EMBEDDING_MODEL_DEPLOYMENT_NAME": "$EMBEDDING_MODEL_DEPLOYMENT_NAME",
    "AGENTS_MODEL_DEPLOYMENT_NAME": "$CHAT_MODEL_DEPLOYMENT_NAME",
    "PROJECT_CONNECTION_STRING": "$AI_PROJECT_CONNECTION_STRING",
    "AZURE_OPENAI_ENDPOINT": "$AI_FOUNDRY_OPENAI_ENDPOINT",
    "AZURE_OPENAI_KEY": "$AI_FOUNDRY_OPENAI_KEY",
    "VECTOR_TOP_K": "5",
    "OPENAI_TEMPERATURE": "0.2",
    "REQUEST_TIMEOUT_SEC": "20",
    "CHUNK_SIZE": "800",
    "INGESTION_CONTAINER": "$STORAGE_CONTAINER_SNIPPETINPUT",
    "MAX_BLOB_MB": "2",
    "DEFAULT_PROJECT_ID": "default-project",
    "OPENAI_CHAT_MODEL": "$CHAT_MODEL_DEPLOYMENT_NAME",
    "MAX_AGENT_ITERATIONS": "3",
    "AGENT_TOKEN_LIMIT": "4000",
    "ENABLE_CONTENT_FILTER": "0",
    "MAX_CONCURRENT_AGENTS": "3",
    "APPLICATIONINSIGHTS_CONNECTION_STRING": "$APP_INSIGHTS_CONNECTION_STRING"
  }
}
"@

# Write content to local.settings.json
$settingsPath = Join-Path (Get-Location) "src" "local.settings.json"
$jsonContent | Out-File -FilePath $settingsPath -Encoding utf8

Write-Host "local.settings.json generated successfully in src directory!"
Write-Host "Using Cosmos DB: $COSMOS_ENDPOINT"
Write-Host "Using AI Foundry: $AI_FOUNDRY_OPENAI_ENDPOINT"
# Helper to mask a value keeping first 3 characters and masking the rest with '*'
function Mask-Keep3 {
  param(
    [string]$Value
  )
  if ([string]::IsNullOrEmpty($Value)) { return "" }
  if ($Value.Length -le 3) { return $Value }
  $prefix = $Value.Substring(0,3)
  $masked = '*' * 5
  return "$prefix$masked"
}

# Print all azd variables (masked where appropriate)
# Print all azd variables; only mask known secrets
Write-Host "`nAZD variables:"
Write-Host "COSMOS_ENDPOINT: $COSMOS_ENDPOINT"
Write-Host "COSMOS_KEY: $(Mask-Keep3 -Value $COSMOS_KEY)"
Write-Host "COSMOS_DATABASE_NAME: $COSMOS_DATABASE_NAME"
Write-Host "COSMOS_CONTAINER_NAME: $COSMOS_CONTAINER_NAME"
# AI_PROJECT_CONNECTION_STRING is secret-ish (mask)
Write-Host "AI_PROJECT_CONNECTION_STRING: $(Mask-Keep3 -Value $AI_PROJECT_CONNECTION_STRING)"
Write-Host "AI_FOUNDRY_OPENAI_ENDPOINT: $AI_FOUNDRY_OPENAI_ENDPOINT"
# API key for OpenAI: mask
Write-Host "AI_FOUNDRY_OPENAI_KEY: $(Mask-Keep3 -Value $AI_FOUNDRY_OPENAI_KEY)"
Write-Host "STORAGE_CONTAINER_SNIPPETBACKUPS: $STORAGE_CONTAINER_SNIPPETBACKUPS"
Write-Host "STORAGE_CONTAINER_SNIPPETINPUT: $STORAGE_CONTAINER_SNIPPETINPUT"
Write-Host "EMBEDDING_MODEL_DEPLOYMENT_NAME: $EMBEDDING_MODEL_DEPLOYMENT_NAME"
Write-Host "CHAT_MODEL_DEPLOYMENT_NAME: $CHAT_MODEL_DEPLOYMENT_NAME"
# Application Insights connection string is secret (mask)
Write-Host "APP_INSIGHTS_CONNECTION_STRING: $(Mask-Keep3 -Value $APP_INSIGHTS_CONNECTION_STRING)"

# Mask only the AccountKey value for storage connection string when displaying the common summary
if ($STORAGE_CONNECTION_STRING -match 'AccountKey=([^;]+)') {
  $accountKey = $Matches[1]
  $maskedKey = Mask-Keep3 -Value $accountKey
  $maskedStorage = $STORAGE_CONNECTION_STRING -replace "AccountKey=[^;]+", "AccountKey=$maskedKey"
} else {
  $maskedStorage = Mask-Keep3 -Value $STORAGE_CONNECTION_STRING
}
Write-Host "Using Storage: $maskedStorage"


# Export the Azure Function key to AZURE_FUNCTION_KEY (PowerShell equivalent of the bash script)
Write-Host "Exporting environment variables for later use..."
# Use azd env get-values to find function app name and resource group, then query function keys
$functionAppName = ($azdValues | Select-String 'FUNCTION_APP_NAME="(.*?)"').Matches.Groups[1].Value
$resourceGroup = ($azdValues | Select-String 'AZURE_RESOURCE_GROUP="(.*?)"').Matches.Groups[1].Value
if ($functionAppName -and $resourceGroup) {
  try {
    $AZURE_FUNCTION_KEY = az functionapp keys list --name $functionAppName --resource-group $resourceGroup --query "functionKeys.default" -o tsv
    # Set as environment variable for the session
    $env:AZURE_FUNCTION_KEY = $AZURE_FUNCTION_KEY
    $AZURE_FUNCTION_NAME = $functionAppName
    $env:AZURE_FUNCTION_NAME = $AZURE_FUNCTION_NAME
  } catch {
    Write-Host "Warning: unable to fetch Azure Function key: $_"
  }
} else {
  Write-Host "Warning: FUNCTION_APP_NAME or AZURE_RESOURCE_GROUP not found in azd environment values; skipping function key export."
}