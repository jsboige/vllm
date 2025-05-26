<#
.SYNOPSIS
    Script d'automatisation pour synchroniser un fork avec le dépôt original vLLM.

.DESCRIPTION
    Ce script automatise le processus de synchronisation d'un fork de vLLM avec le dépôt original.
    Il vérifie l'existence du remote "upstream", récupère les dernières modifications,
    crée une branche de synchronisation avec un timestamp, et tente de fusionner les modifications.
    En cas de conflits, il fournit des instructions pour les résoudre.

.PARAMETER Push
    Si spécifié, pousse automatiquement les modifications vers le fork distant.

.PARAMETER UpstreamUrl
    URL du dépôt original. Par défaut: https://github.com/vllm-project/vllm.git

.PARAMETER UpstreamBranch
    Branche du dépôt original à synchroniser. Par défaut: main

.EXAMPLE
    .\sync-upstream.ps1
    Synchronise avec le dépôt original sans pousser les modifications.

.EXAMPLE
    .\sync-upstream.ps1 -Push
    Synchronise avec le dépôt original et pousse les modifications vers le fork distant.

.EXAMPLE
    .\sync-upstream.ps1 -UpstreamUrl https://github.com/autre-org/vllm.git -UpstreamBranch develop
    Synchronise avec un dépôt et une branche spécifiques.
#>

param (
    [switch]$Push = $false,
    [string]$UpstreamUrl = "https://github.com/vllm-project/vllm.git",
    [string]$UpstreamBranch = "main"
)

# Fonction pour afficher des messages colorés
function Write-ColorOutput {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Message,
        
        [Parameter(Mandatory = $false)]
        [string]$ForegroundColor = "White"
    )
    
    Write-Host $Message -ForegroundColor $ForegroundColor
}

# Fonction pour vérifier si une commande git a réussi
function Test-GitCommand {
    param (
        [Parameter(Mandatory = $true)]
        [int]$ExitCode,
        
        [Parameter(Mandatory = $true)]
        [string]$ErrorMessage
    )
    
    if ($ExitCode -ne 0) {
        Write-ColorOutput "ERREUR: $ErrorMessage" "Red"
        exit $ExitCode
    }
}

# Afficher l'en-tête
Write-ColorOutput "====================================================" "Cyan"
Write-ColorOutput "  Script de synchronisation avec le dépôt original vLLM" "Cyan"
Write-ColorOutput "====================================================" "Cyan"
Write-ColorOutput ""

# Vérifier si git est installé
try {
    $gitVersion = git --version
    Write-ColorOutput "Git détecté: $gitVersion" "Green"
} catch {
    Write-ColorOutput "ERREUR: Git n'est pas installé ou n'est pas dans le PATH." "Red"
    exit 1
}

# Vérifier si nous sommes dans un dépôt git
if (-not (Test-Path -Path ".git" -PathType Container)) {
    Write-ColorOutput "ERREUR: Ce répertoire ne semble pas être un dépôt git." "Red"
    exit 1
}

# Vérifier si le remote "upstream" existe, sinon l'ajouter
$remotes = git remote
if ($remotes -notcontains "upstream") {
    Write-ColorOutput "Le remote 'upstream' n'existe pas. Ajout en cours..." "Yellow"
    git remote add upstream $UpstreamUrl
    Test-GitCommand $LASTEXITCODE "Impossible d'ajouter le remote 'upstream'."
    Write-ColorOutput "Remote 'upstream' ajouté avec succès." "Green"
} else {
    Write-ColorOutput "Le remote 'upstream' existe déjà." "Green"
    
    # Vérifier si l'URL du remote upstream correspond à celle attendue
    $upstreamUrl = git remote get-url upstream
    if ($upstreamUrl -ne $UpstreamUrl) {
        Write-ColorOutput "L'URL du remote 'upstream' ($upstreamUrl) ne correspond pas à l'URL attendue ($UpstreamUrl)." "Yellow"
        $response = Read-Host "Voulez-vous mettre à jour l'URL du remote 'upstream'? (o/N)"
        if ($response -eq "o" -or $response -eq "O") {
            git remote set-url upstream $UpstreamUrl
            Test-GitCommand $LASTEXITCODE "Impossible de mettre à jour l'URL du remote 'upstream'."
            Write-ColorOutput "URL du remote 'upstream' mise à jour avec succès." "Green"
        }
    }
}

# Récupérer les dernières modifications du dépôt original
Write-ColorOutput "Récupération des dernières modifications du dépôt original..." "Blue"
git fetch upstream
Test-GitCommand $LASTEXITCODE "Impossible de récupérer les modifications du dépôt original."
Write-ColorOutput "Modifications récupérées avec succès." "Green"

# Créer une branche pour la synchronisation avec un timestamp
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$syncBranch = "sync-upstream-$timestamp"
Write-ColorOutput "Création de la branche de synchronisation '$syncBranch'..." "Blue"
git checkout -b $syncBranch
Test-GitCommand $LASTEXITCODE "Impossible de créer la branche de synchronisation."
Write-ColorOutput "Branche de synchronisation créée avec succès." "Green"

# Fusionner les modifications du dépôt original
Write-ColorOutput "Fusion des modifications depuis upstream/$UpstreamBranch..." "Blue"
$mergeOutput = git merge upstream/$UpstreamBranch 2>&1
$mergeExitCode = $LASTEXITCODE

if ($mergeExitCode -ne 0) {
    Write-ColorOutput "ATTENTION: Des conflits de fusion ont été détectés." "Yellow"
    Write-ColorOutput "Voici les fichiers en conflit:" "Yellow"
    git diff --name-only --diff-filter=U
    
    Write-ColorOutput "`nInstructions pour résoudre les conflits:" "Cyan"
    Write-ColorOutput "1. Ouvrez les fichiers en conflit et résolvez les conflits manuellement." "White"
    Write-ColorOutput "2. Utilisez 'git add <fichier>' pour marquer les fichiers comme résolus." "White"
    Write-ColorOutput "3. Validez les modifications avec 'git commit -m \"Résolution des conflits de fusion\"'." "White"
    Write-ColorOutput "4. Continuez avec le processus de synchronisation." "White"
    
    $response = Read-Host "Voulez-vous annuler la fusion et revenir à l'état précédent? (o/N)"
    if ($response -eq "o" -or $response -eq "O") {
        git merge --abort
        Write-ColorOutput "Fusion annulée. Retour à l'état précédent." "Yellow"
        exit 1
    } else {
        Write-ColorOutput "Veuillez résoudre les conflits manuellement avant de continuer." "Yellow"
        exit 1
    }
} else {
    Write-ColorOutput "Fusion réussie sans conflits." "Green"
}

# Vérifier s'il y a eu des modifications
$status = git status -s
if ([string]::IsNullOrWhiteSpace($status)) {
    Write-ColorOutput "Aucune modification détectée. Votre fork est déjà à jour avec le dépôt original." "Green"
} else {
    Write-ColorOutput "Des modifications ont été fusionnées depuis le dépôt original." "Green"
    
    # Afficher un résumé des modifications
    Write-ColorOutput "`nRésumé des modifications:" "Cyan"
    git --no-pager diff --stat HEAD@{1}
    
    # Recommander de tester les modifications
    Write-ColorOutput "`nIl est recommandé de tester les modifications avant de les pousser:" "Yellow"
    Write-ColorOutput "- Exécutez les tests: python -m pytest tests/" "White"
    Write-ColorOutput "- Vérifiez que l'application démarre correctement: python -m vllm.entrypoints.openai.api_server --model <votre-modèle>" "White"
    
    # Pousser les modifications si demandé
    if ($Push) {
        $response = Read-Host "Voulez-vous pousser les modifications vers votre fork distant? (o/N)"
        if ($response -eq "o" -or $response -eq "O") {
            Write-ColorOutput "Poussée des modifications vers origin/$syncBranch..." "Blue"
            git push origin $syncBranch
            Test-GitCommand $LASTEXITCODE "Impossible de pousser les modifications vers votre fork distant."
            Write-ColorOutput "Modifications poussées avec succès vers origin/$syncBranch." "Green"
        }
    } else {
        Write-ColorOutput "`nPour pousser les modifications vers votre fork distant, exécutez:" "Cyan"
        Write-ColorOutput "git push origin $syncBranch" "White"
    }
}

# Afficher les instructions pour finaliser la synchronisation
Write-ColorOutput "`nInstructions pour finaliser la synchronisation:" "Cyan"
Write-ColorOutput "1. Testez les modifications pour vous assurer que tout fonctionne correctement." "White"
Write-ColorOutput "2. Pour mettre à jour votre branche principale, exécutez:" "White"
Write-ColorOutput "   git checkout main" "White"
Write-ColorOutput "   git merge $syncBranch" "White"
Write-ColorOutput "   git push origin main" "White"
Write-ColorOutput "`nSynchronisation terminée avec succès!" "Green"