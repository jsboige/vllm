# Script de déploiement et validation des containers Qwen3 (mini, medium, large)
# Ce script déploie séquentiellement les trois containers et vérifie leur bon fonctionnement

# Configuration
$ErrorActionPreference = "Stop"
$MAX_RETRIES = 3
$WAIT_TIME = 180  # Temps d'attente en secondes entre les vérifications
$WAIT_TIME_MEDIUM = 300  # Temps d'attente spécifique pour le modèle medium
$DOCKER_COMPOSE_DIR = "D:/vllm/vllm-configs/docker-compose"
$DOCKER_COMPOSE_FILES = @{
    "micro" = "docker-compose-micro-qwen3.yml"
    "mini" = "docker-compose-mini-qwen3.yml"
    "medium" = "docker-compose-medium-qwen3-memory-optimized.yml"
}
$CONTAINER_NAMES = @{
    "micro" = "myia-vllm-micro-qwen3"
    "mini" = "myia-vllm-mini-qwen3"
    "medium" = "myia-vllm-medium-qwen3"
}
$API_PORTS = @{
    "micro" = "5000"
    "mini" = "5001"
    "medium" = "5002"
}
$LOG_FILE = "D:/vllm/vllm-configs/DEPLOYMENT-VALIDATION-REPORT.md"

# Fonction pour écrire dans le fichier de log
function Write-Log {
    param (
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    
    Write-Host $logMessage
    Add-Content -Path $LOG_FILE -Value $logMessage
}

# Fonction pour initialiser le fichier de log
function Initialize-LogFile {
    $header = @"
# Rapport de déploiement et validation des containers Qwen3

Date: $(Get-Date -Format "yyyy-MM-dd")

## Résumé

Ce rapport contient les résultats du déploiement et de la validation des containers Qwen3 (mini, medium, large).

## Détails du déploiement

"@

    Set-Content -Path $LOG_FILE -Value $header
    Write-Log "Initialisation du fichier de log"
}

# Fonction pour déployer un container
function Deploy-Container {
    param (
        [string]$ContainerType
    )
    
    $composeFile = Join-Path -Path $DOCKER_COMPOSE_DIR -ChildPath $DOCKER_COMPOSE_FILES[$ContainerType]
    $containerName = $CONTAINER_NAMES[$ContainerType]
    
    Write-Log "Déploiement du container $ContainerType ($containerName) avec le fichier $composeFile" "INFO"
    
    # Vérifier si le container existe déjà et l'arrêter si nécessaire
    $containerExists = docker ps -a --format "{{.Names}}" | Select-String -Pattern $containerName
    if ($containerExists) {
        Write-Log "Le container $containerName existe déjà, arrêt en cours..." "INFO"
        docker stop $containerName
        docker rm $containerName
    }
    
    # Déployer le container
    try {
        $envFile = "D:/vllm/vllm-configs/.env"
        docker-compose -f $composeFile --env-file $envFile up -d
        Write-Log "Container $ContainerType déployé avec succès" "SUCCESS"
        return $true
    }
    catch {
        Write-Log "Erreur lors du déploiement du container $ContainerType : $_" "ERROR"
        return $false
    }
}

# Fonction pour vérifier si un container est en cours d'exécution
function Test-ContainerRunning {
    param (
        [string]$ContainerType
    )
    
    $containerName = $CONTAINER_NAMES[$ContainerType]
    $containerStatus = docker ps --format "{{.Names}}" | Select-String -Pattern $containerName
    
    if ($containerStatus) {
        Write-Log "Le container $containerName est en cours d'exécution" "INFO"
        return $true
    }
    else {
        Write-Log "Le container $containerName n'est pas en cours d'exécution" "ERROR"
        return $false
    }
}

# Fonction pour vérifier si l'API est accessible
function Test-ApiAccessible {
    param (
        [string]$ContainerType
    )
    
    $port = $API_PORTS[$ContainerType]
    $url = "http://localhost:$port/v1/models"
    
    try {
        $response = Invoke-WebRequest -Uri $url -Method GET -TimeoutSec 30
        if ($response.StatusCode -eq 200) {
            Write-Log "L'API du container $ContainerType est accessible sur le port $port" "SUCCESS"
            return $true
        }
        else {
            Write-Log "L'API du container $ContainerType a répondu avec le code $($response.StatusCode)" "ERROR"
            return $false
        }
    }
    catch {
        Write-Log "Erreur lors de l'accès à l'API du container $ContainerType : $_" "ERROR"
        return $false
    }
}

# Fonction pour exécuter un test de reasoning
function Test-Reasoning {
    param (
        [string]$ContainerType
    )
    
    $port = $API_PORTS[$ContainerType]
    $url = "http://localhost:$port/v1/chat/completions"
    $body = @{
        model = "Qwen3"
        messages = @(
            @{
                role = "user"
                content = "Explique-moi comment fonctionne la récursivité en programmation avec un exemple simple."
            }
        )
        max_tokens = 500
    } | ConvertTo-Json
    
    try {
        $response = Invoke-RestMethod -Uri $url -Method POST -Body $body -ContentType "application/json" -TimeoutSec 120
        if ($response.choices -and $response.choices.Count -gt 0) {
            Write-Log "Test de reasoning réussi pour le container $ContainerType" "SUCCESS"
            Write-Log "Réponse: $($response.choices[0].message.content | Out-String)" "INFO"
            return $true
        }
        else {
            Write-Log "Test de reasoning échoué pour le container $ContainerType : pas de réponse valide" "ERROR"
            return $false
        }
    }
    catch {
        Write-Log "Erreur lors du test de reasoning pour le container $ContainerType : $_" "ERROR"
        return $false
    }
}

# Fonction pour exécuter un test de tool calling
function Test-ToolCalling {
    param (
        [string]$ContainerType
    )
    
    $port = $API_PORTS[$ContainerType]
    $url = "http://localhost:$port/v1/chat/completions"
    $body = @{
        model = "Qwen3"
        messages = @(
            @{
                role = "user"
                content = "Quelle est la racine carrée de 144?"
            }
        )
        tools = @(
            @{
                type = "function"
                function = @{
                    name = "calculate"
                    description = "Effectue un calcul mathématique"
                    parameters = @{
                        type = "object"
                        properties = @{
                            expression = @{
                                type = "string"
                                description = "L'expression mathématique à calculer"
                            }
                        }
                        required = @("expression")
                    }
                }
            }
        )
        tool_choice = "auto"
        max_tokens = 500
    } | ConvertTo-Json -Depth 10
    
    try {
        $response = Invoke-RestMethod -Uri $url -Method POST -Body $body -ContentType "application/json" -TimeoutSec 120
        if ($response.choices -and $response.choices.Count -gt 0 -and $response.choices[0].message.tool_calls) {
            Write-Log "Test de tool calling réussi pour le container $ContainerType" "SUCCESS"
            Write-Log "Réponse: $($response.choices[0].message.tool_calls | ConvertTo-Json)" "INFO"
            return $true
        }
        else {
            Write-Log "Test de tool calling échoué pour le container $ContainerType : pas d'appel d'outil détecté" "ERROR"
            return $false
        }
    }
    catch {
        Write-Log "Erreur lors du test de tool calling pour le container $ContainerType : $_" "ERROR"
        return $false
    }
}

# Fonction pour collecter les logs d'un container
function Get-ContainerLogs {
    param (
        [string]$ContainerType,
        [int]$Lines = 50
    )
    
    $containerName = $CONTAINER_NAMES[$ContainerType]
    
    try {
        $logs = docker logs --tail $Lines $containerName
        Write-Log "Logs du container $containerName récupérés avec succès" "INFO"
        return $logs
    }
    catch {
        Write-Log "Erreur lors de la récupération des logs du container $containerName : $_" "ERROR"
        return $null
    }
}

# Fonction pour déployer et valider un container avec retry
function Deploy-And-Validate-Container {
    param (
        [string]$ContainerType
    )
    
    Write-Log "=== Déploiement et validation du container $ContainerType ===" "INFO"
    
    # Tentatives de déploiement avec retry
    $deployed = $false
    $retryCount = 0
    
    while (-not $deployed -and $retryCount -lt $MAX_RETRIES) {
        $retryCount++
        Write-Log "Tentative $retryCount/$MAX_RETRIES de déploiement du container $ContainerType" "INFO"
        
        $deployed = Deploy-Container -ContainerType $ContainerType
        
        if (-not $deployed) {
            Write-Log "Échec du déploiement, nouvelle tentative dans 10 secondes..." "WARNING"
            Start-Sleep -Seconds 10
        }
    }
    
    if (-not $deployed) {
        Write-Log "Échec du déploiement du container $ContainerType après $MAX_RETRIES tentatives" "ERROR"
        return $false
    }
    
    # Attendre que le container soit prêt
    if ($ContainerType -eq "medium") {
        Write-Log "Attente de l'initialisation du container $ContainerType ($WAIT_TIME_MEDIUM secondes)..." "INFO"
        Start-Sleep -Seconds $WAIT_TIME_MEDIUM
    } else {
        Write-Log "Attente de l'initialisation du container $ContainerType ($WAIT_TIME secondes)..." "INFO"
        Start-Sleep -Seconds $WAIT_TIME
    }
    
    # Vérifier que le container est en cours d'exécution
    $running = Test-ContainerRunning -ContainerType $ContainerType
    if (-not $running) {
        Write-Log "Le container $ContainerType n'est pas en cours d'exécution après déploiement" "ERROR"
        $logs = Get-ContainerLogs -ContainerType $ContainerType
        Write-Log "Logs du container:" "INFO"
        $logs | ForEach-Object { Write-Log $_ "LOG" }
        return $false
    }
    
    # Vérifier que l'API est accessible
    $apiAccessible = $false
    $retryCount = 0
    
    while (-not $apiAccessible -and $retryCount -lt $MAX_RETRIES) {
        $retryCount++
        Write-Log "Tentative $retryCount/$MAX_RETRIES de connexion à l'API du container $ContainerType" "INFO"
        
        $apiAccessible = Test-ApiAccessible -ContainerType $ContainerType
        
        if (-not $apiAccessible) {
            Write-Log "API non accessible, nouvelle tentative dans 30 secondes..." "WARNING"
            Start-Sleep -Seconds 30
        }
    }
    
    if (-not $apiAccessible) {
        Write-Log "Échec de connexion à l'API du container $ContainerType après $MAX_RETRIES tentatives" "ERROR"
        $logs = Get-ContainerLogs -ContainerType $ContainerType
        Write-Log "Logs du container:" "INFO"
        $logs | ForEach-Object { Write-Log $_ "LOG" }
        return $false
    }
    
    # Exécuter les tests
    Write-Log "Exécution des tests pour le container $ContainerType" "INFO"
    
    # Test de reasoning
    $reasoningSuccess = Test-Reasoning -ContainerType $ContainerType
    
    # Test de tool calling
    $toolCallingSuccess = Test-ToolCalling -ContainerType $ContainerType
    
    # Résumé des tests
    if ($reasoningSuccess -and $toolCallingSuccess) {
        Write-Log "Tous les tests ont réussi pour le container $ContainerType" "SUCCESS"
        return $true
    }
    else {
        Write-Log "Certains tests ont échoué pour le container $ContainerType" "ERROR"
        return $false
    }
}

# Fonction principale
function Main {
    # Initialiser le fichier de log
    Initialize-LogFile
    
    Write-Log "Début du déploiement et de la validation des containers Qwen3" "INFO"
    
    $results = @{}
    
    # Déployer et valider chaque container
    foreach ($containerType in @("micro", "mini", "medium")) {
        $success = Deploy-And-Validate-Container -ContainerType $containerType
        $results[$containerType] = $success
    }
    
    # Générer le résumé
    Write-Log "`n## Résumé des résultats" "INFO"
    
    foreach ($containerType in @("micro", "mini", "medium")) {
        $status = if ($results[$containerType]) { "✅ Réussi" } else { "❌ Échoué" }
        Write-Log "- Container $containerType : $status" "INFO"
    }
    
    # Conclusion
    $allSuccess = ($results.Values | ForEach-Object { $_ } | Where-Object { -not $_ } | Measure-Object | Select-Object -ExpandProperty Count) -eq 0
    
    if ($allSuccess) {
        Write-Log "`n## Conclusion" "SUCCESS"
        Write-Log "Tous les containers ont été déployés et validés avec succès." "SUCCESS"
    }
    else {
        Write-Log "`n## Conclusion" "ERROR"
        Write-Log "Certains containers n'ont pas pu être déployés ou validés correctement. Veuillez consulter les logs pour plus de détails." "ERROR"
    }
    
    Write-Log "Fin du déploiement et de la validation des containers Qwen3" "INFO"
}

# Exécuter la fonction principale
Main