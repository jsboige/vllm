# Script de Monitoring Tight - Service Medium vLLM
# Mission 9 SDDD - Redéploiement Service Medium
# Date: 2025-10-16

<#
.SYNOPSIS
    Monitoring tight des logs du service medium Qwen3-32B-AWQ

.DESCRIPTION
    Surveille le démarrage et l'état de santé du conteneur myia-vllm-medium-qwen3
    avec détection d'erreurs critiques et confirmation de l'état healthy.

.PARAMETER IntervalSeconds
    Intervalle entre chaque vérification (défaut: 10 secondes)

.PARAMETER TimeoutMinutes
    Durée maximale de surveillance avant timeout (défaut: 10 minutes)

.EXAMPLE
    .\monitor_medium.ps1
    # Monitoring avec paramètres par défaut (10s interval, 10 min timeout)

.EXAMPLE
    .\monitor_medium.ps1 -IntervalSeconds 5 -TimeoutMinutes 15
    # Monitoring plus fréquent avec timeout étendu
#>

param(
    [int]$IntervalSeconds = 10,
    [int]$TimeoutMinutes = 10
)

# Configuration
$containerName = "myia_vllm-medium-qwen3"
$startTime = Get-Date
$timeout = $startTime.AddMinutes($TimeoutMinutes)
$errorPatterns = @(
    "ERROR",
    "CRITICAL", 
    "FATAL",
    "Exception",
    "failed",
    "CUDA out of memory",
    "OOM",
    "Connection refused",
    "Cannot allocate"
)

# Fonction pour afficher avec couleurs
function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

# Fonction pour extraire et formater les logs
function Get-ContainerLogs {
    param(
        [string]$Container,
        [int]$TailLines = 20
    )
    
    try {
        $logs = docker logs $Container --tail $TailLines 2>&1
        return $logs
    }
    catch {
        return $null
    }
}

# Fonction pour détecter les erreurs critiques
function Test-CriticalErrors {
    param(
        [string[]]$Logs,
        [string[]]$Patterns
    )
    
    $errors = @()
    foreach ($log in $Logs) {
        foreach ($pattern in $Patterns) {
            if ($log -match $pattern) {
                $errors += $log
            }
        }
    }
    return $errors
}

# En-tête
Write-ColorOutput "`n=== 🔍 MONITORING SERVICE MEDIUM - Qwen3-32B-AWQ ===" -Color Cyan
Write-ColorOutput "Conteneur     : $containerName" -Color White
Write-ColorOutput "Intervalle    : $IntervalSeconds secondes" -Color White
Write-ColorOutput "Timeout       : $TimeoutMinutes minutes" -Color White
Write-ColorOutput "Début         : $($startTime.ToString('HH:mm:ss'))" -Color White
Write-ColorOutput "Fin timeout   : $($timeout.ToString('HH:mm:ss'))" -Color Yellow
Write-ColorOutput "=".PadRight(60, '=') -Color Cyan

# Variables de suivi
$iterationCount = 0
$lastStatus = ""
$healthyDetected = $false

# Boucle de monitoring
while ((Get-Date) -lt $timeout) {
    $iterationCount++
    $currentTime = Get-Date
    $elapsed = $currentTime - $startTime
    
    Write-ColorOutput "`n--- Itération #$iterationCount [+$($elapsed.ToString('mm\:ss'))] ---" -Color Cyan
    
    # Vérifier l'existence du conteneur
    try {
        $containerInfo = docker ps -a --filter "name=$containerName" --format "{{.ID}}|{{.Status}}|{{.State}}" 2>$null
        
        if (-not $containerInfo) {
            Write-ColorOutput "⚠️  ATTENTION: Conteneur '$containerName' introuvable" -Color Yellow
            Write-ColorOutput "   Vérifier que le déploiement a été lancé correctement" -Color Yellow
        }
        else {
            $parts = $containerInfo -split '\|'
            $containerId = $parts[0]
            $status = $parts[1]
            $state = $parts[2]
            
            # Afficher le status
            if ($status -ne $lastStatus) {
                Write-ColorOutput "`n📊 Status: $status" -Color Green
                $lastStatus = $status
            }
            else {
                Write-ColorOutput "📊 Status: $status (inchangé)" -Color Gray
            }
            
            # Récupérer les logs récents
            Write-ColorOutput "`n📜 Derniers logs (20 lignes):" -Color Cyan
            $logs = Get-ContainerLogs -Container $containerName -TailLines 20
            
            if ($logs) {
                # Afficher les logs (limiter pour lisibilité)
                $displayLogs = $logs | Select-Object -Last 10
                foreach ($line in $displayLogs) {
                    if ($line -match "ERROR|CRITICAL|FATAL|Exception|failed") {
                        Write-ColorOutput "  ❌ $line" -Color Red
                    }
                    elseif ($line -match "WARNING|WARN") {
                        Write-ColorOutput "  ⚠️  $line" -Color Yellow
                    }
                    elseif ($line -match "Loading|Initializing|Starting") {
                        Write-ColorOutput "  ⏳ $line" -Color Cyan
                    }
                    elseif ($line -match "success|complete|ready|loaded") {
                        Write-ColorOutput "  ✅ $line" -Color Green
                    }
                    else {
                        Write-ColorOutput "  ℹ️  $line" -Color Gray
                    }
                }
                
                # Détecter erreurs critiques dans tous les logs
                $criticalErrors = Test-CriticalErrors -Logs $logs -Patterns $errorPatterns
                
                if ($criticalErrors.Count -gt 0) {
                    Write-ColorOutput "`n🚨 ERREURS CRITIQUES DÉTECTÉES ($($criticalErrors.Count)):" -Color Red
                    $criticalErrors | Select-Object -First 5 | ForEach-Object {
                        Write-ColorOutput "   $_" -Color Red
                    }
                    
                    # Si OOM ou CUDA errors, c'est critique
                    $oomErrors = $criticalErrors | Where-Object { $_ -match "out of memory|OOM|CUDA" }
                    if ($oomErrors) {
                        Write-ColorOutput "`n❌ ERREUR CUDA/MÉMOIRE CRITIQUE - Déploiement probablement échoué" -Color Red
                        Write-ColorOutput "   Recommandations:" -Color Yellow
                        Write-ColorOutput "   1. Vérifier disponibilité GPU: nvidia-smi" -Color Yellow
                        Write-ColorOutput "   2. Réduire GPU_MEMORY_UTILIZATION à 0.90 dans .env" -Color Yellow
                        Write-ColorOutput "   3. Vérifier qu'aucun autre process n'utilise les GPUs" -Color Yellow
                        exit 1
                    }
                }
                
                # Vérifier progression du chargement
                if ($logs -match "Model loaded successfully") {
                    Write-ColorOutput "`n✅ MODÈLE CHARGÉ AVEC SUCCÈS" -Color Green
                }
                
                if ($logs -match "Application startup complete") {
                    Write-ColorOutput "`n✅ APPLICATION DÉMARRÉE" -Color Green
                }
            }
            else {
                Write-ColorOutput "⚠️  Impossible de récupérer les logs" -Color Yellow
            }
            
            # Vérifier l'état healthy
            if ($status -match "\(healthy\)") {
                Write-ColorOutput "`n🎉 ✅ CONTENEUR EST HEALTHY !" -Color Green
                Write-ColorOutput "`n📊 Statistiques finales:" -Color Cyan
                Write-ColorOutput "   Temps écoulé  : $($elapsed.ToString('mm\:ss'))" -Color White
                Write-ColorOutput "   Itérations    : $iterationCount" -Color White
                Write-ColorOutput "   Status final  : HEALTHY" -Color Green
                
                Write-ColorOutput "`n📜 Derniers logs (confirmation):" -Color Cyan
                $finalLogs = Get-ContainerLogs -Container $containerName -TailLines 15
                $finalLogs | Select-Object -Last 10 | ForEach-Object {
                    Write-ColorOutput "   $_" -Color Gray
                }
                
                Write-ColorOutput "`n✅ MONITORING TERMINÉ AVEC SUCCÈS" -Color Green
                Write-ColorOutput "`n🔗 Endpoints disponibles:" -Color Cyan
                Write-ColorOutput "   Health : http://localhost:5002/health" -Color White
                Write-ColorOutput "   Models : http://localhost:5002/v1/models" -Color White
                Write-ColorOutput "   Chat   : http://localhost:5002/v1/chat/completions" -Color White
                
                exit 0
            }
            elseif ($state -eq "running" -and $status -match "starting") {
                Write-ColorOutput "`n⏳ Conteneur en cours de démarrage (health check pending)..." -Color Yellow
            }
            elseif ($state -eq "exited") {
                Write-ColorOutput "`n❌ CONTENEUR ARRÊTÉ - Déploiement échoué" -Color Red
                Write-ColorOutput "`n📜 Derniers logs avant arrêt:" -Color Red
                $exitLogs = Get-ContainerLogs -Container $containerName -TailLines 30
                $exitLogs | ForEach-Object {
                    Write-ColorOutput "   $_" -Color Red
                }
                exit 1
            }
        }
    }
    catch {
        Write-ColorOutput "❌ Erreur lors de la vérification: $_" -Color Red
    }
    
    # Attendre avant prochaine itération
    Start-Sleep -Seconds $IntervalSeconds
}

# Timeout atteint
Write-ColorOutput "`n⏰ ❌ TIMEOUT ATTEINT ($TimeoutMinutes minutes)" -Color Red
Write-ColorOutput "`n📊 Statistiques:" -Color Yellow
Write-ColorOutput "   Temps total   : $TimeoutMinutes minutes" -Color White
Write-ColorOutput "   Itérations    : $iterationCount" -Color White
Write-ColorOutput "   Status final  : TIMEOUT (pas healthy)" -Color Red

Write-ColorOutput "`n📜 Derniers logs disponibles:" -Color Yellow
$timeoutLogs = Get-ContainerLogs -Container $containerName -TailLines 30
if ($timeoutLogs) {
    $timeoutLogs | ForEach-Object {
        Write-ColorOutput "   $_" -Color Gray
    }
}

Write-ColorOutput "`n💡 Actions recommandées:" -Color Yellow
Write-ColorOutput "   1. Vérifier les logs complets: docker logs $containerName" -Color White
Write-ColorOutput "   2. Vérifier GPUs: nvidia-smi" -Color White
Write-ColorOutput "   3. Vérifier token HuggingFace dans .env" -Color White
Write-ColorOutput "   4. Consulter guide troubleshooting: docs/deployment/MEDIUM_SERVICE.md" -Color White

exit 1