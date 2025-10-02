# Script d'analyse comparative des fichiers entre main et feature
# Ce script identifie les fichiers présents uniquement sur main et uniquement sur feature

Write-Host "=== ANALYSE COMPARATIVE DES FICHIERS ===" -ForegroundColor Cyan

# Charger les listes de fichiers
Write-Host "`nChargement des listes de fichiers..." -ForegroundColor Yellow
$mainFiles = Get-Content "analysis_comparative/analysis_main_files.txt" | Where-Object { $_ -ne "" }
$featureFiles = Get-Content "analysis_comparative/analysis_feature_files.txt" | Where-Object { $_ -ne "" }

Write-Host "Fichiers sur main: $($mainFiles.Count)" -ForegroundColor Green
Write-Host "Fichiers sur feature: $($featureFiles.Count)" -ForegroundColor Green

# Identifier les fichiers présents UNIQUEMENT sur main
Write-Host "`nRecherche des fichiers exclusifs à main..." -ForegroundColor Yellow
$mainOnly = $mainFiles | Where-Object { $_ -notin $featureFiles }
$mainOnly | Out-File -FilePath "analysis_comparative/analysis_main_only.txt" -Encoding utf8
Write-Host "Fichiers exclusifs à main: $($mainOnly.Count)" -ForegroundColor Magenta

# Identifier les fichiers présents UNIQUEMENT sur feature
Write-Host "`nRecherche des fichiers exclusifs à feature..." -ForegroundColor Yellow
$featureOnly = $featureFiles | Where-Object { $_ -notin $mainFiles }
$featureOnly | Out-File -FilePath "analysis_comparative/analysis_feature_only.txt" -Encoding utf8
Write-Host "Fichiers exclusifs à feature: $($featureOnly.Count)" -ForegroundColor Magenta

# Identifier les fichiers communs
Write-Host "`nRecherche des fichiers communs..." -ForegroundColor Yellow
$commonFiles = $mainFiles | Where-Object { $_ -in $featureFiles }
$commonFiles | Out-File -FilePath "analysis_comparative/analysis_common_files.txt" -Encoding utf8
Write-Host "Fichiers communs: $($commonFiles.Count)" -ForegroundColor Green

# Créer un rapport de synthèse
$summary = @"
=== RAPPORT DE COMPARAISON DES BRANCHES ===
Date: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

STATISTIQUES:
- Fichiers sur main: $($mainFiles.Count)
- Fichiers sur feature: $($featureFiles.Count)
- Fichiers communs: $($commonFiles.Count)
- Fichiers exclusifs à main: $($mainOnly.Count)
- Fichiers exclusifs à feature: $($featureOnly.Count)

FICHIERS EXCLUSIFS À MAIN (premiers 50):
$($mainOnly | Select-Object -First 50 | ForEach-Object { "  - $_" } | Out-String)

FICHIERS EXCLUSIFS À FEATURE (premiers 50):
$($featureOnly | Select-Object -First 50 | ForEach-Object { "  - $_" } | Out-String)
"@

$summary | Out-File -FilePath "analysis_comparative/comparison_summary.txt" -Encoding utf8

Write-Host "`n=== ANALYSE TERMINÉE ===" -ForegroundColor Cyan
Write-Host "Les fichiers suivants ont été créés:" -ForegroundColor Green
Write-Host "  - analysis_main_only.txt" -ForegroundColor White
Write-Host "  - analysis_feature_only.txt" -ForegroundColor White
Write-Host "  - analysis_common_files.txt" -ForegroundColor White
Write-Host "  - comparison_summary.txt" -ForegroundColor White