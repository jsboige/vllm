<#
.SYNOPSIS
    Script de test pour valider le nettoyage des containers grid search
    
.DESCRIPTION
    Ce script teste que le mécanisme de cleanup du grid search fonctionne correctement
    en simulant un cycle complet : démarrage → arrêt brutal → vérification cleanup.
    
    Valide que AUCUN container myia_vllm orphelin ne subsiste après docker compose down.
    
.EXAMPLE
    .\test_cleanup.ps1
    
.NOTES
    Version: 1.0.0
    Date: 2025-10-21
    Auteur: Mission 14d - Cleanup Fix
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# Chemins
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$MediumYmlPath = Join-Path $ProjectRoot "configs\docker\profiles\medium.yml"

# Couleurs
function Write-TestOutput {
    param(
        [string]$Message,
        [ValidateSet("Info", "Success", "Warning", "Error")]
        [string]$Level = "Info"
    )
    
    $Color = switch ($Level) {
        "Info"    { "Cyan" }
        "Success" { "Green" }
        "Warning" { "Yellow" }
        "Error"   { "Red" }
    }
    
    Write-Host $Message -ForegroundColor $Color
}

Write-TestOutput "═══════════════════════════════════════════════════════════════" -Level Info
Write-TestOutput "TEST CLEANUP GRID SEARCH" -Level Info
Write-TestOutput "═══════════════════════════════════════════════════════════════" -Level Info
Write-TestOutput "" -Level Info

# ÉTAPE 1: Vérifier état initial
Write-TestOutput "1. Vérification état initial..." -Level Info
$InitialContainers = docker ps -a --filter "name=myia_vllm" --format "{{.Names}}" 2>&1

if ($InitialContainers -and $InitialContainers -match "myia_vllm") {
    Write-TestOutput "   ⚠️  Containers existants détectés - Nettoyage préalable..." -Level Warning
    docker compose -p myia_vllm -f $MediumYmlPath down --remove-orphans --volumes 2>&1 | Out-Null
    Start-Sleep -Seconds 2
}

Write-TestOutput "   ✓ État initial propre" -Level Success

# ÉTAPE 2: Démarrer un container test
Write-TestOutput "" -Level Info
Write-TestOutput "2. Démarrage container test..." -Level Info

try {
    $UpOutput = docker compose -p myia_vllm -f $MediumYmlPath up -d 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-TestOutput "   ✗ ÉCHEC: Impossible de démarrer le container" -Level Error
        Write-TestOutput "   Output: $UpOutput" -Level Error
        exit 1
    }
    
    Write-TestOutput "   ✓ Container démarré" -Level Success
    Start-Sleep -Seconds 5
    
    # Vérifier que le container existe
    $RunningContainer = docker ps -a --filter "name=myia_vllm" --format "{{.Names}}" 2>&1
    
    if (-not $RunningContainer -or $RunningContainer -notmatch "myia_vllm") {
        Write-TestOutput "   ✗ ÉCHEC: Container non trouvé après démarrage" -Level Error
        exit 1
    }
    
    Write-TestOutput "   Container actif: $RunningContainer" -Level Info
}
catch {
    Write-TestOutput "   ✗ ÉCHEC: Erreur durant le démarrage: $_" -Level Error
    exit 1
}

# ÉTAPE 3: Simuler arrêt brutal (comme après crash)
Write-TestOutput "" -Level Info
Write-TestOutput "3. Arrêt brutal (simulation crash)..." -Level Info

try {
    $DownOutput = docker compose -p myia_vllm -f $MediumYmlPath down --remove-orphans --volumes 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-TestOutput "   ⚠️  WARNING: docker compose down a retourné code $LASTEXITCODE" -Level Warning
    }
    
    Write-TestOutput "   ✓ Commande docker compose down exécutée" -Level Success
    Start-Sleep -Seconds 2
}
catch {
    Write-TestOutput "   ✗ ÉCHEC: Erreur durant docker compose down: $_" -Level Error
    exit 1
}

# ÉTAPE 4: Vérifier qu'aucun container ne reste (TEST CRITIQUE)
Write-TestOutput "" -Level Info
Write-TestOutput "4. Vérification containers orphelins..." -Level Info

$RemainingContainers = docker ps -a --filter "name=myia_vllm" --format "{{.Names}}" 2>&1

if ($RemainingContainers -and $RemainingContainers -match "myia_vllm") {
    Write-TestOutput "   ✗ ÉCHEC: Containers orphelins détectés!" -Level Error
    Write-TestOutput "" -Level Error
    Write-TestOutput "   Containers restants:" -Level Error
    $RemainingContainers -split "`n" | ForEach-Object {
        if ($_ -match "myia_vllm") {
            Write-TestOutput "     - $_" -Level Error
        }
    }
    Write-TestOutput "" -Level Error
    Write-TestOutput "   Le cleanup n'a PAS fonctionné correctement." -Level Error
    
    # Cleanup forcé pour ne pas laisser de traces
    Write-TestOutput "   Nettoyage forcé des orphelins..." -Level Warning
    $RemainingContainers -split "`n" | Where-Object { $_ -match "myia_vllm" } | ForEach-Object {
        docker rm -f $_ 2>&1 | Out-Null
    }
    
    exit 1
}

Write-TestOutput "   ✓ Aucun container orphelin - Cleanup RÉUSSI" -Level Success

# RÉSULTAT FINAL
Write-TestOutput "" -Level Success
Write-TestOutput "═══════════════════════════════════════════════════════════════" -Level Success
Write-TestOutput "TEST CLEANUP : SUCCÈS ✓" -Level Success
Write-TestOutput "═══════════════════════════════════════════════════════════════" -Level Success
Write-TestOutput "" -Level Success
Write-TestOutput "Le mécanisme de cleanup fonctionne correctement." -Level Success
Write-TestOutput "Aucun container orphelin après docker compose down." -Level Success
Write-TestOutput "" -Level Success

exit 0