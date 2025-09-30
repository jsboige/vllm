#!/usr/bin/env pwsh
<#
.SYNOPSIS
Archive les scripts redondants de la racine selon le Plan de Restauration V2 - Phase 1.2

.DESCRIPTION
Identifie et archive les scripts redondants de la racine myia_vllm/scripts/ qui sont
des doublons avec les scripts déjà archivés ou remplacés par l'architecture moderne.

.NOTES
Date: 25 septembre 2025
Méthodologie: SDDD - Phase 6e: Consolidation Scripturale Finale
Responsable: Roo Code Mode
#>

[CmdletBinding()]
param()

Write-Host "=== ARCHIVAGE SCRIPTS REDONDANTS RACINE - PLAN V2 PHASE 1.2 ===" -ForegroundColor Cyan
Write-Host "Méthodologie: SDDD - Élimination de l'entropie redondante`n"

# Scripts redondants identifiés selon le diagnostic Plan V2
$RedundantScripts = @(
    "setup-qwen3-environment.ps1",      # Doublon avec archived/powershell-deprecated/
    "validate-qwen3-configurations.ps1", # Doublon avec archived/powershell-deprecated/ 
    "test-backup-task.ps1",             # Doublon avec archived/powershell-deprecated/
    "update-qwen3-services.ps1",        # Doublon avec archived/powershell-deprecated/
    "archive-powershell-scripts.ps1"    # Script d'archivage temporaire (mission accomplie)
)

$ScriptsDir = "myia_vllm/scripts"
$ArchiveDir = "myia_vllm/scripts/archived/redundant-root-scripts"

# Créer le répertoire d'archive
Write-Host "📁 Création répertoire d'archive: $ArchiveDir" -ForegroundColor Green
New-Item -ItemType Directory -Path $ArchiveDir -Force | Out-Null

Write-Host "🔍 Identification des scripts redondants:" -ForegroundColor Yellow

$ArchivedCount = 0
foreach ($scriptName in $RedundantScripts) {
    $scriptPath = Join-Path $ScriptsDir $scriptName
    
    if (Test-Path $scriptPath) {
        $script = Get-Item $scriptPath
        $sizeKB = [math]::Round($script.Length / 1KB, 2)
        Write-Host "  ✅ Trouvé: $scriptName ($sizeKB KB)" -ForegroundColor Green
        
        # Archiver le script
        try {
            Move-Item -Path $scriptPath -Destination $ArchiveDir -Force
            Write-Host "     → Archivé vers archived/redundant-root-scripts/" -ForegroundColor Gray
            $ArchivedCount++
        } catch {
            Write-Host "     ❌ ERREUR archivage: $($_.Exception.Message)" -ForegroundColor Red
        }
    } else {
        Write-Host "  ⚪ Absent: $scriptName (déjà supprimé)" -ForegroundColor Gray
    }
}

Write-Host "`n📊 RÉSULTATS PHASE 1.2:" -ForegroundColor Cyan
Write-Host "✅ Scripts redondants archivés: $ArchivedCount" -ForegroundColor Green
Write-Host "📁 Localisation: archived/redundant-root-scripts/" -ForegroundColor Gray

# Vérification finale
$ArchivedFiles = Get-ChildItem -Path $ArchiveDir -File -Filter "*.ps1" -ErrorAction SilentlyContinue
if ($ArchivedFiles) {
    Write-Host "`n🗂️ Scripts archivés confirmés:" -ForegroundColor Yellow
    foreach ($file in $ArchivedFiles) {
        Write-Host "  - $($file.Name)" -ForegroundColor Gray
    }
}

Write-Host "`n🎯 PHASE 1.2 ACCOMPLIE - Scripts redondants éliminés" -ForegroundColor Green
Write-Host "Progression vers les 8 scripts essentiels du Plan V2..." -ForegroundColor Cyan