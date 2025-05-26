# quick-update-qwen3.ps1 - Script de mise à jour rapide des services vLLM Qwen3
# 
# Ce script:
# - Arrête les services vLLM Qwen3 existants
# - Démarre les services avec la nouvelle image Docker
# - Vérifie que tout fonctionne correctement

# Définition des couleurs pour les messages
$RED = [System.ConsoleColor]::Red
$GREEN = [System.ConsoleColor]::Green
$YELLOW = [System.ConsoleColor]::Yellow
$BLUE = [System.ConsoleColor]::Blue

# Chemin du script et du répertoire de configuration
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$CONFIG_FILE = Join-Path $SCRIPT_DIR "update-config.json"
$LOG_FILE = Join-Path $SCRIPT_DIR "quick-update-qwen3.log"

# Variables globales
$config = Get-Content -Path $CONFIG_FILE | ConvertFrom-Json
$DOCKER_COMPOSE_PROJECT = $config.settings.docker_compose_project
$START_TIME = [int](Get-Date -UFormat %s)

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

# Fonction pour arrêter les services vLLM Qwen3
function Stop-Qwen3Services {
    Write-Log "INFO" "Arrêt des services vLLM Qwen3..."
    
    $compose_files = @(
        "vllm-configs\docker-compose\docker-compose-micro-qwen3.yml",
        "vllm-configs\docker-compose\docker-compose-mini-qwen3.yml",
        "vllm-configs\docker-compose\docker-compose-medium-qwen3.yml"
    )
    
    $compose_cmd = "docker compose -p $DOCKER_COMPOSE_PROJECT"
    
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
        "vllm-configs\docker-compose\docker-compose-micro-qwen3.yml",
        "vllm-configs\docker-compose\docker-compose-mini-qwen3.yml",
        "vllm-configs\docker-compose\docker-compose-medium-qwen3.yml"
    )
    
    $compose_cmd = "docker compose -p $DOCKER_COMPOSE_PROJECT"
    
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
    $end_time = [int](Get-Date -UFormat %s)
    $downtime = $end_time - $START_TIME
    $minutes = [math]::Floor($downtime / 60)
    $seconds = $downtime % 60
    
    Write-Log "INFO" "Mise à jour rapide des services vLLM Qwen3 terminée avec succès."
    Write-Log "INFO" "Temps d'indisponibilité total: ${minutes}m ${seconds}s"
    return $true
}

# Exécuter la fonction principale
Main
exit $LASTEXITCODE
