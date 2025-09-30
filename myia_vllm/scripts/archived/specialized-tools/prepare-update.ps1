# prepare-update.ps1 - Script de préparation pour la mise à jour des services vLLM
# 
# Ce script:
# - Vérifie l'état actuel des services vLLM
# - Crée un répertoire de build temporaire pour la nouvelle image Docker
# - Configure un mécanisme pour construire la nouvelle image sans arrêter les services existants

# Définition des couleurs pour les messages
$RED = [System.ConsoleColor]::Red
$GREEN = [System.ConsoleColor]::Green
$YELLOW = [System.ConsoleColor]::Yellow
$BLUE = [System.ConsoleColor]::Blue

# Chemin du script et du répertoire de configuration
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PARENT_DIR = Split-Path -Parent $SCRIPT_DIR
$CONFIG_FILE = Join-Path $PARENT_DIR "update-config.json"
$BUILD_DIR = Join-Path $PARENT_DIR "docker-compose\build-temp"
$LOG_FILE = Join-Path $PARENT_DIR "prepare-update.log"

# Variables globales
$DOCKER_COMPOSE_PROJECT = ""
$HUGGINGFACE_TOKEN = ""
$VERBOSE = $false
$DRY_RUN = $false

# Fonction pour afficher l'aide
function Show-Help {
    Write-Host "Usage: $($MyInvocation.MyCommand.Name) [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Help                Affiche cette aide"
    Write-Host "  -Verbose             Mode verbeux (affiche plus de détails)"
    Write-Host "  -DryRun              Simule les actions sans les exécuter"
    Write-Host ""
}

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

# Fonction pour vérifier les dépendances
function Check-Dependencies {
    Write-Log "INFO" "Vérification des dépendances..."
    
    # Vérifier si docker est installé
    try {
        $null = docker --version
    }
    catch {
        Write-Log "ERROR" "docker n'est pas installé ou n'est pas accessible. Veuillez l'installer avant d'utiliser ce script."
        exit 1
    }
    
    # Vérifier si docker compose est installé
    try {
        $null = docker compose version
    }
    catch {
        Write-Log "ERROR" "docker compose n'est pas installé ou n'est pas accessible."
        exit 1
    }
    
    Write-Log "INFO" "Toutes les dépendances sont installées."
}

# Fonction pour charger la configuration
function Load-Config {
    Write-Log "INFO" "Chargement de la configuration depuis $CONFIG_FILE..."
    
    if (-not (Test-Path $CONFIG_FILE)) {
        Write-Log "ERROR" "Fichier de configuration non trouvé: $CONFIG_FILE"
        exit 1
    }
    
    # Charger les paramètres de configuration
    $config = Get-Content -Path $CONFIG_FILE | ConvertFrom-Json
    $script:DOCKER_COMPOSE_PROJECT = $config.settings.docker_compose_project
    
    $script:HUGGINGFACE_TOKEN = $config.settings.huggingface_token
    # Remplacer la variable d'environnement si présente
    if ($HUGGINGFACE_TOKEN -match '\${HUGGING_FACE_HUB_TOKEN') {
        # Extraire la valeur par défaut
        $DEFAULT_TOKEN = $HUGGINGFACE_TOKEN -replace '.*:-(.*)}..*', '$1'
        # Utiliser la variable d'environnement ou la valeur par défaut
        $script:HUGGINGFACE_TOKEN = if ($env:HUGGING_FACE_HUB_TOKEN) { $env:HUGGING_FACE_HUB_TOKEN } else { $DEFAULT_TOKEN }
    }
    
    Write-Log "INFO" "Configuration chargée avec succès."
    if ($VERBOSE) {
        Write-Log "DEBUG" "Paramètres chargés:"
        Write-Log "DEBUG" "  - DOCKER_COMPOSE_PROJECT: $DOCKER_COMPOSE_PROJECT"
    }
}

# Fonction pour vérifier l'état des services vLLM
function Check-ServicesStatus {
    Write-Log "INFO" "Vérification de l'état des services vLLM..."
    
    $services = @(
        "vllm-micro:5000",
        "vllm-mini:5001",
        "vllm-medium:5002",
        "vllm-micro-qwen3:5000",
        "vllm-mini-qwen3:5001",
        "vllm-medium-qwen3:5002"
    )
    
    $running_services = @()
    $stopped_services = @()
    
    foreach ($service_port in $services) {
        $service, $port = $service_port -split ':'
        
        if ($DRY_RUN) {
            Write-Log "INFO" "[DRY RUN] Vérification du service $service sur le port $port"
            $running_services += $service
        }
        else {
            # Vérifier si le service est en cours d'exécution
            $container_id = docker ps -q -f "name=${DOCKER_COMPOSE_PROJECT}_${service}"
            if (-not $container_id) {
                $stopped_services += $service
                Write-Log "INFO" "Le service $service n'est pas en cours d'exécution."
            }
            else {
                $running_services += $service
                Write-Log "INFO" "Le service $service est en cours d'exécution (container ID: $container_id)."
                
                # Vérifier l'utilisation des ressources
                $stats = docker stats --no-stream --format "{{.CPUPerc}}|{{.MemUsage}}" $container_id
                $cpu_usage, $mem_usage = $stats -split '\|'
                Write-Log "INFO" "  - Utilisation CPU: $cpu_usage"
                Write-Log "INFO" "  - Utilisation mémoire: $mem_usage"
            }
        }
    }
    
    Write-Log "INFO" "Services en cours d'exécution: $($running_services.Count)"
    Write-Log "INFO" "Services arrêtés: $($stopped_services.Count)"
    
    # Retourner le nombre de services en cours d'exécution
    return $running_services.Count
}

# Fonction pour créer un répertoire de build temporaire
function Create-BuildDirectory {
    Write-Log "INFO" "Création du répertoire de build temporaire..."
    
    if ($DRY_RUN) {
        Write-Log "INFO" "[DRY RUN] Création du répertoire: $BUILD_DIR"
    }
    else {
        # Supprimer le répertoire s'il existe déjà
        if (Test-Path $BUILD_DIR) {
            Write-Log "INFO" "Suppression du répertoire de build existant..."
            Remove-Item -Path $BUILD_DIR -Recurse -Force
        }
        
        # Créer le répertoire
        New-Item -Path $BUILD_DIR -ItemType Directory -Force | Out-Null
        New-Item -Path "$BUILD_DIR\tool_parsers" -ItemType Directory -Force | Out-Null
        New-Item -Path "$BUILD_DIR\reasoning" -ItemType Directory -Force | Out-Null
        
        # Copier les fichiers nécessaires
        Copy-Item -Path "$PARENT_DIR\docker-compose\build\tool_parsers\qwen3_tool_parser.py" -Destination "$BUILD_DIR\tool_parsers\" -Force
        Copy-Item -Path "$PARENT_DIR\docker-compose\build\tool_parsers\__init__.py" -Destination "$BUILD_DIR\tool_parsers\" -Force
        
        # Copier le fichier du parser de raisonnement Qwen3 corrigé (PR #17506)
        Copy-Item -Path "$SCRIPT_DIR\..\vllm\reasoning\qwen3_reasoning_parser.py" -Destination "$BUILD_DIR\reasoning\" -Force
        
        Write-Log "INFO" "Répertoire de build créé avec succès: $BUILD_DIR"
    }
}

# Fonction pour créer un Dockerfile temporaire optimisé
function Create-OptimizedDockerfile {
    Write-Log "INFO" "Création d'un Dockerfile temporaire optimisé..."
    
    $dockerfile_path = Join-Path $BUILD_DIR "Dockerfile.qwen3.optimized"
    
    if ($DRY_RUN) {
        Write-Log "INFO" "[DRY RUN] Création du Dockerfile: $dockerfile_path"
    }
    else {
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
    }
}

# Fonction pour construire l'image Docker
function Build-DockerImage {
    Write-Log "INFO" "Construction de l'image Docker..."
    
    $image_name = "vllm-qwen3:latest"
    $dockerfile_path = Join-Path $BUILD_DIR "Dockerfile.qwen3.optimized"
    
    if ($DRY_RUN) {
        Write-Log "INFO" "[DRY RUN] Construction de l'image Docker: $image_name"
    }
    else {
        # Construire l'image
        Write-Log "INFO" "Démarrage de la construction de l'image Docker..."
        $log_file = Join-Path $BUILD_DIR "docker-build.log"
        
        try {
            $process = Start-Process -FilePath "docker" -ArgumentList "build -t $image_name -f $dockerfile_path $BUILD_DIR" -NoNewWindow -PassThru -RedirectStandardOutput $log_file -RedirectStandardError $log_file
            Write-Log "INFO" "Construction de l'image Docker en cours (PID: $($process.Id))..."
            Write-Log "INFO" "Vous pouvez suivre la progression avec: Get-Content -Path $log_file -Wait"
            
            # Attendre que la construction soit terminée
            $process.WaitForExit()
            
            if ($process.ExitCode -eq 0) {
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
}

# Fonction pour créer un script de mise à jour rapide
function Create-QuickUpdateScript {
    Write-Log "INFO" "Création d'un script de mise à jour rapide..."
    
    $script_path = Join-Path $PARENT_DIR "quick-update-qwen3.ps1"
    
    if ($DRY_RUN) {
        Write-Log "INFO" "[DRY RUN] Création du script: $script_path"
    }
    else {
        $script_content = @"
# quick-update-qwen3.ps1 - Script de mise à jour rapide des services vLLM Qwen3
# 
# Ce script:
# - Arrête les services vLLM Qwen3 existants
# - Démarre les services avec la nouvelle image Docker
# - Vérifie que tout fonctionne correctement

# Définition des couleurs pour les messages
`$RED = [System.ConsoleColor]::Red
`$GREEN = [System.ConsoleColor]::Green
`$YELLOW = [System.ConsoleColor]::Yellow
`$BLUE = [System.ConsoleColor]::Blue

# Chemin du script et du répertoire de configuration
`$SCRIPT_DIR = Split-Path -Parent `$MyInvocation.MyCommand.Path
`$CONFIG_FILE = Join-Path `$SCRIPT_DIR "update-config.json"
`$LOG_FILE = Join-Path `$SCRIPT_DIR "quick-update-qwen3.log"

# Variables globales
`$config = Get-Content -Path `$CONFIG_FILE | ConvertFrom-Json
`$DOCKER_COMPOSE_PROJECT = `$config.settings.docker_compose_project
`$START_TIME = [int](Get-Date -UFormat %s)

# Fonction de journalisation
function Write-Log {
    param (
        [string]`$level,
        [string]`$message
    )
    
    `$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    `$color = `$null
    
    switch (`$level) {
        "INFO" { `$color = `$GREEN }
        "WARNING" { `$color = `$YELLOW }
        "ERROR" { `$color = `$RED }
        "DEBUG" { `$color = `$BLUE }
    }
    
    # Affichage dans la console
    Write-Host -ForegroundColor `$color "[`$timestamp] [`$level] `$message"
    
    # Journalisation dans le fichier de log
    Add-Content -Path `$LOG_FILE -Value "[`$timestamp] [`$level] `$message"
}

# Fonction pour arrêter les services vLLM Qwen3
function Stop-Qwen3Services {
    Write-Log "INFO" "Arrêt des services vLLM Qwen3..."
    
    `$compose_files = @(
        "docker-compose\docker-compose-micro-qwen3.yml",
        "docker-compose\docker-compose-mini-qwen3.yml",
        "docker-compose\docker-compose-medium-qwen3.yml"
    )
    
    `$compose_cmd = "docker compose -p `$DOCKER_COMPOSE_PROJECT"
    
    # Ajouter les fichiers docker-compose
    foreach (`$file in `$compose_files) {
        `$compose_cmd += " -f `"`$SCRIPT_DIR\`$file`""
    }
    
    # Ajouter la commande d'arrêt
    `$compose_cmd += " down"
    
    # Exécuter la commande
    try {
        Invoke-Expression `$compose_cmd
        Write-Log "INFO" "Services vLLM Qwen3 arrêtés avec succès."
        return `$true
    }
    catch {
        Write-Log "ERROR" "Échec de l'arrêt des services vLLM Qwen3: `$_"
        return `$false
    }
}

# Fonction pour démarrer les services vLLM Qwen3
function Start-Qwen3Services {
    Write-Log "INFO" "Démarrage des services vLLM Qwen3..."
    
    `$compose_files = @(
        "docker-compose\docker-compose-micro-qwen3.yml",
        "docker-compose\docker-compose-mini-qwen3.yml",
        "docker-compose\docker-compose-medium-qwen3.yml"
    )
    
    `$compose_cmd = "docker compose -p `$DOCKER_COMPOSE_PROJECT"
    
    # Ajouter les fichiers docker-compose
    foreach (`$file in `$compose_files) {
        `$compose_cmd += " -f `"`$SCRIPT_DIR\`$file`""
    }
    
    # Ajouter la commande de démarrage
    `$compose_cmd += " up -d"
    
    # Exécuter la commande
    try {
        Invoke-Expression `$compose_cmd
        Write-Log "INFO" "Services vLLM Qwen3 démarrés avec succès."
        return `$true
    }
    catch {
        Write-Log "ERROR" "Échec du démarrage des services vLLM Qwen3: `$_"
        return `$false
    }
}

# Fonction pour vérifier que les services fonctionnent correctement
function Check-Services {
    Write-Log "INFO" "Vérification du fonctionnement des services Qwen3..."
    
    `$services = @(
        "vllm-micro-qwen3:5000",
        "vllm-mini-qwen3:5001",
        "vllm-medium-qwen3:5002"
    )
    
    `$all_running = `$true
    `$max_retries = 10
    `$retry_interval = 5
    
    foreach (`$service_port in `$services) {
        `$service, `$port = `$service_port -split ':'
        
        Write-Log "INFO" "Vérification du service `$service sur le port `$port..."
        
        `$retries = 0
        `$service_running = `$false
        
        while (`$retries -lt `$max_retries -and -not `$service_running) {
            # Vérifier si le service est en cours d'exécution
            `$container_id = docker ps -q -f "name=`${DOCKER_COMPOSE_PROJECT}_`${service}"
            if (-not `$container_id) {
                Write-Log "WARNING" "Le service `$service n'est pas en cours d'exécution. Tentative `$((`$retries+1))/`$max_retries..."
                `$retries++
                Start-Sleep -Seconds `$retry_interval
                continue
            }
            
            # Vérifier si le service répond
            try {
                `$response = Invoke-WebRequest -Uri "http://localhost:`$port/v1/models" -Method Get -UseBasicParsing
                if (`$response.StatusCode -eq 200) {
                    Write-Log "INFO" "Le service `$service fonctionne correctement."
                    `$service_running = `$true
                }
                else {
                    Write-Log "WARNING" "Le service `$service ne répond pas correctement (code HTTP: `$(`$response.StatusCode)). Tentative `$((`$retries+1))/`$max_retries..."
                    `$retries++
                    Start-Sleep -Seconds `$retry_interval
                }
            }
            catch {
                Write-Log "WARNING" "Le service `$service ne répond pas. Tentative `$((`$retries+1))/`$max_retries..."
                `$retries++
                Start-Sleep -Seconds `$retry_interval
            }
        }
        
        if (-not `$service_running) {
            Write-Log "ERROR" "Le service `$service ne fonctionne pas correctement après `$max_retries tentatives."
            `$all_running = `$false
        }
    }
    
    if (-not `$all_running) {
        Write-Log "ERROR" "Certains services Qwen3 ne fonctionnent pas correctement."
        return `$false
    }
    
    Write-Log "INFO" "Tous les services Qwen3 fonctionnent correctement."
    return `$true
}

# Fonction principale
function Main {
    Write-Log "INFO" "Démarrage de la mise à jour rapide des services vLLM Qwen3..."
    
    # Arrêter les services vLLM Qwen3
    if (-not (Stop-Qwen3Services)) {
        Write-Log "ERROR" "Échec de l'arrêt des services vLLM Qwen3. Mise à jour annulée."
        exit 1
    }
    
    # Démarrer les services vLLM Qwen3
    if (-not (Start-Qwen3Services)) {
        Write-Log "ERROR" "Échec du démarrage des services vLLM Qwen3. Mise à jour annulée."
        exit 1
    }
    
    # Vérifier que les services fonctionnent correctement
    if (-not (Check-Services)) {
        Write-Log "ERROR" "Certains services vLLM Qwen3 ne fonctionnent pas correctement."
        exit 1
    }
    
    # Calculer le temps d'indisponibilité
    `$end_time = [int](Get-Date -UFormat %s)
    `$downtime = `$end_time - `$START_TIME
    `$minutes = [math]::Floor(`$downtime / 60)
    `$seconds = `$downtime % 60
    
    Write-Log "INFO" "Mise à jour rapide des services vLLM Qwen3 terminée avec succès."
    Write-Log "INFO" "Temps d'indisponibilité total: `${minutes}m `${seconds}s"
    return `$true
}

# Exécuter la fonction principale
Main
exit `$LASTEXITCODE
"@
        
        Set-Content -Path $script_path -Value $script_content
        
        Write-Log "INFO" "Script de mise à jour rapide créé avec succès: $script_path"
    }
}

# Fonction principale
function Main {
    param (
        [switch]$Help,
        [switch]$Verbose,
        [switch]$DryRun
    )
    
    if ($Help) {
        Show-Help
        return
    }
    
    $script:VERBOSE = $Verbose
    $script:DRY_RUN = $DryRun
    
    Write-Log "INFO" "Démarrage du script de préparation pour la mise à jour des services vLLM..."
    
    # Vérifier les dépendances
    Check-Dependencies
    
    # Charger la configuration
    Load-Config
    
    # Vérifier l'état des services vLLM
    $running_services = Check-ServicesStatus
    Write-Log "INFO" "Nombre de services en cours d'exécution: $running_services"
    
    # Créer un répertoire de build temporaire
    Create-BuildDirectory
    
    # Créer un Dockerfile temporaire optimisé
    Create-OptimizedDockerfile
    
    # Construire l'image Docker
    Build-DockerImage
    
    # Créer un script de mise à jour rapide
    Create-QuickUpdateScript
    
    Write-Log "INFO" "Préparation pour la mise à jour des services vLLM terminée avec succès."
    Write-Log "INFO" "Pour effectuer la mise à jour rapide, exécutez: $PARENT_DIR\quick-update-qwen3.ps1"
    return 0
}

# Traitement des arguments en ligne de commande
$params = @{}
if ($PSBoundParameters.ContainsKey('Help')) { $params['Help'] = $true }
if ($PSBoundParameters.ContainsKey('Verbose')) { $params['Verbose'] = $true }
if ($PSBoundParameters.ContainsKey('DryRun')) { $params['DryRun'] = $true }

# Exécuter la fonction principale
Main @params