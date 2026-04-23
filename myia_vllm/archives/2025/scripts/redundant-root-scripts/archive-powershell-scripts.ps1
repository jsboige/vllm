#!/usr/bin/env pwsh
<#
.SYNOPSIS
Archive le répertoire powershell/ selon le Plan de Restauration V2 - Phase 1.1

.DESCRIPTION
Ce script archive tous les scripts du répertoire powershell/ vers archived/powershell-deprecated/
selon les directives SDDD du Plan de Restauration V2.

.NOTES
Date: 25 septembre 2025
Méthodologie: SDDD - Phase 6e: Consolidation Scripturale Finale
Responsable: Roo Code Mode
#>

[CmdletBinding()]
param()

# Configuration
$PowerShellDir = "myia_vllm/scripts/powershell"
$ArchiveDir = "myia_vllm/scripts/archived/powershell-deprecated"

Write-Host "=== ARCHIVAGE POWERSHELL/ - PLAN V2 PHASE 1.1 ===" -ForegroundColor Cyan
Write-Host "Méthodologie: SDDD - Consolidation Scripturale Finale`n"

# Vérifier existence du répertoire source
if (-not (Test-Path $PowerShellDir)) {
    Write-Host "❌ ERREUR: Répertoire $PowerShellDir introuvable" -ForegroundColor Red
    exit 1
}

# Compter les scripts à archiver
$ScriptsToArchive = Get-ChildItem -Path $PowerShellDir -File -Filter "*.ps1"
$ScriptCount = $ScriptsToArchive.Count

Write-Host "📊 Scripts identifiés dans powershell/: $ScriptCount" -ForegroundColor Yellow
foreach ($script in $ScriptsToArchive) {
    $sizeKB = [math]::Round($script.Length / 1KB, 2)
    Write-Host "  - $($script.Name) ($sizeKB KB)"
}
Write-Host

# Créer le répertoire d'archive
Write-Host "📁 Création répertoire d'archive: $ArchiveDir" -ForegroundColor Green
New-Item -ItemType Directory -Path $ArchiveDir -Force | Out-Null

# Archiver tous les scripts
Write-Host "🔄 Archivage en cours..." -ForegroundColor Yellow
try {
    Move-Item -Path "$PowerShellDir/*" -Destination $ArchiveDir -Force
    Write-Host "✅ $ScriptCount scripts archivés avec succès" -ForegroundColor Green
} catch {
    Write-Host "❌ ERREUR lors de l'archivage: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Supprimer le répertoire vide
Write-Host "🗑️ Suppression répertoire vide powershell/" -ForegroundColor Yellow
Remove-Item -Path $PowerShellDir -Force

# Vérifications finales
Write-Host "`n=== VÉRIFICATION POST-ARCHIVAGE ===" -ForegroundColor Cyan

$ArchivedFiles = Get-ChildItem -Path $ArchiveDir -File -Filter "*.ps1"
Write-Host "✅ Fichiers archivés: $($ArchivedFiles.Count)" -ForegroundColor Green

if (Test-Path $PowerShellDir) {
    Write-Host "❌ ERREUR: Répertoire powershell/ existe encore" -ForegroundColor Red
    exit 1
} else {
    Write-Host "✅ Répertoire powershell/ supprimé avec succès" -ForegroundColor Green
}

Write-Host "`n🎯 PHASE 1.1 ACCOMPLIE - Entropie powershell/ éliminée" -ForegroundColor Green
Write-Host "Conformité Plan V2: powershell/ → archived/powershell-deprecated/" -ForegroundColor Cyan