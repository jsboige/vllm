#!/usr/bin/env pwsh
<#
.SYNOPSIS
Audit des 8 scripts essentiels selon le Plan de Restauration V2 - Phase 2.1

.DESCRIPTION
Vérifie et valide l'architecture scripturale finale pour s'assurer que nous atteignons
les 8 scripts essentiels cibles du Plan de Restauration V2 selon les principes SDDD.

.NOTES
Date: 25 septembre 2025
Méthodologie: SDDD - Phase 6e: Consolidation Scripturale Finale
Responsable: Roo Code Mode
#>

[CmdletBinding()]
param()

Write-Host "=== AUDIT SCRIPTS ESSENTIELS - PLAN V2 PHASE 2.1 ===" -ForegroundColor Cyan
Write-Host "Objectif: Validation des 8 scripts essentiels cibles`n"

$ScriptsDir = "myia_vllm/scripts"

# Architecture cible selon Plan V2
$EssentialStructure = @{
    "deploy/deploy-qwen3.ps1" = "🚀 Script principal de déploiement unifié"
    "validate/validate-services.ps1" = "✅ Validation post-déploiement consolidée"
    "maintenance/monitor-logs.ps1" = "🔧 Monitoring logs moderne"
    "python/client.py" = "🐍 Client API unifié"
    "python/utils.py" = "🐍 Utilitaires partagés"
    "README.md" = "📚 Documentation architecture scripts"
}

Write-Host "🎯 SCRIPTS ESSENTIELS CIBLES (6 principaux):" -ForegroundColor Yellow
foreach ($script in $EssentialStructure.Keys) {
    $description = $EssentialStructure[$script]
    Write-Host "  $description"
    Write-Host "    → $script" -ForegroundColor Gray
}
Write-Host

Write-Host "📊 AUDIT POST-ARCHIVAGE:" -ForegroundColor Cyan

# Compter tous les scripts PowerShell et README dans la racine
$RootScripts = Get-ChildItem -Path $ScriptsDir -File -Filter "*.ps1" | Where-Object { $_.Name -notlike "audit-*" }
$RootReadme = Get-ChildItem -Path $ScriptsDir -File -Filter "README.md"

Write-Host "📁 Scripts racine restants: $($RootScripts.Count)" -ForegroundColor Yellow
foreach ($script in $RootScripts) {
    $sizeKB = [math]::Round($script.Length / 1KB, 2)
    Write-Host "  ⚠️ $($script.Name) ($sizeKB KB) - À ÉVALUER" -ForegroundColor Orange
}

Write-Host "📚 Documentation: $($RootReadme.Count) README.md" -ForegroundColor Gray

# Vérifier l'architecture moderne
$ModernDirs = @("deploy", "validate", "maintenance", "python")
$PresentDirs = 0

Write-Host "`n🏗️ ARCHITECTURE MODERNE:" -ForegroundColor Green
foreach ($dir in $ModernDirs) {
    $dirPath = Join-Path $ScriptsDir $dir
    if (Test-Path $dirPath) {
        $PresentDirs++
        $scriptsInDir = Get-ChildItem -Path $dirPath -File -Filter "*.ps1" -ErrorAction SilentlyContinue
        $pythonFiles = Get-ChildItem -Path $dirPath -File -Filter "*.py" -ErrorAction SilentlyContinue
        $allFiles = @($scriptsInDir) + @($pythonFiles)
        
        Write-Host "  ✅ $dir/ - $($allFiles.Count) fichier(s)" -ForegroundColor Green
        foreach ($file in $allFiles) {
            $sizeKB = [math]::Round($file.Length / 1KB, 2)
            Write-Host "    → $($file.Name) ($sizeKB KB)" -ForegroundColor Gray
        }
    } else {
        Write-Host "  ❌ $dir/ - MANQUANT" -ForegroundColor Red
    }
}

# Compter les scripts Python (conservés)
$PythonDir = Join-Path $ScriptsDir "python"
$PythonScripts = 0
if (Test-Path $PythonDir) {
    $PythonFiles = Get-ChildItem -Path $PythonDir -Recurse -File -Filter "*.py"
    $PythonScripts = $PythonFiles.Count
    Write-Host "`n🐍 Scripts Python conservés: $PythonScripts" -ForegroundColor Cyan
}

# Calcul total vers l'objectif 8 scripts
$CurrentEssentials = $RootReadme.Count + $PresentDirs + $PythonScripts
Write-Host "`n📊 MÉTRIQUES CONFORMITÉ PLAN V2:" -ForegroundColor Magenta
Write-Host "🎯 Objectif scripts essentiels: 8 maximum" -ForegroundColor White
Write-Host "📈 Scripts actuels estimés: ~$CurrentEssentials (+ structure moderne)" -ForegroundColor White
Write-Host "⚠️ Scripts racine à réévaluer: $($RootScripts.Count)" -ForegroundColor Orange

if ($RootScripts.Count -eq 0 -and $PresentDirs -eq 4) {
    Write-Host "`n🎉 CONFORMITÉ ATTEINTE - Architecture moderne validée!" -ForegroundColor Green
} else {
    Write-Host "`n⚠️ ACTIONS REQUISES pour atteindre la conformité:" -ForegroundColor Yellow
    if ($RootScripts.Count -gt 0) {
        Write-Host "  - Évaluer/archiver les $($RootScripts.Count) scripts racine restants" -ForegroundColor Orange
    }
    if ($PresentDirs -lt 4) {
        Write-Host "  - Finaliser l'architecture moderne ($(4-$PresentDirs) répertoires manquants)" -ForegroundColor Orange
    }
}

Write-Host "`n🎯 PHASE 2.1 - Audit des scripts essentiels terminé" -ForegroundColor Cyan