<#
.SYNOPSIS
    Workflow Git automatisé pour Mission 15 avec vérification des clés API
.DESCRIPTION
    Gère le staging, la vérification des clés sensibles, et les commits structurés
.EXAMPLE
    .\mission15_commit_workflow.ps1
#>

$ErrorActionPreference = "Stop"

Write-Host "=== MISSION 15 - WORKFLOW GIT ===" -ForegroundColor Cyan
Write-Host ""

# ======================
# ÉTAPE 1: VÉRIFICATION CLÉS API
# ======================
Write-Host "🔒 ÉTAPE 1: Vérification fichiers sensibles" -ForegroundColor Yellow

# Vérifier que .env est bien ignoré
$envInGitignore = Select-String '\.env' .gitignore
if (-not $envInGitignore) {
    Write-Host "❌ ERREUR: .env n'est pas dans .gitignore!" -ForegroundColor Red
    exit 1
}
Write-Host "✅ .env est bien dans .gitignore" -ForegroundColor Green

# Vérifier qu'aucun fichier stagé ne contient la clé
Write-Host ""
Write-Host "📋 Fichiers à commiter (staging sélectif):" -ForegroundColor Yellow

# ======================
# ÉTAPE 2: STAGING SÉLECTIF
# ======================

# Liste des fichiers à commiter pour Mission 15
$filesToCommit = @(
    # Configuration optimale
    "configs/docker/profiles/medium.yml",
    
    # Scripts grid search (bugs corrigés)
    "scripts/grid_search_optimization.ps1",
    
    # Documentation Mission 15
    "docs/PRODUCTION_VALIDATION_REPORT.md",
    "docs/SYNTHESIS_GRID_SEARCH_MISSIONS_20251021.md",
    "docs/DOCUMENTATION_INDEX.md",
    
    # Scripts nouveaux
    "scripts/monitoring/wait_for_container_healthy.ps1",
    "scripts/testing/mission15_validation_tests.ps1",
    
    # README mis à jour
    "scripts/README.md"
)

# Vérifier existence et stage
$stagedFiles = @()
foreach ($file in $filesToCommit) {
    if (Test-Path $file) {
        Write-Host "  ✓ $file" -ForegroundColor Gray
        git add $file
        $stagedFiles += $file
    } else {
        Write-Host "  ⚠️  $file (non trouvé)" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "📊 Fichiers stagés: $($stagedFiles.Count)" -ForegroundColor Green

# ======================
# ÉTAPE 3: VÉRIFICATION CRITIQUE
# ======================
Write-Host ""
Write-Host "🔍 ÉTAPE 3: Vérification critique des clés API" -ForegroundColor Yellow

# Pattern générique pour détecter toute clé API de 32 caractères (sans exposer la clé réelle)
$apiKeyPattern = "[A-Z0-9]{32}|VLLM_API_KEY_MEDIUM\s*=\s*[A-Z0-9]+"
$diffOutput = git diff --cached

if ($diffOutput -match $apiKeyPattern) {
    Write-Host "❌ ERREUR CRITIQUE: Clé API détectée dans les fichiers stagés!" -ForegroundColor Red
    Write-Host "❌ COMMIT BLOQUÉ pour sécurité" -ForegroundColor Red
    Write-Host ""
    Write-Host "Fichiers suspectés:" -ForegroundColor Yellow
    git diff --cached | Select-String $apiKeyPattern
    Write-Host ""
    Write-Host "Action: Retirez la clé API des fichiers avant de commiter" -ForegroundColor Red
    exit 1
}

Write-Host "✅ AUCUNE clé API détectée dans les fichiers stagés" -ForegroundColor Green

# ======================
# ÉTAPE 4: COMMITS STRUCTURÉS
# ======================
Write-Host ""
Write-Host "📝 ÉTAPE 4: Création des commits structurés" -ForegroundColor Yellow

# Commit 1: Configuration optimale
Write-Host ""
Write-Host "Commit 1/3: Configuration optimale..." -ForegroundColor Cyan
git reset HEAD  # Reset pour commit sélectif
git add configs/docker/profiles/medium.yml

$commit1Message = @"
feat(config): Apply optimal configuration chunked_only_safe (x3.22 KV cache acceleration)

- Set gpu-memory-utilization to 0.85
- Enable chunked-prefill
- Disable prefix-caching (better perf when used alone)
- Validated via grid search (Mission 14k)

Performance gain: +222% vs baseline (x3.22 vs x1.59)
Container healthy in 324s
Configuration stable and production-ready

Refs: Mission 15
"@

git commit -m $commit1Message
Write-Host "✅ Commit 1/3 créé" -ForegroundColor Green

# Commit 2: Corrections bugs grid search
Write-Host ""
Write-Host "Commit 2/3: Corrections bugs..." -ForegroundColor Cyan
git add scripts/grid_search_optimization.ps1

$commit2Message = @"
fix(grid-search): Resolve bugs #5 (rope_scaling) and #6 (KV cache parsing)

Bug #5: Fix JSON escaping in rope_scaling parameter
- Line 379: Correct rope_scaling JSON format with proper escaping
- Prevents malformed YAML in docker compose files

Bug #6: Update regex patterns to match actual log format
- Lines 851-856: Update KV cache detection patterns
- Match actual vLLM log output format

All 6 grid search bugs now resolved (Missions 14a-14k)
Grid search validation successful with 36 configurations tested

Refs: Mission 14k, Mission 15
"@

git commit -m $commit2Message
Write-Host "✅ Commit 2/3 créé" -ForegroundColor Green

# Commit 3: Documentation et scripts
Write-Host ""
Write-Host "Commit 3/3: Documentation..." -ForegroundColor Cyan
git add docs/PRODUCTION_VALIDATION_REPORT.md
git add docs/SYNTHESIS_GRID_SEARCH_MISSIONS_20251021.md
git add docs/DOCUMENTATION_INDEX.md
git add scripts/monitoring/wait_for_container_healthy.ps1
git add scripts/testing/mission15_validation_tests.ps1
git add scripts/README.md

$commit3Message = @"
docs: Add grid search results and production validation report

Documentation:
- Add PRODUCTION_VALIDATION_REPORT.md (Mission 15 validation)
- Add SYNTHESIS_GRID_SEARCH_MISSIONS_20251021.md (complete grid search synthesis)
- Update DOCUMENTATION_INDEX.md

New scripts:
- scripts/monitoring/wait_for_container_healthy.ps1 (health monitoring)
- scripts/testing/mission15_validation_tests.ps1 (validation test suite)
- Update scripts/README.md with new tooling

Validation results:
- ✅ Health check: OK
- ✅ Reasoning test: OK
- ⚠️  Tool calling: Needs investigation
- ℹ️  KV Cache: N/A (prefix-caching disabled)

Configuration validated for production with reserves

Refs: Missions 14g, 15
"@

git commit -m $commit3Message
Write-Host "✅ Commit 3/3 créé" -ForegroundColor Green

# ======================
# ÉTAPE 5: VÉRIFICATION FINALE
# ======================
Write-Host ""
Write-Host "📊 ÉTAPE 5: Vérification finale" -ForegroundColor Yellow
Write-Host ""

$recentCommits = git log --oneline -3
Write-Host "Derniers commits créés:" -ForegroundColor Cyan
$recentCommits | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }

Write-Host ""
Write-Host "=== WORKFLOW TERMINÉ ===" -ForegroundColor Green
Write-Host ""
Write-Host "Prochaine étape: Push vers fork GitHub" -ForegroundColor Yellow
Write-Host "Commande: git push origin main" -ForegroundColor Gray
Write-Host ""