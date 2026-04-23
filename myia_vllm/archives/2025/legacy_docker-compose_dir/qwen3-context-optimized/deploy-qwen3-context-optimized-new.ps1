# Script de déploiement pour les modèles Qwen3 avec contexte optimisé
# Ce script configure et déploie les modèles Qwen3 (32B, 8B et Micro) avec des tailles de contexte optimisées

# Définition des couleurs pour les messages
$Green = [System.ConsoleColor]::Green
$Yellow = [System.ConsoleColor]::Yellow
$Red = [System.ConsoleColor]::Red
$Cyan = [System.ConsoleColor]::Cyan
$Magenta = [System.ConsoleColor]::Magenta

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

# Fonction pour analyser les logs d'un conteneur
function Test-ContainerLogs {
    param (
        [string]$ContainerName,
        [int]$MaxRetries = 10,
        [int]$RetryInterval = 15,
        [string]$ModelSize = "standard" # "micro", "8b", "32b"
    )
    
    Write-ColorMessage "Analyse des logs du conteneur ${ContainerName}..." $Cyan
    
    # Définir les messages de succès et d'erreur à rechercher dans les logs
    $successPatterns = @(
        "Server is ready",
        "Application startup complete",
        "Running on http://0.0.0.0:8000"
    )
    
    $errorPatterns = @(
        "Error:",
        "Exception:",
        "Failed to load model",
        "CUDA out of memory",
        "RuntimeError:",
        "Aborted"
    )
    
    # Adapter le nombre de tentatives et l'intervalle en fonction de la taille du modèle
    switch ($ModelSize) {
        "micro" {
            $MaxRetries = [Math]::Max($MaxRetries, 12)
            $RetryInterval = 15
        }
        "8b" {
            $MaxRetries = [Math]::Max($MaxRetries, 20)
            $RetryInterval = 20
        }
        "32b" {
            $MaxRetries = [Math]::Max($MaxRetries, 30)
            $RetryInterval = 30
        }
    }
    
    $totalTime = $MaxRetries * $RetryInterval
    Write-ColorMessage "Surveillance des logs pendant ${totalTime} secondes maximum..." $Yellow
    
    $restartCount = 0
    $previousLogLength = 0
    $consecutiveIdenticalLogs = 0
    $lastLogContent = ""
    
    for ($i = 1; $i -le $MaxRetries; $i++) {
        # Vérifier si le conteneur existe et est en cours d'exécution
        $containerStatus = docker ps -a --filter "name=$ContainerName" --format "{{.Status}}" 2>&1
        if (-not $containerStatus -or $containerStatus -like "*Exited*") {
            Write-ColorMessage "Le conteneur $ContainerName n'est pas en cours d'exécution." $Red
            return $false
        }
        
        # Vérifier les redémarrages
        $containerInfo = docker inspect $ContainerName --format "{{.RestartCount}}" 2>&1
        if ($containerInfo -and $containerInfo -match "^\d+$") {
            $currentRestarts = [int]$containerInfo
            if ($i -gt 1 -and $currentRestarts -gt $restartCount) {
                Write-ColorMessage "Détection de redémarrage du conteneur $ContainerName (redémarrages: $currentRestarts)" $Red
                $restartCount = $currentRestarts
                
                # Si plus de 3 redémarrages, considérer comme un échec
                if ($restartCount -gt 3) {
                    Write-ColorMessage "Trop de redémarrages détectés pour $ContainerName. Vérifiez les logs pour plus de détails." $Red
                    return $false
                }
            }
            $restartCount = $currentRestarts
        }
        
        # Récupérer les logs du conteneur
        $logs = docker logs $ContainerName --tail 50 2>&1
        
        # Vérifier si les logs sont identiques à la dernière vérification (signe potentiel de blocage)
        $currentLogContent = $logs -join "`n"
        if ($currentLogContent -eq $lastLogContent -and $currentLogContent) {
            $consecutiveIdenticalLogs++
            if ($consecutiveIdenticalLogs -ge 5) {
                Write-ColorMessage "Les logs n'évoluent plus depuis plusieurs vérifications. Possible blocage du conteneur." $Yellow
            }
        } else {
            $consecutiveIdenticalLogs = 0
            $lastLogContent = $currentLogContent
        }
        
        # Vérifier les messages de succès
        foreach ($pattern in $successPatterns) {
            if ($logs -match $pattern) {
                Write-ColorMessage "Succès détecté dans les logs: '$pattern'" $Green
                
                # Vérifier également l'état de santé du conteneur
                $health = docker inspect --format='{{.State.Health.Status}}' $ContainerName 2>&1
                if ($health -eq "healthy") {
                    Write-ColorMessage "Le conteneur ${ContainerName} est en bonne santé et les logs indiquent un démarrage réussi!" $Green
                    return $true
                } else {
                    Write-ColorMessage "Les logs indiquent un démarrage réussi, mais l'état de santé est: $health. Attente de la mise à jour de l'état..." $Yellow
                }
            }
        }
        
        # Vérifier les messages d'erreur
        $errorFound = $false
        foreach ($pattern in $errorPatterns) {
            $errorLines = $logs | Select-String -Pattern $pattern
            if ($errorLines) {
                Write-ColorMessage "Erreur détectée dans les logs:" $Red
                foreach ($line in $errorLines) {
                    Write-ColorMessage "  $line" $Red
                }
                $errorFound = $true
            }
        }
        
        # Vérifier l'état de santé du conteneur
        $health = docker inspect --format='{{.State.Health.Status}}' $ContainerName 2>&1
        
        if ($LASTEXITCODE -eq 0 -and $health -eq "healthy") {
            Write-ColorMessage "Le conteneur $ContainerName est en bonne santé!" $Green
            return $true
        }
        
        # Afficher la progression
        if ($i -lt $MaxRetries) {
            Write-ColorMessage "Attente de la mise en service du conteneur ${ContainerName} (tentative ${i}/${MaxRetries}, état: ${health})..." $Yellow
            
            # Afficher les dernières lignes de log pour le diagnostic
            if ($logs) {
                $newLogs = $logs | Select-Object -Skip $previousLogLength
                if ($newLogs) {
                    Write-ColorMessage "Dernières lignes de log:" $Magenta
                    $newLogs | Select-Object -Last 5 | ForEach-Object { Write-Host "  $_" }
                }
                $previousLogLength = $logs.Count
            }
            
            Start-Sleep -Seconds $RetryInterval
        }
    }
    
    Write-ColorMessage "Le conteneur $ContainerName n'a pas atteint un état de santé après $MaxRetries tentatives." $Red
    
    # Afficher les derniers logs pour aider au diagnostic
    Write-ColorMessage "Derniers logs du conteneur pour diagnostic:" $Magenta
    docker logs $ContainerName --tail 20 2>&1 | ForEach-Object { Write-Host "  $_" }
    
    return $false
}

# Fonction pour démarrer un modèle
function Start-QwenModel {
    param (
        [string]$ModelPath,
        [string]$ModelName,
        [string]$ContainerName,
        [string]$ModelSize = "standard" # "micro", "8b", "32b"
    )
    
    Write-ColorMessage "Démarrage du modèle ${ModelName}..." $Cyan
    
    try {
        Set-Location -Path "$PSScriptRoot/$ModelPath"
        docker compose -p myia-vllm up -d
        
        if ($LASTEXITCODE -ne 0) {
            Write-ColorMessage "Erreur lors du démarrage du modèle $ModelName." $Red
            return $false
        }
        
        # Attendre un peu pour que le conteneur commence à démarrer
        Start-Sleep -Seconds 5
        
        # Vérification de la santé du conteneur et analyse des logs
        $maxRetries = switch ($ModelSize) {
            "micro" { 12 }
            "8b" { 20 }
            "32b" { 30 }
            default { 15 }
        }
        
        $retryInterval = switch ($ModelSize) {
            "micro" { 15 }
            "8b" { 20 }
            "32b" { 30 }
            default { 20 }
        }
        
        $healthy = Test-ContainerLogs -ContainerName $ContainerName -MaxRetries $maxRetries -RetryInterval $retryInterval -ModelSize $ModelSize
        
        if (-not $healthy) {
            Write-ColorMessage "Le modèle $ModelName n'a pas démarré correctement. Tentative de redémarrage..." $Yellow
            docker compose -p myia-vllm restart
            Start-Sleep -Seconds 10
            $healthy = Test-ContainerLogs -ContainerName $ContainerName -MaxRetries ($maxRetries / 2) -RetryInterval $retryInterval -ModelSize $ModelSize
            
            if (-not $healthy) {
                Write-ColorMessage "Échec du redémarrage du modèle $ModelName." $Red
                
                # Afficher des informations supplémentaires pour le diagnostic
                Write-ColorMessage "Informations de diagnostic pour ${ContainerName}:" $Magenta
                docker inspect $ContainerName | Select-String -Pattern "Health|Error|Status|RestartCount" | ForEach-Object { Write-Host "  $_" }
                
                return $false
            }
        }
        
        Write-ColorMessage "Le modèle ${ModelName} a démarré avec succès!" $Green
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
    
    Write-ColorMessage "Arrêt du modèle ${ModelName}..." $Cyan
    
    try {
        Set-Location -Path "$PSScriptRoot/$ModelPath"
        docker compose -p myia-vllm down
        
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

# Fonction pour vérifier l'état des modèles avec des informations détaillées
function Get-ModelsStatus {
    Write-ColorMessage "État des modèles Qwen3 avec contexte optimisé:" $Cyan
    
    $containers = @(
        @{Name="myia-vllm_vllm-qwen3-32b-awq"; Model="Qwen3 32B AWQ"},
        @{Name="myia-vllm_vllm-qwen3-8b-awq"; Model="Qwen3 8B AWQ"},
        @{Name="myia-vllm_vllm-qwen3-micro-awq"; Model="Qwen3 Micro AWQ"}
    )
    
    foreach ($container in $containers) {
        $containerName = $container.Name
        $modelName = $container.Model
        
        $status = docker ps -a --filter "name=$containerName" --format "{{.Status}}" 2>&1
        $health = docker inspect --format='{{.State.Health.Status}}' $containerName 2>&1
        $restarts = docker inspect --format='{{.RestartCount}}' $containerName 2>&1
        
        if ($status) {
            $color = switch -Regex ($status) {
                "Up.*\(healthy\)" { $Green }
                "Up" { $Yellow }
                default { $Red }
            }
            
            Write-ColorMessage "${modelName} (${containerName}):" $Cyan
            Write-ColorMessage "  Status: $status" $color
            
            if ($LASTEXITCODE -eq 0) {
                Write-ColorMessage "  Health: $health" $(if ($health -eq "healthy") { $Green } else { $Yellow })
                Write-ColorMessage "  Restarts: $restarts" $(if ([int]$restarts -gt 0) { $Yellow } else { $Green })
                
                # Vérifier si le conteneur est en cours d'exécution
                if ($status -match "Up") {
                    # Afficher les dernières lignes de log
                    Write-ColorMessage "  Derniers logs:" $Magenta
                    docker logs $containerName --tail 3 2>&1 | ForEach-Object { Write-Host "    $_" }
                }
            }
        }
        else {
            Write-ColorMessage "${modelName} (${containerName}) : Non trouvé" $Yellow
        }
        
        Write-Host ""
    }
}

# Fonction pour tester la taille de contexte
function Test-ContextSize {
    param (
        [string]$ModelName,
        [string]$ApiEndpoint,
        [string]$ApiKey,
        [int]$TargetTokens
    )
    
    Write-ColorMessage "Test de la taille de contexte pour ${ModelName} (cible: ${TargetTokens} tokens)..." $Cyan
    
    try {
        # Génération d'un texte de test avec un nombre approximatif de tokens
        $testPrompt = "A" * ($TargetTokens * 3) # Approximation: 1 caractère = ~0.3 tokens
        
        $headers = @{
            "Content-Type" = "application/json"
            "Authorization" = "Bearer $ApiKey"
        }
        
        $body = @{
            model = $ModelName
            messages = @(
                @{
                    role = "user"
                    content = $testPrompt
                }
            )
            max_tokens = 10
        } | ConvertTo-Json
        
        $response = Invoke-RestMethod -Uri "$ApiEndpoint/v1/chat/completions" -Method Post -Headers $headers -Body $body -ErrorAction Stop
        
        Write-ColorMessage "Test réussi! Le modèle ${ModelName} peut gérer au moins ${TargetTokens} tokens." $Green
        return $true
    }
    catch {
        Write-ColorMessage "Erreur lors du test de la taille de contexte pour $ModelName" $Red
        Write-ColorMessage $_.Exception.Message $Red
        return $false
    }
}

# Fonction principale
function Start-QwenDeployment {
    param (
        [switch]$All,
        [switch]$Model32B,
        [switch]$Model8B,
        [switch]$ModelMicro,
        [switch]$Stop,
        [switch]$TestContext,
        [switch]$Verbose
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
        
        if ($All -or $ModelMicro) {
            Stop-QwenModel -ModelPath "micro-awq" -ModelName "Qwen3 Micro AWQ"
        }
        
        Get-ModelsStatus
        return
    }
    
    # Démarrage des modèles
    $success = $true
    
    if ($All -or $Model32B) {
        $result = Start-QwenModel -ModelPath "32b-awq" -ModelName "Qwen3 32B AWQ" -ContainerName "myia-vllm_vllm-qwen3-32b-awq" -ModelSize "32b"
        $success = $success -and $result
    }
    
    if ($All -or $Model8B) {
        $result = Start-QwenModel -ModelPath "8b-awq" -ModelName "Qwen3 8B AWQ" -ContainerName "myia-vllm_vllm-qwen3-8b-awq" -ModelSize "8b"
        $success = $success -and $result
    }
    
    if ($All -or $ModelMicro) {
        $result = Start-QwenModel -ModelPath "micro-awq" -ModelName "Qwen3 Micro AWQ" -ContainerName "myia-vllm_vllm-qwen3-micro-awq" -ModelSize "micro"
        $success = $success -and $result
    }
    
    # Affichage de l'état final
    Get-ModelsStatus
    
    # Test de la taille de contexte si demandé
    if ($TestContext -and $success) {
        Write-ColorMessage "Démarrage des tests de taille de contexte..." $Cyan
        Start-Sleep -Seconds 10 # Attendre que les API soient pleinement disponibles
        
        if ($All -or $Model32B) {
            Test-ContextSize -ModelName "vllm-qwen3-32b-awq" -ApiEndpoint "http://localhost:5001" -ApiKey "X0EC4YYP068CPD5TGARP9VQB5U4MAGHY" -TargetTokens 70000
        }
        
        if ($All -or $Model8B) {
            Test-ContextSize -ModelName "vllm-qwen3-8b-awq" -ApiEndpoint "http://localhost:5002" -ApiKey "2NEQLFX1OONFHLFCMMW9U7L15DOC9ECB" -TargetTokens 128000
        }
        
        if ($All -or $ModelMicro) {
            Test-ContextSize -ModelName "vllm-qwen3-micro-awq" -ApiEndpoint "http://localhost:5003" -ApiKey "LFXNQWMVP9OONFH1O7L15DOC9ECBEC2B" -TargetTokens 32000
        }
    }
    
    if ($success) {
        Write-ColorMessage "Tous les modèles demandés ont été démarrés avec succès!" $Green
    }
    else {
        Write-ColorMessage "Certains modèles n'ont pas pu être démarrés correctement. Vérifiez les logs pour plus de détails." $Yellow
    }
}

# Affichage de l'aide si aucun paramètre n'est fourni
if ($args.Count -eq 0) {
    Write-ColorMessage "Script de déploiement des modèles Qwen3 avec contexte optimisé" $Cyan
    Write-ColorMessage "Usage:" $Cyan
    Write-ColorMessage "  .\deploy-qwen3-context-optimized-new.ps1 -All                # Démarrer tous les modèles" $Yellow
    Write-ColorMessage "  .\deploy-qwen3-context-optimized-new.ps1 -Model32B           # Démarrer uniquement le modèle 32B" $Yellow
    Write-ColorMessage "  .\deploy-qwen3-context-optimized-new.ps1 -Model8B            # Démarrer uniquement le modèle 8B" $Yellow
    Write-ColorMessage "  .\deploy-qwen3-context-optimized-new.ps1 -ModelMicro         # Démarrer uniquement le modèle Micro" $Yellow
    Write-ColorMessage "  .\deploy-qwen3-context-optimized-new.ps1 -Model8B -ModelMicro # Démarrer les modèles 8B et Micro" $Yellow
    Write-ColorMessage "  .\deploy-qwen3-context-optimized-new.ps1 -All -Stop          # Arrêter tous les modèles" $Yellow
    Write-ColorMessage "  .\deploy-qwen3-context-optimized-new.ps1 -Status             # Afficher l'état des modèles" $Yellow
    Write-ColorMessage "  .\deploy-qwen3-context-optimized-new.ps1 -All -TestContext   # Démarrer tous les modèles et tester la taille de contexte" $Yellow
    Write-ColorMessage "  .\deploy-qwen3-context-optimized-new.ps1 -All -Verbose       # Démarrer tous les modèles avec plus de détails" $Yellow
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

if ($args -contains "-ModelMicro") {
    $ModelMicro = $true
}

if ($args -contains "-Stop") {
    $Stop = $true
}

if ($args -contains "-TestContext") {
    $TestContext = $true
}

if ($args -contains "-Verbose") {
    $Verbose = $true
}

if ($args -contains "-Status") {
    Get-ModelsStatus
    exit
}

# Démarrage du déploiement
Start-QwenDeployment -All:$All -Model32B:$Model32B -Model8B:$Model8B -ModelMicro:$ModelMicro -Stop:$Stop -TestContext:$TestContext -Verbose:$Verbose