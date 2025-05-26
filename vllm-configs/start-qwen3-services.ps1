# start-qwen3-services.ps1 - Script optimisé pour démarrer les services vLLM Qwen3
# 
# Ce script:
# - Définit les variables d'environnement nécessaires
# - Vérifie l'état des services avant le démarrage
# - Démarre les services avec des paramètres optimisés
# - Vérifie l'état des services après le démarrage
# - Inclut des mécanismes de récupération en cas d'échec

# Définition des couleurs pour les messages
$RED = [System.ConsoleColor]::Red
$GREEN = [System.ConsoleColor]::Green
$YELLOW = [System.ConsoleColor]::Yellow
$BLUE = [System.ConsoleColor]::Blue

# Chemin du script et du répertoire de configuration
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$LOG_FILE = Join-Path $SCRIPT_DIR "start-qwen3-services.log"

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
    $env:GPU_MEMORY_UTILIZATION_MICRO = "0.9"
    $env:GPU_MEMORY_UTILIZATION_MINI = "0.9"
    $env:GPU_MEMORY_UTILIZATION_MEDIUM = "0.9"
    
    # Dispositifs CUDA visibles
    $env:CUDA_VISIBLE_DEVICES_MICRO = "2"
    $env:CUDA_VISIBLE_DEVICES_MINI = "1"
    $env:CUDA_VISIBLE_DEVICES_MEDIUM = "0,1"
    
    Write-Log "INFO" "Variables d'environnement définies avec succès."
}

# Fonction pour vérifier l'état des services Docker
function Check-DockerServices {
    Write-Log "INFO" "Vérification de l'état des services Docker..."
    
    # Vérifier si Docker est en cours d'exécution
    try {
        $dockerStatus = docker info 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Log "ERROR" "Docker n'est pas en cours d'exécution. Veuillez démarrer Docker Desktop."
            return $false
        }
    }
    catch {
        Write-Log "ERROR" "Erreur lors de la vérification de l'état de Docker: $_"
        return $false
    }
    
    # Vérifier si les conteneurs vLLM Qwen3 sont déjà en cours d'exécution
    $containers = docker ps --format "{{.Names}}" | Where-Object { $_ -like "*vllm*qwen3*" }
    
    if ($containers) {
        Write-Log "WARNING" "Des conteneurs vLLM Qwen3 sont déjà en cours d'exécution:"
        foreach ($container in $containers) {
            $containerInfo = docker inspect --format "{{.Name}} - {{.State.Status}} - {{.State.Health.Status}}" $container
            Write-Log "WARNING" "  $containerInfo"
        }
        
        $choice = Read-Host "Voulez-vous arrêter ces conteneurs et redémarrer les services? (O/N)"
        if ($choice -eq "O" -or $choice -eq "o") {
            Write-Log "INFO" "Arrêt des conteneurs vLLM Qwen3 existants..."
            Stop-Qwen3Services
        }
        else {
            Write-Log "INFO" "Les services vLLM Qwen3 sont déjà en cours d'exécution. Aucune action nécessaire."
            return $false
        }
    }
    
    return $true
}

# Fonction pour arrêter les services vLLM Qwen3
function Stop-Qwen3Services {
    Write-Log "INFO" "Arrêt des services vLLM Qwen3..."
    
    $compose_files = @(
        "docker-compose/docker-compose-micro-qwen3.yml",
        "docker-compose/docker-compose-mini-qwen3.yml",
        "docker-compose/docker-compose-medium-qwen3.yml"
    )
    
    $compose_cmd = "docker compose -p myia-vllm"
    
    # Ajouter les fichiers docker-compose
    foreach ($file in $compose_files) {
        $full_path = Join-Path $SCRIPT_DIR $file
        if (Test-Path $full_path) {
            $compose_cmd += " -f `"$full_path`""
        }
        else {
            Write-Log "WARNING" "Le fichier $full_path n'existe pas. Il sera ignoré."
        }
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
        "docker-compose/docker-compose-micro-qwen3.yml",
        "docker-compose/docker-compose-mini-qwen3.yml",
        "docker-compose/docker-compose-medium-qwen3.yml"
    )
    
    $compose_cmd = "docker compose -p myia-vllm"
    
    # Ajouter les fichiers docker-compose
    foreach ($file in $compose_files) {
        $full_path = Join-Path $SCRIPT_DIR $file
        if (Test-Path $full_path) {
            $compose_cmd += " -f `"$full_path`""
        }
        else {
            Write-Log "ERROR" "Le fichier $full_path n'existe pas. Impossible de démarrer les services."
            return $false
        }
    }
    
    # Ajouter la commande de démarrage
    $compose_cmd += " up -d"
    
    # Exécuter la commande
    try {
        Write-Log "INFO" "Exécution de la commande: $compose_cmd"
        Invoke-Expression $compose_cmd
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "INFO" "Services vLLM Qwen3 démarrés avec succès."
            return $true
        }
        else {
            Write-Log "ERROR" "Échec du démarrage des services vLLM Qwen3. Code de sortie: $LASTEXITCODE"
            return $false
        }
    }
    catch {
        Write-Log "ERROR" "Erreur lors du démarrage des services vLLM Qwen3: $_"
        return $false
    }
}

# Fonction pour vérifier la santé des services
function Check-ServicesHealth {
    param (
        [int]$maxRetries = 10,
        [int]$retryInterval = 30
    )
    
    Write-Log "INFO" "Vérification de la santé des services vLLM Qwen3..."
    
    $services = @(
        @{Name="vllm-micro-qwen3"; Port="5000"; Key=$env:VLLM_API_KEY_MICRO},
        @{Name="vllm-mini-qwen3"; Port="5001"; Key=$env:VLLM_API_KEY_MINI},
        @{Name="vllm-medium-qwen3"; Port="5002"; Key=$env:VLLM_API_KEY_MEDIUM}
    )
    
    $allHealthy = $true
    
    foreach ($service in $services) {
        $serviceName = $service.Name
        $port = $service.Port
        $apiKey = $service.Key
        
        Write-Log "INFO" "Vérification de la santé du service $serviceName sur le port $port..."
        
        $retries = 0
        $serviceHealthy = $false
        
        while ($retries -lt $maxRetries -and -not $serviceHealthy) {
            # Vérifier si le conteneur est en cours d'exécution
            $containerName = "myia-vllm_$serviceName"
            $containerStatus = docker ps -q -f "name=$containerName"
            
            if (-not $containerStatus) {
                Write-Log "WARNING" "Le conteneur $containerName n'est pas en cours d'exécution. Tentative $(($retries+1))/$maxRetries..."
                $retries++
                Start-Sleep -Seconds $retryInterval
                continue
            }
            
            # Vérifier l'état de santé du conteneur
            $healthStatus = docker inspect --format "{{.State.Health.Status}}" $containerName 2>$null
            
            if ($healthStatus -eq "healthy") {
                Write-Log "INFO" "Le service $serviceName est en bonne santé."
                $serviceHealthy = $true
            }
            else {
                # Vérifier si le service répond à l'API
                try {
                    $headers = @{ "Authorization" = "Bearer $apiKey" }
                    $response = Invoke-WebRequest -Uri "http://localhost:$port/v1/models" -Method Get -Headers $headers -UseBasicParsing -TimeoutSec 10
                    
                    if ($response.StatusCode -eq 200) {
                        Write-Log "INFO" "Le service $serviceName répond correctement à l'API, mais son état de santé est '$healthStatus'."
                        $serviceHealthy = $true
                    }
                    else {
                        Write-Log "WARNING" "Le service $serviceName ne répond pas correctement à l'API (code HTTP: $($response.StatusCode)). Tentative $(($retries+1))/$maxRetries..."
                    }
                }
                catch {
                    Write-Log "WARNING" "Le service $serviceName ne répond pas à l'API. Tentative $(($retries+1))/$maxRetries..."
                }
                
                $retries++
                Start-Sleep -Seconds $retryInterval
            }
        }
        
        if (-not $serviceHealthy) {
            Write-Log "ERROR" "Le service $serviceName n'est pas en bonne santé après $maxRetries tentatives."
            $allHealthy = $false
            
            # Afficher les logs du conteneur pour le diagnostic
            Write-Log "INFO" "Dernières lignes des logs du conteneur $containerName:"
            docker logs --tail 20 $containerName
        }
    }
    
    return $allHealthy
}

# Fonction pour récupérer un service défaillant
function Recover-FailedService {
    param (
        [string]$serviceName
    )
    
    Write-Log "INFO" "Tentative de récupération du service $serviceName..."
    
    $containerName = "myia-vllm_$serviceName"
    
    # Redémarrer le conteneur
    try {
        Write-Log "INFO" "Redémarrage du conteneur $containerName..."
        docker restart $containerName
        
        # Attendre que le conteneur soit prêt
        Start-Sleep -Seconds 30
        
        # Vérifier l'état du conteneur
        $containerStatus = docker inspect --format "{{.State.Status}}" $containerName 2>$null
        
        if ($containerStatus -eq "running") {
            Write-Log "INFO" "Le conteneur $containerName a été redémarré avec succès."
            return $true
        }
        else {
            Write-Log "ERROR" "Le conteneur $containerName n'est pas en cours d'exécution après le redémarrage."
            return $false
        }
    }
    catch {
        Write-Log "ERROR" "Erreur lors du redémarrage du conteneur $containerName: $_"
        return $false
    }
}

# Fonction pour tester l'appel d'outils
function Test-ToolCalling {
    param (
        [string]$service = "micro"
    )
    
    Write-Log "INFO" "Test de l'appel d'outils pour le service $service..."
    
    try {
        $cmd = "python `"$SCRIPT_DIR\test_qwen3_tool_calling_custom_fixed.py`" --service $service"
        Write-Log "INFO" "Exécution de la commande: $cmd"
        Invoke-Expression $cmd
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "INFO" "Test de l'appel d'outils réussi pour le service $service."
            return $true
        }
        else {
            Write-Log "ERROR" "Échec du test de l'appel d'outils pour le service $service."
            return $false
        }
    }
    catch {
        Write-Log "ERROR" "Erreur lors du test de l'appel d'outils pour le service $service: $_"
        return $false
    }
}

# Fonction principale
function Main {
    param (
        [switch]$SkipTests = $false,
        [switch]$ForceRestart = $false
    )
    
    Write-Log "INFO" "Démarrage du script de démarrage optimisé pour les services vLLM Qwen3..."
    
    # Définir les variables d'environnement
    Set-EnvironmentVariables
    
    # Vérifier l'état des services Docker
    if ($ForceRestart -or (Check-DockerServices)) {
        # Arrêter les services existants si nécessaire
        if ($ForceRestart) {
            Stop-Qwen3Services
        }
        
        # Démarrer les services
        if (Start-Qwen3Services) {
            Write-Log "INFO" "Services vLLM Qwen3 démarrés. Vérification de la santé des services..."
            
            # Vérifier la santé des services
            $servicesHealthy = Check-ServicesHealth -maxRetries 15 -retryInterval 20
            
            if (-not $servicesHealthy) {
                Write-Log "WARNING" "Certains services ne sont pas en bonne santé. Tentative de récupération..."
                
                # Récupérer les services défaillants
                $services = @("vllm-micro-qwen3", "vllm-mini-qwen3", "vllm-medium-qwen3")
                foreach ($service in $services) {
                    $containerName = "myia-vllm_$service"
                    $healthStatus = docker inspect --format "{{.State.Health.Status}}" $containerName 2>$null
                    
                    if ($healthStatus -ne "healthy") {
                        Write-Log "WARNING" "Le service $service n'est pas en bonne santé. Tentative de récupération..."
                        Recover-FailedService -serviceName $service
                    }
                }
                
                # Vérifier à nouveau la santé des services
                $servicesHealthy = Check-ServicesHealth -maxRetries 5 -retryInterval 20
                
                if (-not $servicesHealthy) {
                    Write-Log "ERROR" "Impossible de récupérer tous les services. Veuillez vérifier les logs pour plus de détails."
                }
            }
            
            # Tester l'appel d'outils si demandé
            if (-not $SkipTests) {
                Write-Log "INFO" "Test de l'appel d'outils pour tous les services..."
                
                $testResults = @{
                    "micro" = Test-ToolCalling -service "micro"
                    "mini" = Test-ToolCalling -service "mini"
                    "medium" = Test-ToolCalling -service "medium"
                }
                
                $allTestsPassed = $testResults.Values | ForEach-Object { $_ } | Where-Object { -not $_ } | Measure-Object | Select-Object -ExpandProperty Count -eq 0
                
                if ($allTestsPassed) {
                    Write-Log "INFO" "Tous les tests d'appel d'outils ont réussi."
                }
                else {
                    Write-Log "WARNING" "Certains tests d'appel d'outils ont échoué:"
                    foreach ($service in $testResults.Keys) {
                        $result = if ($testResults[$service]) { "Réussi" } else { "Échoué" }
                        Write-Log "WARNING" "  Service $service: $result"
                    }
                }
            }
            
            Write-Log "INFO" "Démarrage des services vLLM Qwen3 terminé."
            return 0
        }
        else {
            Write-Log "ERROR" "Échec du démarrage des services vLLM Qwen3."
            return 1
        }
    }
    else {
        Write-Log "INFO" "Aucune action nécessaire."
        return 0
    }
}

# Analyser les arguments de la ligne de commande
$skipTests = $false
$forceRestart = $false

for ($i = 0; $i -lt $args.Count; $i++) {
    switch ($args[$i]) {
        "--skip-tests" {
            $skipTests = $true
        }
        "--force-restart" {
            $forceRestart = $true
        }
        "--help" {
            Write-Host "Usage: .\start-qwen3-services.ps1 [--skip-tests] [--force-restart] [--help]"
            Write-Host "  --skip-tests      Ignorer les tests d'appel d'outils"
            Write-Host "  --force-restart   Forcer le redémarrage des services même s'ils sont déjà en cours d'exécution"
            Write-Host "  --help            Afficher cette aide"
            exit 0
        }
    }
}

# Exécuter la fonction principale
Main -SkipTests:$skipTests -ForceRestart:$forceRestart
exit $LASTEXITCODE