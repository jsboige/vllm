<#
.SYNOPSIS
    Script de monitoring actif pour le Grid Search vLLM en cours d'exécution

.DESCRIPTION
    Surveille en temps réel l'exécution du grid search en affichant :
    - Configuration en cours de test
    - Progression (N/12 configs)
    - Temps écoulé et temps restant estimé
    - Logs récents du grid search
    - Détection des erreurs critiques
    
    Ce script est conçu pour être exécuté PENDANT que grid_search_optimization.ps1
    tourne en arrière-plan.

.PARAMETER LogFile
    Chemin vers le fichier de log principal du grid search.
    Si non spécifié, recherche automatiquement le log le plus récent.

.PARAMETER RefreshInterval
    Intervalle de rafraîchissement en secondes (défaut: 10s)

.PARAMETER TailLines
    Nombre de lignes de log à afficher (défaut: 20)

.EXAMPLE
    .\monitor_grid_search.ps1
    Lance le monitoring avec détection automatique du log le plus récent.

.EXAMPLE
    .\monitor_grid_search.ps1 -LogFile "logs\grid_search_20251018_183000.log" -RefreshInterval 5
    Monitoring avec log spécifique et rafraîchissement toutes les 5 secondes.

.NOTES
    Version: 1.0.0
    Date: 2025-10-18
    Auteur: Roo Code (Mode)
    Utilisation: Lancez ce script dans un terminal séparé pendant le grid search
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$LogFile = "",
    
    [Parameter(Mandatory=$false)]
    [int]$RefreshInterval = 10,
    
    [Parameter(Mandatory=$false)]
    [int]$TailLines = 20
)

# =============================================================================
# CONFIGURATION
# =============================================================================

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$LogsDir = Join-Path $ProjectRoot "logs"
$ProgressFile = Join-Path $ProjectRoot "grid_search_progress.json"

# Couleurs pour affichage
$Colors = @{
    Header = "Cyan"
    Success = "Green"
    Warning = "Yellow"
    Error = "Red"
    Info = "White"
    Highlight = "Magenta"
}

# Constantes
$TOTAL_CONFIGS = 12
$AVG_TIME_PER_CONFIG_MIN = 8.5  # Moyenne entre 6 et 11 minutes

# =============================================================================
# FONCTIONS UTILITAIRES
# =============================================================================

function Get-LatestGridSearchLog {
    <#
    .SYNOPSIS
        Trouve automatiquement le fichier de log le plus récent du grid search.
    #>
    
    if (-not (Test-Path $LogsDir)) {
        Write-Host "Répertoire logs introuvable : $LogsDir" -ForegroundColor Red
        return $null
    }
    
    $LogFiles = Get-ChildItem -Path $LogsDir -Filter "grid_search_*.log" -File | 
                Sort-Object LastWriteTime -Descending
    
    if ($LogFiles.Count -eq 0) {
        Write-Host "Aucun fichier de log grid search trouvé dans : $LogsDir" -ForegroundColor Red
        return $null
    }
    
    return $LogFiles[0].FullName
}

function Get-GridSearchProgress {
    <#
    .SYNOPSIS
        Lit le fichier de progression pour déterminer l'état actuel.
    .OUTPUTS
        Hashtable avec current_config, completed_count, remaining_count
    #>
    
    $Progress = @{
        current_config = "Inconnu"
        completed_count = 0
        remaining_count = $TOTAL_CONFIGS
        percentage = 0
    }
    
    if (-not (Test-Path $ProgressFile)) {
        return $Progress
    }
    
    try {
        $ProgressData = Get-Content -Path $ProgressFile -Raw | ConvertFrom-Json
        
        $CompletedCount = $ProgressData.completed_indices.Count
        $Progress.current_config = $ProgressData.last_completed_config
        $Progress.completed_count = $CompletedCount
        $Progress.remaining_count = $TOTAL_CONFIGS - $CompletedCount
        $Progress.percentage = [math]::Round(($CompletedCount / $TOTAL_CONFIGS) * 100, 1)
        
        return $Progress
    }
    catch {
        Write-Host "Erreur lors de la lecture du fichier de progression : $_" -ForegroundColor Yellow
        return $Progress
    }
}

function Get-CurrentConfigFromLog {
    <#
    .SYNOPSIS
        Parse les dernières lignes du log pour identifier la configuration en cours.
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string]$LogPath
    )
    
    if (-not (Test-Path $LogPath)) {
        return "Log introuvable"
    }
    
    try {
        # Lire les 50 dernières lignes pour trouver la dernière mention de config
        $LastLines = Get-Content -Path $LogPath -Tail 50
        
        # Chercher le pattern "CONFIGURATION X/12 : nom_config"
        foreach ($line in ($LastLines | Select-Object -Last 50 | Sort-Object -Descending)) {
            if ($line -match 'CONFIGURATION\s+(\d+)/\d+\s+:\s+(.+)') {
                $ConfigNum = $Matches[1]
                $ConfigName = $Matches[2].Trim()
                return "$ConfigNum/12: $ConfigName"
            }
        }
        
        return "En attente de démarrage..."
    }
    catch {
        return "Erreur parsing log"
    }
}

function Get-EstimatedTimeRemaining {
    <#
    .SYNOPSIS
        Calcule le temps restant estimé basé sur la progression.
    #>
    param(
        [Parameter(Mandatory=$true)]
        [hashtable]$Progress,
        
        [Parameter(Mandatory=$true)]
        [datetime]$StartTime
    )
    
    $Elapsed = (Get-Date) - $StartTime
    $ElapsedMinutes = $Elapsed.TotalMinutes
    
    if ($Progress.completed_count -eq 0) {
        # Aucune config terminée, estimation basée sur moyenne
        $RemainingMinutes = $AVG_TIME_PER_CONFIG_MIN * $TOTAL_CONFIGS
    }
    else {
        # Calcul basé sur le temps réel écoulé
        $AvgTimePerCompletedConfig = $ElapsedMinutes / $Progress.completed_count
        $RemainingMinutes = $AvgTimePerCompletedConfig * $Progress.remaining_count
    }
    
    return [TimeSpan]::FromMinutes($RemainingMinutes)
}

function Get-RecentLogErrors {
    <#
    .SYNOPSIS
        Détecte les erreurs critiques dans les dernières lignes du log.
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string]$LogPath,
        
        [Parameter(Mandatory=$false)]
        [int]$Lines = 50
    )
    
    if (-not (Test-Path $LogPath)) {
        return @()
    }
    
    try {
        $LastLines = Get-Content -Path $LogPath -Tail $Lines
        
        $Errors = @()
        
        foreach ($line in $LastLines) {
            if ($line -match '\[Error\]|\[Critical\]|✗|ÉCHEC|Erreur|Exception|Timeout|Crash') {
                $Errors += $line
            }
        }
        
        return $Errors
    }
    catch {
        return @()
    }
}

function Show-MonitoringHeader {
    <#
    .SYNOPSIS
        Affiche l'en-tête du monitoring.
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string]$LogPath,
        
        [Parameter(Mandatory=$true)]
        [datetime]$StartTime
    )
    
    Clear-Host
    
    Write-Host "╔═══════════════════════════════════════════════════════════════════════════╗" -ForegroundColor $Colors.Header
    Write-Host "║          GRID SEARCH MONITORING - vLLM Optimization en cours             ║" -ForegroundColor $Colors.Header
    Write-Host "╚═══════════════════════════════════════════════════════════════════════════╝" -ForegroundColor $Colors.Header
    Write-Host ""
    Write-Host "Fichier de log surveillé : " -NoNewline -ForegroundColor $Colors.Info
    Write-Host $LogPath -ForegroundColor $Colors.Highlight
    Write-Host "Heure de début           : " -NoNewline -ForegroundColor $Colors.Info
    Write-Host $StartTime.ToString("yyyy-MM-dd HH:mm:ss") -ForegroundColor $Colors.Highlight
    Write-Host "Rafraîchissement         : " -NoNewline -ForegroundColor $Colors.Info
    Write-Host "Toutes les $RefreshInterval secondes" -ForegroundColor $Colors.Highlight
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════════════════════════════" -ForegroundColor $Colors.Info
    Write-Host ""
}

function Show-ProgressBar {
    <#
    .SYNOPSIS
        Affiche une barre de progression visuelle.
    #>
    param(
        [Parameter(Mandatory=$true)]
        [int]$Percentage
    )
    
    $BarLength = 50
    $FilledLength = [math]::Floor(($Percentage / 100) * $BarLength)
    $EmptyLength = $BarLength - $FilledLength
    
    $Bar = ("[" + 
            ("█" * $FilledLength) + 
            ("░" * $EmptyLength) + 
            "] $Percentage%")
    
    if ($Percentage -lt 33) {
        Write-Host $Bar -ForegroundColor Red
    }
    elseif ($Percentage -lt 66) {
        Write-Host $Bar -ForegroundColor Yellow
    }
    else {
        Write-Host $Bar -ForegroundColor Green
    }
}

function Format-TimeSpan {
    <#
    .SYNOPSIS
        Formate un TimeSpan en chaîne lisible.
    #>
    param(
        [Parameter(Mandatory=$true)]
        [TimeSpan]$TimeSpan
    )
    
    $Hours = [math]::Floor($TimeSpan.TotalHours)
    $Minutes = $TimeSpan.Minutes
    $Seconds = $TimeSpan.Seconds
    
    if ($Hours -gt 0) {
        return "${Hours}h ${Minutes}m ${Seconds}s"
    }
    elseif ($Minutes -gt 0) {
        return "${Minutes}m ${Seconds}s"
    }
    else {
        return "${Seconds}s"
    }
}

# =============================================================================
# BOUCLE PRINCIPALE DE MONITORING
# =============================================================================

try {
    # Déterminer le fichier de log à surveiller
    if ([string]::IsNullOrEmpty($LogFile)) {
        Write-Host "Recherche automatique du log le plus récent..." -ForegroundColor Cyan
        $LogFile = Get-LatestGridSearchLog
        
        if (-not $LogFile) {
            Write-Host "Aucun log trouvé. Assurez-vous que grid_search_optimization.ps1 est en cours d'exécution." -ForegroundColor Red
            exit 1
        }
        
        Write-Host "Log trouvé : $LogFile" -ForegroundColor Green
        Start-Sleep -Seconds 2
    }
    
    if (-not (Test-Path $LogFile)) {
        Write-Host "Fichier de log introuvable : $LogFile" -ForegroundColor Red
        exit 1
    }
    
    # Déterminer l'heure de début (création du fichier log)
    $StartTime = (Get-Item $LogFile).CreationTime
    
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════════════════════════════" -ForegroundColor Green
    Write-Host "  MONITORING ACTIF - Appuyez sur CTRL+C pour quitter" -ForegroundColor Green
    Write-Host "═══════════════════════════════════════════════════════════════════════════" -ForegroundColor Green
    Write-Host ""
    Start-Sleep -Seconds 2
    
    # Boucle de monitoring infinie
    while ($true) {
        # Récupérer les informations actuelles
        $Progress = Get-GridSearchProgress
        $CurrentConfig = Get-CurrentConfigFromLog -LogPath $LogFile
        $Elapsed = (Get-Date) - $StartTime
        $Remaining = Get-EstimatedTimeRemaining -Progress $Progress -StartTime $StartTime
        $Errors = Get-RecentLogErrors -LogPath $LogFile -Lines 100
        
        # Afficher l'en-tête
        Show-MonitoringHeader -LogPath $LogFile -StartTime $StartTime
        
        # Afficher la progression
        Write-Host "📊 PROGRESSION GLOBALE" -ForegroundColor $Colors.Header
        Write-Host "─────────────────────────────────────────────────────────────────────────" -ForegroundColor $Colors.Info
        Write-Host ""
        
        Write-Host "Configuration en cours : " -NoNewline -ForegroundColor $Colors.Info
        Write-Host $CurrentConfig -ForegroundColor $Colors.Highlight
        
        Write-Host "Configs terminées      : " -NoNewline -ForegroundColor $Colors.Info
        Write-Host "$($Progress.completed_count)/$TOTAL_CONFIGS" -ForegroundColor $Colors.Success
        
        Write-Host "Configs restantes      : " -NoNewline -ForegroundColor $Colors.Info
        Write-Host $Progress.remaining_count -ForegroundColor $Colors.Warning
        
        Write-Host ""
        Write-Host "Progression            : " -NoNewline -ForegroundColor $Colors.Info
        Show-ProgressBar -Percentage $Progress.percentage
        
        Write-Host ""
        
        # Afficher les temps
        Write-Host "⏱️  TEMPS" -ForegroundColor $Colors.Header
        Write-Host "─────────────────────────────────────────────────────────────────────────" -ForegroundColor $Colors.Info
        Write-Host ""
        
        Write-Host "Temps écoulé           : " -NoNewline -ForegroundColor $Colors.Info
        Write-Host (Format-TimeSpan -TimeSpan $Elapsed) -ForegroundColor $Colors.Highlight
        
        Write-Host "Temps restant (estimé) : " -NoNewline -ForegroundColor $Colors.Info
        Write-Host (Format-TimeSpan -TimeSpan $Remaining) -ForegroundColor $Colors.Warning
        
        $EstimatedEnd = (Get-Date).Add($Remaining)
        Write-Host "Heure de fin estimée   : " -NoNewline -ForegroundColor $Colors.Info
        Write-Host $EstimatedEnd.ToString("HH:mm:ss") -ForegroundColor $Colors.Highlight
        
        Write-Host ""
        
        # Afficher les erreurs récentes
        if ($Errors.Count -gt 0) {
            Write-Host "⚠️  ERREURS RÉCENTES ($($Errors.Count) détectées)" -ForegroundColor $Colors.Error
            Write-Host "─────────────────────────────────────────────────────────────────────────" -ForegroundColor $Colors.Info
            Write-Host ""
            
            foreach ($error in ($Errors | Select-Object -Last 5)) {
                Write-Host "  • $error" -ForegroundColor $Colors.Error
            }
            
            Write-Host ""
        }
        
        # Afficher les dernières lignes du log
        Write-Host "📄 LOGS RÉCENTS (dernières $TailLines lignes)" -ForegroundColor $Colors.Header
        Write-Host "─────────────────────────────────────────────────────────────────────────" -ForegroundColor $Colors.Info
        Write-Host ""
        
        $RecentLogs = Get-Content -Path $LogFile -Tail $TailLines
        
        foreach ($line in $RecentLogs) {
            # Coloriser selon le niveau de log
            if ($line -match '\[Success\]|✓') {
                Write-Host $line -ForegroundColor $Colors.Success
            }
            elseif ($line -match '\[Warning\]|⚠️') {
                Write-Host $line -ForegroundColor $Colors.Warning
            }
            elseif ($line -match '\[Error\]|\[Critical\]|✗') {
                Write-Host $line -ForegroundColor $Colors.Error
            }
            elseif ($line -match 'CONFIGURATION|═══') {
                Write-Host $line -ForegroundColor $Colors.Highlight
            }
            else {
                Write-Host $line -ForegroundColor $Colors.Info
            }
        }
        
        Write-Host ""
        Write-Host "═══════════════════════════════════════════════════════════════════════════" -ForegroundColor $Colors.Info
        Write-Host "Prochain rafraîchissement dans $RefreshInterval secondes... (CTRL+C pour quitter)" -ForegroundColor $Colors.Warning
        Write-Host ""
        
        # Attendre avant le prochain rafraîchissement
        Start-Sleep -Seconds $RefreshInterval
    }
}
catch {
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════════════════════════════" -ForegroundColor Red
    Write-Host "Monitoring interrompu" -ForegroundColor Red
    Write-Host "═══════════════════════════════════════════════════════════════════════════" -ForegroundColor Red
    Write-Host ""
    Write-Host "Raison : $_" -ForegroundColor Yellow
    Write-Host ""
    exit 0
}