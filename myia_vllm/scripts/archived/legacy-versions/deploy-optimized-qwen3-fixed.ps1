# Script de déploiement des configurations optimisées pour Qwen3
# Basé sur les configurations historiques de Qwen 2.5 QwQ

Write-Host "Déploiement des configurations optimisées pour Qwen3..." -ForegroundColor Green

# Chargement des variables d'environnement depuis le fichier .env
Write-Host "Chargement des variables d'environnement..." -ForegroundColor Yellow
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

# Définition des variables d'environnement pour les GPUs
$env:CUDA_VISIBLE_DEVICES_MEDIUM = "0,1"
$env:CUDA_VISIBLE_DEVICES_MINI = "2"
$env:CUDA_VISIBLE_DEVICES_MICRO = "2"

$env:GPU_MEMORY_UTILIZATION_MEDIUM = "0.99"
$env:GPU_MEMORY_UTILIZATION_MINI = "0.99"
$env:GPU_MEMORY_UTILIZATION_MICRO = "0.99"

# Arrêt des conteneurs existants
Write-Host "Arrêt des conteneurs existants..." -ForegroundColor Yellow
docker-compose -f vllm-configs/docker-compose/docker-compose-medium-qwen3.yml down
docker-compose -f vllm-configs/docker-compose/docker-compose-mini-qwen3.yml down
docker-compose -f vllm-configs/docker-compose/docker-compose-micro-qwen3.yml down

# Création d'un fichier .env temporaire pour Docker Compose
$tempEnvFile = "vllm-configs/docker-compose/.env.temp"
@"
HUGGING_FACE_HUB_TOKEN=$env:HUGGING_FACE_HUB_TOKEN
VLLM_API_KEY_MEDIUM=$env:VLLM_API_KEY_MEDIUM
VLLM_API_KEY_MINI=$env:VLLM_API_KEY_MINI
VLLM_API_KEY_MICRO=$env:VLLM_API_KEY_MICRO
VLLM_PORT_MEDIUM=$env:VLLM_PORT_MEDIUM
VLLM_PORT_MINI=$env:VLLM_PORT_MINI
VLLM_PORT_MICRO=$env:VLLM_PORT_MICRO
CUDA_VISIBLE_DEVICES_MEDIUM=$env:CUDA_VISIBLE_DEVICES_MEDIUM
CUDA_VISIBLE_DEVICES_MINI=$env:CUDA_VISIBLE_DEVICES_MINI
CUDA_VISIBLE_DEVICES_MICRO=$env:CUDA_VISIBLE_DEVICES_MICRO
GPU_MEMORY_UTILIZATION_MEDIUM=$env:GPU_MEMORY_UTILIZATION_MEDIUM
GPU_MEMORY_UTILIZATION_MINI=$env:GPU_MEMORY_UTILIZATION_MINI
GPU_MEMORY_UTILIZATION_MICRO=$env:GPU_MEMORY_UTILIZATION_MICRO
TZ=$env:TZ
VLLM_PORT=$env:VLLM_PORT_MEDIUM
"@ | Out-File -FilePath $tempEnvFile -Encoding utf8

# Déploiement des nouveaux conteneurs avec les configurations optimisées
Write-Host "Déploiement du modèle MEDIUM (32B)..." -ForegroundColor Cyan
docker-compose --env-file $tempEnvFile -f vllm-configs/docker-compose/docker-compose-medium-qwen3-optimized.yml up -d

# Mise à jour du fichier .env temporaire pour le modèle MINI
@"
HUGGING_FACE_HUB_TOKEN=$env:HUGGING_FACE_HUB_TOKEN
VLLM_API_KEY_MEDIUM=$env:VLLM_API_KEY_MEDIUM
VLLM_API_KEY_MINI=$env:VLLM_API_KEY_MINI
VLLM_API_KEY_MICRO=$env:VLLM_API_KEY_MICRO
VLLM_PORT_MEDIUM=$env:VLLM_PORT_MEDIUM
VLLM_PORT_MINI=$env:VLLM_PORT_MINI
VLLM_PORT_MICRO=$env:VLLM_PORT_MICRO
CUDA_VISIBLE_DEVICES_MEDIUM=$env:CUDA_VISIBLE_DEVICES_MEDIUM
CUDA_VISIBLE_DEVICES_MINI=$env:CUDA_VISIBLE_DEVICES_MINI
CUDA_VISIBLE_DEVICES_MICRO=$env:CUDA_VISIBLE_DEVICES_MICRO
GPU_MEMORY_UTILIZATION_MEDIUM=$env:GPU_MEMORY_UTILIZATION_MEDIUM
GPU_MEMORY_UTILIZATION_MINI=$env:GPU_MEMORY_UTILIZATION_MINI
GPU_MEMORY_UTILIZATION_MICRO=$env:GPU_MEMORY_UTILIZATION_MICRO
TZ=$env:TZ
VLLM_PORT=$env:VLLM_PORT_MINI
"@ | Out-File -FilePath $tempEnvFile -Encoding utf8

Write-Host "Déploiement du modèle MINI (8B)..." -ForegroundColor Cyan
docker-compose --env-file $tempEnvFile -f vllm-configs/docker-compose/docker-compose-mini-qwen3-optimized.yml up -d

# Mise à jour du fichier .env temporaire pour le modèle MICRO
@"
HUGGING_FACE_HUB_TOKEN=$env:HUGGING_FACE_HUB_TOKEN
VLLM_API_KEY_MEDIUM=$env:VLLM_API_KEY_MEDIUM
VLLM_API_KEY_MINI=$env:VLLM_API_KEY_MINI
VLLM_API_KEY_MICRO=$env:VLLM_API_KEY_MICRO
VLLM_PORT_MEDIUM=$env:VLLM_PORT_MEDIUM
VLLM_PORT_MINI=$env:VLLM_PORT_MINI
VLLM_PORT_MICRO=$env:VLLM_PORT_MICRO
CUDA_VISIBLE_DEVICES_MEDIUM=$env:CUDA_VISIBLE_DEVICES_MEDIUM
CUDA_VISIBLE_DEVICES_MINI=$env:CUDA_VISIBLE_DEVICES_MINI
CUDA_VISIBLE_DEVICES_MICRO=$env:CUDA_VISIBLE_DEVICES_MICRO
GPU_MEMORY_UTILIZATION_MEDIUM=$env:GPU_MEMORY_UTILIZATION_MEDIUM
GPU_MEMORY_UTILIZATION_MINI=$env:GPU_MEMORY_UTILIZATION_MINI
GPU_MEMORY_UTILIZATION_MICRO=$env:GPU_MEMORY_UTILIZATION_MICRO
TZ=$env:TZ
VLLM_PORT=$env:VLLM_PORT_MICRO
"@ | Out-File -FilePath $tempEnvFile -Encoding utf8

Write-Host "Déploiement du modèle MICRO (1.7B)..." -ForegroundColor Cyan
docker-compose --env-file $tempEnvFile -f vllm-configs/docker-compose/docker-compose-micro-qwen3-optimized.yml up -d

# Suppression du fichier .env temporaire
Remove-Item -Path $tempEnvFile -Force

# Vérification de l'état des conteneurs
Write-Host "Vérification de l'état des conteneurs..." -ForegroundColor Yellow
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

Write-Host "Déploiement terminé. Les modèles Qwen3 sont maintenant optimisés avec les configurations basées sur Qwen 2.5 QwQ." -ForegroundColor Green