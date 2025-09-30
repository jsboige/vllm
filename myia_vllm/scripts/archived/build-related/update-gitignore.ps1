# Script PowerShell pour mettre à jour le fichier .gitignore
# Ce script modifie le fichier .gitignore pour exclure les fichiers sensibles

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

# Fonction pour mettre à jour le .gitignore
function Update-GitIgnore {
    param (
        [Parameter(Mandatory = $false)]
        [string]$GitIgnorePath = ".gitignore"
    )
    
    Write-ColorOutput "Mise à jour du fichier .gitignore..." "Cyan"
    
    # Vérifier si le fichier .gitignore existe
    if (-not (Test-Path -Path $GitIgnorePath)) {
        Write-ColorOutput "Le fichier .gitignore n'existe pas. Création du fichier..." "Yellow"
        New-Item -Path $GitIgnorePath -ItemType File -Force | Out-Null
    }
    
    # Lire le contenu actuel du .gitignore
    $gitignoreContent = Get-Content -Path $GitIgnorePath -Raw
    if ($null -eq $gitignoreContent) {
        $gitignoreContent = ""
    }
    
    # Entrées à ajouter au .gitignore
    $entriesToAdd = @(
        "# Secrets et fichiers sensibles",
        ".env",
        "huggingface.env",
        "*.env",
        "!*.env.example",
        "*.log",
        "logs/",
        "__pycache__/",
        "*.pyc",
        "*.pyo",
        "*.pyd",
        ".Python",
        "env/",
        "venv/",
        "ENV/",
        ".venv",
        ".env.local",
        ".env.development.local",
        ".env.test.local",
        ".env.production.local",
        "*.key",
        "*.pem",
        "*.pfx",
        "*.p12",
        "*.cer",
        "*.der",
        "*.crt",
        "# Caches",
        ".cache/",
        "huggingface_cache/",
        "# Fichiers temporaires",
        "*.tmp",
        "*.bak",
        "*.swp",
        "*.swo",
        "*~",
        "# Fichiers système",
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini"
    )
    
    # Entrées à supprimer du .gitignore (lignes qui incluent explicitement des fichiers sensibles)
    $entriesToRemove = @(
        "!.env",
        "!huggingface.env"
    )
    
    # Supprimer les entrées indésirables
    $modified = $false
    foreach ($entry in $entriesToRemove) {
        if ($gitignoreContent -match [regex]::Escape($entry)) {
            Write-ColorOutput "Suppression de l'entrée: $entry" "Yellow"
            $gitignoreContent = $gitignoreContent -replace "(?m)^$([regex]::Escape($entry))$", ""
            $modified = $true
        }
    }
    
    # Ajouter les nouvelles entrées si elles n'existent pas déjà
    foreach ($entry in $entriesToAdd) {
        # Ignorer les commentaires lors de la vérification des doublons
        if ($entry.StartsWith("#")) {
            if (-not ($gitignoreContent -match [regex]::Escape($entry))) {
                $gitignoreContent += "`n$entry"
                $modified = $true
            }
        }
        else {
            # Pour les entrées non-commentaires, vérifier si elles existent déjà
            if (-not ($gitignoreContent -match "(?m)^$([regex]::Escape($entry))$")) {
                $gitignoreContent += "`n$entry"
                $modified = $true
            }
        }
    }
    
    # Nettoyer les lignes vides multiples
    $gitignoreContent = $gitignoreContent -replace "(?m)^\s*\n\s*\n\s*\n+", "`n`n"
    
    # Écrire le contenu mis à jour dans le fichier .gitignore
    if ($modified) {
        Set-Content -Path $GitIgnorePath -Value $gitignoreContent
        Write-ColorOutput "✓ Fichier .gitignore mis à jour avec succès" "Green"
    }
    else {
        Write-ColorOutput "✓ Fichier .gitignore déjà correctement configuré" "Green"
    }
    
    return $modified
}

# Fonction pour vérifier si le fichier .gitignore est correctement configuré
function Test-GitIgnoreConfiguration {
    param (
        [Parameter(Mandatory = $false)]
        [string]$GitIgnorePath = ".gitignore"
    )
    
    Write-ColorOutput "Vérification de la configuration du fichier .gitignore..." "Cyan"
    
    # Vérifier si le fichier .gitignore existe
    if (-not (Test-Path -Path $GitIgnorePath)) {
        Write-ColorOutput "✗ Le fichier .gitignore n'existe pas" "Red"
        return $false
    }
    
    # Lire le contenu du .gitignore
    $gitignoreContent = Get-Content -Path $GitIgnorePath -Raw
    
    # Vérifier que les fichiers sensibles sont exclus
    $requiredEntries = @(
        ".env",
        "huggingface.env",
        "*.env",
        "!*.env.example"
    )
    
    # Vérifier que les entrées indésirables ne sont pas présentes
    $forbiddenEntries = @(
        "!.env",
        "!huggingface.env"
    )
    
    $allRequiredPresent = $true
    foreach ($entry in $requiredEntries) {
        if (-not ($gitignoreContent -match "(?m)^$([regex]::Escape($entry))$")) {
            Write-ColorOutput "✗ Entrée manquante dans .gitignore: $entry" "Red"
            $allRequiredPresent = $false
        }
    }
    
    $noForbiddenPresent = $true
    foreach ($entry in $forbiddenEntries) {
        if ($gitignoreContent -match "(?m)^$([regex]::Escape($entry))$") {
            Write-ColorOutput "✗ Entrée indésirable dans .gitignore: $entry" "Red"
            $noForbiddenPresent = $false
        }
    }
    
    if ($allRequiredPresent -and $noForbiddenPresent) {
        Write-ColorOutput "✓ Fichier .gitignore correctement configuré" "Green"
        return $true
    }
    else {
        return $false
    }
}

# Fonction principale
function Main {
    Write-ColorOutput "=== Mise à jour du fichier .gitignore pour Qwen3 ===" "Magenta"
    
    # Chemin du fichier .gitignore
    $gitignorePath = ".gitignore"
    $vllmConfigsGitignorePath = "vllm-configs/.gitignore"
    
    # Mettre à jour le fichier .gitignore principal
    $mainUpdated = Update-GitIgnore -GitIgnorePath $gitignorePath
    
    # Mettre à jour le fichier .gitignore dans vllm-configs s'il existe
    if (Test-Path -Path $vllmConfigsGitignorePath) {
        $configsUpdated = Update-GitIgnore -GitIgnorePath $vllmConfigsGitignorePath
    }
    
    # Vérifier la configuration du .gitignore
    $mainConfigOk = Test-GitIgnoreConfiguration -GitIgnorePath $gitignorePath
    
    if (Test-Path -Path $vllmConfigsGitignorePath) {
        $configsConfigOk = Test-GitIgnoreConfiguration -GitIgnorePath $vllmConfigsGitignorePath
    }
    else {
        $configsConfigOk = $true  # Pas de fichier .gitignore dans vllm-configs, donc pas d'erreur
    }
    
    # Afficher le résultat final
    Write-ColorOutput "`n=== Résultat de la mise à jour ===" "Magenta"
    
    if ($mainConfigOk -and $configsConfigOk) {
        Write-ColorOutput "✓ Les fichiers .gitignore sont correctement configurés" "Green"
        Write-ColorOutput "`nVous pouvez maintenant committer les modifications:" "Cyan"
        Write-ColorOutput "git add .gitignore" "White"
        if (Test-Path -Path $vllmConfigsGitignorePath) {
            Write-ColorOutput "git add vllm-configs/.gitignore" "White"
        }
        Write-ColorOutput "git commit -m 'Sécurisation: Mise à jour du .gitignore pour exclure les fichiers sensibles'" "White"
    }
    else {
        Write-ColorOutput "✗ Des problèmes ont été détectés dans la configuration du .gitignore" "Red"
        Write-ColorOutput "Veuillez vérifier et corriger manuellement les fichiers .gitignore" "Red"
    }
}

# Exécuter la fonction principale
Main