#!/usr/bin/env pwsh
# Script d'archivage des scripts obsolètes selon le plan de rationalisation
# Partie de la mission de consolidation de l'architecture des scripts

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

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        if (-not $DryRun) {
            New-Item -Path $Path -ItemType Directory -Force | Out-Null
        }
        Write-ColorOutput "📁 Création du répertoire: $Path" $Cyan
    }
}

function Move-ScriptFile {
    param(
        [string]$SourcePath,
        [string]$DestPath,
        [string]$ScriptName,
        [string]$Category
    )
    
    if (Test-Path $SourcePath) {
        if ($DryRun) {
            Write-ColorOutput "🔄 [DRY-RUN] Archiverait: $ScriptName → $Category/" $Yellow
        } else {
            try {
                Move-Item -Path $SourcePath -Destination $DestPath -Force
                Write-ColorOutput "✅ Archivé: $ScriptName → $Category/" $Green
                return $true
            } catch {
                Write-ColorOutput "❌ Erreur lors de l'archivage de $ScriptName : $($_.Exception.Message)" $Red
                return $false
            }
        }
    } else {
        if ($Verbose) {
            Write-ColorOutput "⚠️  Script non trouvé: $ScriptName" $Yellow
        }
        return $false
    }
    return $true
}

# Début du script
Write-ColorOutput "🗂️ === ARCHIVAGE DES SCRIPTS OBSOLÈTES ===" $Cyan
Write-ColorOutput "📋 Selon le plan de rationalisation défini" $Cyan

if ($DryRun) {
    Write-ColorOutput "⚠️  MODE DRY-RUN ACTIVÉ - Aucun fichier ne sera déplacé" $Yellow
}

# Configuration des répertoires
$scriptsRoot = "myia_vllm/scripts"
$archivedRoot = "$scriptsRoot/archived"

# Créer les répertoires d'archivage
Ensure-Directory "$archivedRoot/build-related"
Ensure-Directory "$archivedRoot/legacy-versions" 
Ensure-Directory "$archivedRoot/specialized-tools"

# Compteurs
$totalMoved = 0
$totalErrors = 0

Write-ColorOutput "`n📦 === ARCHIVAGE DES SCRIPTS BUILD-RELATED ===" $Cyan

# Scripts obsolètes liés aux builds personnalisés (maintenant inutiles avec l'image officielle)
$buildRelatedScripts = @(
    'extract-qwen3-parser.ps1',
    'fix-hardcoded-paths.ps1', 
    'fix-improved-cli-args.ps1',
    'prepare-secure-push.ps1',
    'remove-hardcoded-api-keys.ps1',
    'update-gitignore.ps1'
)

foreach ($script in $buildRelatedScripts) {
    $sourcePath = "$scriptsRoot/$script"
    $destPath = "$archivedRoot/build-related/$script"
    
    if (Move-ScriptFile $sourcePath $destPath $script "build-related") {
        if (-not $DryRun) { $totalMoved++ }
    } else {
        $totalErrors++
    }
}

Write-ColorOutput "`n📚 === ARCHIVAGE DES VERSIONS MULTIPLES (LEGACY) ===" $Cyan

# Scripts avec multiples versions (garder seulement la version consolidée)
$legacyVersions = @(
    'run-validation-improved.ps1',
    'run-validation-final.ps1', 
    'validate-optimized-qwen3-final-v2.ps1',
    'validate-optimized-qwen3-final-v3.ps1',
    'validate-optimized-qwen3-final.ps1',
    'validate-optimized-qwen3-fixed.ps1',
    'validate-optimized-qwen3-improved.ps1',
    'validate-optimized-qwen3.ps1',
    'deploy-optimized-qwen3-fixed.ps1',
    'deploy-optimized-qwen3.ps1'
)

foreach ($script in $legacyVersions) {
    $sourcePath = "$scriptsRoot/$script"
    $destPath = "$archivedRoot/legacy-versions/$script"
    
    if (Move-ScriptFile $sourcePath $destPath $script "legacy-versions") {
        if (-not $DryRun) { $totalMoved++ }
    } else {
        $totalErrors++
    }
}

Write-ColorOutput "`n🔧 === ARCHIVAGE DES OUTILS SPÉCIALISÉS ===" $Cyan

# Scripts spécialisés (gardés pour référence mais pas essentiels)
$specializedTools = @(
    'sync-upstream.ps1',
    'final-commits.ps1',
    'prepare-update.ps1',
    'test-after-sync.ps1',
    'check-containers.ps1'
)

foreach ($script in $specializedTools) {
    $sourcePath = "$scriptsRoot/$script"
    $destPath = "$archivedRoot/specialized-tools/$script"
    
    if (Move-ScriptFile $sourcePath $destPath $script "specialized-tools") {
        if (-not $DryRun) { $totalMoved++ }
    } else {
        $totalErrors++
    }
}

# Résumé final
Write-ColorOutput "`n📊 === RÉSUMÉ DE L'ARCHIVAGE ===" $Cyan

if (-not $DryRun) {
    Write-ColorOutput "✅ Scripts archivés avec succès: $totalMoved" $Green
    if ($totalErrors -gt 0) {
        Write-ColorOutput "❌ Erreurs rencontrées: $totalErrors" $Red
    }
    
    # Afficher le contenu des répertoires d'archive
    Write-ColorOutput "`n📁 Contenu des archives:" $Cyan
    
    $archiveDirs = @("build-related", "legacy-versions", "specialized-tools")
    foreach ($dir in $archiveDirs) {
        $fullPath = "$archivedRoot/$dir"
        if (Test-Path $fullPath) {
            $count = (Get-ChildItem $fullPath -File).Count
            Write-ColorOutput "   └── $dir/: $count fichiers" $Cyan
        }
    }
} else {
    Write-ColorOutput "🔍 Simulation terminée. Utilisez sans -DryRun pour exécuter l'archivage." $Yellow
}

Write-ColorOutput "`n🎯 Archivage terminé selon le plan de rationalisation!" $Green