# finalize-qwen3-integration.ps1 - Script pour finaliser l'intégration du tool calling avec Qwen3 dans vLLM
# 
# Ce script:
# - Définit les variables d'environnement nécessaires
# - Reconstruit l'image Docker avec le parser d'outils Qwen3
# - Redémarre les services avec la nouvelle image
# - Teste la solution complète

# Définition des couleurs pour les messages
$RED = [System.ConsoleColor]::Red
$GREEN = [System.ConsoleColor]::Green
$YELLOW = [System.ConsoleColor]::Yellow
$BLUE = [System.ConsoleColor]::Blue

# Chemin du script et du répertoire de configuration
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$LOG_FILE = Join-Path $SCRIPT_DIR "finalize-qwen3-integration.log"

# Fonction de journalisation
function Write-Log {
    param (
        [string]$level,
        [string]$message
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = $null
    
    switch ($level) {
        "INFO" { $color = $GREEN }
        "WARNING" { $color = $YELLOW }
        "ERROR" { $color = $RED }
        "DEBUG" { $color = $BLUE }
    }
    
    # Affichage dans la console
    Write-Host -ForegroundColor $color "[$timestamp] [$level] $message"
    
    # Journalisation dans le fichier de log
    Add-Content -Path $LOG_FILE -Value "[$timestamp] [$level] $message"
}

# Fonction pour définir les variables d'environnement
function Set-EnvironmentVariables {
    Write-Log "INFO" "Définition des variables d'environnement..."
    
    # Ports
    $env:VLLM_PORT_MICRO = "5000"
    $env:VLLM_PORT_MINI = "5001"
    $env:VLLM_PORT_MEDIUM = "5002"
    
    # Clés API
    $env:VLLM_API_KEY_MICRO = "KEY_REMOVED_FOR_SECURITY"
    $env:VLLM_API_KEY_MINI = "KEY_REMOVED_FOR_SECURITY"
    $env:VLLM_API_KEY_MEDIUM = "KEY_REMOVED_FOR_SECURITY"
    
    # Utilisation de la mémoire GPU
    $env:GPU_MEMORY_UTILIZATION_MICRO = "0.9999"
    $env:GPU_MEMORY_UTILIZATION_MINI = "0.9999"
    $env:GPU_MEMORY_UTILIZATION_MEDIUM = "0.9999"
    
    # Dispositifs CUDA visibles
    $env:CUDA_VISIBLE_DEVICES_MICRO = "2"
    $env:CUDA_VISIBLE_DEVICES_MINI = "1"
    $env:CUDA_VISIBLE_DEVICES_MEDIUM = "0,1"
    
    Write-Log "INFO" "Variables d'environnement définies avec succès."
}

# Fonction pour créer le répertoire de build
function Create-BuildDirectory {
    Write-Log "INFO" "Création du répertoire de build..."
    
    $BUILD_DIR = Join-Path $SCRIPT_DIR "docker-compose\build-temp"
    
    # Supprimer le répertoire s'il existe déjà
    if (Test-Path $BUILD_DIR) {
        Write-Log "INFO" "Suppression du répertoire de build existant..."
        Remove-Item -Path $BUILD_DIR -Recurse -Force
    }
    
    # Créer le répertoire
    New-Item -Path $BUILD_DIR -ItemType Directory -Force | Out-Null
    New-Item -Path "$BUILD_DIR\tool_parsers" -ItemType Directory -Force | Out-Null
    New-Item -Path "$BUILD_DIR\reasoning" -ItemType Directory -Force | Out-Null
    
    # Vérifier les chemins des fichiers source
    $tool_parser_path = Join-Path $SCRIPT_DIR "..\..\..\..\vllm\entrypoints\openai\tool_parsers\qwen3_tool_parser.py"
    $init_path = Join-Path $SCRIPT_DIR "..\..\..\..\vllm\entrypoints\openai\tool_parsers\__init__.py"
    $reasoning_parser_path = Join-Path $SCRIPT_DIR "..\..\..\..\deployment\docker\build\reasoning\qwen3_reasoning_parser.py"
    
    # Vérifier si les fichiers existent
    if (-not (Test-Path $tool_parser_path)) {
        Write-Log "WARNING" "Le fichier $tool_parser_path n'existe pas. Recherche d'alternatives..."
        $tool_parser_path = (Get-ChildItem -Path $SCRIPT_DIR -Recurse -Filter "qwen3_tool_parser.py" | Select-Object -First 1).FullName
        if (-not $tool_parser_path) {
            Write-Log "ERROR" "Impossible de trouver le fichier qwen3_tool_parser.py"
            exit 1
        }
        Write-Log "INFO" "Fichier trouvé: $tool_parser_path"
    }
    
    if (-not (Test-Path $init_path)) {
        Write-Log "WARNING" "Le fichier $init_path n'existe pas. Recherche d'alternatives..."
        $init_path = (Get-ChildItem -Path $SCRIPT_DIR -Recurse -Filter "__init__.py" -Depth 5 | Where-Object { $_.DirectoryName -like "*tool_parsers*" } | Select-Object -First 1).FullName
        if (-not $init_path) {
            Write-Log "ERROR" "Impossible de trouver le fichier __init__.py dans un répertoire tool_parsers"
            exit 1
        }
        Write-Log "INFO" "Fichier trouvé: $init_path"
    }
    
    if (-not (Test-Path $reasoning_parser_path)) {
        Write-Log "WARNING" "Le fichier $reasoning_parser_path n'existe pas. Recherche d'alternatives..."
        $reasoning_parser_path = (Get-ChildItem -Path $SCRIPT_DIR -Recurse -Filter "qwen3_reasoning_parser.py" | Select-Object -First 1).FullName
        if (-not $reasoning_parser_path) {
            Write-Log "ERROR" "Impossible de trouver le fichier qwen3_reasoning_parser.py"
            exit 1
        }
        Write-Log "INFO" "Fichier trouvé: $reasoning_parser_path"
    }
    
    # Copier les fichiers nécessaires
    Copy-Item -Path $tool_parser_path -Destination "$BUILD_DIR\tool_parsers\" -Force
    Copy-Item -Path $init_path -Destination "$BUILD_DIR\tool_parsers\" -Force
    Copy-Item -Path $reasoning_parser_path -Destination "$BUILD_DIR\reasoning\" -Force
    
    Write-Log "INFO" "Répertoire de build créé avec succès: $BUILD_DIR"
    
    return $BUILD_DIR
}

# Fonction pour créer un Dockerfile optimisé
function Create-OptimizedDockerfile {
    param (
        [string]$BUILD_DIR
    )
    
    Write-Log "INFO" "Création d'un Dockerfile optimisé..."
    
    $dockerfile_path = Join-Path $BUILD_DIR "Dockerfile.qwen3.optimized"
    
    $dockerfile_content = @"
FROM vllm/vllm-openai:latest

# Optimisation des couches Docker
# Copier tous les fichiers en une seule couche pour réduire la taille de l'image
COPY tool_parsers/qwen3_tool_parser.py /vllm/vllm/entrypoints/openai/tool_parsers/
COPY tool_parsers/__init__.py /vllm/vllm/entrypoints/openai/tool_parsers/
COPY reasoning/qwen3_reasoning_parser.py /vllm/vllm/reasoning/

# Définir le répertoire de travail
WORKDIR /vllm

# Optimisation pour le démarrage rapide
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONOPTIMIZE=1
"@
    
    Set-Content -Path $dockerfile_path -Value $dockerfile_content
    
    Write-Log "INFO" "Dockerfile optimisé créé avec succès: $dockerfile_path"
    
    return $dockerfile_path
}

# Fonction pour construire l'image Docker
function Build-DockerImage {
    param (
        [string]$BUILD_DIR,
        [string]$dockerfile_path
    )
    
    Write-Log "INFO" "Construction de l'image Docker..."
    
    $image_name = "vllm/vllm-openai:qwen3"
    
    # Construire l'image
    Write-Log "INFO" "Démarrage de la construction de l'image Docker..."
    $log_file = Join-Path $BUILD_DIR "docker-build.log"
    
    try {
        # Utiliser Invoke-Expression au lieu de Start-Process pour éviter les problèmes de redirection
        $cmd = "docker build -t $image_name -f $dockerfile_path $BUILD_DIR > $log_file 2>&1"
        Write-Log "INFO" "Exécution de la commande: $cmd"
        Invoke-Expression $cmd
        
        # Vérifier si la construction a réussi
        if ($LASTEXITCODE -eq 0) {
            Write-Log "INFO" "Image Docker construite avec succès: $image_name"
        }
        else {
            Write-Log "ERROR" "Échec de la construction de l'image Docker. Consultez le journal pour plus de détails: $log_file"
            exit 1
        }
    }
    catch {
        Write-Log "ERROR" "Erreur lors de la construction de l'image Docker: $($_.Exception.Message)"
        exit 1
    }
}

# Fonction pour arrêter les services vLLM Qwen3
function Stop-Qwen3Services {
    Write-Log "INFO" "Arrêt des services vLLM Qwen3..."
    
    $compose_files = @(
        "myia-vllm\qwen3\deployment\docker\docker-compose-micro-qwen3.yml",
        "myia-vllm\qwen3\deployment\docker\docker-compose-mini-qwen3.yml",
        "myia-vllm\qwen3\deployment\docker\docker-compose-medium-qwen3.yml"
    )
    
    $compose_cmd = "docker compose -p myia-vllm"
    
    # Ajouter les fichiers docker-compose
    foreach ($file in $compose_files) {
        $compose_cmd += " -f `"$file`""
    }
    
    # Ajouter la commande d'arrêt
    $compose_cmd += " down"
    
    # Exécuter la commande
    try {
        Write-Log "INFO" "Exécution de la commande: $compose_cmd"
        Invoke-Expression $compose_cmd
        Write-Log "INFO" "Services vLLM Qwen3 arrêtés avec succès."
        return $true
    }
    catch {
        Write-Log "ERROR" "Échec de l'arrêt des services vLLM Qwen3: $_"
        return $false
    }
}

# Fonction pour démarrer les services vLLM Qwen3
function Start-Qwen3Services {
    Write-Log "INFO" "Démarrage des services vLLM Qwen3..."
    
    $compose_files = @(
        "myia-vllm\qwen3\deployment\docker\docker-compose-micro-qwen3.yml",
        "myia-vllm\qwen3\deployment\docker\docker-compose-mini-qwen3.yml",
        "myia-vllm\qwen3\deployment\docker\docker-compose-medium-qwen3.yml"
    )
    
    $compose_cmd = "docker compose -p myia-vllm"
    
    # Ajouter les fichiers docker-compose
    foreach ($file in $compose_files) {
        $compose_cmd += " -f `"$file`""
    }
    
    # Ajouter la commande de démarrage
    $compose_cmd += " up -d"
    
    # Exécuter la commande
    try {
        Write-Log "INFO" "Exécution de la commande: $compose_cmd"
        Invoke-Expression $compose_cmd
        Write-Log "INFO" "Services vLLM Qwen3 démarrés avec succès."
        return $true
    }
    catch {
        Write-Log "ERROR" "Échec du démarrage des services vLLM Qwen3: $_"
        return $false
    }
}

# Fonction pour vérifier que les services fonctionnent correctement
function Check-Services {
    Write-Log "INFO" "Vérification du fonctionnement des services Qwen3..."
    
    $services = @(
        "vllm-micro-qwen3:5000",
        "vllm-mini-qwen3:5001",
        "vllm-medium-qwen3:5002"
    )
    
    $all_running = $true
    $max_retries = 10
    $retry_interval = 5
    
    foreach ($service_port in $services) {
        $service, $port = $service_port -split ':'
        
        Write-Log "INFO" "Vérification du service $service sur le port $port..."
        
        $retries = 0
        $service_running = $false
        
        while ($retries -lt $max_retries -and -not $service_running) {
            # Vérifier si le service est en cours d'exécution
            $container_id = docker ps -q -f "name=myia-vllm_${service}"
            if (-not $container_id) {
                Write-Log "WARNING" "Le service $service n'est pas en cours d'exécution. Tentative $(($retries+1))/$max_retries..."
                $retries++
                Start-Sleep -Seconds $retry_interval
                continue
            }
            
            # Vérifier si le service répond
            try {
                $headers = @{ "Authorization" = "Bearer $env:VLLM_API_KEY_MICRO" }
                $response = Invoke-WebRequest -Uri "http://localhost:$port/v1/models" -Method Get -Headers $headers -UseBasicParsing
                if ($response.StatusCode -eq 200) {
                    Write-Log "INFO" "Le service $service fonctionne correctement."
                    $service_running = $true
                }
                else {
                    Write-Log "WARNING" "Le service $service ne répond pas correctement (code HTTP: $($response.StatusCode)). Tentative $(($retries+1))/$max_retries..."
                    $retries++
                    Start-Sleep -Seconds $retry_interval
                }
            }
            catch {
                Write-Log "WARNING" "Le service $service ne répond pas. Tentative $(($retries+1))/$max_retries..."
                $retries++
                Start-Sleep -Seconds $retry_interval
            }
        }
        
        if (-not $service_running) {
            Write-Log "ERROR" "Le service $service ne fonctionne pas correctement après $max_retries tentatives."
            $all_running = $false
        }
    }
    
    if (-not $all_running) {
        Write-Log "ERROR" "Certains services Qwen3 ne fonctionnent pas correctement."
        return $false
    }
    
    Write-Log "INFO" "Tous les services Qwen3 fonctionnent correctement."
    return $true
}

# Fonction pour tester le tool calling
function Test-ToolCalling {
    Write-Log "INFO" "Test du tool calling avec Qwen3..."
    
    # Exécuter le script de test
    try {
        $cmd = "python tests\tool_calling\test_qwen3_tool_calling_fixed.py --service micro"
        Write-Log "INFO" "Exécution de la commande: $cmd"
        Invoke-Expression $cmd
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "INFO" "Test du tool calling réussi."
            return $true
        }
        else {
            Write-Log "ERROR" "Échec du test du tool calling."
            return $false
        }
    }
    catch {
        Write-Log "ERROR" "Erreur lors du test du tool calling: $($_.Exception.Message)"
        return $false
    }
}

# Fonction pour mettre à jour la documentation
function Update-Documentation {
    Write-Log "INFO" "Mise à jour de la documentation..."
    
    $doc_file = Join-Path $SCRIPT_DIR "..\..\..\..\docs\WINDOWS-README.md"
    
    # Ajouter une section sur le tool calling avec Qwen3
    $doc_content = @"
# Guide d'utilisation des services vLLM sous Windows 11

Ce document explique comment gérer les services vLLM sous Windows 11 avec Docker Desktop.

## Prérequis

- Windows 11
- Docker Desktop installé et configuré avec WSL 2
- PowerShell

## Structure des fichiers

- `prepare-update.ps1` : Script de préparation pour la mise à jour des services vLLM
- `start-vllm-services.ps1` : Script pour démarrer les services vLLM
- `test-vllm-services.ps1` : Script pour tester les services vLLM
- `quick-update-qwen3.ps1` : Script généré automatiquement pour mettre à jour rapidement les services vLLM Qwen3

## Démarrer les services vLLM

Pour démarrer les services vLLM, exécutez le script suivant dans PowerShell :

```powershell
.\start-vllm-services.ps1
```

Options disponibles :
- `-Help` : Affiche l'aide
- `-Verbose` : Mode verbeux (affiche plus de détails)

## Tester les services vLLM

Pour vérifier que les services vLLM fonctionnent correctement, exécutez :

```powershell
.\test-vllm-services.ps1
```

Options disponibles :
- `-Help` : Affiche l'aide
- `-Verbose` : Mode verbeux (affiche plus de détails)
- `-DetailedTest` : Effectue des tests détaillés des API (génération de texte)

## Préparer une mise à jour des services vLLM

Pour préparer une mise à jour des services vLLM, exécutez :

```powershell
.\prepare-update.ps1
```

Options disponibles :
- `-Help` : Affiche l'aide
- `-Verbose` : Mode verbeux (affiche plus de détails)
- `-DryRun` : Simule les actions sans les exécuter

Ce script va :
1. Vérifier l'état actuel des services vLLM
2. Créer un répertoire de build temporaire
3. Créer un Dockerfile optimisé
4. Construire l'image Docker
5. Générer un script de mise à jour rapide (`quick-update-qwen3.ps1`)

## Effectuer une mise à jour rapide

Une fois la préparation terminée, vous pouvez effectuer la mise à jour rapide en exécutant :

```powershell
.\quick-update-qwen3.ps1
```

Ce script va :
1. Arrêter les services vLLM Qwen3
2. Démarrer les services avec la nouvelle image Docker
3. Vérifier que tout fonctionne correctement

## Configuration des services

Les services vLLM sont configurés dans les fichiers docker-compose suivants :
- `docker-compose-micro-qwen3.yml` : Service micro (modèle 1.7B)
- `docker-compose-mini-qwen3.yml` : Service mini (modèle 8B)
- `docker-compose-medium-qwen3.yml` : Service medium (modèle 8B avec 2 GPUs)

Ces fichiers sont déjà adaptés pour Windows 11 avec WSL.

## Tool Calling avec Qwen3

Les services vLLM Qwen3 prennent en charge le tool calling avec le parser `qwen3`. Pour tester le tool calling, utilisez le script suivant :

```powershell
python tests\tool_calling\test_qwen3_tool_calling.py --service micro
```

Options disponibles :
- `--service` : Service à tester (micro, mini, medium)
- `--endpoint` : URL de l'API OpenAI de vLLM (par défaut : selon le service)
- `--api-key` : Clé API pour l'authentification
- `--no-streaming` : Désactiver le test en streaming

Le script teste à la fois le mode normal et le mode streaming, et vérifie que le tool calling fonctionne correctement.

## Résolution des problèmes

Si vous rencontrez des problèmes, vérifiez les fichiers de log générés par les scripts :
- `prepare-update.log`
- `start-vllm-services.log`
- `test-vllm-services.log`
- `quick-update-qwen3.log`

Ces fichiers contiennent des informations détaillées sur les actions effectuées et les erreurs rencontrées.
"@
    
    Set-Content -Path $doc_file -Value $doc_content
    
    Write-Log "INFO" "Documentation mise à jour avec succès: $doc_file"
}

# Fonction principale
function Main {
    Write-Log "INFO" "Démarrage de la finalisation de l'intégration du tool calling avec Qwen3 dans vLLM..."
    
    # Définir les variables d'environnement
    Set-EnvironmentVariables
    
    # Créer le répertoire de build
    $BUILD_DIR = Create-BuildDirectory
    
    # Créer un Dockerfile optimisé
    $dockerfile_path = Create-OptimizedDockerfile -BUILD_DIR $BUILD_DIR
    
    # Construire l'image Docker
    Build-DockerImage -BUILD_DIR $BUILD_DIR -dockerfile_path $dockerfile_path
    
    # Arrêter les services vLLM Qwen3
    if (-not (Stop-Qwen3Services)) {
        Write-Log "ERROR" "Échec de l'arrêt des services vLLM Qwen3. Finalisation annulée."
        exit 1
    }
    
    # Démarrer les services vLLM Qwen3
    if (-not (Start-Qwen3Services)) {
        Write-Log "ERROR" "Échec du démarrage des services vLLM Qwen3. Finalisation annulée."
        exit 1
    }
    
    # Vérifier que les services fonctionnent correctement
    if (-not (Check-Services)) {
        Write-Log "ERROR" "Certains services vLLM Qwen3 ne fonctionnent pas correctement."
        exit 1
    }
    
    # Tester le tool calling
    if (-not (Test-ToolCalling)) {
        Write-Log "ERROR" "Échec du test du tool calling."
        exit 1
    }
    
    # Mettre à jour la documentation
    Update-Documentation
    
    Write-Log "INFO" "Finalisation de l'intégration du tool calling avec Qwen3 dans vLLM terminée avec succès."
    return 0
}

# Exécuter la fonction principale
Main
exit $LASTEXITCODE