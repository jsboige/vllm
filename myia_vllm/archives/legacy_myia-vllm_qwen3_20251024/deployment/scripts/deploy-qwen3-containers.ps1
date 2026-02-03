# Script de déploiement automatisé des containers Qwen3
# Ce script vérifie les prérequis, configure les variables d'environnement et déploie les containers

# Fonction pour afficher les messages avec des couleurs
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    else {
        $input | Write-Output
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

# Fonction pour vérifier si un fichier existe
function Test-FileExists($path) {
    if (-not (Test-Path $path)) {
        Write-ColorOutput Red "Erreur: Le fichier $path n'existe pas."
        return $false
    }
    return $true
}

# Fonction pour vérifier si Docker est installé
function Test-DockerInstalled {
    try {
        $dockerVersion = docker --version
        Write-ColorOutput Green "Docker est installé: $dockerVersion"
        return $true
    }
    catch {
        Write-ColorOutput Red "Erreur: Docker n'est pas installé ou n'est pas accessible."
        return $false
    }
}

# Fonction pour vérifier si Docker Compose est installé
function Test-DockerComposeInstalled {
    try {
        $dockerComposeVersion = docker-compose --version
        Write-ColorOutput Green "Docker Compose est installé: $dockerComposeVersion"
        return $true
    }
    catch {
        Write-ColorOutput Red "Erreur: Docker Compose n'est pas installé ou n'est pas accessible."
        return $false
    }
}

# Fonction pour vérifier si le token Hugging Face est configuré
function Test-HuggingFaceToken {
    $envFile = "myia-vllm/qwen3/huggingface.env"
    
    if (-not (Test-Path $envFile)) {
        Write-ColorOutput Yellow "Avertissement: Le fichier $envFile n'existe pas."
        
        # Créer le fichier huggingface.env à partir de l'exemple
        if (Test-Path "myia-vllm/qwen3/huggingface.env.example") {
            Copy-Item "myia-vllm/qwen3/huggingface.env.example" $envFile
            Write-ColorOutput Yellow "Le fichier $envFile a été créé à partir de l'exemple."
        }
        else {
            Write-ColorOutput Red "Erreur: Le fichier myia-vllm/qwen3/huggingface.env.example n'existe pas."
            return $false
        }
    }
    
    $content = Get-Content $envFile
    $tokenLine = $content | Where-Object { $_ -match "HUGGING_FACE_HUB_TOKEN=" }
    
    if (-not $tokenLine) {
        Write-ColorOutput Red "Erreur: La variable HUGGING_FACE_HUB_TOKEN n'est pas définie dans $envFile."
        return $false
    }
    
    if ($tokenLine -match "HUGGING_FACE_HUB_TOKEN=YOUR_TOKEN_HERE") {
        Write-ColorOutput Red "Erreur: Le token Hugging Face n'est pas configuré dans $envFile."
        return $false
    }
    
    Write-ColorOutput Green "Le token Hugging Face est configuré."
    return $true
}

# Fonction pour déployer un container
function Deploy-Container($name, $composePath) {
    Write-ColorOutput Cyan "Déploiement du container $name..."
    
    try {
        # Vérifier si le fichier docker-compose existe
        if (-not (Test-Path $composePath)) {
            Write-ColorOutput Red "Erreur: Le fichier $composePath n'existe pas."
            return $false
        }
        
        # Déployer le container
        $currentDir = Get-Location
        Set-Location (Split-Path $composePath)
        $fileName = Split-Path $composePath -Leaf
        
        docker-compose -f $fileName up -d
        
        if ($LASTEXITCODE -ne 0) {
            Write-ColorOutput Red "Erreur lors du déploiement du container $name."
            Set-Location $currentDir
            return $false
        }
        
        Write-ColorOutput Green "Le container $name a été déployé avec succès."
        Set-Location $currentDir
        return $true
    }
    catch {
        Write-ColorOutput Red ("Erreur lors du déploiement du container " + $name + ": " + $_)
        Set-Location $currentDir
        return $false
    }
}

# Fonction principale
function Main {
    Write-ColorOutput Cyan "=== Déploiement des containers Qwen3 ==="
    
    # Vérifier les prérequis
    $prerequisites = $true
    
    if (-not (Test-DockerInstalled)) {
        $prerequisites = $false
    }
    
    if (-not (Test-DockerComposeInstalled)) {
        $prerequisites = $false
    }
    
    if (-not (Test-HuggingFaceToken)) {
        $prerequisites = $false
    }
    
    if (-not $prerequisites) {
        Write-ColorOutput Red "Erreur: Certains prérequis ne sont pas satisfaits. Veuillez corriger les erreurs ci-dessus."
        return
    }
    
    # Vérifier les fichiers docker-compose
    $composeFiles = @(
        "myia-vllm/qwen3/deployment/docker/docker-compose-micro-qwen3.yml",
        "myia-vllm/qwen3/deployment/docker/docker-compose-mini-qwen3.yml",
        "myia-vllm/qwen3/deployment/docker/docker-compose-medium-qwen3.yml"
    )
    
    foreach ($file in $composeFiles) {
        if (-not (Test-FileExists $file)) {
            Write-ColorOutput Red "Erreur: Le fichier $file n'existe pas."
            return
        }
    }
    
    # Vérifier le script de démarrage
    if (-not (Test-FileExists "myia-vllm/qwen3/deployment/docker/start-with-qwen3-parser.sh")) {
        Write-ColorOutput Red "Erreur: Le script de démarrage myia-vllm/qwen3/deployment/docker/start-with-qwen3-parser.sh n'existe pas."
        return
    }
    
    # Déployer les containers
    $deploymentSuccess = $true
    
    Write-ColorOutput Cyan "`nDéploiement des containers..."
    
    # Déployer le container Micro
    if (-not (Deploy-Container "Micro" $composeFiles[0])) {
        $deploymentSuccess = $false
    }
    
    # Déployer le container Mini
    if (-not (Deploy-Container "Mini" $composeFiles[1])) {
        $deploymentSuccess = $false
    }
    
    # Déployer le container Medium
    if (-not (Deploy-Container "Medium" $composeFiles[2])) {
        $deploymentSuccess = $false
    }
    
    # Afficher le résultat
    if ($deploymentSuccess) {
        Write-ColorOutput Green "`nTous les containers ont été déployés avec succès."
        Write-ColorOutput Yellow "`nNote: Les configurations ont été mises à jour pour utiliser:"
        Write-ColorOutput Yellow "- Les modèles Qwen3 AWQ pour résoudre les problèmes d'accès aux versions Instruct-AWQ"
        Write-ColorOutput Yellow "- Le parser llama3_json au lieu de qwen3 pour résoudre les problèmes de compatibilité"
        Write-ColorOutput Yellow "Voir myia-vllm/qwen3/deployment/logs/DEPLOYMENT-RESULTS.md pour plus de détails."
        Write-ColorOutput Cyan "`nPour tester les containers, utilisez les commandes suivantes:"
        Write-ColorOutput White "curl -X POST http://localhost:8000/v1/chat/completions -H `"Content-Type: application/json`" -d @myia-vllm/qwen3/test_tool_calling/test-tool-request.json"
        Write-ColorOutput White "curl -X POST http://localhost:5001/v1/chat/completions -H `"Content-Type: application/json`" -d @myia-vllm/qwen3/test_tool_calling/test-tool-request.json"
        Write-ColorOutput White "curl -X POST http://localhost:5002/v1/chat/completions -H `"Content-Type: application/json`" -d @myia-vllm/qwen3/test_tool_calling/test-tool-request.json"
    }
    else {
        Write-ColorOutput Red "`nCertains containers n'ont pas pu être déployés. Veuillez vérifier les erreurs ci-dessus."
    }
}

# Exécuter la fonction principale
Main