# Script PowerShell pour préparer les commits sécurisés pour Qwen3
# Ce script vérifie qu'aucun secret n'est exposé et prépare les fichiers pour le commit

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

# Fonction pour vérifier les secrets dans les fichiers
function Test-FileForSecrets {
    param (
        [Parameter(Mandatory = $true)]
        [string]$FilePath
    )
    
    $content = Get-Content -Path $FilePath -Raw
    $secretPatterns = @(
        'hf_[a-zA-Z0-9]{20,}',                  # Hugging Face tokens
        'sk-[a-zA-Z0-9]{20,}',                  # OpenAI API keys
        'github_pat_[a-zA-Z0-9]{20,}',          # GitHub tokens
        'ghp_[a-zA-Z0-9]{20,}',                 # GitHub tokens (new format)
        'api[_-]?key["\s:=]+[a-zA-Z0-9]{16,}',  # Generic API keys
        'password["\s:=]+[^\s]{8,}',            # Passwords
        'secret["\s:=]+[^\s]{8,}'               # Secrets
    )
    
    $foundSecrets = $false
    foreach ($pattern in $secretPatterns) {
        if ($content -match $pattern) {
            $foundSecrets = $true
            Write-ColorOutput "ALERTE: Secret potentiel trouvé dans $FilePath (motif: $pattern)" "Red"
            Write-ColorOutput "  Correspondance: $($Matches[0])" "Red"
        }
    }
    
    return -not $foundSecrets
}

# Fonction pour vérifier les chemins hardcodés
function Test-FileForHardcodedPaths {
    param (
        [Parameter(Mandatory = $true)]
        [string]$FilePath
    )
    
    $content = Get-Content -Path $FilePath -Raw
    $pathPatterns = @(
        '\\\\wsl\.localhost\\\\Ubuntu\\\\home\\\\[a-zA-Z0-9]+',  # WSL paths
        'D:\\\\vllm',                                           # Absolute Windows paths
        'G:\\\\Mon Drive'                                       # Google Drive paths
    )
    
    $foundPaths = $false
    foreach ($pattern in $pathPatterns) {
        if ($content -match $pattern) {
            $foundPaths = $true
            Write-ColorOutput "ALERTE: Chemin hardcodé trouvé dans $FilePath (motif: $pattern)" "Yellow"
            Write-ColorOutput "  Correspondance: $($Matches[0])" "Yellow"
        }
    }
    
    return -not $foundPaths
}

# Fonction pour vérifier si un fichier est ignoré par git
function Test-GitIgnored {
    param (
        [Parameter(Mandatory = $true)]
        [string]$FilePath
    )
    
    $output = git check-ignore -v $FilePath 2>&1
    return $LASTEXITCODE -eq 0
}

# Fonction pour vérifier les fichiers sensibles
function Test-SensitiveFiles {
    $sensitivePatterns = @(
        "*.env",
        "huggingface.env",
        "*.log",
        "*.key",
        "*.pem",
        "*.pfx",
        "*.p12"
    )
    
    $foundSensitiveFiles = $false
    foreach ($pattern in $sensitivePatterns) {
        $files = Get-ChildItem -Path "." -Recurse -File -Filter $pattern
        foreach ($file in $files) {
            if (-not (Test-GitIgnored -FilePath $file.FullName)) {
                $foundSensitiveFiles = $true
                Write-ColorOutput "ALERTE: Fichier sensible non ignoré par git: $($file.FullName)" "Red"
            }
        }
    }
    
    return -not $foundSensitiveFiles
}

# Fonction pour mettre à jour le .gitignore
function Update-GitIgnore {
    $gitignorePath = ".gitignore"
    $gitignoreContent = Get-Content -Path $gitignorePath -Raw
    
    $entriesToAdd = @(
        "# Secrets et fichiers sensibles",
        ".env",
        "huggingface.env",
        "*.env",
        "!*.env.example",
        "*.log",
        "logs/",
        "*.key",
        "*.pem",
        "*.pfx",
        "*.p12"
    )
    
    $modified = $false
    foreach ($entry in $entriesToAdd) {
        if (-not ($gitignoreContent -match [regex]::Escape($entry))) {
            $gitignoreContent += "`n$entry"
            $modified = $true
        }
    }
    
    # Supprimer les lignes qui incluent explicitement des fichiers sensibles
    $linesToRemove = @(
        "!.env",
        "!huggingface.env"
    )
    
    foreach ($line in $linesToRemove) {
        if ($gitignoreContent -match [regex]::Escape($line)) {
            $gitignoreContent = $gitignoreContent -replace [regex]::Escape($line), ""
            $modified = $true
        }
    }
    
    if ($modified) {
        Set-Content -Path $gitignorePath -Value $gitignoreContent
        Write-ColorOutput "✓ Fichier .gitignore mis à jour" "Green"
    }
    else {
        Write-ColorOutput "✓ Fichier .gitignore déjà correctement configuré" "Green"
    }
}

# Fonction pour créer ou mettre à jour les fichiers .env.example
function Update-EnvExampleFiles {
    $envFiles = @(
        @{
            "Source" = ".env";
            "Example" = ".env.example"
        },
        @{
            "Source" = "vllm-configs/.env";
            "Example" = "vllm-configs/.env.example"
        },
        @{
            "Source" = "vllm-configs/huggingface.env";
            "Example" = "vllm-configs/huggingface.env.example"
        }
    )
    
    foreach ($envFile in $envFiles) {
        $sourcePath = $envFile.Source
        $examplePath = $envFile.Example
        
        if (Test-Path -Path $sourcePath) {
            if (-not (Test-Path -Path $examplePath)) {
                # Créer un nouveau fichier .env.example basé sur .env mais avec des placeholders
                $sourceContent = Get-Content -Path $sourcePath -Raw
                $exampleContent = $sourceContent -replace '=.*', '=YOUR_VALUE_HERE'
                Set-Content -Path $examplePath -Value $exampleContent
                Write-ColorOutput "✓ Fichier $examplePath créé" "Green"
            }
            else {
                # Vérifier que le fichier .env.example contient toutes les variables du fichier .env
                $sourceLines = Get-Content -Path $sourcePath | Where-Object { $_ -match '^[A-Za-z0-9_]+=.+' }
                $exampleLines = Get-Content -Path $examplePath
                
                $modified = $false
                foreach ($line in $sourceLines) {
                    $varName = ($line -split '=')[0]
                    $exampleVar = $exampleLines | Where-Object { $_ -match "^$varName=" }
                    
                    if (-not $exampleVar) {
                        $exampleContent = Get-Content -Path $examplePath -Raw
                        $newLine = "$varName=YOUR_VALUE_HERE"
                        $exampleContent += "`n$newLine"
                        Set-Content -Path $examplePath -Value $exampleContent
                        $modified = $true
                    }
                }
                
                if ($modified) {
                    Write-ColorOutput "✓ Fichier $examplePath mis à jour avec de nouvelles variables" "Green"
                }
                else {
                    Write-ColorOutput "✓ Fichier $examplePath déjà à jour" "Green"
                }
            }
        }
    }
}

# Fonction pour vérifier les fichiers docker-compose
function Test-DockerComposeFiles {
    $dockerComposeDir = "vllm-configs/docker-compose"
    $dockerComposeFiles = Get-ChildItem -Path $dockerComposeDir -Filter "*.yml"
    
    $allValid = $true
    foreach ($file in $dockerComposeFiles) {
        $fileValid = $true
        
        # Vérifier les secrets
        if (-not (Test-FileForSecrets -FilePath $file.FullName)) {
            $fileValid = $false
            $allValid = $false
        }
        
        # Vérifier les chemins hardcodés
        if (-not (Test-FileForHardcodedPaths -FilePath $file.FullName)) {
            $fileValid = $false
            $allValid = $false
        }
        
        if ($fileValid) {
            Write-ColorOutput "✓ $($file.Name) est valide" "Green"
        }
        else {
            Write-ColorOutput "✗ $($file.Name) contient des problèmes" "Red"
        }
    }
    
    return $allValid
}

# Fonction pour vérifier les scripts PowerShell
function Test-PowerShellScripts {
    $scriptDirs = @(
        "vllm-configs",
        "vllm-configs/scripts"
    )
    
    $allValid = $true
    foreach ($dir in $scriptDirs) {
        $scripts = Get-ChildItem -Path $dir -Filter "*.ps1"
        
        foreach ($script in $scripts) {
            $fileValid = $true
            
            # Vérifier les secrets
            if (-not (Test-FileForSecrets -FilePath $script.FullName)) {
                $fileValid = $false
                $allValid = $false
            }
            
            # Vérifier les chemins hardcodés
            if (-not (Test-FileForHardcodedPaths -FilePath $script.FullName)) {
                $fileValid = $false
                $allValid = $false
            }
            
            if ($fileValid) {
                Write-ColorOutput "✓ $($script.Name) est valide" "Green"
            }
            else {
                Write-ColorOutput "✗ $($script.Name) contient des problèmes" "Red"
            }
        }
    }
    
    return $allValid
}

# Fonction principale
function Main {
    Write-ColorOutput "=== Préparation des commits sécurisés pour Qwen3 ===" "Magenta"
    
    # Vérifier si nous sommes dans un dépôt git
    if (-not (Test-Path -Path ".git")) {
        Write-ColorOutput "Ce script doit être exécuté à la racine d'un dépôt git." "Red"
        return
    }
    
    # Mettre à jour le .gitignore
    Write-ColorOutput "Mise à jour du .gitignore..." "Cyan"
    Update-GitIgnore
    
    # Mettre à jour les fichiers .env.example
    Write-ColorOutput "Mise à jour des fichiers .env.example..." "Cyan"
    Update-EnvExampleFiles
    
    # Vérifier les fichiers sensibles
    Write-ColorOutput "Vérification des fichiers sensibles..." "Cyan"
    $sensitivesOk = Test-SensitiveFiles
    
    # Vérifier les fichiers docker-compose
    Write-ColorOutput "Vérification des fichiers docker-compose..." "Cyan"
    $dockerComposeOk = Test-DockerComposeFiles
    
    # Vérifier les scripts PowerShell
    Write-ColorOutput "Vérification des scripts PowerShell..." "Cyan"
    $scriptsOk = Test-PowerShellScripts
    
    # Afficher le résultat final
    Write-ColorOutput "`n=== Résultat de la vérification ===" "Magenta"
    
    if ($sensitivesOk -and $dockerComposeOk -and $scriptsOk) {
        Write-ColorOutput "✓ Tous les fichiers sont prêts pour le commit" "Green"
        Write-ColorOutput "`nVous pouvez maintenant procéder aux commits avec les commandes suivantes:" "Cyan"
        Write-ColorOutput "git add .gitignore vllm-configs/.env.example vllm-configs/huggingface.env.example" "White"
        Write-ColorOutput "git commit -m 'Sécurisation: Mise à jour du .gitignore pour exclure les fichiers sensibles'" "White"
        Write-ColorOutput "git add vllm-configs/docker-compose/*.yml" "White"
        Write-ColorOutput "git commit -m 'Sécurisation: Remplacement des chemins hardcodés par des variables d'environnement'" "White"
        Write-ColorOutput "git add vllm-configs/scripts/*.ps1" "White"
        Write-ColorOutput "git commit -m 'Sécurisation: Utilisation de chemins relatifs et variables d'environnement dans les scripts'" "White"
        Write-ColorOutput "git add vllm-configs/SECURITY-GUIDE.md" "White"
        Write-ColorOutput "git commit -m 'Documentation: Guide de sécurisation pour les commits et push'" "White"
    }
    else {
        Write-ColorOutput "✗ Des problèmes ont été détectés. Veuillez les corriger avant de committer." "Red"
    }
}

# Exécuter la fonction principale
Main