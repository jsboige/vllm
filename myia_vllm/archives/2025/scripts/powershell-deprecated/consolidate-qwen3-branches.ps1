# Script PowerShell pour consolider les branches Qwen3
# Ce script implémente la stratégie de consolidation recommandée dans le rapport d'analyse

# Fonction pour afficher les messages avec des couleurs
function Write-ColorOutput {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Message,
        
        [Parameter(Mandatory=$false)]
        [string]$ForegroundColor = "White"
    )
    
    Write-Host $Message -ForegroundColor $ForegroundColor
}

# Fonction pour exécuter une commande Git et vérifier son résultat
function Invoke-GitCommand {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Command,
        
        [Parameter(Mandatory=$false)]
        [string]$ErrorMessage = "Erreur lors de l'exécution de la commande Git"
    )
    
    Write-ColorOutput "Exécution de: git $Command" -ForegroundColor Cyan
    
    try {
        $output = Invoke-Expression "git $Command 2>&1"
        if ($LASTEXITCODE -ne 0) {
            Write-ColorOutput "$ErrorMessage`n$output" -ForegroundColor Red
            return $false
        }
        Write-Output $output
        return $true
    }
    catch {
        Write-ColorOutput "$ErrorMessage`n$_" -ForegroundColor Red
        return $false
    }
}

# Fonction pour vérifier si une branche existe
function Test-BranchExists {
    param(
        [Parameter(Mandatory=$true)]
        [string]$BranchName
    )
    
    $branches = git branch --list $BranchName
    return $branches.Length -gt 0
}

# Fonction pour créer une branche de sauvegarde
function New-BackupBranch {
    param(
        [Parameter(Mandatory=$true)]
        [string]$SourceBranch,
        
        [Parameter(Mandatory=$false)]
        [string]$BackupSuffix = "backup"
    )
    
    $backupBranch = "$SourceBranch-$BackupSuffix"
    
    if (Test-BranchExists $backupBranch) {
        Write-ColorOutput "La branche de sauvegarde $backupBranch existe déjà" -ForegroundColor Yellow
        return $true
    }
    
    if (-not (Invoke-GitCommand "checkout $SourceBranch" "Erreur lors du checkout de la branche $SourceBranch")) {
        return $false
    }
    
    if (-not (Invoke-GitCommand "checkout -b $backupBranch" "Erreur lors de la création de la branche de sauvegarde $backupBranch")) {
        return $false
    }
    
    Write-ColorOutput "Branche de sauvegarde $backupBranch créée avec succès" -ForegroundColor Green
    
    # Revenir à la branche source
    if (-not (Invoke-GitCommand "checkout $SourceBranch" "Erreur lors du retour à la branche $SourceBranch")) {
        return $false
    }
    
    return $true
}

# Fonction pour fusionner une branche dans la branche consolidée
function Merge-Branch {
    param(
        [Parameter(Mandatory=$true)]
        [string]$SourceBranch,
        
        [Parameter(Mandatory=$true)]
        [string]$TargetBranch
    )
    
    Write-ColorOutput "Fusion de la branche $SourceBranch dans $TargetBranch" -ForegroundColor Magenta
    
    # Vérifier si la branche source existe
    if (-not (Test-BranchExists $SourceBranch)) {
        Write-ColorOutput "La branche $SourceBranch n'existe pas" -ForegroundColor Red
        return $false
    }
    
    # Vérifier si la branche cible existe
    if (-not (Test-BranchExists $TargetBranch)) {
        Write-ColorOutput "La branche $TargetBranch n'existe pas" -ForegroundColor Red
        return $false
    }
    
    # Checkout de la branche cible
    if (-not (Invoke-GitCommand "checkout $TargetBranch" "Erreur lors du checkout de la branche $TargetBranch")) {
        return $false
    }
    
    # Fusionner la branche source dans la branche cible
    $mergeResult = Invoke-GitCommand "merge $SourceBranch --no-ff -m `"Merge branch '$SourceBranch' into $TargetBranch`"" "Erreur lors de la fusion de la branche $SourceBranch dans $TargetBranch"
    
    if (-not $mergeResult) {
        Write-ColorOutput "Conflit détecté lors de la fusion de $SourceBranch dans $TargetBranch" -ForegroundColor Yellow
        Write-ColorOutput "Veuillez résoudre les conflits manuellement, puis exécuter:" -ForegroundColor Yellow
        Write-ColorOutput "git add ." -ForegroundColor Yellow
        Write-ColorOutput "git commit -m `"Résolution des conflits lors de la fusion de $SourceBranch dans $TargetBranch`"" -ForegroundColor Yellow
        
        # Demander à l'utilisateur s'il a résolu les conflits
        $response = Read-Host "Avez-vous résolu les conflits? (O/N)"
        if ($response -eq "O" -or $response -eq "o") {
            Write-ColorOutput "Fusion terminée avec résolution manuelle des conflits" -ForegroundColor Green
            return $true
        }
        else {
            Write-ColorOutput "Annulation de la fusion" -ForegroundColor Red
            Invoke-GitCommand "merge --abort" "Erreur lors de l'annulation de la fusion"
            return $false
        }
    }
    
    Write-ColorOutput "Fusion de $SourceBranch dans $TargetBranch réussie" -ForegroundColor Green
    return $true
}

# Fonction principale pour consolider les branches
function Start-BranchConsolidation {
    param(
        [Parameter(Mandatory=$false)]
        [string]$ConsolidatedBranch = "qwen3-consolidated",
        
        [Parameter(Mandatory=$false)]
        [string]$BaseBranch = "main",
        
        [Parameter(Mandatory=$false)]
        [switch]$CreateBackups = $true
    )
    
    Write-ColorOutput "Début de la consolidation des branches Qwen3" -ForegroundColor Green
    
    # Liste des branches à fusionner dans l'ordre recommandé
    $branchesToMerge = @(
        "feature/qwen3-support",
        "qwen3-parser",
        "qwen3-parser-improvements",
        "pr-qwen3-parser-improvements-clean",
        "qwen3-integration",
        "qwen3-deployment"
    )
    
    # Vérifier si la branche consolidée existe déjà
    if (Test-BranchExists $ConsolidatedBranch) {
        $response = Read-Host "La branche $ConsolidatedBranch existe déjà. Voulez-vous la supprimer et la recréer? (O/N)"
        if ($response -eq "O" -or $response -eq "o") {
            if (-not (Invoke-GitCommand "checkout $BaseBranch" "Erreur lors du checkout de la branche $BaseBranch")) {
                return
            }
            
            if (-not (Invoke-GitCommand "branch -D $ConsolidatedBranch" "Erreur lors de la suppression de la branche $ConsolidatedBranch")) {
                return
            }
        }
        else {
            Write-ColorOutput "Consolidation annulée" -ForegroundColor Red
            return
        }
    }
    
    # Créer des branches de sauvegarde si demandé
    if ($CreateBackups) {
        Write-ColorOutput "Création des branches de sauvegarde" -ForegroundColor Cyan
        
        foreach ($branch in $branchesToMerge) {
            if (-not (New-BackupBranch -SourceBranch $branch -BackupSuffix "backup-$(Get-Date -Format 'yyyyMMdd')")) {
                Write-ColorOutput "Erreur lors de la création de la branche de sauvegarde pour $branch" -ForegroundColor Red
                return
            }
        }
    }
    
    # Créer la branche consolidée à partir de la branche de base
    if (-not (Invoke-GitCommand "checkout $BaseBranch" "Erreur lors du checkout de la branche $BaseBranch")) {
        return
    }
    
    if (-not (Invoke-GitCommand "checkout -b $ConsolidatedBranch" "Erreur lors de la création de la branche $ConsolidatedBranch")) {
        return
    }
    
    Write-ColorOutput "Branche $ConsolidatedBranch créée avec succès" -ForegroundColor Green
    
    # Fusionner chaque branche dans l'ordre recommandé
    foreach ($branch in $branchesToMerge) {
        if (-not (Merge-Branch -SourceBranch $branch -TargetBranch $ConsolidatedBranch)) {
            Write-ColorOutput "Erreur lors de la fusion de la branche $branch dans $ConsolidatedBranch" -ForegroundColor Red
            Write-ColorOutput "Consolidation interrompue" -ForegroundColor Red
            return
        }
    }
    
    Write-ColorOutput "Consolidation des branches Qwen3 terminée avec succès" -ForegroundColor Green
    Write-ColorOutput "La branche consolidée est: $ConsolidatedBranch" -ForegroundColor Green
    Write-ColorOutput "N'oubliez pas de tester la branche consolidée avant de la fusionner dans $BaseBranch" -ForegroundColor Yellow
}

# Exécution de la fonction principale
Write-ColorOutput "Script de consolidation des branches Qwen3" -ForegroundColor Cyan
Write-ColorOutput "Ce script va consolider les branches Qwen3 selon la stratégie recommandée" -ForegroundColor Cyan
Write-ColorOutput "Les branches seront fusionnées dans l'ordre suivant:" -ForegroundColor Cyan
Write-ColorOutput "1. feature/qwen3-support" -ForegroundColor Cyan
Write-ColorOutput "2. qwen3-parser" -ForegroundColor Cyan
Write-ColorOutput "3. qwen3-parser-improvements" -ForegroundColor Cyan
Write-ColorOutput "4. pr-qwen3-parser-improvements-clean" -ForegroundColor Cyan
Write-ColorOutput "5. qwen3-integration" -ForegroundColor Cyan
Write-ColorOutput "6. qwen3-deployment" -ForegroundColor Cyan

$response = Read-Host "Voulez-vous continuer? (O/N)"
if ($response -eq "O" -or $response -eq "o") {
    Start-BranchConsolidation -CreateBackups
}
else {
    Write-ColorOutput "Consolidation annulée" -ForegroundColor Red
}