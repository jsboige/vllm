# Script de vérification des logs des containers Qwen3
# Ce script collecte et analyse les logs des containers Qwen3 pour identifier les erreurs et problèmes

# Configuration
$ErrorActionPreference = "Stop"
$CONTAINER_NAMES = @{
    "micro" = "myia-vllm-micro-qwen3"
    "mini" = "myia-vllm-mini-qwen3"
    "medium" = "myia-vllm-medium-qwen3"
}
$LOG_FILE = "../../docs/QWEN3-LOGS-ANALYSIS.md"
$ERROR_PATTERNS = @(
    "Error",
    "Exception",
    "Failed",
    "NCCL",
    "CUDA error",
    "Out of memory",
    "OOM",
    "Segmentation fault",
    "shm",
    "shared memory",
    "Killed",
    "Timeout"
)
$WARNING_PATTERNS = @(
    "Warning",
    "Warn",
    "Deprecated"
)

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
# Analyse des logs des containers Qwen3

Date: $(Get-Date -Format "yyyy-MM-dd")

## Résumé

Ce rapport contient l'analyse des logs des containers Qwen3 (micro, mini, medium).

## Détails de l'analyse

"@

    Set-Content -Path $LOG_FILE -Value $header
    Write-Log "Initialisation du fichier de log"
}

# Fonction pour vérifier si un container est en cours d'exécution
function Test-ContainerRunning {
    param (
        [string]$ContainerName
    )
    
    $containerStatus = docker ps --format "{{.Names}}" | Select-String -Pattern $ContainerName
    
    if ($containerStatus) {
        return $true
    }
    else {
        return $false
    }
}

# Fonction pour collecter les logs d'un container
function Get-ContainerLogs {
    param (
        [string]$ContainerName,
        [int]$Lines = 1000
    )
    
    try {
        $logs = docker logs --tail $Lines $ContainerName
        return $logs
    }
    catch {
        Write-Log "Erreur lors de la récupération des logs du container $ContainerName : $_" "ERROR"
        return $null
    }
}

# Fonction pour analyser les logs d'un container
function Analyze-ContainerLogs {
    param (
        [string]$ContainerType,
        [string[]]$Logs
    )
    
    $containerName = $CONTAINER_NAMES[$ContainerType]
    Write-Log "Analyse des logs du container $containerName" "INFO"
    
    if (-not $Logs -or $Logs.Count -eq 0) {
        Write-Log "Aucun log disponible pour le container $containerName" "WARNING"
        return @{
            ErrorCount = 0
            WarningCount = 0
            Errors = @()
            Warnings = @()
            IsHealthy = $false
        }
    }
    
    $errors = @()
    $warnings = @()
    
    # Rechercher les erreurs et avertissements
    foreach ($line in $Logs) {
        $isError = $false
        $isWarning = $false
        
        # Vérifier si la ligne contient une erreur
        foreach ($pattern in $ERROR_PATTERNS) {
            if ($line -match $pattern) {
                $errors += $line
                $isError = $true
                break
            }
        }
        
        # Si ce n'est pas une erreur, vérifier si c'est un avertissement
        if (-not $isError) {
            foreach ($pattern in $WARNING_PATTERNS) {
                if ($line -match $pattern) {
                    $warnings += $line
                    $isWarning = $true
                    break
                }
            }
        }
    }
    
    # Vérifier si le container est en bonne santé
    $isHealthy = $errors.Count -eq 0
    
    # Retourner les résultats
    return @{
        ErrorCount = $errors.Count
        WarningCount = $warnings.Count
        Errors = $errors
        Warnings = $warnings
        IsHealthy = $isHealthy
    }
}

# Fonction pour surveiller les logs d'un container en temps réel
function Monitor-ContainerLogs {
    param (
        [string]$ContainerType,
        [int]$DurationMinutes = 10
    )
    
    $containerName = $CONTAINER_NAMES[$ContainerType]
    Write-Log "Surveillance des logs du container $containerName pendant $DurationMinutes minutes" "INFO"
    
    $endTime = (Get-Date).AddMinutes($DurationMinutes)
    $errorCount = 0
    $warningCount = 0
    
    try {
        # Démarrer la surveillance des logs
        $process = Start-Process -FilePath "docker" -ArgumentList "logs", "-f", $containerName -NoNewWindow -PassThru
        
        # Surveiller pendant la durée spécifiée
        while ((Get-Date) -lt $endTime) {
            Start-Sleep -Seconds 10
            
            # Vérifier si le container est toujours en cours d'exécution
            if (-not (Test-ContainerRunning -ContainerName $containerName)) {
                Write-Log "Le container $containerName s'est arrêté pendant la surveillance" "ERROR"
                break
            }
        }
        
        # Arrêter la surveillance
        Stop-Process -Id $process.Id -Force
        
        # Collecter et analyser les logs finaux
        $logs = Get-ContainerLogs -ContainerName $containerName -Lines 100
        $analysis = Analyze-ContainerLogs -ContainerType $ContainerType -Logs $logs
        
        Write-Log "Surveillance terminée pour le container $containerName" "INFO"
        Write-Log "Erreurs détectées: $($analysis.ErrorCount)" "INFO"
        Write-Log "Avertissements détectés: $($analysis.WarningCount)" "INFO"
        
        return $analysis
    }
    catch {
        Write-Log "Erreur lors de la surveillance des logs du container $containerName : $_" "ERROR"
        return $null
    }
}

# Fonction pour vérifier les performances du container
function Check-ContainerPerformance {
    param (
        [string]$ContainerType
    )
    
    $containerName = $CONTAINER_NAMES[$ContainerType]
    Write-Log "Vérification des performances du container $containerName" "INFO"
    
    try {
        # Collecter les statistiques du container
        $stats = docker stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}}" $containerName
        
        if ($stats) {
            $statsParts = $stats -split ','
            $cpuUsage = $statsParts[1]
            $memUsage = $statsParts[2]
            $memPerc = $statsParts[3]
            
            Write-Log "Performances du container $containerName :" "INFO"
            Write-Log "- CPU: $cpuUsage" "INFO"
            Write-Log "- Mémoire: $memUsage ($memPerc)" "INFO"
            
            return @{
                CPUUsage = $cpuUsage
                MemoryUsage = $memUsage
                MemoryPercentage = $memPerc
            }
        }
        else {
            Write-Log "Impossible de récupérer les statistiques du container $containerName" "ERROR"
            return $null
        }
    }
    catch {
        Write-Log "Erreur lors de la vérification des performances du container $containerName : $_" "ERROR"
        return $null
    }
}

# Fonction pour vérifier les logs et performances d'un container
function Check-Container {
    param (
        [string]$ContainerType
    )
    
    $containerName = $CONTAINER_NAMES[$ContainerType]
    Write-Log "=== Vérification du container $containerType ($containerName) ===" "INFO"
    
    # Vérifier si le container est en cours d'exécution
    if (-not (Test-ContainerRunning -ContainerName $containerName)) {
        Write-Log "Le container $containerName n'est pas en cours d'exécution" "ERROR"
        return @{
            ContainerType = $ContainerType
            IsRunning = $false
            IsHealthy = $false
            ErrorCount = 0
            WarningCount = 0
            Performance = $null
        }
    }
    
    # Collecter les logs
    $logs = Get-ContainerLogs -ContainerName $containerName
    
    # Analyser les logs
    $analysis = Analyze-ContainerLogs -ContainerType $ContainerType -Logs $logs
    
    # Vérifier les performances
    $performance = Check-ContainerPerformance -ContainerType $ContainerType
    
    # Afficher les erreurs détectées
    if ($analysis.ErrorCount -gt 0) {
        Write-Log "Erreurs détectées dans les logs du container $containerName :" "ERROR"
        foreach ($error in $analysis.Errors) {
            Write-Log "- $error" "ERROR"
        }
    }
    
    # Afficher les avertissements détectés
    if ($analysis.WarningCount -gt 0) {
        Write-Log "Avertissements détectés dans les logs du container $containerName :" "WARNING"
        foreach ($warning in $analysis.Warnings | Select-Object -First 10) {
            Write-Log "- $warning" "WARNING"
        }
        
        if ($analysis.Warnings.Count -gt 10) {
            Write-Log "... et $($analysis.Warnings.Count - 10) autres avertissements" "WARNING"
        }
    }
    
    # Retourner les résultats
    return @{
        ContainerType = $ContainerType
        IsRunning = $true
        IsHealthy = $analysis.IsHealthy
        ErrorCount = $analysis.ErrorCount
        WarningCount = $analysis.WarningCount
        Performance = $performance
    }
}

# Fonction pour rechercher des erreurs spécifiques liées à la mémoire partagée
function Find-SharedMemoryErrors {
    param (
        [string]$ContainerType,
        [string[]]$Logs
    )
    
    $containerName = $CONTAINER_NAMES[$ContainerType]
    Write-Log "Recherche d'erreurs de mémoire partagée dans les logs du container $containerName" "INFO"
    
    $shmErrors = @()
    $patterns = @(
        "Error while creating shared memory segment",
        "shm",
        "shared memory",
        "NCCL.*error"
    )
    
    foreach ($line in $Logs) {
        foreach ($pattern in $patterns) {
            if ($line -match $pattern) {
                $shmErrors += $line
                break
            }
        }
    }
    
    if ($shmErrors.Count -gt 0) {
        Write-Log "Erreurs de mémoire partagée détectées dans les logs du container $containerName :" "ERROR"
        foreach ($error in $shmErrors) {
            Write-Log "- $error" "ERROR"
        }
    }
    else {
        Write-Log "Aucune erreur de mémoire partagée détectée dans les logs du container $containerName" "INFO"
    }
    
    return $shmErrors
}

# Fonction principale
function Main {
    # Initialiser le fichier de log
    Initialize-LogFile
    
    Write-Log "Début de l'analyse des logs des containers Qwen3" "INFO"
    
    $results = @{}
    
    # Vérifier chaque container
    foreach ($containerType in @("micro", "mini", "medium")) {
        $containerName = $CONTAINER_NAMES[$containerType]
        
        # Vérifier si le container est en cours d'exécution
        if (Test-ContainerRunning -ContainerName $containerName) {
            Write-Log "Le container $containerName est en cours d'exécution" "INFO"
            
            # Collecter et analyser les logs
            $logs = Get-ContainerLogs -ContainerName $containerName
            $result = Check-Container -ContainerType $containerType
            
            # Rechercher des erreurs spécifiques liées à la mémoire partagée
            $shmErrors = Find-SharedMemoryErrors -ContainerType $containerType -Logs $logs
            $result.ShmErrorCount = $shmErrors.Count
            
            $results[$containerType] = $result
        }
        else {
            Write-Log "Le container $containerName n'est pas en cours d'exécution" "WARNING"
            $results[$containerType] = @{
                ContainerType = $containerType
                IsRunning = $false
                IsHealthy = $false
                ErrorCount = 0
                WarningCount = 0
                ShmErrorCount = 0
                Performance = $null
            }
        }
    }
    
    # Générer le résumé
    Write-Log "`n## Résumé des résultats" "INFO"
    
    foreach ($containerType in @("micro", "mini", "medium")) {
        $result = $results[$containerType]
        $status = if ($result.IsRunning) {
            if ($result.IsHealthy) { "✅ En cours d'exécution et en bonne santé" } else { "⚠️ En cours d'exécution mais avec des erreurs" }
        } else {
            "❌ Non démarré"
        }
        
        Write-Log "### Container $containerType" "INFO"
        Write-Log "- Statut: $status" "INFO"
        Write-Log "- Erreurs: $($result.ErrorCount)" "INFO"
        Write-Log "- Avertissements: $($result.WarningCount)" "INFO"
        Write-Log "- Erreurs de mémoire partagée: $($result.ShmErrorCount)" "INFO"
        
        if ($result.Performance) {
            Write-Log "- CPU: $($result.Performance.CPUUsage)" "INFO"
            Write-Log "- Mémoire: $($result.Performance.MemoryUsage) ($($result.Performance.MemoryPercentage))" "INFO"
        }
        
        Write-Log "" "INFO"
    }
    
    # Conclusion
    $allHealthy = ($results.Values | ForEach-Object { $_.IsHealthy } | Where-Object { -not $_ } | Measure-Object | Select-Object -ExpandProperty Count) -eq 0
    $allRunning = ($results.Values | ForEach-Object { $_.IsRunning } | Where-Object { -not $_ } | Measure-Object | Select-Object -ExpandProperty Count) -eq 0
    
    Write-Log "`n## Conclusion" "INFO"
    
    if ($allRunning -and $allHealthy) {
        Write-Log "Tous les containers sont en cours d'exécution et en bonne santé." "SUCCESS"
    }
    elseif ($allRunning) {
        Write-Log "Tous les containers sont en cours d'exécution, mais certains présentent des erreurs." "WARNING"
    }
    else {
        Write-Log "Certains containers ne sont pas en cours d'exécution." "ERROR"
    }
    
    # Vérifier spécifiquement les erreurs de mémoire partagée
    $shmErrorsExist = ($results.Values | ForEach-Object { $_.ShmErrorCount -gt 0 } | Where-Object { $_ } | Measure-Object | Select-Object -ExpandProperty Count) -gt 0
    
    if ($shmErrorsExist) {
        Write-Log "`n## Erreurs de mémoire partagée" "ERROR"
        Write-Log "Des erreurs de mémoire partagée ont été détectées. Vérifiez que l'option 'shm_size' est correctement configurée dans les fichiers docker-compose." "ERROR"
    }
    
    Write-Log "Fin de l'analyse des logs des containers Qwen3" "INFO"
}

# Exécuter la fonction principale
Main