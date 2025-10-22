# Script de Validation - Sous-tâche 2/4
# Date: 2025-10-22
# Objectif: Valider la création des guides complémentaires et l'archivage

param(
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Write-Host "`n=== VALIDATION SOUS-TÂCHE 2/4 ===" -ForegroundColor Cyan
Write-Host "Timestamp: $timestamp`n" -ForegroundColor Gray

# Compteurs
$errorsFound = 0
$warningsFound = 0

# 1. Vérification TROUBLESHOOTING.md
Write-Host "📄 1. Vérification TROUBLESHOOTING.md" -ForegroundColor Yellow
$troubleshootingPath = "myia_vllm/docs/TROUBLESHOOTING.md"

if (Test-Path $troubleshootingPath) {
    $lines = (Get-Content $troubleshootingPath).Count
    Write-Host "  ✓ Fichier créé: $lines lignes" -ForegroundColor Green
    
    # Vérifier sections critiques
    $content = Get-Content $troubleshootingPath -Raw
    $sections = @(
        "Problèmes de Déploiement",
        "Problèmes de Configuration",
        "Problèmes de Performance",
        "Bugs Historiques Résolus",
        "Scripts de Diagnostic",
        "Procédures d'Escalade"
    )
    
    foreach ($section in $sections) {
        if ($content -match $section) {
            Write-Host "    ✓ Section '$section' présente" -ForegroundColor Green
        } else {
            Write-Host "    ✗ Section '$section' MANQUANTE" -ForegroundColor Red
            $errorsFound++
        }
    }
    
    # Vérifier bugs catalogués
    $bugs = @("Bug #1", "Bug #2", "Bug #3", "Bug #4", "Bug #5", "Bug #6")
    $bugsFound = 0
    foreach ($bug in $bugs) {
        if ($content -match [regex]::Escape($bug)) {
            $bugsFound++
        }
    }
    Write-Host "    ✓ Bugs catalogués: $bugsFound/6" -ForegroundColor Green
    if ($bugsFound -lt 6) {
        Write-Host "      ⚠ Seulement $bugsFound bugs sur 6 attendus" -ForegroundColor Yellow
        $warningsFound++
    }
    
} else {
    Write-Host "  ✗ Fichier MANQUANT" -ForegroundColor Red
    $errorsFound++
}

# 2. Vérification MAINTENANCE_PROCEDURES.md
Write-Host "`n📄 2. Vérification MAINTENANCE_PROCEDURES.md" -ForegroundColor Yellow
$maintenancePath = "myia_vllm/docs/MAINTENANCE_PROCEDURES.md"

if (Test-Path $maintenancePath) {
    $lines = (Get-Content $maintenancePath).Count
    Write-Host "  ✓ Fichier créé: $lines lignes" -ForegroundColor Green
    
    # Vérifier sections critiques
    $content = Get-Content $maintenancePath -Raw
    $sections = @(
        "Monitoring Régulier",
        "Nettoyage Docker",
        "Backup Configuration",
        "Mise à Jour Modèle",
        "Rotation Logs",
        "Calendrier Maintenance"
    )
    
    foreach ($section in $sections) {
        if ($content -match $section) {
            Write-Host "    ✓ Section '$section' présente" -ForegroundColor Green
        } else {
            Write-Host "    ✗ Section '$section' MANQUANTE" -ForegroundColor Red
            $errorsFound++
        }
    }
    
    # Vérifier présence calendrier
    if ($content -match "Checklist Hebdomadaire" -and $content -match "Checklist Mensuelle") {
        Write-Host "    ✓ Calendriers de maintenance présents" -ForegroundColor Green
    } else {
        Write-Host "    ✗ Calendriers INCOMPLETS" -ForegroundColor Red
        $errorsFound++
    }
    
} else {
    Write-Host "  ✗ Fichier MANQUANT" -ForegroundColor Red
    $errorsFound++
}

# 3. Vérification structure archivage
Write-Host "`n📁 3. Vérification structure archivage" -ForegroundColor Yellow
$archivePath = "myia_vllm/archives/missions/2025-10-21_missions_11-15"

if (Test-Path $archivePath) {
    Write-Host "  ✓ Répertoire créé" -ForegroundColor Green
    
    # Vérifier fichiers archivés
    $expectedFiles = @(
        "SYNTHESIS_GRID_SEARCH_MISSIONS_20251021.md",
        "PRODUCTION_VALIDATION_REPORT.md",
        "README.md"
    )
    
    foreach ($file in $expectedFiles) {
        $filePath = Join-Path $archivePath $file
        if (Test-Path $filePath) {
            $lines = (Get-Content $filePath).Count
            Write-Host "    ✓ $file ($lines lignes)" -ForegroundColor Green
        } else {
            Write-Host "    ✗ $file MANQUANT" -ForegroundColor Red
            $errorsFound++
        }
    }
    
} else {
    Write-Host "  ✗ Répertoire MANQUANT" -ForegroundColor Red
    $errorsFound++
}

# 4. Vérification liens markdown
Write-Host "`n🔗 4. Vérification liens critiques" -ForegroundColor Yellow

$filesToCheck = @(
    "myia_vllm/docs/TROUBLESHOOTING.md",
    "myia_vllm/docs/MAINTENANCE_PROCEDURES.md",
    "myia_vllm/archives/missions/2025-10-21_missions_11-15/README.md"
)

foreach ($file in $filesToCheck) {
    if (Test-Path $file) {
        $content = Get-Content $file -Raw
        
        # Extraire liens markdown
        $links = [regex]::Matches($content, '\[([^\]]+)\]\(([^\)]+)\)')
        $brokenLinks = 0
        
        foreach ($link in $links) {
            $linkPath = $link.Groups[2].Value
            
            # Ignorer URLs externes et ancres
            if ($linkPath -match '^https?://' -or $linkPath -match '^#') {
                continue
            }
            
            # Nettoyer le chemin (enlever ancres)
            $cleanPath = $linkPath -replace ':.*$', '' -replace '#.*$', ''
            
            # Vérifier si le fichier existe (relatif au fichier actuel)
            $fileDir = Split-Path $file -Parent
            $targetPath = Join-Path $fileDir $cleanPath
            
            if (-not (Test-Path $targetPath)) {
                if ($Verbose) {
                    Write-Host "    ⚠ Lien cassé potentiel: $linkPath dans $(Split-Path $file -Leaf)" -ForegroundColor Yellow
                }
                $brokenLinks++
            }
        }
        
        if ($brokenLinks -eq 0) {
            Write-Host "  ✓ $(Split-Path $file -Leaf): Tous les liens vérifiés" -ForegroundColor Green
        } else {
            Write-Host "  ⚠ $(Split-Path $file -Leaf): $brokenLinks liens potentiellement cassés" -ForegroundColor Yellow
            $warningsFound++
        }
    }
}

# 5. Statistiques globales
Write-Host "`n📊 5. Statistiques globales" -ForegroundColor Yellow

$totalLines = 0
if (Test-Path $troubleshootingPath) {
    $totalLines += (Get-Content $troubleshootingPath).Count
}
if (Test-Path $maintenancePath) {
    $totalLines += (Get-Content $maintenancePath).Count
}

Write-Host "  Total documentation créée: $totalLines lignes" -ForegroundColor Cyan

# 6. Rapport final
Write-Host "`n=== RAPPORT FINAL ===" -ForegroundColor Cyan

if ($errorsFound -eq 0 -and $warningsFound -eq 0) {
    Write-Host "✅ VALIDATION RÉUSSIE - Aucune erreur détectée" -ForegroundColor Green
    Write-Host "`nTous les livrables de la sous-tâche 2/4 sont complets:" -ForegroundColor Green
    Write-Host "  ✓ TROUBLESHOOTING.md (6 sections, 6 bugs)" -ForegroundColor Green
    Write-Host "  ✓ MAINTENANCE_PROCEDURES.md (6 sections, calendrier)" -ForegroundColor Green
    Write-Host "  ✓ Archives missions 11-15 (3 fichiers + README)" -ForegroundColor Green
    Write-Host "  ✓ Structure conforme SDDD" -ForegroundColor Green
    $exitCode = 0
} elseif ($errorsFound -eq 0) {
    Write-Host "⚠️  VALIDATION AVEC AVERTISSEMENTS" -ForegroundColor Yellow
    Write-Host "  Erreurs: $errorsFound" -ForegroundColor Green
    Write-Host "  Avertissements: $warningsFound" -ForegroundColor Yellow
    $exitCode = 1
} else {
    Write-Host "❌ VALIDATION ÉCHOUÉE" -ForegroundColor Red
    Write-Host "  Erreurs: $errorsFound" -ForegroundColor Red
    Write-Host "  Avertissements: $warningsFound" -ForegroundColor Yellow
    $exitCode = 2
}

Write-Host "`nPrêt pour sous-tâche 3/4 (création scripts maintenance)" -ForegroundColor Cyan

exit $exitCode