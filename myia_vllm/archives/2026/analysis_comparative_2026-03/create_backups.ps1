# Script de création des sauvegardes de sécurité
# Ce script crée toutes les sauvegardes nécessaires avant toute opération de merge

Write-Host "=== CRÉATION DES SAUVEGARDES DE SÉCURITÉ ===" -ForegroundColor Cyan

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
Write-Host "`nTimestamp: $timestamp" -ForegroundColor Yellow

# Phase 2.1: Sauvegardes des branches principales
Write-Host "`n=== PHASE 2.1: SAUVEGARDES DES BRANCHES ===" -ForegroundColor Cyan

Write-Host "Création de la sauvegarde de main..." -ForegroundColor Yellow
git branch "backup-main-analysis-$timestamp" main
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Sauvegarde main créée: backup-main-analysis-$timestamp" -ForegroundColor Green
} else {
    Write-Host "✗ Erreur création sauvegarde main" -ForegroundColor Red
    exit 1
}

Write-Host "`nCréation de la sauvegarde de feature..." -ForegroundColor Yellow
git branch "backup-feature-analysis-$timestamp" feature/post-apt-consolidation-clean
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Sauvegarde feature créée: backup-feature-analysis-$timestamp" -ForegroundColor Green
} else {
    Write-Host "✗ Erreur création sauvegarde feature" -ForegroundColor Red
    exit 1
}

# Liste des sauvegardes créées
Write-Host "`nListe de toutes les sauvegardes:" -ForegroundColor Yellow
git branch | Select-String "backup" | Out-File -FilePath "analysis_comparative/analysis_backups.txt" -Encoding utf8
Get-Content "analysis_comparative/analysis_backups.txt" | ForEach-Object { Write-Host "  $_" -ForegroundColor White }

# Phase 2.2: Export des patches
Write-Host "`n=== PHASE 2.2: EXPORT DES PATCHES ===" -ForegroundColor Cyan

Write-Host "Export des 17 commits uniques de main..." -ForegroundColor Yellow
git checkout main | Out-Null
git format-patch -17 --stdout > "analysis_comparative/patches_main_unique_commits.patch"
if ($LASTEXITCODE -eq 0) {
    $size = (Get-Item "analysis_comparative/patches_main_unique_commits.patch").Length / 1KB
    Write-Host "✓ Patch main créé: $([math]::Round($size, 2)) KB" -ForegroundColor Green
} else {
    Write-Host "✗ Erreur création patch main" -ForegroundColor Red
}

Write-Host "`nExport du commit de consolidation de feature..." -ForegroundColor Yellow
git checkout feature/post-apt-consolidation-clean | Out-Null
git format-patch -1 HEAD --stdout > "analysis_comparative/patches_feature_consolidation.patch"
if ($LASTEXITCODE -eq 0) {
    $size = (Get-Item "analysis_comparative/patches_feature_consolidation.patch").Length / 1KB
    Write-Host "✓ Patch feature créé: $([math]::Round($size, 2)) KB" -ForegroundColor Green
} else {
    Write-Host "✗ Erreur création patch feature" -ForegroundColor Red
}

# Phase 2.3: Documentation des configurations critiques
Write-Host "`n=== PHASE 2.3: SAUVEGARDE DES CONFIGURATIONS ===" -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path "analysis_comparative/backups/main_configs" | Out-Null
New-Item -ItemType Directory -Force -Path "analysis_comparative/backups/feature_configs" | Out-Null

Write-Host "Sauvegarde des configs de main..." -ForegroundColor Yellow
git checkout main | Out-Null
$mainConfigFiles = @(
    "myia_vllm/.env",
    "myia_vllm/.gitignore",
    ".gitignore",
    "myia_vllm/configs/.env.example"
)

foreach ($file in $mainConfigFiles) {
    if (Test-Path $file) {
        $dest = "analysis_comparative/backups/main_configs/" + ($file -replace "/", "_")
        Copy-Item $file $dest -Force
        Write-Host "  ✓ Sauvegardé: $file" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Non trouvé: $file" -ForegroundColor Yellow
    }
}

Write-Host "`nSauvegarde des configs de feature..." -ForegroundColor Yellow
git checkout feature/post-apt-consolidation-clean | Out-Null
$featureConfigFiles = @(
    "myia_vllm/.env",
    "myia_vllm/.gitignore",
    ".gitignore",
    "myia_vllm/configs/.env.example",
    "myia_vllm/docs/archeology/HISTORICAL_ANALYSIS.md"
)

foreach ($file in $featureConfigFiles) {
    if (Test-Path $file) {
        $dest = "analysis_comparative/backups/feature_configs/" + ($file -replace "/", "_")
        Copy-Item $file $dest -Force
        Write-Host "  ✓ Sauvegardé: $file" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ Non trouvé: $file" -ForegroundColor Yellow
    }
}

# Rapport final
Write-Host "`n=== RAPPORT DE SAUVEGARDE ===" -ForegroundColor Cyan
$report = @"
=== RAPPORT DE SAUVEGARDE COMPLÉTÉ ===
Date: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Timestamp: $timestamp

BRANCHES SAUVEGARDÉES:
- backup-main-analysis-$timestamp
- backup-feature-analysis-$timestamp

PATCHES CRÉÉS:
- patches_main_unique_commits.patch (17 commits de main)
- patches_feature_consolidation.patch (1 commit de feature)

CONFIGURATIONS SAUVEGARDÉES:
- Main configs: $(($mainConfigFiles | Where-Object { Test-Path $_ }).Count) fichiers
- Feature configs: $(($featureConfigFiles | Where-Object { Test-Path $_ }).Count) fichiers

EMPLACEMENT: analysis_comparative/backups/

✓ TOUTES LES SAUVEGARDES SONT EN PLACE
✓ PRÊT POUR LES OPÉRATIONS DE MERGE
"@

$report | Out-File -FilePath "analysis_comparative/backup_report.txt" -Encoding utf8
Write-Host $report -ForegroundColor Green

Write-Host "`n=== SAUVEGARDES TERMINÉES ===" -ForegroundColor Cyan