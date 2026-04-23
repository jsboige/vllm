# Script de déploiement unifié pour les modèles Qwen3 optimisés
# Ce script configure et déploie les trois modèles Qwen3 (32B, 8B et 1.7B)
# avec des vérifications de santé et des mécanismes de récupération

# Définition des couleurs pour les messages
$Green = [System.ConsoleColor]::Green
$Yellow = [System.ConsoleColor]::Yellow
$Red = [System.ConsoleColor]::Red
$Cyan = [System.ConsoleColor]::Cyan

# Fonction pour afficher des messages avec couleur
function Write-ColorMessage {
    param (
        [string]$Message,
        [System.ConsoleColor]$Color = [System.ConsoleColor]::White
    )
    Write-Host $Message -ForegroundColor $Color
}

# Fonction pour vérifier si Docker est en cours d'exécution
function Test-DockerRunning {
    try {
        $dockerStatus = docker info 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-ColorMessage "Docker n'est pas en cours d'exécution. Veuillez démarrer Docker et réessayer." $Red
            return $false
        }
        return $true
    }
    catch {
        Write-ColorMessage "Erreur lors de la vérification de Docker: $_" $Red
        return $false
    }
}

# Fonction pour vérifier si les GPUs sont disponibles
function Test-GPUsAvailable {
    try {
        $gpuInfo = docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi
        if ($LASTEXITCODE -ne 0) {
            Write-ColorMessage "Les GPUs ne sont pas disponibles pour Docker. Vérifiez votre installation NVIDIA et Docker." $Red
            return $false
        }
        Write-ColorMessage "GPUs détectées et disponibles pour Docker:" $Green
        Write-Host $gpuInfo
        return $true
    }
    catch {
        Write-ColorMessage "Erreur lors de la vérification des GPUs: $_" $Red
        return $false
    }
}

# Fonction pour vérifier la santé d'un conteneur
function Test-ContainerHealth {
    param (
        [string]$ContainerName,
        [int]$MaxRetries = 10,
        [int]$RetryInterval = 30
    )
    
    Write-ColorMessage "Vérification de la santé du conteneur $ContainerName..." $Cyan
    
    for ($i = 1; $i -le $MaxRetries; $i++) {
        $health = docker inspect --format='{{.State.Health.Status}}' $ContainerName 2>&1
        
        if ($LASTEXITCODE -eq 0 -and $health -eq "healthy") {
            Write-ColorMessage "Le conteneur $ContainerName est en bonne santé!" $Green
            return $true
        }
        
        if ($i -lt $MaxRetries) {
            Write-ColorMessage "Attente de la mise en service du conteneur $ContainerName (tentative $i/$MaxRetries)..." $Yellow
            Start-Sleep -Seconds $RetryInterval
        }
    }
    
    Write-ColorMessage "Le conteneur $ContainerName n'a pas atteint un état de santé après $MaxRetries tentatives." $Red
    return $false
}

# Fonction pour démarrer un modèle
function Start-QwenModel {
    param (
        [string]$ModelPath,
        [string]$ModelName,
        [string]$ContainerName
    )
    
    Write-ColorMessage "Démarrage du modèle $ModelName..." $Cyan
    
    try {
        Set-Location -Path "$PSScriptRoot/$ModelPath"
        docker-compose up -d
        
        if ($LASTEXITCODE -ne 0) {
            Write-ColorMessage "Erreur lors du démarrage du modèle $ModelName." $Red
            return $false
        }
        
        # Vérification de la santé du conteneur
        $healthy = Test-ContainerHealth -ContainerName $ContainerName -MaxRetries 15 -RetryInterval 30
        
        if (-not $healthy) {
            Write-ColorMessage "Le modèle $ModelName n'a pas démarré correctement. Tentative de redémarrage..." $Yellow
            docker-compose restart
            $healthy = Test-ContainerHealth -ContainerName $ContainerName -MaxRetries 5 -RetryInterval 30
            
            if (-not $healthy) {
                Write-ColorMessage "Échec du redémarrage du modèle $ModelName." $Red
                return $false
            }
        }
        
        Write-ColorMessage "Le modèle $ModelName a démarré avec succès!" $Green
        return $true
    }
    catch {
        Write-ColorMessage "Erreur lors du demarrage du modele $ModelName" $Red
        Write-ColorMessage $_.Exception.Message $Red
        return $false
    }
    finally {
        Set-Location -Path $PSScriptRoot
    }
}

# Fonction pour arrêter un modèle
function Stop-QwenModel {
    param (
        [string]$ModelPath,
        [string]$ModelName
    )
    
    Write-ColorMessage "Arrêt du modèle $ModelName..." $Cyan
    
    try {
        Set-Location -Path "$PSScriptRoot/$ModelPath"
        docker-compose down
        
        if ($LASTEXITCODE -ne 0) {
            Write-ColorMessage "Erreur lors de l'arrêt du modèle $ModelName." $Red
            return $false
        }
        
        Write-ColorMessage "Le modèle $ModelName a été arrêté avec succès." $Green
        return $true
    }
    catch {
        Write-ColorMessage "Erreur lors de l'arret du modele $ModelName" $Red
        Write-ColorMessage $_.Exception.Message $Red
        return $false
    }
    finally {
        Set-Location -Path $PSScriptRoot
    }
}

# Fonction pour vérifier l'état des modèles
function Get-ModelsStatus {
    Write-ColorMessage "État des modèles Qwen3:" $Cyan
    
    $containers = @(
        "myia-vllm_vllm-qwen3-32b-awq",
        "myia-vllm_vllm-qwen3-8b-awq",
        "myia-vllm_vllm-qwen3-1.7b-awq"
    )
    
    foreach ($container in $containers) {
        $status = docker ps -a --filter "name=$container" --format "{{.Status}}" 2>&1
        
        if ($status) {
            Write-ColorMessage "$container : $status" $Green
        }
        else {
            Write-ColorMessage "$container : Non trouvé" $Yellow
        }
    }
}

# Fonction principale
function Start-QwenDeployment {
    param (
        [switch]$All,
        [switch]$Model32B,
        [switch]$Model8B,
        [switch]$Model1_7B,
        [switch]$Stop
    )
    
    # Vérification des prérequis
    if (-not (Test-DockerRunning)) {
        return
    }
    
    if (-not (Test-GPUsAvailable)) {
        return
    }
    
    # Arrêt des modèles si demandé
    if ($Stop) {
        if ($All -or $Model32B) {
            Stop-QwenModel -ModelPath "32b-awq" -ModelName "Qwen3 32B AWQ"
        }
        
        if ($All -or $Model8B) {
            Stop-QwenModel -ModelPath "8b-awq" -ModelName "Qwen3 8B AWQ"
        }
        
        if ($All -or $Model1_7B) {
            Stop-QwenModel -ModelPath "1.7b-awq" -ModelName "Qwen3 1.7B AWQ"
        }
        
        Get-ModelsStatus
        return
    }
    
    # Démarrage des modèles
    $success = $true
    
    if ($All -or $Model32B) {
        $result = Start-QwenModel -ModelPath "32b-awq" -ModelName "Qwen3 32B AWQ" -ContainerName "myia-vllm_vllm-qwen3-32b-awq"
        $success = $success -and $result
    }
    
    if ($All -or $Model8B) {
        $result = Start-QwenModel -ModelPath "8b-awq" -ModelName "Qwen3 8B AWQ" -ContainerName "myia-vllm_vllm-qwen3-8b-awq"
        $success = $success -and $result
    }
    
    if ($All -or $Model1_7B) {
        $result = Start-QwenModel -ModelPath "1.7b-awq" -ModelName "Qwen3 1.7B AWQ" -ContainerName "myia-vllm_vllm-qwen3-1.7b-awq"
        $success = $success -and $result
    }
    
    # Affichage de l'état final
    Get-ModelsStatus
    
    if ($success) {
        Write-ColorMessage "Tous les modèles demandés ont été démarrés avec succès!" $Green
    }
    else {
        Write-ColorMessage "Certains modèles n'ont pas pu être démarrés correctement. Vérifiez les logs pour plus de détails." $Yellow
    }
}

# Affichage de l'aide si aucun paramètre n'est fourni
if ($args.Count -eq 0) {
    Write-ColorMessage "Script de déploiement des modèles Qwen3" $Cyan
    Write-ColorMessage "Usage:" $Cyan
    Write-ColorMessage "  .\deploy-qwen3-models.ps1 -All                # Démarrer tous les modèles" $Yellow
    Write-ColorMessage "  .\deploy-qwen3-models.ps1 -Model32B           # Démarrer uniquement le modèle 32B" $Yellow
    Write-ColorMessage "  .\deploy-qwen3-models.ps1 -Model8B            # Démarrer uniquement le modèle 8B" $Yellow
    Write-ColorMessage "  .\deploy-qwen3-models.ps1 -Model1_7B          # Démarrer uniquement le modèle 1.7B" $Yellow
    Write-ColorMessage "  .\deploy-qwen3-models.ps1 -Model8B -Model1_7B # Démarrer les modèles 8B et 1.7B" $Yellow
    Write-ColorMessage "  .\deploy-qwen3-models.ps1 -All -Stop          # Arrêter tous les modèles" $Yellow
    Write-ColorMessage "  .\deploy-qwen3-models.ps1 -Status             # Afficher l'état des modèles" $Yellow
    exit
}

# Traitement des paramètres
if ($args -contains "-All") {
    $All = $true
}

if ($args -contains "-Model32B") {
    $Model32B = $true
}

if ($args -contains "-Model8B") {
    $Model8B = $true
}

if ($args -contains "-Model1_7B") {
    $Model1_7B = $true
}

if ($args -contains "-Stop") {
    $Stop = $true
}

if ($args -contains "-Status") {
    Get-ModelsStatus
    exit
}

# Démarrage du déploiement
Start-QwenDeployment -All:$All -Model32B:$Model32B -Model8B:$Model8B -Model1_7B:$Model1_7B -Stop:$Stop