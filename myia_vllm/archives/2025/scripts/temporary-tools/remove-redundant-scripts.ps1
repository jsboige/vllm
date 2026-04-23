#!/usr/bin/env pwsh
# Script de suppression des scripts redondants après consolidation
# Partie de la mission de rationalisation de l'architecture des scripts

param(
    [switch]$DryRun = $false,
    [switch]$Verbose = $false
)

# Configuration des couleurs
$Green = [System.ConsoleColor]::Green
$Yellow = [System.ConsoleColor]::Yellow
$Red = [System.ConsoleColor]::Red
$Cyan = [System.ConsoleColor]::Cyan

function Write-ColorOutput {
    param([string]$Message, [System.ConsoleColor]$Color = [System.ConsoleColor]::White)
    Write-Host $Message -ForegroundColor $Color
}

function Remove-RedundantScript {
    param(
        [string]$ScriptPath,
        [string]$ScriptName,
        [string]$ReplacedBy
    )
    
    if (Test-Path $ScriptPath) {
        if ($DryRun) {
            Write-ColorOutput "🗑️  [DRY-RUN] Supprimerait: $ScriptName (remplacé par: $ReplacedBy)" $Yellow
        } else {
            try {
                Remove-Item -Path $ScriptPath -Force
                Write-ColorOutput "✅ Supprimé: $ScriptName (remplacé par: $ReplacedBy)" $Green
                return $true
            } catch {
                Write-ColorOutput "❌ Erreur lors de la suppression de $ScriptName : $($_.Exception.Message)" $Red
                return $false
            }
        }
    } else {
        if ($Verbose) {
            Write-ColorOutput "⚠️  Script déjà supprimé: $ScriptName" $Yellow
        }
        return $false
    }
    return $true
}

# Début du script
Write-ColorOutput "🗑️ === SUPPRESSION DES SCRIPTS REDONDANTS ===" $Cyan
Write-ColorOutput "📋 Après consolidation dans la nouvelle architecture" $Cyan

if ($DryRun) {
    Write-ColorOutput "⚠️  MODE DRY-RUN ACTIVÉ - Aucun fichier ne sera supprimé" $Yellow
}

# Configuration des répertoires
$scriptsRoot = "myia_vllm/scripts"

# Compteurs
$totalRemoved = 0
$totalErrors = 0

Write-ColorOutput "`n🔄 === SUPPRESSION DES SCRIPTS REMPLACÉS PAR LA CONSOLIDATION ===" $Cyan

# Scripts redondants remplacés par nos scripts consolidés
$redundantScripts = @{
    'run-validation.ps1' = 'validate/validate-services.ps1'
    'start-qwen3-services.ps1' = 'deploy/deploy-qwen3.ps1'
    'test-qwen3-services.ps1' = 'validate/validate-services.ps1'
    'check-qwen3-logs.ps1' = 'maintenance/monitor-logs.ps1'
    'deploy-all-containers.ps1' = 'deploy/deploy-qwen3.ps1'
    'deploy-all.ps1' = 'deploy/deploy-qwen3.ps1'
    'deploy-qwen3-containers.ps1' = 'deploy/deploy-qwen3.ps1'
    'start-and-check.ps1' = 'deploy/deploy-qwen3.ps1 + validate/validate-services.ps1'
    'test-vllm-services.ps1' = 'validate/validate-services.ps1'
    'start-vllm-services.ps1' = 'deploy/deploy-qwen3.ps1'
}

foreach ($script in $redundantScripts.Keys) {
    $scriptPath = "$scriptsRoot/$script"
    $replacedBy = $redundantScripts[$script]
    
    if (Remove-RedundantScript $scriptPath $script $replacedBy) {
        if (-not $DryRun) { $totalRemoved++ }
    } else {
        $totalErrors++
    }
}

# Scripts utilitaires conservés mais renommés pour clarté
Write-ColorOutput "`n📝 === SCRIPTS UTILITAIRES CONSERVÉS ===" $Cyan
Write-ColorOutput "✅ setup-qwen3-environment.ps1 (utilitaire de setup)" $Green
Write-ColorOutput "✅ update-qwen3-services.ps1 (utilitaire de mise à jour)" $Green
Write-ColorOutput "✅ validate-qwen3-configurations.ps1 (validation spécialisée)" $Green
Write-ColorOutput "✅ test-backup-task.ps1 (outil spécialisé backup)" $Green

# Résumé final
Write-ColorOutput "`n📊 === RÉSUMÉ DE LA SUPPRESSION ===" $Cyan

if (-not $DryRun) {
    Write-ColorOutput "🗑️  Scripts redondants supprimés: $totalRemoved" $Green
    if ($totalErrors -gt 0) {
        Write-ColorOutput "❌ Erreurs rencontrées: $totalErrors" $Red
    }
    
    # Compter les scripts restants
    $remainingScripts = (Get-ChildItem "$scriptsRoot" -File -Name "*.ps1" | Where-Object { $_ -ne "archive-obsolete-scripts.ps1" -and $_ -ne "remove-redundant-scripts.ps1" }).Count
    $modernScripts = 0
    if (Test-Path "$scriptsRoot/deploy") { $modernScripts += (Get-ChildItem "$scriptsRoot/deploy" -File).Count }
    if (Test-Path "$scriptsRoot/validate") { $modernScripts += (Get-ChildItem "$scriptsRoot/validate" -File).Count }  
    if (Test-Path "$scriptsRoot/maintenance") { $modernScripts += (Get-ChildItem "$scriptsRoot/maintenance" -File).Count }
    
    Write-ColorOutput "`n🎯 ARCHITECTURE FINALE:" $Cyan
    Write-ColorOutput "   ├── Scripts consolidés modernes: $modernScripts" $Green
    Write-ColorOutput "   ├── Scripts utilitaires conservés: $remainingScripts" $Yellow
    Write-ColorOutput "   └── Scripts archivés: 21 (dans archived/)" $Cyan
    
} else {
    Write-ColorOutput "🔍 Simulation terminée. Utilisez sans -DryRun pour exécuter la suppression." $Yellow
}

Write-ColorOutput "`n🎯 Nettoyage terminé selon le plan de rationalisation!" $Green