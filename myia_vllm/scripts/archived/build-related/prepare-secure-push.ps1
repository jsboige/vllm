# Script PowerShell principal pour préparer les commits et push sécurisés pour Qwen3
# Ce script orchestre l'ensemble du processus de sécurisation et de préparation des commits

# Fonction pour afficher des messages colorés
function Write-ColorOutput {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Message,
        
        [Parameter(Mandatory = $false)]
        [string]$ForegroundColor = "White"
    )
    
    $originalColor = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    Write-Output $Message
    $host.UI.RawUI.ForegroundColor = $originalColor
}

# Fonction pour exécuter un script et vérifier son résultat
function Invoke-SecurityScript {
    param (
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        
        [Parameter(Mandatory = $true)]
        [string]$Description
    )
    
    Write-ColorOutput "`n=== Exécution: $Description ===" "Magenta"
    
    # Vérifier si le script existe
    if (-not (Test-Path -Path $ScriptPath)) {
        Write-ColorOutput "✗ Le script n'existe pas: $ScriptPath" "Red"
        return $false
    }
    
    # Exécuter le script
    try {
        & $ScriptPath
        $success = $?
        
        if ($success) {
            Write-ColorOutput "✓ Script exécuté avec succès: $ScriptPath" "Green"
        }
        else {
            Write-ColorOutput "✗ Erreur lors de l'exécution du script: $ScriptPath" "Red"
        }
        
        return $success
    }
    catch {
        Write-ColorOutput "✗ Exception lors de l'exécution du script: $_" "Red"
        return $false
    }
}

# Fonction pour vérifier si git est disponible
function Test-GitAvailable {
    try {
        $gitVersion = git --version
        return $true
    }
    catch {
        return $false
    }
}

# Fonction pour vérifier l'état git
function Show-GitStatus {
    Write-ColorOutput "`n=== État Git actuel ===" "Magenta"
    
    # Vérifier si git est disponible
    if (-not (Test-GitAvailable)) {
        Write-ColorOutput "✗ Git n'est pas disponible. Veuillez l'installer avant de continuer." "Red"
        return $false
    }
    
    # Vérifier si nous sommes dans un dépôt git
    if (-not (Test-Path -Path ".git")) {
        Write-ColorOutput "✗ Ce script doit être exécuté à la racine d'un dépôt git." "Red"
        return $false
    }
    
    # Afficher la branche actuelle
    $currentBranch = git branch --show-current
    Write-ColorOutput "Branche actuelle: $currentBranch" "Cyan"
    
    # Afficher l'état git
    Write-ColorOutput "État des fichiers:" "Cyan"
    git status --short
    
    return $true
}

# Fonction pour générer les commandes git pour les commits
function Show-GitCommitCommands {
    Write-ColorOutput "`n=== Commandes Git pour les commits ===" "Magenta"
    
    Write-ColorOutput "Voici les commandes git à exécuter pour committer les modifications:" "Cyan"
    
    Write-ColorOutput "`n# Commit 1: Mise à jour du .gitignore et des fichiers .env.example" "Yellow"
    Write-ColorOutput "git add .gitignore vllm-configs/.gitignore vllm-configs/.env.example vllm-configs/huggingface.env.example" "White"
    Write-ColorOutput "git commit -m 'Sécurisation: Mise à jour du .gitignore pour exclure les fichiers sensibles'" "White"
    
    Write-ColorOutput "`n# Commit 2: Correction des chemins hardcodés dans les fichiers docker-compose" "Yellow"
    Write-ColorOutput "git add vllm-configs/docker-compose/*.yml" "White"
    Write-ColorOutput "git commit -m 'Sécurisation: Remplacement des chemins hardcodés par des variables d'environnement'" "White"
    
    Write-ColorOutput "`n# Commit 3: Suppression des clés API hardcodées" "Yellow"
    Write-ColorOutput "git add vllm-configs/docker-compose/docker-compose-micro-qwen3-new.yml vllm-configs/docker-compose/docker-compose-micro-qwen3-improved.yml" "White"
    Write-ColorOutput "git commit -m 'Sécurisation: Suppression des clés API hardcodées dans les fichiers de configuration'" "White"
    
    Write-ColorOutput "`n# Commit 4: Correction des chemins hardcodés dans les scripts PowerShell" "Yellow"
    Write-ColorOutput "git add vllm-configs/scripts/*.ps1 vllm-configs/*.ps1" "White"
    Write-ColorOutput "git commit -m 'Sécurisation: Utilisation de chemins relatifs et variables d'environnement dans les scripts'" "White"
    
    Write-ColorOutput "`n# Commit 5: Documentation du processus de sécurisation" "Yellow"
    Write-ColorOutput "git add vllm-configs/SECURITY-GUIDE.md" "White"
    Write-ColorOutput "git commit -m 'Documentation: Guide de sécurisation pour les commits et push'" "White"
    
    Write-ColorOutput "`n# Vérifier une dernière fois qu'aucun fichier sensible n'est inclus" "Yellow"
    Write-ColorOutput "git status" "White"
    
    Write-ColorOutput "`n# Push vers le dépôt distant" "Yellow"
    Write-ColorOutput "git push origin $(git branch --show-current)" "White"
}

# Fonction pour vérifier les fichiers sensibles avant push
function Test-SensitiveFilesBeforePush {
    Write-ColorOutput "`n=== Vérification finale des fichiers sensibles ===" "Magenta"
    
    # Vérifier si des fichiers .env sont inclus dans le commit
    $envFiles = git diff --cached --name-only | Where-Object { $_ -match '\.env$' -and $_ -notmatch '\.env\.example$' }
    
    if ($envFiles.Count -gt 0) {
        Write-ColorOutput "⚠️ ATTENTION: Des fichiers .env sont inclus dans le commit:" "Red"
        foreach ($file in $envFiles) {
            Write-ColorOutput "  - $file" "Red"
        }
        Write-ColorOutput "Ces fichiers contiennent probablement des secrets et ne devraient pas être commités." "Red"
        Write-ColorOutput "Utilisez 'git reset HEAD <fichier>' pour les retirer du commit." "Yellow"
        return $false
    }
    
    # Rechercher des tokens ou clés API dans les fichiers à committer
    $suspiciousFiles = @()
    $filesToCheck = git diff --cached --name-only
    
    foreach ($file in $filesToCheck) {
        if (Test-Path -Path $file) {
            $content = Get-Content -Path $file -Raw
            
            # Rechercher des motifs de secrets
            $secretPatterns = @(
                'hf_[a-zA-Z0-9]{20,}',                  # Hugging Face tokens
                'sk-[a-zA-Z0-9]{20,}',                  # OpenAI API keys
                'github_pat_[a-zA-Z0-9]{20,}',          # GitHub tokens
                'ghp_[a-zA-Z0-9]{20,}',                 # GitHub tokens (new format)
                'api[_-]?key["\s:=]+[a-zA-Z0-9]{16,}',  # Generic API keys
                'password["\s:=]+[^\s]{8,}',            # Passwords
                'secret["\s:=]+[^\s]{8,}'               # Secrets
            )
            
            foreach ($pattern in $secretPatterns) {
                if ($content -match $pattern) {
                    $suspiciousFiles += $file
                    break
                }
            }
        }
    }
    
    if ($suspiciousFiles.Count -gt 0) {
        Write-ColorOutput "⚠️ ATTENTION: Des fichiers potentiellement sensibles sont inclus dans le commit:" "Red"
        foreach ($file in $suspiciousFiles) {
            Write-ColorOutput "  - $file" "Red"
        }
        Write-ColorOutput "Ces fichiers pourraient contenir des secrets. Veuillez les vérifier avant de committer." "Red"
        return $false
    }
    
    Write-ColorOutput "✓ Aucun fichier sensible détecté dans les fichiers à committer" "Green"
    return $true
}

# Fonction principale
function Main {
    Write-ColorOutput "=== Préparation des commits et push sécurisés pour Qwen3 ===" "Magenta"
    
    # Vérifier l'état git initial
    if (-not (Show-GitStatus)) {
        return
    }
    
    # Chemin des scripts
    $scriptDir = $PSScriptRoot
    $updateGitignoreScript = Join-Path -Path $scriptDir -ChildPath "update-gitignore.ps1"
    $fixHardcodedPathsScript = Join-Path -Path $scriptDir -ChildPath "fix-hardcoded-paths.ps1"
    $removeApiKeysScript = Join-Path -Path $scriptDir -ChildPath "remove-hardcoded-api-keys.ps1"
    
    # Étape 1: Mettre à jour le .gitignore
    $gitignoreUpdated = Invoke-SecurityScript -ScriptPath $updateGitignoreScript -Description "Mise à jour du .gitignore"
    
    # Étape 2: Corriger les chemins hardcodés
    $pathsFixed = Invoke-SecurityScript -ScriptPath $fixHardcodedPathsScript -Description "Correction des chemins hardcodés"
    
    # Étape 3: Supprimer les clés API hardcodées
    $apiKeysRemoved = Invoke-SecurityScript -ScriptPath $removeApiKeysScript -Description "Suppression des clés API hardcodées"
    
    # Vérifier l'état git après les modifications
    Show-GitStatus
    
    # Vérifier les fichiers sensibles avant push
    $safeToCommit = Test-SensitiveFilesBeforePush
    
    # Afficher les commandes git pour les commits
    if ($safeToCommit) {
        Show-GitCommitCommands
    }
    else {
        Write-ColorOutput "`n⚠️ Des problèmes ont été détectés. Veuillez les corriger avant de committer." "Red"
    }
    
    Write-ColorOutput "`n=== Fin de la préparation des commits et push sécurisés ===" "Magenta"
    
    if ($safeToCommit) {
        Write-ColorOutput "Vous pouvez maintenant procéder aux commits et push en suivant les commandes ci-dessus." "Green"
    }
}

# Exécuter la fonction principale
Main