# Script PowerShell pour configurer l'environnement Qwen3
# Ce script vérifie les prérequis, clone le dépôt si nécessaire,
# checkout la branche consolidée et déploie les containers avec la configuration optimisée

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

# Fonction pour vérifier si une commande existe
function Test-CommandExists {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Command
    )
    
    $exists = $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
    return $exists
}

# Fonction pour vérifier les prérequis
function Test-Prerequisites {
    Write-ColorOutput "Vérification des prérequis..." "Cyan"
    
    # Vérifier Docker
    if (-not (Test-CommandExists "docker")) {
        Write-ColorOutput "Docker n'est pas installé. Veuillez l'installer avant de continuer." "Red"
        return $false
    }
    Write-ColorOutput "✓ Docker est installé" "Green"
    
    # Vérifier Docker Compose
    $dockerComposeVersion = docker compose version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-ColorOutput "Docker Compose n'est pas installé. Veuillez l'installer avant de continuer." "Red"
        return $false
    }
    Write-ColorOutput "✓ Docker Compose est installé" "Green"
    
    # Vérifier Git
    if (-not (Test-CommandExists "git")) {
        Write-ColorOutput "Git n'est pas installé. Veuillez l'installer avant de continuer." "Red"
        return $false
    }
    Write-ColorOutput "✓ Git est installé" "Green"
    
    # Vérifier NVIDIA Container Toolkit
    $dockerInfo = docker info --format '{{json .}}' | ConvertFrom-Json
    $runtimeNames = $dockerInfo.Runtimes.PSObject.Properties.Name
    if (-not ($runtimeNames -contains "nvidia")) {
        Write-ColorOutput "NVIDIA Container Toolkit n'est pas installé ou configuré. Veuillez l'installer avant de continuer." "Red"
        return $false
    }
    Write-ColorOutput "✓ NVIDIA Container Toolkit est installé" "Green"
    
    # Vérifier les GPUs NVIDIA
    try {
        $gpuInfo = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
        if ($LASTEXITCODE -ne 0) {
            throw "Erreur lors de l'exécution de nvidia-smi"
        }
        
        $gpuCount = ($gpuInfo -split "`n").Count
        Write-ColorOutput "✓ $gpuCount GPU(s) NVIDIA détecté(s)" "Green"
        
        foreach ($gpu in $gpuInfo -split "`n") {
            Write-ColorOutput "  - $gpu" "Green"
        }
        
        if ($gpuCount -lt 2) {
            Write-ColorOutput "⚠ Attention: Au moins 2 GPUs sont recommandés pour le modèle medium" "Yellow"
        }
    }
    catch {
        Write-ColorOutput "Impossible de détecter les GPUs NVIDIA. Veuillez vérifier que les pilotes NVIDIA sont installés." "Red"
        return $false
    }
    
    return $true
}

# Fonction pour cloner le dépôt si nécessaire
function Initialize-Repository {
    param (
        [Parameter(Mandatory = $false)]
        [string]$RepoPath = "."
    )
    
    Write-ColorOutput "Initialisation du dépôt..." "Cyan"
    
    # Vérifier si le dépôt existe déjà
    if (-not (Test-Path -Path "$RepoPath\.git")) {
        # Le dépôt n'existe pas, demander à l'utilisateur s'il souhaite le cloner
        $repoUrl = Read-Host "Le dépôt Git n'existe pas dans ce répertoire. Veuillez entrer l'URL du dépôt à cloner (ou laisser vide pour ignorer)"
        
        if (-not [string]::IsNullOrWhiteSpace($repoUrl)) {
            Write-ColorOutput "Clonage du dépôt depuis $repoUrl..." "Cyan"
            git clone $repoUrl $RepoPath
            
            if ($LASTEXITCODE -ne 0) {
                Write-ColorOutput "Erreur lors du clonage du dépôt." "Red"
                return $false
            }
            
            Write-ColorOutput "✓ Dépôt cloné avec succès" "Green"
        }
        else {
            Write-ColorOutput "Aucun dépôt cloné. Utilisation du répertoire actuel." "Yellow"
        }
    }
    else {
        Write-ColorOutput "✓ Le dépôt Git existe déjà" "Green"
    }
    
    return $true
}

# Fonction pour checkout la branche consolidée
function Checkout-ConsolidatedBranch {
    param (
        [Parameter(Mandatory = $false)]
        [string]$RepoPath = ".",
        
        [Parameter(Mandatory = $false)]
        [string]$Branch = "qwen3-consolidated"
    )
    
    Write-ColorOutput "Checkout de la branche $Branch..." "Cyan"
    
    # Vérifier si la branche existe localement
    $localBranches = git -C $RepoPath branch --list $Branch
    $remoteBranches = git -C $RepoPath branch -r --list "*/$Branch"
    
    if ([string]::IsNullOrWhiteSpace($localBranches) -and [string]::IsNullOrWhiteSpace($remoteBranches)) {
        Write-ColorOutput "La branche $Branch n'existe pas localement ou à distance." "Red"
        
        # Demander à l'utilisateur s'il souhaite créer la branche
        $createBranch = Read-Host "Souhaitez-vous créer la branche $Branch? (O/N)"
        
        if ($createBranch -eq "O" -or $createBranch -eq "o") {
            Write-ColorOutput "Création de la branche $Branch..." "Cyan"
            git -C $RepoPath checkout -b $Branch
            
            if ($LASTEXITCODE -ne 0) {
                Write-ColorOutput "Erreur lors de la création de la branche $Branch." "Red"
                return $false
            }
            
            Write-ColorOutput "✓ Branche $Branch créée avec succès" "Green"
        }
        else {
            Write-ColorOutput "Opération annulée. La branche $Branch n'a pas été créée." "Yellow"
            return $false
        }
    }
    else {
        # Checkout de la branche
        git -C $RepoPath checkout $Branch
        
        if ($LASTEXITCODE -ne 0) {
            Write-ColorOutput "Erreur lors du checkout de la branche $Branch." "Red"
            return $false
        }
        
        Write-ColorOutput "✓ Branche $Branch checkout avec succès" "Green"
        
        # Mettre à jour la branche si elle existe à distance
        if (-not [string]::IsNullOrWhiteSpace($remoteBranches)) {
            Write-ColorOutput "Mise à jour de la branche $Branch depuis le dépôt distant..." "Cyan"
            git -C $RepoPath pull
            
            if ($LASTEXITCODE -ne 0) {
                Write-ColorOutput "⚠ Avertissement: Impossible de mettre à jour la branche depuis le dépôt distant." "Yellow"
            }
            else {
                Write-ColorOutput "✓ Branche $Branch mise à jour avec succès" "Green"
            }
        }
    }
    
    return $true
}

# Fonction pour vérifier et créer le fichier huggingface.env
function Initialize-HuggingFaceToken {
    param (
        [Parameter(Mandatory = $false)]
        [string]$ConfigPath = "myia-vllm/qwen3"
    )
    
    Write-ColorOutput "Configuration du token Hugging Face..." "Cyan"
    
    $envFilePath = "$ConfigPath\configs\huggingface.env"
    $envExamplePath = "$ConfigPath\configs\huggingface.env.example"
    
    # Vérifier si le fichier huggingface.env existe déjà
    if (-not (Test-Path -Path $envFilePath)) {
        # Vérifier si le fichier exemple existe
        if (Test-Path -Path $envExamplePath) {
            # Copier le fichier exemple
            Copy-Item -Path $envExamplePath -Destination $envFilePath
            Write-ColorOutput "✓ Fichier $envFilePath créé à partir de l'exemple" "Green"
        }
        else {
            # Créer un nouveau fichier
            New-Item -Path $envFilePath -ItemType File -Force | Out-Null
            Write-ColorOutput "✓ Fichier $envFilePath créé" "Green"
        }
        
        # Demander le token à l'utilisateur
        $token = Read-Host "Veuillez entrer votre token Hugging Face (ou laisser vide pour le configurer plus tard)"
        
        if (-not [string]::IsNullOrWhiteSpace($token)) {
            # Écrire le token dans le fichier
            Set-Content -Path $envFilePath -Value "HF_TOKEN=$token"
            Write-ColorOutput "✓ Token Hugging Face configuré" "Green"
        }
        else {
            Write-ColorOutput "⚠ Aucun token configuré. Vous devrez le configurer manuellement avant de déployer les containers." "Yellow"
            Set-Content -Path $envFilePath -Value "HF_TOKEN=your_token_here"
        }
    }
    else {
        Write-ColorOutput "✓ Fichier $envFilePath existe déjà" "Green"
        
        # Vérifier si le token est configuré
        $envContent = Get-Content -Path $envFilePath -Raw
        if ($envContent -match "HF_TOKEN=your_token_here" -or $envContent -match "HF_TOKEN=$") {
            Write-ColorOutput "⚠ Le token Hugging Face n'est pas configuré correctement dans $envFilePath" "Yellow"
            
            # Demander le token à l'utilisateur
            $token = Read-Host "Veuillez entrer votre token Hugging Face (ou laisser vide pour le configurer plus tard)"
            
            if (-not [string]::IsNullOrWhiteSpace($token)) {
                # Mettre à jour le token dans le fichier
                $envContent = $envContent -replace "HF_TOKEN=.*", "HF_TOKEN=$token"
                Set-Content -Path $envFilePath -Value $envContent
                Write-ColorOutput "✓ Token Hugging Face mis à jour" "Green"
            }
        }
        else {
            Write-ColorOutput "✓ Token Hugging Face déjà configuré" "Green"
        }
    }
    
    return $true
}

# Fonction pour déployer les containers
function Deploy-Containers {
    param (
        [Parameter(Mandatory = $false)]
        [string]$ConfigPath = "myia-vllm/qwen3"
    )
    
    Write-ColorOutput "Déploiement des containers Qwen3..." "Cyan"
    
    # Vérifier si le script de déploiement existe
    $deployScriptPath = "$ConfigPath\deployment\scripts\deploy-qwen3-containers.ps1"
    if (Test-Path -Path $deployScriptPath) {
        # Exécuter le script de déploiement
        Write-ColorOutput "Exécution du script de déploiement $deployScriptPath..." "Cyan"
        & $deployScriptPath
        
        if ($LASTEXITCODE -ne 0) {
            Write-ColorOutput "Erreur lors du déploiement des containers." "Red"
            return $false
        }
        
        Write-ColorOutput "✓ Containers déployés avec succès" "Green"
    }
    else {
        # Déployer manuellement les containers
        Write-ColorOutput "Script de déploiement non trouvé. Déploiement manuel des containers..." "Yellow"
        
        # Déployer le container micro
        Write-ColorOutput "Déploiement du container micro..." "Cyan"
        docker compose -p myia-vllm -f "$ConfigPath\deployment\docker\docker-compose-micro-qwen3.yml" up -d
        
        if ($LASTEXITCODE -ne 0) {
            Write-ColorOutput "Erreur lors du déploiement du container micro." "Red"
        }
        else {
            Write-ColorOutput "✓ Container micro déployé avec succès" "Green"
        }
        
        # Déployer le container mini
        Write-ColorOutput "Déploiement du container mini..." "Cyan"
        docker compose -p myia-vllm -f "$ConfigPath\deployment\docker\docker-compose-mini-qwen3.yml" up -d
        
        if ($LASTEXITCODE -ne 0) {
            Write-ColorOutput "Erreur lors du déploiement du container mini." "Red"
        }
        else {
            Write-ColorOutput "✓ Container mini déployé avec succès" "Green"
        }
        
        # Déployer le container medium avec la configuration optimisée
        Write-ColorOutput "Déploiement du container medium avec la configuration optimisée..." "Cyan"
        docker compose -p myia-vllm -f "$ConfigPath\deployment\docker\docker-compose-medium-qwen3-memory-optimized.yml" up -d
        
        if ($LASTEXITCODE -ne 0) {
            Write-ColorOutput "Erreur lors du déploiement du container medium." "Red"
        }
        else {
            Write-ColorOutput "✓ Container medium déployé avec succès" "Green"
        }
    }
    
    return $true
}

# Fonction principale
function Main {
    Write-ColorOutput "=== Configuration de l'environnement Qwen3 ===" "Magenta"
    
    # Vérifier les prérequis
    if (-not (Test-Prerequisites)) {
        Write-ColorOutput "Certains prérequis ne sont pas satisfaits. Veuillez les installer avant de continuer." "Red"
        return
    }
    
    # Initialiser le dépôt
    if (-not (Initialize-Repository)) {
        Write-ColorOutput "Erreur lors de l'initialisation du dépôt." "Red"
        return
    }
    
    # Checkout la branche consolidée
    if (-not (Checkout-ConsolidatedBranch)) {
        Write-ColorOutput "Erreur lors du checkout de la branche consolidée." "Red"
        return
    }
    
    # Configurer le token Hugging Face
    if (-not (Initialize-HuggingFaceToken)) {
        Write-ColorOutput "Erreur lors de la configuration du token Hugging Face." "Red"
        return
    }
    
    # Déployer les containers
    if (-not (Deploy-Containers)) {
        Write-ColorOutput "Erreur lors du déploiement des containers." "Red"
        return
    }
    
    Write-ColorOutput "=== Configuration de l'environnement Qwen3 terminée avec succès ===" "Magenta"
    Write-ColorOutput "Les containers Qwen3 sont maintenant déployés avec la configuration optimisée." "Green"
    Write-ColorOutput "Vous pouvez vérifier leur état avec la commande: docker ps | Select-String myia-vllm" "Cyan"
    Write-ColorOutput "Pour plus d'informations, consultez les guides:" "Cyan"
    Write-ColorOutput "- docs/QWEN3-USER-GUIDE.md" "Cyan"
    Write-ColorOutput "- docs/QWEN3-MAINTENANCE-GUIDE.md" "Cyan"
}

# Exécuter la fonction principale
Main