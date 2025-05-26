# Script PowerShell pour déployer tous les services vLLM avec le préfixe commun myia-vllm

# Vérifier si l'utilisateur veut démarrer ou arrêter les services
param (
    [switch]$down
)

if ($down) {
    Write-Host "Arrêt des services vLLM..." -ForegroundColor Yellow
    docker compose -p myia-vllm `
        -f "vllm-configs/docker-compose/docker-compose-micro-qwen3.yml" `
        -f "vllm-configs/docker-compose/docker-compose-mini-qwen3.yml" `
        -f "vllm-configs/docker-compose/docker-compose-medium-qwen3.yml" `
        down
    Write-Host "Services vLLM arrêtés." -ForegroundColor Green
}
else {
    Write-Host "Démarrage des services vLLM..." -ForegroundColor Yellow
    docker compose -p myia-vllm `
        -f "vllm-configs/docker-compose/docker-compose-micro-qwen3.yml" `
        -f "vllm-configs/docker-compose/docker-compose-mini-qwen3.yml" `
        -f "vllm-configs/docker-compose/docker-compose-medium-qwen3.yml" `
        up -d
    Write-Host "Services vLLM démarrés." -ForegroundColor Green
    
    # Afficher l'état des services
    Write-Host "État des services:" -ForegroundColor Cyan
    docker compose -p myia-vllm ps
}