# Script PowerShell pour déployer tous les containers Qwen3 avec vLLM

# Fonction pour afficher l'aide
function Show-Help {
    Write-Host "Usage: .\deploy-all-containers.ps1 [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Help                Afficher cette aide"
    Write-Host "  -Down                Arrêter les containers au lieu de les démarrer"
    Write-Host "  -WithAuth            Utiliser l'authentification Hugging Face (nécessite HF_TOKEN)"
    Write-Host "  -LocalModels         Utiliser des modèles téléchargés localement"
    Write-Host "  -ModelsPath PATH     Chemin vers les modèles locaux (avec -LocalModels)"
    Write-Host "  -Parser TYPE         Type de parser à utiliser (llama3_json ou qwen3)"
    Write-Host ""
    Write-Host "Exemples:"
    Write-Host "  .\deploy-all-containers.ps1                    # Déployer tous les containers avec configuration par défaut"
    Write-Host "  .\deploy-all-containers.ps1 -Down              # Arrêter tous les containers"
    Write-Host "  .\deploy-all-containers.ps1 -WithAuth          # Déployer avec authentification Hugging Face"
}

# Paramètres
param (
    [switch]$Help,
    [switch]$Down,
    [switch]$WithAuth,
    [switch]$LocalModels,
    [string]$ModelsPath = "",
    [string]$Parser = "llama3_json"
)

# Afficher l'aide si demandé
if ($Help) {
    Show-Help
    exit 0
}

# Variables par défaut
$Action = if ($Down) { "down" } else { "up -d" }

# Vérifier si l'authentification est configurée
if ($WithAuth) {
    if (-not $env:HF_TOKEN) {
        Write-Host "Erreur: La variable d'environnement HF_TOKEN n'est pas définie." -ForegroundColor Red
        Write-Host "Définissez-la avec: `$env:HF_TOKEN = 'votre_token_huggingface'" -ForegroundColor Red
        exit 1
    }
    Write-Host "Utilisation de l'authentification Hugging Face avec le token fourni." -ForegroundColor Green
}

# Vérifier si les modèles locaux sont configurés correctement
if ($LocalModels) {
    if (-not $ModelsPath) {
        Write-Host "Erreur: Le chemin vers les modèles locaux n'est pas spécifié." -ForegroundColor Red
        Write-Host "Utilisez -ModelsPath pour spécifier le chemin." -ForegroundColor Red
        exit 1
    }
    
    # Vérifier si le répertoire existe
    if (-not (Test-Path $ModelsPath -PathType Container)) {
        Write-Host "Erreur: Le répertoire des modèles '$ModelsPath' n'existe pas." -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Utilisation des modèles locaux depuis: $ModelsPath" -ForegroundColor Green
}

# Sélectionner les fichiers docker-compose en fonction du parser
if ($Parser -eq "qwen3") {
    $ComposeFiles = "-f vllm-configs/docker-compose/docker-compose-micro-qwen3-original-parser.yml -f vllm-configs/docker-compose/docker-compose-mini-qwen3-original-parser.yml -f vllm-configs/docker-compose/docker-compose-medium-qwen3-original-parser.yml"
    Write-Host "Utilisation du parser Qwen3 original" -ForegroundColor Yellow
}
else {
    $ComposeFiles = "-f vllm-configs/docker-compose/docker-compose-micro-qwen3.yml -f vllm-configs/docker-compose/docker-compose-mini-qwen3.yml -f vllm-configs/docker-compose/docker-compose-medium-qwen3.yml"
    Write-Host "Utilisation du parser llama3_json" -ForegroundColor Green
}

# Exécuter l'action demandée
if ($Down) {
    Write-Host "Arrêt des containers Qwen3..." -ForegroundColor Yellow
    Invoke-Expression "docker compose -p myia-vllm $ComposeFiles down"
    Write-Host "Containers arrêtés." -ForegroundColor Green
}
else {
    Write-Host "Démarrage des containers Qwen3..." -ForegroundColor Yellow
    
    # Ajouter l'authentification Hugging Face si demandée
    if ($WithAuth) {
        $env:HUGGING_FACE_HUB_TOKEN = $env:HF_TOKEN
    }
    
    # Démarrer les containers
    Invoke-Expression "docker compose -p myia-vllm $ComposeFiles up -d"
    
    Write-Host "Containers démarrés." -ForegroundColor Green
    
    # Afficher l'état des containers
    Write-Host "État des containers:" -ForegroundColor Cyan
    Invoke-Expression "docker compose -p myia-vllm ps"
    
    # Afficher les logs initiaux
    Write-Host "Logs des containers (premiers messages):" -ForegroundColor Cyan
    Write-Host "Logs de myia-vllm-micro-qwen3:" -ForegroundColor Magenta
    Invoke-Expression "docker logs myia-vllm-micro-qwen3 --tail 20"
    
    Write-Host "Logs de myia-vllm-mini-qwen3:" -ForegroundColor Magenta
    Invoke-Expression "docker logs myia-vllm-mini-qwen3 --tail 20"
    
    Write-Host "Logs de myia-vllm-medium-qwen3:" -ForegroundColor Magenta
    Invoke-Expression "docker logs myia-vllm-medium-qwen3 --tail 20"
}