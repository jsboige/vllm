# Script pour charger les variables d'environnement et exécuter la validation améliorée

Write-Host "Chargement des variables d'environnement..." -ForegroundColor Yellow

# Charger les variables d'environnement depuis le fichier .env
$envFile = "vllm-configs/.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, [System.EnvironmentVariableTarget]::Process)
            Write-Host "Variable définie: $name" -ForegroundColor Gray
        }
    }
    Write-Host "Variables d'environnement chargées avec succès." -ForegroundColor Green
} else {
    Write-Host "Fichier .env non trouvé: $envFile" -ForegroundColor Red
    exit 1
}

# Afficher les variables clés pour vérification
Write-Host "`nVérification des variables clés:" -ForegroundColor Yellow
Write-Host "VLLM_PORT_MEDIUM: $env:VLLM_PORT_MEDIUM" -ForegroundColor Cyan
Write-Host "VLLM_PORT_MINI: $env:VLLM_PORT_MINI" -ForegroundColor Cyan
Write-Host "VLLM_PORT_MICRO: $env:VLLM_PORT_MICRO" -ForegroundColor Cyan
Write-Host "VLLM_API_KEY_MEDIUM: $env:VLLM_API_KEY_MEDIUM" -ForegroundColor Cyan
Write-Host "VLLM_API_KEY_MINI: $env:VLLM_API_KEY_MINI" -ForegroundColor Cyan
Write-Host "VLLM_API_KEY_MICRO: $env:VLLM_API_KEY_MICRO" -ForegroundColor Cyan

# Vérifier l'état des conteneurs
Write-Host "`nVérification de l'état des conteneurs..." -ForegroundColor Yellow
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | Select-String -Pattern "vllm-.*-qwen3"

# Exécuter le script de validation amélioré
Write-Host "`nExécution du script de validation amélioré..." -ForegroundColor Yellow
& ".\vllm-configs\scripts\validate-optimized-qwen3-improved.ps1"