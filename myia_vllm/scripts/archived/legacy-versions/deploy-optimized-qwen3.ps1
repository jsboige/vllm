# Script de déploiement des configurations optimisées pour Qwen3
# Basé sur les configurations historiques de Qwen 2.5 QwQ

Write-Host "Déploiement des configurations optimisées pour Qwen3..." -ForegroundColor Green

# Définition des variables d'environnement
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

# Déploiement des nouveaux conteneurs avec les configurations optimisées
Write-Host "Déploiement du modèle MEDIUM (32B)..." -ForegroundColor Cyan
docker-compose -f vllm-configs/docker-compose/docker-compose-medium-qwen3-optimized.yml up -d

Write-Host "Déploiement du modèle MINI (8B)..." -ForegroundColor Cyan
docker-compose -f vllm-configs/docker-compose/docker-compose-mini-qwen3-optimized.yml up -d

Write-Host "Déploiement du modèle MICRO (1.7B)..." -ForegroundColor Cyan
docker-compose -f vllm-configs/docker-compose/docker-compose-micro-qwen3-optimized.yml up -d

# Vérification de l'état des conteneurs
Write-Host "Vérification de l'état des conteneurs..." -ForegroundColor Yellow
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

Write-Host "Déploiement terminé. Les modèles Qwen3 sont maintenant optimisés avec les configurations basées sur Qwen 2.5 QwQ." -ForegroundColor Green