# Script PowerShell pour corriger les chemins hardcodés dans les fichiers docker-compose
# Ce script remplace les chemins spécifiques à l'environnement par des variables d'environnement

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

# Fonction pour corriger les chemins hardcodés dans un fichier
function Fix-HardcodedPaths {
    param (
        [Parameter(Mandatory = $true)]
        [string]$FilePath
    )
    
    Write-ColorOutput "Traitement du fichier: $FilePath" "Cyan"
    
    # Vérifier si le fichier existe
    if (-not (Test-Path -Path $FilePath)) {
        Write-ColorOutput "✗ Le fichier n'existe pas: $FilePath" "Red"
        return $false
    }
    
    # Lire le contenu du fichier
    $content = Get-Content -Path $FilePath -Raw
    $originalContent = $content
    
    # Remplacer les chemins WSL hardcodés
    $wslPathPattern = '\\\\wsl\.localhost\\Ubuntu\\home\\[a-zA-Z0-9]+\\vllm\\\\.cache\\huggingface\\hub'
    if ($content -match $wslPathPattern) {
        Write-ColorOutput "  Remplacement des chemins WSL hardcodés..." "Yellow"
        $content = $content -replace $wslPathPattern, '${HF_CACHE_PATH}'
    }
    
    # Remplacer les chemins Windows hardcodés
    $winPathPattern = 'D:\\\\vllm'
    if ($content -match $winPathPattern) {
        Write-ColorOutput "  Remplacement des chemins Windows hardcodés..." "Yellow"
        $content = $content -replace $winPathPattern, '${VLLM_ROOT_DIR}'
    }
    
    # Remplacer les chemins Google Drive hardcodés
    $gdrivePathPattern = 'G:\\\\Mon Drive'
    if ($content -match $gdrivePathPattern) {
        Write-ColorOutput "  Remplacement des chemins Google Drive hardcodés..." "Yellow"
        $content = $content -replace $gdrivePathPattern, '${GDRIVE_PATH}'
    }
    
    # Vérifier si des modifications ont été apportées
    $modified = ($content -ne $originalContent)
    
    if ($modified) {
        # Écrire le contenu modifié dans le fichier
        Set-Content -Path $FilePath -Value $content
        Write-ColorOutput "✓ Chemins hardcodés corrigés dans: $FilePath" "Green"
    }
    else {
        Write-ColorOutput "✓ Aucun chemin hardcodé trouvé dans: $FilePath" "Green"
    }
    
    return $modified
}

# Fonction pour corriger les chemins hardcodés dans tous les fichiers docker-compose
function Fix-DockerComposeFiles {
    param (
        [Parameter(Mandatory = $false)]
        [string]$DockerComposeDir = "vllm-configs/docker-compose"
    )
    
    Write-ColorOutput "Correction des chemins hardcodés dans les fichiers docker-compose..." "Cyan"
    
    # Vérifier si le répertoire existe
    if (-not (Test-Path -Path $DockerComposeDir)) {
        Write-ColorOutput "✗ Le répertoire n'existe pas: $DockerComposeDir" "Red"
        return $false
    }
    
    # Récupérer tous les fichiers docker-compose
    $dockerComposeFiles = Get-ChildItem -Path $DockerComposeDir -Filter "*.yml"
    
    if ($dockerComposeFiles.Count -eq 0) {
        Write-ColorOutput "✗ Aucun fichier docker-compose trouvé dans: $DockerComposeDir" "Red"
        return $false
    }
    
    $modifiedCount = 0
    
    # Traiter chaque fichier docker-compose
    foreach ($file in $dockerComposeFiles) {
        $modified = Fix-HardcodedPaths -FilePath $file.FullName
        if ($modified) {
            $modifiedCount++
        }
    }
    
    Write-ColorOutput "Nombre de fichiers modifiés: $modifiedCount / $($dockerComposeFiles.Count)" "Cyan"
    
    return $true
}

# Fonction pour corriger les chemins hardcodés dans les scripts PowerShell
function Fix-PowerShellScripts {
    param (
        [Parameter(Mandatory = $false)]
        [string[]]$ScriptDirs = @("vllm-configs", "vllm-configs/scripts")
    )
    
    Write-ColorOutput "Correction des chemins hardcodés dans les scripts PowerShell..." "Cyan"
    
    $modifiedCount = 0
    $totalCount = 0
    
    # Traiter chaque répertoire de scripts
    foreach ($dir in $ScriptDirs) {
        # Vérifier si le répertoire existe
        if (-not (Test-Path -Path $dir)) {
            Write-ColorOutput "✗ Le répertoire n'existe pas: $dir" "Red"
            continue
        }
        
        # Récupérer tous les scripts PowerShell
        $scripts = Get-ChildItem -Path $dir -Filter "*.ps1"
        
        if ($scripts.Count -eq 0) {
            Write-ColorOutput "Aucun script PowerShell trouvé dans: $dir" "Yellow"
            continue
        }
        
        $totalCount += $scripts.Count
        
        # Traiter chaque script PowerShell
        foreach ($script in $scripts) {
            # Lire le contenu du script
            $content = Get-Content -Path $script.FullName -Raw
            $originalContent = $content
            
            # Remplacer les chemins hardcodés
            
            # 1. Remplacer les chemins absolus par des chemins relatifs
            $content = $content -replace 'D:\\vllm\\vllm-configs', '$PSScriptRoot'
            $content = $content -replace 'D:\\vllm', '$(Split-Path -Parent $PSScriptRoot)'
            
            # 2. Remplacer les chemins Google Drive hardcodés
            $content = $content -replace 'G:\\Mon Drive\\MyIA\\IA\\LLMs\\vllm-secrets', '$env:GDRIVE_BACKUP_PATH'
            
            # 3. Remplacer les chemins WSL hardcodés
            $content = $content -replace '\\\\wsl\.localhost\\Ubuntu\\home\\[a-zA-Z0-9]+\\vllm\\\\.cache\\huggingface\\hub', '$env:HF_CACHE_PATH'
            
            # Vérifier si des modifications ont été apportées
            $modified = ($content -ne $originalContent)
            
            if ($modified) {
                # Écrire le contenu modifié dans le fichier
                Set-Content -Path $script.FullName -Value $content
                Write-ColorOutput "✓ Chemins hardcodés corrigés dans: $($script.Name)" "Green"
                $modifiedCount++
            }
        }
    }
    
    Write-ColorOutput "Nombre de scripts modifiés: $modifiedCount / $totalCount" "Cyan"
    
    return $true
}

# Fonction pour vérifier si un fichier contient des chemins hardcodés
function Test-FileForHardcodedPaths {
    param (
        [Parameter(Mandatory = $true)]
        [string]$FilePath
    )
    
    # Vérifier si le fichier existe
    if (-not (Test-Path -Path $FilePath)) {
        return $false
    }
    
    # Lire le contenu du fichier
    $content = Get-Content -Path $FilePath -Raw
    
    # Définir les motifs de chemins hardcodés
    $pathPatterns = @(
        '\\\\wsl\.localhost\\\\Ubuntu\\\\home\\\\[a-zA-Z0-9]+',  # WSL paths
        'D:\\\\vllm',                                           # Absolute Windows paths
        'G:\\\\Mon Drive'                                       # Google Drive paths
    )
    
    # Vérifier chaque motif
    foreach ($pattern in $pathPatterns) {
        if ($content -match $pattern) {
            return $true  # Le fichier contient des chemins hardcodés
        }
    }
    
    return $false  # Le fichier ne contient pas de chemins hardcodés
}

# Fonction pour vérifier tous les fichiers docker-compose
function Test-AllDockerComposeFiles {
    param (
        [Parameter(Mandatory = $false)]
        [string]$DockerComposeDir = "vllm-configs/docker-compose"
    )
    
    Write-ColorOutput "Vérification des chemins hardcodés dans les fichiers docker-compose..." "Cyan"
    
    # Vérifier si le répertoire existe
    if (-not (Test-Path -Path $DockerComposeDir)) {
        Write-ColorOutput "✗ Le répertoire n'existe pas: $DockerComposeDir" "Red"
        return $false
    }
    
    # Récupérer tous les fichiers docker-compose
    $dockerComposeFiles = Get-ChildItem -Path $DockerComposeDir -Filter "*.yml"
    
    if ($dockerComposeFiles.Count -eq 0) {
        Write-ColorOutput "✗ Aucun fichier docker-compose trouvé dans: $DockerComposeDir" "Red"
        return $false
    }
    
    $allFilesOk = $true
    
    # Vérifier chaque fichier docker-compose
    foreach ($file in $dockerComposeFiles) {
        $hasHardcodedPaths = Test-FileForHardcodedPaths -FilePath $file.FullName
        
        if ($hasHardcodedPaths) {
            Write-ColorOutput "✗ Chemins hardcodés trouvés dans: $($file.Name)" "Red"
            $allFilesOk = $false
        }
        else {
            Write-ColorOutput "✓ Aucun chemin hardcodé dans: $($file.Name)" "Green"
        }
    }
    
    return $allFilesOk
}

# Fonction principale
function Main {
    Write-ColorOutput "=== Correction des chemins hardcodés pour Qwen3 ===" "Magenta"
    
    # Corriger les chemins hardcodés dans les fichiers docker-compose
    $dockerComposeFixed = Fix-DockerComposeFiles
    
    # Corriger les chemins hardcodés dans les scripts PowerShell
    $scriptsFixed = Fix-PowerShellScripts
    
    # Vérifier si tous les fichiers docker-compose sont maintenant corrects
    $allDockerComposeOk = Test-AllDockerComposeFiles
    
    # Afficher le résultat final
    Write-ColorOutput "`n=== Résultat de la correction ===" "Magenta"
    
    if ($allDockerComposeOk) {
        Write-ColorOutput "✓ Tous les chemins hardcodés ont été corrigés" "Green"
        Write-ColorOutput "`nVous pouvez maintenant committer les modifications:" "Cyan"
        Write-ColorOutput "git add vllm-configs/docker-compose/*.yml" "White"
        Write-ColorOutput "git commit -m 'Sécurisation: Remplacement des chemins hardcodés par des variables d'environnement'" "White"
        Write-ColorOutput "git add vllm-configs/scripts/*.ps1" "White"
        Write-ColorOutput "git commit -m 'Sécurisation: Utilisation de chemins relatifs dans les scripts PowerShell'" "White"
    }
    else {
        Write-ColorOutput "✗ Certains chemins hardcodés n'ont pas pu être corrigés" "Red"
        Write-ColorOutput "Veuillez vérifier et corriger manuellement les fichiers restants" "Red"
    }
    
    # Rappel pour mettre à jour le fichier .env.example
    Write-ColorOutput "`nN'oubliez pas de mettre à jour les fichiers .env.example avec les nouvelles variables:" "Yellow"
    Write-ColorOutput "- HF_CACHE_PATH: Chemin vers le cache Hugging Face" "Yellow"
    Write-ColorOutput "- VLLM_ROOT_DIR: Chemin racine du projet vLLM" "Yellow"
    Write-ColorOutput "- GDRIVE_PATH: Chemin vers Google Drive" "Yellow"
    Write-ColorOutput "- GDRIVE_BACKUP_PATH: Chemin vers le répertoire de sauvegarde sur Google Drive" "Yellow"
}

# Exécuter la fonction principale
Main