<#
.SYNOPSIS
    Monitoring quotidien automatisé du service vLLM medium

.DESCRIPTION
    Effectue une série de vérifications de santé du service vLLM medium :
    - Statut container Docker (doit être "healthy")
    - Utilisation GPU NVIDIA (< 90%)
    - Uptime du service
    - Génère un rapport de santé horodaté
    
    Conçu pour être exécuté quotidiennement via scheduler ou manuellement.

.PARAMETER ContainerName
    Nom du container à vérifier (défaut: myia_vllm-medium-qwen3)

.PARAMETER OutputDir
    Répertoire de sortie pour les rapports (défaut: logs/health_checks)

.PARAMETER GpuThreshold
    Seuil d'alerte pour utilisation GPU en pourcentage (défaut: 90)

.PARAMETER Silent
    Mode silencieux - pas de sortie console, seulement fichier de rapport

.EXAMPLE
    .\health_check.ps1
    Exécute le health check avec paramètres par défaut

.EXAMPLE
    .\health_check.ps1 -GpuThreshold 85 -Silent
    Health check avec seuil GPU 85% en mode silencieux

.NOTES
    Version: 1.0.0
    Date: 2025-10-22
    Auteur: Roo Code (Mode)
    Fréquence recommandée: Quotidienne (chaque jour ouvré)
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$ContainerName = "myia_vllm-medium-qwen3",
    
    [Parameter(Mandatory=$false)]
    [string]$OutputDir = "logs/health_checks",
    
    [Parameter(Mandatory=$false)]
    [int]$GpuThreshold = 90,
    
    [Parameter(Mandatory=$false)]
    [switch]$Silent
)

# =============================================================================
# CONFIGURATION
# =============================================================================

$ErrorActionPreference = "Continue"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$DateDisplay = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# Chemins
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptRoot)
$OutputPath = Join-Path $ProjectRoot $OutputDir
$ReportFile = Join-Path $OutputPath "health_check_$Timestamp.txt"

# Créer répertoire de sortie si nécessaire
if (-not (Test-Path $OutputPath)) {
    New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null
}

# =============================================================================
# FONCTIONS
# =============================================================================

function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $logEntry = "[$DateDisplay] [$Level] $Message"
    
    # Écrire dans le fichier
    Add-Content -Path $ReportFile -Value $logEntry
    
    # Afficher dans la console si pas en mode silencieux
    if (-not $Silent) {
        $color = switch ($Level) {
            "SUCCESS" { "Green" }
            "WARNING" { "Yellow" }
            "ERROR" { "Red" }
            default { "White" }
        }
        Write-Host $logEntry -ForegroundColor $color
    }
}

function Get-ContainerStatus {
    try {
        $status = docker ps --filter "name=$ContainerName" --format "{{.Status}}"
        
        if (-not $status) {
            Write-Log "Container '$ContainerName' non trouvé" "ERROR"
            return $false
        }
        
        Write-Log "Status container: $status" "INFO"
        
        if ($status -like '*healthy*') {
            Write-Log "✓ Container est HEALTHY" "SUCCESS"
            return $true
        } else {
            Write-Log "✗ Container n'est PAS healthy" "WARNING"
            return $false
        }
    }
    catch {
        Write-Log "Erreur lors de la vérification du container: $_" "ERROR"
        return $false
    }
}

function Get-GpuUtilization {
    try {
        $gpuInfo = nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits
        
        if (-not $gpuInfo) {
            Write-Log "Impossible de récupérer les informations GPU" "ERROR"
            return $false
        }
        
        # Parser les valeurs
        $values = $gpuInfo -split ','
        $gpuUtil = [int]$values[0].Trim()
        $memUsed = [int]$values[1].Trim()
        $memTotal = [int]$values[2].Trim()
        $memPercent = [math]::Round(($memUsed / $memTotal) * 100, 2)
        
        Write-Log "GPU Utilization: $gpuUtil%" "INFO"
        Write-Log "VRAM: $memUsed MB / $memTotal MB ($memPercent%)" "INFO"
        
        if ($gpuUtil -ge $GpuThreshold) {
            Write-Log "✗ Utilisation GPU excessive: $gpuUtil% (seuil: $GpuThreshold%)" "WARNING"
            return $false
        } else {
            Write-Log "✓ Utilisation GPU acceptable: $gpuUtil% < $GpuThreshold%" "SUCCESS"
            return $true
        }
    }
    catch {
        Write-Log "Erreur lors de la vérification GPU: $_" "ERROR"
        return $false
    }
}

function Get-ContainerUptime {
    try {
        $startedAt = docker inspect $ContainerName --format='{{.State.StartedAt}}'
        
        if (-not $startedAt) {
            Write-Log "Impossible de récupérer l'uptime du container" "ERROR"
            return $false
        }
        
        # Convertir en DateTime et calculer uptime
        $startTime = [DateTime]::Parse($startedAt)
        $uptime = (Get-Date) - $startTime
        $uptimeDisplay = "{0}j {1}h {2}m" -f $uptime.Days, $uptime.Hours, $uptime.Minutes
        
        Write-Log "Container démarré: $startedAt" "INFO"
        Write-Log "✓ Uptime: $uptimeDisplay" "SUCCESS"
        return $true
    }
    catch {
        Write-Log "Erreur lors de la récupération de l'uptime: $_" "ERROR"
        return $false
    }
}

# =============================================================================
# MAIN
# =============================================================================

Write-Log "=== HEALTH CHECK QUOTIDIEN - Service vLLM Medium ===" "INFO"
Write-Log "Container: $ContainerName" "INFO"
Write-Log "" "INFO"

$allChecksPass = $true

# 1. Vérification statut container
Write-Log "--- Vérification 1/3: Statut Container ---" "INFO"
$containerOk = Get-ContainerStatus
$allChecksPass = $allChecksPass -and $containerOk
Write-Log "" "INFO"

# 2. Vérification GPU
Write-Log "--- Vérification 2/3: Utilisation GPU ---" "INFO"
$gpuOk = Get-GpuUtilization
$allChecksPass = $allChecksPass -and $gpuOk
Write-Log "" "INFO"

# 3. Vérification uptime
Write-Log "--- Vérification 3/3: Uptime Service ---" "INFO"
$uptimeOk = Get-ContainerUptime
$allChecksPass = $allChecksPass -and $uptimeOk
Write-Log "" "INFO"

# Rapport final
Write-Log "=== RÉSUMÉ HEALTH CHECK ===" "INFO"
if ($allChecksPass) {
    Write-Log "✓ TOUTES les vérifications ont RÉUSSI" "SUCCESS"
    Write-Log "Service vLLM Medium en BONNE SANTÉ" "SUCCESS"
    $exitCode = 0
} else {
    Write-Log "✗ CERTAINES vérifications ont ÉCHOUÉ" "WARNING"
    Write-Log "Action recommandée: Consulter MAINTENANCE_PROCEDURES.md" "WARNING"
    $exitCode = 1
}

Write-Log "Rapport complet: $ReportFile" "INFO"

exit $exitCode