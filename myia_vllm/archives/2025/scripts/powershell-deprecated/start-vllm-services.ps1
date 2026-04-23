# start-vllm-services.ps1 - Script pour démarrer les services vLLM
# 
# Ce script:
# - Vérifie l'état actuel des services vLLM
# - Démarre les services qui ne sont pas en cours d'exécution

# Définition des couleurs pour les messages
$RED = [System.ConsoleColor]::Red
$GREEN = [System.ConsoleColor]::Green
$YELLOW = [System.ConsoleColor]::Yellow
$BLUE = [System.ConsoleColor]::Blue

# Chemin du script et du répertoire de configuration
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$CONFIG_FILE = Join-Path $SCRIPT_DIR "update-config.json"
$LOG_FILE = Join-Path $SCRIPT_DIR "start-vllm-services.log"

# Variables globales
$DOCKER_COMPOSE_PROJECT = ""
$VERBOSE = $false

# Fonction pour afficher l'aide
function Show-Help {
    Write-Host "Usage: $($MyInvocation.MyCommand.Name) [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Help                Affiche cette aide"
    Write-Host "  -Verbose             Mode verbeux (affiche plus de détails)"
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
        "vllm-micro-qwen3:5000",
        "vllm-mini-qwen3:5001",
        "vllm-medium-qwen3:5002"
    )
    
    $running_services = @()
    $stopped_services = @()
    
    foreach ($service_port in $services) {
        $service, $port = $service_port -split ':'
        
        # Vérifier si le service est en cours d'exécution
        $container_id = docker ps -q -f "name=${DOCKER_COMPOSE_PROJECT}_${service}"
        if (-not $container_id) {
            $stopped_services += $service_port
            Write-Log "INFO" "Le service $service n'est pas en cours d'exécution."
        }
        else {
            $running_services += $service_port
            Write-Log "INFO" "Le service $service est en cours d'exécution (container ID: $container_id)."
            
            if ($VERBOSE) {
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
    
    # Retourner les services arrêtés
    return $stopped_services
}

# Fonction pour démarrer un service vLLM
function Start-VllmService {
    param (
        [string]$service_port
    )
    
    $service, $port = $service_port -split ':'
    Write-Log "INFO" "Démarrage du service $service sur le port $port..."
    
    # Déterminer le fichier docker-compose à utiliser
    $compose_file = ""
    switch ($service) {
        "vllm-micro-qwen3" { $compose_file = "docker-compose\docker-compose-micro-qwen3.yml" }
        "vllm-mini-qwen3" { $compose_file = "docker-compose\docker-compose-mini-qwen3.yml" }
        "vllm-medium-qwen3" { $compose_file = "docker-compose\docker-compose-medium-qwen3.yml" }
        default { 
            Write-Log "ERROR" "Service inconnu: $service"
            return $false
        }
    }
    
    # Construire la commande docker-compose
    $compose_cmd = "docker compose -p $DOCKER_COMPOSE_PROJECT -f `"$SCRIPT_DIR\$compose_file`" up -d"
    
    # Exécuter la commande
    try {
        Write-Log "INFO" "Exécution de la commande: $compose_cmd"
        Invoke-Expression $compose_cmd
        Write-Log "INFO" "Service $service démarré avec succès."
        return $true
    }
    catch {
        Write-Log "ERROR" "Échec du démarrage du service $service: $($_.Exception.Message)"
        return $false
    }
}

# Fonction pour vérifier que le service fonctionne correctement
function Check-ServiceHealth {
    param (
        [string]$service_port
    )
    
    $service, $port = $service_port -split ':'
    Write-Log "INFO" "Vérification de la santé du service $service sur le port $port..."
    
    $max_retries = 10
    $retry_interval = 5
    $retries = 0
    $service_healthy = $false
    
    while ($retries -lt $max_retries -and -not $service_healthy) {
        # Vérifier si le service est en cours d'exécution
        $container_id = docker ps -q -f "name=${DOCKER_COMPOSE_PROJECT}_${service}"
        if (-not $container_id) {
            Write-Log "WARNING" "Le service $service n'est pas en cours d'exécution. Tentative $(($retries+1))/$max_retries..."
            $retries++
            Start-Sleep -Seconds $retry_interval
            continue
        }
        
        # Vérifier si le service répond
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:$port/v1/models" -Method Get -UseBasicParsing
            if ($response.StatusCode -eq 200) {
                Write-Log "INFO" "Le service $service fonctionne correctement."
                $service_healthy = $true
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
    
    if (-not $service_healthy) {
        Write-Log "ERROR" "Le service $service ne fonctionne pas correctement après $max_retries tentatives."
        return $false
    }
    
    return $true
}

# Fonction principale
function Main {
    param (
        [switch]$Help,
        [switch]$Verbose
    )
    
    if ($Help) {
        Show-Help
        return
    }
    
    $script:VERBOSE = $Verbose
    
    Write-Log "INFO" "Démarrage du script pour démarrer les services vLLM..."
    
    # Charger la configuration
    Load-Config
    
    # Vérifier l'état des services vLLM
    $stopped_services = Check-ServicesStatus
    
    if ($stopped_services.Count -eq 0) {
        Write-Log "INFO" "Tous les services vLLM sont déjà en cours d'exécution."
        return 0
    }
    
    # Démarrer les services arrêtés
    $start_failures = 0
    foreach ($service_port in $stopped_services) {
        if (-not (Start-VllmService -service_port $service_port)) {
            $start_failures++
            continue
        }
        
        # Vérifier que le service fonctionne correctement
        if (-not (Check-ServiceHealth -service_port $service_port)) {
            $start_failures++
        }
    }
    
    if ($start_failures -gt 0) {
        Write-Log "ERROR" "Échec du démarrage de $start_failures service(s)."
        return 1
    }
    
    Write-Log "INFO" "Tous les services vLLM ont été démarrés avec succès."
    return 0
}

# Traitement des arguments en ligne de commande
$params = @{}
if ($PSBoundParameters.ContainsKey('Help')) { $params['Help'] = $true }
if ($PSBoundParameters.ContainsKey('Verbose')) { $params['Verbose'] = $true }

# Exécuter la fonction principale
Main @params