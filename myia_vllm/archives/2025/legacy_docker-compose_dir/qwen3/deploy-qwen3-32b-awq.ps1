# Script PowerShell pour déployer le modèle Qwen3 32B AWQ

# Définir les variables d'environnement
$env:CUDA_VISIBLE_DEVICES_MEDIUM = "0"
$env:GPU_MEMORY_UTILIZATION_MEDIUM = "0.9"
$env:VLLM_PORT_MEDIUM = "5002"
$env:VLLM_API_KEY_MEDIUM = "KEY_REMOVED_FOR_SECURITY"

# Afficher les informations de configuration
Write-Host "Configuration du déploiement Qwen3 32B AWQ:"
Write-Host "- GPUs: $env:CUDA_VISIBLE_DEVICES_MEDIUM"
Write-Host "- Utilisation mémoire GPU: $env:GPU_MEMORY_UTILIZATION_MEDIUM"
Write-Host "- Port: $env:VLLM_PORT_MEDIUM"

# Vérifier si Docker est en cours d'exécution
try {
    docker info | Out-Null
} catch {
    Write-Host "Erreur: Docker n'est pas en cours d'exécution. Veuillez démarrer Docker et réessayer." -ForegroundColor Red
    exit 1
}

# Vérifier si les GPUs sont disponibles
try {
    nvidia-smi | Out-Null
} catch {
    Write-Host "Erreur: Impossible d'accéder aux GPUs NVIDIA. Vérifiez que les pilotes NVIDIA sont correctement installés." -ForegroundColor Red
    exit 1
}

# Déployer le conteneur
Write-Host "Déploiement du modèle Qwen3 32B AWQ..." -ForegroundColor Green
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootPath = Split-Path -Parent $scriptPath
Set-Location $rootPath # Remonter au répertoire docker-compose

docker-compose -f qwen3/docker-compose-qwen3-32b-awq.yml up -d

# Vérifier le statut du déploiement
if ($LASTEXITCODE -eq 0) {
    Write-Host "Le modèle Qwen3 32B AWQ a été déployé avec succès." -ForegroundColor Green
    Write-Host "API accessible à: http://localhost:$env:VLLM_PORT_MEDIUM/v1"
    Write-Host "Pour vérifier les logs: docker logs myia-vllm_vllm-medium-qwen3"
} else {
    Write-Host "Erreur lors du déploiement du modèle Qwen3 32B AWQ." -ForegroundColor Red
}