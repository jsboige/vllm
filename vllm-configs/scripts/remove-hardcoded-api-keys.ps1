# Script PowerShell pour supprimer les clés API hardcodées dans les fichiers docker-compose
# Ce script remplace les clés API hardcodées par des variables d'environnement

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

# Fonction pour supprimer les clés API hardcodées dans un fichier
function Remove-HardcodedApiKeys {
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
    
    # Remplacer les clés API hardcodées dans les variables d'environnement
    $apiKeyPattern = 'VLLM_API_KEY(_[A-Z]+)?:-([a-zA-Z0-9]{16,})'
    if ($content -match $apiKeyPattern) {
        Write-ColorOutput "  Suppression des clés API hardcodées dans les variables d'environnement..." "Yellow"
        $content = $content -replace $apiKeyPattern, 'VLLM_API_KEY$1}'
    }
    
    # Remplacer les clés API hardcodées dans les arguments de ligne de commande
    $cmdApiKeyPattern = '--api-key \$\{VLLM_API_KEY(_[A-Z]+)?:-([a-zA-Z0-9]{16,})\}'
    if ($content -match $cmdApiKeyPattern) {
        Write-ColorOutput "  Suppression des clés API hardcodées dans les arguments de ligne de commande..." "Yellow"
        $content = $content -replace $cmdApiKeyPattern, '--api-key ${VLLM_API_KEY$1}'
    }
    
    # Vérifier si des modifications ont été apportées
    $modified = ($content -ne $originalContent)
    
    if ($modified) {
        # Écrire le contenu modifié dans le fichier
        Set-Content -Path $FilePath -Value $content
        Write-ColorOutput "✓ Clés API hardcodées supprimées dans: $FilePath" "Green"
    }
    else {
        Write-ColorOutput "✓ Aucune clé API hardcodée trouvée dans: $FilePath" "Green"
    }
    
    return $modified
}

# Fonction pour supprimer les clés API hardcodées dans tous les fichiers docker-compose
function Remove-ApiKeysFromDockerComposeFiles {
    param (
        [Parameter(Mandatory = $false)]
        [string]$DockerComposeDir = "vllm-configs/docker-compose"
    )
    
    Write-ColorOutput "Suppression des clés API hardcodées dans les fichiers docker-compose..." "Cyan"
    
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
        $modified = Remove-HardcodedApiKeys -FilePath $file.FullName
        if ($modified) {
            $modifiedCount++
        }
    }
    
    Write-ColorOutput "Nombre de fichiers modifiés: $modifiedCount / $($dockerComposeFiles.Count)" "Cyan"
    
    return $true
}

# Fonction pour vérifier si un fichier contient des clés API hardcodées
function Test-FileForHardcodedApiKeys {
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
    
    # Définir les motifs de clés API hardcodées
    $apiKeyPatterns = @(
        'VLLM_API_KEY(_[A-Z]+)?:-([a-zA-Z0-9]{16,})',  # Clés API dans les variables d'environnement
        '--api-key \$\{VLLM_API_KEY(_[A-Z]+)?:-([a-zA-Z0-9]{16,})\}'  # Clés API dans les arguments de ligne de commande
    )
    
    # Vérifier chaque motif
    foreach ($pattern in $apiKeyPatterns) {
        if ($content -match $pattern) {
            return $true  # Le fichier contient des clés API hardcodées
        }
    }
    
    return $false  # Le fichier ne contient pas de clés API hardcodées
}

# Fonction pour vérifier tous les fichiers docker-compose
function Test-AllDockerComposeFilesForApiKeys {
    param (
        [Parameter(Mandatory = $false)]
        [string]$DockerComposeDir = "vllm-configs/docker-compose"
    )
    
    Write-ColorOutput "Vérification des clés API hardcodées dans les fichiers docker-compose..." "Cyan"
    
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
        $hasHardcodedApiKeys = Test-FileForHardcodedApiKeys -FilePath $file.FullName
        
        if ($hasHardcodedApiKeys) {
            Write-ColorOutput "✗ Clés API hardcodées trouvées dans: $($file.Name)" "Red"
            $allFilesOk = $false
        }
        else {
            Write-ColorOutput "✓ Aucune clé API hardcodée dans: $($file.Name)" "Green"
        }
    }
    
    return $allFilesOk
}

# Fonction principale
function Main {
    Write-ColorOutput "=== Suppression des clés API hardcodées pour Qwen3 ===" "Magenta"
    
    # Supprimer les clés API hardcodées dans les fichiers docker-compose
    $apiKeysRemoved = Remove-ApiKeysFromDockerComposeFiles
    
    # Vérifier si tous les fichiers docker-compose sont maintenant corrects
    $allDockerComposeOk = Test-AllDockerComposeFilesForApiKeys
    
    # Afficher le résultat final
    Write-ColorOutput "`n=== Résultat de la suppression ===" "Magenta"
    
    if ($allDockerComposeOk) {
        Write-ColorOutput "✓ Toutes les clés API hardcodées ont été supprimées" "Green"
        Write-ColorOutput "`nVous pouvez maintenant committer les modifications:" "Cyan"
        Write-ColorOutput "git add vllm-configs/docker-compose/*.yml" "White"
        Write-ColorOutput "git commit -m 'Sécurisation: Suppression des clés API hardcodées dans les fichiers de configuration'" "White"
    }
    else {
        Write-ColorOutput "✗ Certaines clés API hardcodées n'ont pas pu être supprimées" "Red"
        Write-ColorOutput "Veuillez vérifier et corriger manuellement les fichiers restants" "Red"
    }
    
    # Rappel pour mettre à jour le fichier .env.example
    Write-ColorOutput "`nN'oubliez pas de vérifier que les variables d'API sont bien définies dans les fichiers .env.example:" "Yellow"
    Write-ColorOutput "- VLLM_API_KEY_MICRO: Clé API pour le service micro" "Yellow"
    Write-ColorOutput "- VLLM_API_KEY_MINI: Clé API pour le service mini" "Yellow"
    Write-ColorOutput "- VLLM_API_KEY_MEDIUM: Clé API pour le service medium" "Yellow"
}

# Exécuter la fonction principale
Main