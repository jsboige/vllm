# monitor-logs.ps1 - Script de monitoring des logs des services Qwen3
#
# Version consolidée et modernisée du script check-qwen3-logs.ps1
# Auteur: Roo Code (consolidation septembre 2025)
# Compatible avec: Image Docker officielle vLLM v0.9.2

param(
    [switch]$Help,
    [switch]$Verbose,
    [ValidateSet("micro", "mini", "medium", "all")]
    [string]$Profile = "all",
    [int]$TailLines = 50,
    [switch]$Follow,
    [switch]$ErrorsOnly,
    [string]$OutputFile
)

# Définition des couleurs
$RED = [System.ConsoleColor]::Red
$GREEN = [System.ConsoleColor]::Green
$YELLOW = [System.ConsoleColor]::Yellow
$BLUE = [System.ConsoleColor]::Blue
$CYAN = [System.ConsoleColor]::Cyan

# Configuration
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_ROOT = Split-Path -Parent (Split-Path -Parent $SCRIPT_DIR)

# Configuration des services (alignée sur le document maître)
$SERVICES = @{
    "micro" = @{
        "container_name" = "vllm-micro"
        "description" = "Qwen3 Micro (1.7B)"
        "compose_file" = "docker-compose/qwen3/production/docker-compose-qwen3-micro.yml"
    }
    "mini" = @{
        "container_name" = "vllm-mini"
        "description" = "Qwen3 Mini (8B)"
        "compose_file" = "docker-compose/qwen3/production/docker-compose-qwen3-mini.yml"
    }
    "medium" = @{
        "container_name" = "vllm-medium"
        "description" = "Qwen3 Medium (32B)"
        "compose_file" = "docker-compose/qwen3/production/docker-compose-qwen3-medium.yml"
    }
}

# Patterns critiques à surveiller
$CRITICAL_PATTERNS = @(
    "ERROR",
    "CRITICAL",
    "FATAL",
    "Exception",
    "Traceback",
    "OutOfMemoryError",
    "CUDA out of memory",
    "Segmentation fault"
)

$WARNING_PATTERNS = @(
    "WARNING",
    "WARN",
    "Deprecated",
    "RetryError",
    "Timeout"
)

$INFO_PATTERNS = @(
    "INFO",
    "Finished loading",
    "Server running",
    "Model loaded",
    "Started server"
)

function Show-Help {
    Write-Host ""
    Write-Host "=== MONITOR DES LOGS QWEN3 ===" -ForegroundColor $CYAN
    Write-Host ""
    Write-Host "UTILISATION:" -ForegroundColor $YELLOW
    Write-Host "  .\monitor-logs.ps1 [-Profile <profil>] [-TailLines <n>] [-Follow] [-ErrorsOnly]"
    Write-Host ""
    Write-Host "PARAMÈTRES:" -ForegroundColor $YELLOW
    Write-Host "  -Profile      Service à monitorer: micro|mini|medium|all (défaut: all)"
    Write-Host "  -TailLines    Nombre de lignes à afficher (défaut: 50)"
    Write-Host "  -Follow       Mode suivi en temps réel (comme tail -f)"
    Write-Host "  -ErrorsOnly   Afficher uniquement les erreurs et warnings"
    Write-Host "  -OutputFile   Sauvegarder les logs dans un fichier"
    Write-Host "  -Verbose      Mode verbeux avec métadonnées"
    Write-Host "  -Help         Afficher cette aide"
    Write-Host ""
    Write-Host "EXEMPLES:" -ForegroundColor $YELLOW
    Write-Host "  .\monitor-logs.ps1                        # Logs de tous les services"
    Write-Host "  .\monitor-logs.ps1 -Profile medium -Follow # Suivi du service medium"
    Write-Host "  .\monitor-logs.ps1 -ErrorsOnly            # Erreurs uniquement"
    Write-Host "  .\monitor-logs.ps1 -OutputFile logs.txt   # Sauvegarde dans fichier"
    Write-Host ""
    exit 0
}

function Write-Log {
    param (
        [string]$Level,
        [string]$Message,
        [string]$Service = ""
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = $GREEN
    
    switch ($Level) {
        "INFO" { $color = $GREEN }
        "WARN" { $color = $YELLOW }
        "ERROR" { $color = $RED }
        "DEBUG" { $color = $BLUE }
    }
    
    $prefix = if ($Service) { "[$Service]" } else { "" }
    $logEntry = "[$timestamp] $prefix $Message"
    
    Write-Host -ForegroundColor $color $logEntry
    
    if ($OutputFile) {
        Add-Content -Path $OutputFile -Value $logEntry
    }
}

function Test-ContainerStatus {
    param (
        [string]$ContainerName
    )
    
    try {
        $containerInfo = docker ps --filter "name=$ContainerName" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>$null
        
        if ($containerInfo -match $ContainerName) {
            return $true
        } else {
            return $false
        }
    } catch {
        return $false
    }
}

function Get-ContainerLogs {
    param (
        [string]$ContainerName,
        [string]$ServiceName
    )
    
    Write-Log "INFO" "Récupération des logs..." $ServiceName
    
    if (-not (Test-ContainerStatus $ContainerName)) {
        Write-Log "ERROR" "Conteneur non trouvé ou arrêté: $ContainerName" $ServiceName
        return
    }
    
    $dockerArgs = @("logs")
    
    if ($Follow) {
        $dockerArgs += "-f"
    }
    
    $dockerArgs += "--tail", $TailLines.ToString()
    $dockerArgs += $ContainerName
    
    try {
        if ($Follow) {
            Write-Log "INFO" "Mode suivi activé (Ctrl+C pour arrêter)" $ServiceName
            & docker $dockerArgs | ForEach-Object {
                Format-LogLine $_ $ServiceName
            }
        } else {
            $logs = & docker $dockerArgs 2>&1
            
            if ($LASTEXITCODE -eq 0) {
                $logs | ForEach-Object {
                    Format-LogLine $_ $ServiceName
                }
            } else {
                Write-Log "ERROR" "Erreur lors de la récupération des logs: $($logs -join ' ')" $ServiceName
            }
        }
    } catch {
        Write-Log "ERROR" "Exception lors de la lecture des logs: $($_.Exception.Message)" $ServiceName
    }
}

function Format-LogLine {
    param (
        [string]$LogLine,
        [string]$ServiceName
    )
    
    if ([string]::IsNullOrWhiteSpace($LogLine)) {
        return
    }
    
    # Déterminer le niveau de log
    $level = "INFO"
    $color = $GREEN
    
    # Vérifier les patterns critiques
    foreach ($pattern in $CRITICAL_PATTERNS) {
        if ($LogLine -match $pattern) {
            $level = "ERROR"
            $color = $RED
            break
        }
    }
    
    # Vérifier les warnings si pas d'erreur
    if ($level -eq "INFO") {
        foreach ($pattern in $WARNING_PATTERNS) {
            if ($LogLine -match $pattern) {
                $level = "WARN"
                $color = $YELLOW
                break
            }
        }
    }
    
    # Filtrer si ErrorsOnly est activé
    if ($ErrorsOnly -and $level -eq "INFO") {
        return
    }
    
    # Formater et afficher
    $timestamp = Get-Date -Format "HH:mm:ss"
    $prefix = "[$timestamp] [$ServiceName] [$level]"
    
    if ($Verbose) {
        Write-Host -ForegroundColor $color "$prefix $LogLine"
    } else {
        # Version compacte
        $cleanLine = $LogLine -replace '^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', '' # Supprimer timestamp Docker
        $cleanLine = $cleanLine -replace '^\s*\[.*?\]\s*', '' # Supprimer préfixes
        Write-Host -ForegroundColor $color "$prefix $cleanLine"
    }
    
    # Sauvegarder si demandé
    if ($OutputFile) {
        Add-Content -Path $OutputFile -Value "$prefix $LogLine"
    }
}

function Show-ServiceStatus {
    param (
        [array]$ServiceNames
    )
    
    Write-Log "INFO" "=== STATUT DES SERVICES QWEN3 ==="
    
    foreach ($serviceName in $ServiceNames) {
        $service = $SERVICES[$serviceName]
        $containerName = $service.container_name
        
        if (Test-ContainerStatus $containerName) {
            $status = "✅ ACTIF"
            $color = $GREEN
        } else {
            $status = "❌ ARRÊTÉ"
            $color = $RED
        }
        
        Write-Host -ForegroundColor $color "  $serviceName ($($service.description)): $status"
        
        if ($Verbose) {
            try {
                $containerInfo = docker inspect $containerName --format "{{.State.Status}} - Démarré: {{.State.StartedAt}}" 2>$null
                if ($containerInfo) {
                    Write-Host -ForegroundColor $BLUE "    Détails: $containerInfo"
                }
            } catch {
                # Ignorer les erreurs de détail
            }
        }
    }
    Write-Log "INFO" ""
}

function Monitor-Services {
    param (
        [array]$ServiceNames
    )
    
    foreach ($serviceName in $ServiceNames) {
        $service = $SERVICES[$serviceName]
        $containerName = $service.container_name
        
        Write-Log "INFO" "=== MONITORING: $serviceName ($($service.description)) ==="
        
        if ($ServiceNames.Count -gt 1 -and -not $Follow) {
            Write-Log "INFO" "Conteneur: $containerName"
            Write-Log "INFO" "Dernières $TailLines lignes:"
            Write-Host ""
        }
        
        Get-ContainerLogs $containerName $serviceName
        
        if ($ServiceNames.Count -gt 1 -and -not $Follow) {
            Write-Host ""
            Write-Log "INFO" "--- Fin des logs pour $serviceName ---"
            Write-Host ""
        }
    }
}

function Main {
    if ($Help) {
        Show-Help
    }
    
    Write-Log "INFO" "=== MONITORING DES LOGS QWEN3 ==="
    
    # Déterminer les services à monitorer
    $servicesToMonitor = if ($Profile -eq "all") { $SERVICES.Keys } else { @($Profile) }
    
    # Vérifier que les services existent
    foreach ($serviceName in $servicesToMonitor) {
        if (-not $SERVICES.ContainsKey($serviceName)) {
            Write-Log "ERROR" "Service inconnu: $serviceName"
            Write-Log "INFO" "Services disponibles: $($SERVICES.Keys -join ', ')"
            exit 1
        }
    }
    
    # Afficher le statut des services
    Show-ServiceStatus $servicesToMonitor
    
    # Informations sur la session
    Write-Log "INFO" "Configuration:"
    Write-Log "INFO" "  - Services: $($servicesToMonitor -join ', ')"
    Write-Log "INFO" "  - Lignes: $TailLines"
    Write-Log "INFO" "  - Mode suivi: $(if($Follow){'Activé'}else{'Désactivé'})"
    Write-Log "INFO" "  - Erreurs seulement: $(if($ErrorsOnly){'Activé'}else{'Désactivé'})"
    if ($OutputFile) {
        Write-Log "INFO" "  - Fichier de sortie: $OutputFile"
    }
    Write-Host ""
    
    # Commencer le monitoring
    try {
        Monitor-Services $servicesToMonitor
    } catch {
        Write-Log "ERROR" "Erreur durant le monitoring: $($_.Exception.Message)"
        exit 1
    }
    
    Write-Log "INFO" "Monitoring terminé."
}

# Gestion des signaux pour Follow mode
if ($Follow) {
    # Configuration pour gérer Ctrl+C proprement
    $null = [System.Console]::TreatControlCAsInput = $false
    [System.Console]::CancelKeyPress = {
        param($sender, $e)
        Write-Host ""
        Write-Log "INFO" "Arrêt du monitoring demandé par l'utilisateur"
        $e.Cancel = $false
    }
}

# Point d'entrée
Main