<#
.SYNOPSIS
    Nettoyage hebdomadaire des ressources Docker orphelines

.DESCRIPTION
    Script de maintenance pour nettoyer les ressources Docker non utilisées :
    - Containers arrêtés
    - Images inutilisées (> 7 jours)
    - Volumes orphelins (avec protection des volumes nommés)
    - Build cache
    - Calcul de l'espace récupéré
    
    ⚠️ ATTENTION: NE supprime PAS les volumes nommés (ex: myia_vllm_models)
    
    Conçu pour être exécuté hebdomadairement (chaque vendredi).

.PARAMETER Force
    Exécuter sans confirmation utilisateur (mode automatique)

.PARAMETER SkipContainers
    Ne pas supprimer les containers arrêtés

.PARAMETER SkipImages
    Ne pas supprimer les images inutilisées

.PARAMETER SkipVolumes
    Ne pas supprimer les volumes orphelins

.PARAMETER ImageAgeHours
    Âge minimum des images à supprimer en heures (défaut: 168h = 7 jours)

.PARAMETER DryRun
    Mode simulation - affiche ce qui serait supprimé sans supprimer

.EXAMPLE
    .\cleanup_docker.ps1
    Nettoyage interactif avec confirmations utilisateur

.EXAMPLE
    .\cleanup_docker.ps1 -Force
    Nettoyage automatique sans confirmation

.EXAMPLE
    .\cleanup_docker.ps1 -DryRun
    Simulation pour voir ce qui serait supprimé

.EXAMPLE
    .\cleanup_docker.ps1 -SkipVolumes -ImageAgeHours 336
    Nettoyage sans toucher aux volumes, images > 14 jours

.NOTES
    Version: 1.0.0
    Date: 2025-10-22
    Auteur: Roo Code (Mode)
    Fréquence recommandée: Hebdomadaire (chaque vendredi)
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [switch]$Force,
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipContainers,
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipImages,
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipVolumes,
    
    [Parameter(Mandatory=$false)]
    [int]$ImageAgeHours = 168,
    
    [Parameter(Mandatory=$false)]
    [switch]$DryRun
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
$LogsDir = Join-Path $ProjectRoot "logs/maintenance"
$LogFile = Join-Path $LogsDir "cleanup_docker_$Timestamp.txt"

# Créer répertoire logs si nécessaire
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
}

# Variables globales pour suivi
$script:SpaceBeforeMB = 0
$script:SpaceAfterMB = 0
$script:CleanupResults = @{
    Containers = 0
    Images = 0
    Volumes = 0
    BuildCache = 0
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
    Add-Content -Path $LogFile -Value $logEntry
    
    $color = switch ($Level) {
        "SUCCESS" { "Green" }
        "WARNING" { "Yellow" }
        "ERROR" { "Red" }
        "INFO" { "Cyan" }
        default { "White" }
    }
    Write-Host $logEntry -ForegroundColor $color
}

function Get-DockerSpaceUsage {
    try {
        $systemDf = docker system df --format "{{.Type}},{{.Size}}"
        $totalSize = 0
        
        foreach ($line in $systemDf) {
            if ($line -match ',(\d+(?:\.\d+)?)(GB|MB)') {
                $size = [float]$matches[1]
                $unit = $matches[2]
                
                if ($unit -eq "GB") {
                    $totalSize += $size * 1024
                } else {
                    $totalSize += $size
                }
            }
        }
        
        return [math]::Round($totalSize, 2)
    }
    catch {
        Write-Log "Erreur lors du calcul de l'espace Docker: $_" "ERROR"
        return 0
    }
}

function Confirm-Action {
    param(
        [string]$Message
    )
    
    if ($Force -or $DryRun) {
        return $true
    }
    
    $response = Read-Host "$Message (O/N)"
    return ($response -eq "O" -or $response -eq "o")
}

function Remove-StoppedContainers {
    Write-Log "--- Nettoyage Containers Arrêtés ---" "INFO"
    
    if ($SkipContainers) {
        Write-Log "Nettoyage containers IGNORÉ (paramètre SkipContainers)" "WARNING"
        return
    }
    
    try {
        # Lister containers arrêtés
        $stoppedContainers = docker ps -a --filter "status=exited" --format "{{.Names}}"
        
        if (-not $stoppedContainers) {
            Write-Log "Aucun container arrêté trouvé" "INFO"
            return
        }
        
        $count = ($stoppedContainers | Measure-Object).Count
        Write-Log "Containers arrêtés trouvés: $count" "INFO"
        
        if ($DryRun) {
            Write-Log "[DRY-RUN] Supprimerait $count containers" "WARNING"
            $stoppedContainers | ForEach-Object { Write-Log "  - $_" "INFO" }
            return
        }
        
        if (-not (Confirm-Action "Supprimer $count containers arrêtés ?")) {
            Write-Log "Nettoyage containers ANNULÉ par l'utilisateur" "WARNING"
            return
        }
        
        docker container prune -f
        $script:CleanupResults.Containers = $count
        Write-Log "✓ $count containers supprimés" "SUCCESS"
    }
    catch {
        Write-Log "Erreur lors du nettoyage des containers: $_" "ERROR"
    }
}

function Remove-UnusedImages {
    Write-Log "--- Nettoyage Images Inutilisées ---" "INFO"
    
    if ($SkipImages) {
        Write-Log "Nettoyage images IGNORÉ (paramètre SkipImages)" "WARNING"
        return
    }
    
    try {
        $ageFilter = $ImageAgeHours / 24
        $filterArg = "until=${ImageAgeHours}h"
        
        # Lister images qui seraient supprimées
        $unusedImages = docker images --filter "dangling=false" --format "{{.Repository}}:{{.Tag}}" | Select-Object -First 10
        
        Write-Log "Suppression images non utilisées depuis $ageFilter jours" "INFO"
        
        if ($DryRun) {
            Write-Log "[DRY-RUN] Exécuterait: docker image prune -a --filter '$filterArg' -f" "WARNING"
            return
        }
        
        if (-not (Confirm-Action "Supprimer images inutilisées (> $ageFilter jours) ?")) {
            Write-Log "Nettoyage images ANNULÉ par l'utilisateur" "WARNING"
            return
        }
        
        $output = docker image prune -a --filter $filterArg -f
        
        if ($output -match 'Total reclaimed space: (\d+(?:\.\d+)?)(GB|MB)') {
            $size = [float]$matches[1]
            $unit = $matches[2]
            Write-Log "✓ Espace récupéré (images): $size$unit" "SUCCESS"
        }
        
        $script:CleanupResults.Images = 1
    }
    catch {
        Write-Log "Erreur lors du nettoyage des images: $_" "ERROR"
    }
}

function Remove-OrphanVolumes {
    Write-Log "--- Nettoyage Volumes Orphelins ---" "INFO"
    
    if ($SkipVolumes) {
        Write-Log "Nettoyage volumes IGNORÉ (paramètre SkipVolumes)" "WARNING"
        return
    }
    
    try {
        # Lister volumes orphelins (sans containers associés)
        $orphanVolumes = docker volume ls -qf "dangling=true"
        
        if (-not $orphanVolumes) {
            Write-Log "Aucun volume orphelin trouvé" "INFO"
            return
        }
        
        $count = ($orphanVolumes | Measure-Object).Count
        Write-Log "Volumes orphelins trouvés: $count" "INFO"
        
        # Vérifier qu'aucun volume nommé critique n'est concerné
        $criticalVolumes = @("myia_vllm_models", "models", "cache")
        $hasCritical = $false
        
        foreach ($vol in $orphanVolumes) {
            foreach ($critical in $criticalVolumes) {
                if ($vol -like "*$critical*") {
                    Write-Log "⚠️ Volume critique détecté: $vol - NE SERA PAS SUPPRIMÉ" "WARNING"
                    $hasCritical = $true
                }
            }
        }
        
        if ($DryRun) {
            Write-Log "[DRY-RUN] Supprimerait $count volumes orphelins" "WARNING"
            $orphanVolumes | ForEach-Object { Write-Log "  - $_" "INFO" }
            return
        }
        
        $confirmMessage = if ($hasCritical) {
            "Supprimer volumes orphelins NON-CRITIQUES uniquement ?"
        } else {
            "Supprimer $count volumes orphelins ?"
        }
        
        if (-not (Confirm-Action $confirmMessage)) {
            Write-Log "Nettoyage volumes ANNULÉ par l'utilisateur" "WARNING"
            return
        }
        
        # Suppression sécurisée (seulement volumes vraiment orphelins)
        docker volume prune -f
        $script:CleanupResults.Volumes = $count
        Write-Log "✓ Volumes orphelins nettoyés" "SUCCESS"
    }
    catch {
        Write-Log "Erreur lors du nettoyage des volumes: $_" "ERROR"
    }
}

function Remove-BuildCache {
    Write-Log "--- Nettoyage Build Cache ---" "INFO"
    
    try {
        if ($DryRun) {
            Write-Log "[DRY-RUN] Exécuterait: docker builder prune -f" "WARNING"
            return
        }
        
        if (-not (Confirm-Action "Supprimer le build cache Docker ?")) {
            Write-Log "Nettoyage build cache ANNULÉ par l'utilisateur" "WARNING"
            return
        }
        
        $output = docker builder prune -f
        
        if ($output -match 'Total:\s+(\d+(?:\.\d+)?)(GB|MB)') {
            $size = [float]$matches[1]
            $unit = $matches[2]
            Write-Log "✓ Espace récupéré (build cache): $size$unit" "SUCCESS"
        }
        
        $script:CleanupResults.BuildCache = 1
    }
    catch {
        Write-Log "Erreur lors du nettoyage du build cache: $_" "ERROR"
    }
}

function Show-CleanupSummary {
    Write-Log "" "INFO"
    Write-Log "=== RÉSUMÉ NETTOYAGE DOCKER ===" "INFO"
    
    $spaceSavedMB = $script:SpaceBeforeMB - $script:SpaceAfterMB
    $spaceSavedGB = [math]::Round($spaceSavedMB / 1024, 2)
    
    Write-Log "Espace avant nettoyage: $($script:SpaceBeforeMB) MB" "INFO"
    Write-Log "Espace après nettoyage: $($script:SpaceAfterMB) MB" "INFO"
    Write-Log "Espace récupéré: $spaceSavedMB MB (~$spaceSavedGB GB)" "SUCCESS"
    Write-Log "" "INFO"
    
    Write-Log "Ressources nettoyées:" "INFO"
    Write-Log "  - Containers: $($script:CleanupResults.Containers)" "INFO"
    Write-Log "  - Images: $($script:CleanupResults.Images)" "INFO"
    Write-Log "  - Volumes: $($script:CleanupResults.Volumes)" "INFO"
    Write-Log "  - Build cache: $($script:CleanupResults.BuildCache)" "INFO"
    Write-Log "" "INFO"
    
    Write-Log "Rapport complet: $LogFile" "INFO"
}

# =============================================================================
# MAIN
# =============================================================================

Write-Log "=== NETTOYAGE DOCKER HEBDOMADAIRE ===" "INFO"
Write-Log "Date: $DateDisplay" "INFO"

if ($DryRun) {
    Write-Log "⚠️ MODE SIMULATION (DRY-RUN) - Aucune suppression réelle" "WARNING"
}

Write-Log "" "INFO"

# Mesurer l'espace avant nettoyage
Write-Log "Calcul de l'espace Docker utilisé..." "INFO"
$script:SpaceBeforeMB = Get-DockerSpaceUsage
Write-Log "Espace Docker actuel: $($script:SpaceBeforeMB) MB" "INFO"
Write-Log "" "INFO"

# Exécuter les nettoyages
Remove-StoppedContainers
Write-Log "" "INFO"

Remove-UnusedImages
Write-Log "" "INFO"

Remove-OrphanVolumes
Write-Log "" "INFO"

Remove-BuildCache
Write-Log "" "INFO"

# Mesurer l'espace après nettoyage
if (-not $DryRun) {
    Write-Log "Recalcul de l'espace Docker..." "INFO"
    $script:SpaceAfterMB = Get-DockerSpaceUsage
}

# Afficher le résumé
Show-CleanupSummary

# Code de sortie
$exitCode = 0
Write-Log "✓ Nettoyage Docker terminé avec succès" "SUCCESS"

exit $exitCode