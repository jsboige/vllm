# deploy-qwen3-services.ps1 - Script pour déployer les services vLLM Qwen3 avec la nouvelle image refactorisée
# 
# Ce script:
# - Arrête les services vLLM Qwen3 existants
# - Déploie les services avec la nouvelle image vllm/vllm-openai:qwen3-refactored
# - Vérifie que les services fonctionnent correctement

# Définition des couleurs pour les messages
$RED = [System.ConsoleColor]::Red
$GREEN = [System.ConsoleColor]::Green
$YELLOW = [System.ConsoleColor]::Yellow
$BLUE = [System.ConsoleColor]::Blue

# Chemin du script et du répertoire de configuration
$SCRIPT_DIR = "vllm-configs"
$LOG_FILE = Join-Path $PWD "deploy-qwen3-services.log"

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
        
        $choice = Read-Host "Voulez-vous arrêter ces conteneurs et redéployer les services? (O/N)"
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
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "INFO" "Services vLLM Qwen3 arrêtés avec succès."
            return $true
        }
        else {
            Write-Log "ERROR" "Échec de l'arrêt des services vLLM Qwen3. Code de sortie: $LASTEXITCODE"
            return $false
        }
    }
    catch {
        Write-Log "ERROR" "Erreur lors de l'arrêt des services vLLM Qwen3: $_"
        return $false
    }
}

# Fonction pour démarrer les services vLLM Qwen3
function Start-Qwen3Services {
    Write-Log "INFO" "Démarrage des services vLLM Qwen3 avec la nouvelle image refactorisée..."
    
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
            Write-Log "INFO" "Dernières lignes des logs du conteneur ${containerName}:"
            docker logs --tail 20 $containerName
        }
    }
    
    return $allHealthy
}

# Fonction pour tester le déploiement Qwen3
function Test-Qwen3Deployment {
    param (
        [string]$service = "micro",
        [switch]$NoStreaming = $false
    )
    
    Write-Log "INFO" "Test complet du déploiement pour le service $service..."
    
    try {
        $streamingParam = if ($NoStreaming) { "--no-streaming" } else { "" }
        $cmd = "python `"$SCRIPT_DIR\test_qwen3_deployment.py`" --service $service $streamingParam"
        Write-Log "INFO" "Exécution de la commande: $cmd"
        Invoke-Expression $cmd
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "INFO" "Tests de déploiement réussis pour le service $service."
            return $true
        }
        else {
            Write-Log "ERROR" "Échec des tests de déploiement pour le service $service."
            return $false
        }
    }
    catch {
        Write-Log "ERROR" "Erreur lors des tests de déploiement pour le service ${service}: $_"
        return $false
    }
}

# Fonction pour vérifier si l'image Docker existe
function Test-DockerImage {
    param (
        [string]$imageName
    )
    
    Write-Log "INFO" "Vérification de l'existence de l'image Docker $imageName..."
    
    try {
        $image = docker images --format "{{.Repository}}:{{.Tag}}" | Where-Object { $_ -eq $imageName }
        
        if ($image) {
            Write-Log "INFO" "L'image Docker $imageName existe."
            return $true
        }
        else {
            Write-Log "WARNING" "L'image Docker $imageName n'existe pas."
            return $false
        }
    }
    catch {
        Write-Log "ERROR" "Erreur lors de la vérification de l'existence de l'image Docker: $_"
        return $false
    }
}

# Fonction principale
function Main {
    param (
        [switch]$SkipTests = $false,
        [switch]$ForceRestart = $false
    )
    
    Write-Log "INFO" "Démarrage du script de déploiement des services vLLM Qwen3 avec la nouvelle image refactorisée..."
    
    # Définir les variables d'environnement
    Set-EnvironmentVariables
    
    # Vérifier si l'image Docker existe
    $imageName = "vllm/vllm-openai:qwen3-refactored"
    if (-not (Test-DockerImage -imageName $imageName)) {
        Write-Log "ERROR" "L'image Docker $imageName n'existe pas. Veuillez d'abord construire cette image."
        return 1
    }
    
    # Vérifier si les fichiers Docker Compose existent
    $composeFiles = @(
        "docker-compose/docker-compose-micro-qwen3.yml",
        "docker-compose/docker-compose-mini-qwen3.yml",
        "docker-compose/docker-compose-medium-qwen3.yml"
    )
    
    $allFilesExist = $true
    foreach ($file in $composeFiles) {
        $fullPath = Join-Path $SCRIPT_DIR $file
        if (-not (Test-Path $fullPath)) {
            Write-Log "ERROR" "Le fichier $fullPath n'existe pas."
            $allFilesExist = $false
        }
    }
    
    if (-not $allFilesExist) {
        Write-Log "ERROR" "Certains fichiers Docker Compose n'existent pas. Impossible de continuer."
        return 1
    }
    
    # Vérifier si le script start-api-server.sh existe
    $scriptPath = Join-Path $SCRIPT_DIR "start-api-server.sh"
    if (-not (Test-Path $scriptPath)) {
        Write-Log "ERROR" "Le script $scriptPath n'existe pas. Impossible de continuer."
        return 1
    }
    
    # Vérifier si les services sont déjà en cours d'exécution
    if (-not $ForceRestart) {
        if (-not (Check-DockerServices)) {
            return 0
        }
    }
    else {
        # Arrêter les services existants
        Stop-Qwen3Services
    }
    
    # Démarrer les services vLLM Qwen3
    if (-not (Start-Qwen3Services)) {
        Write-Log "ERROR" "Échec du démarrage des services vLLM Qwen3. Déploiement annulé."
        return 1
    }
    
    # Vérifier la santé des services
    $servicesHealthy = Check-ServicesHealth -maxRetries 15 -retryInterval 20
    
    if (-not $servicesHealthy) {
        Write-Log "WARNING" "Certains services ne sont pas en bonne santé après le déploiement."
    }
    
    # Tester le déploiement si demandé
    if (-not $SkipTests) {
        Write-Log "INFO" "Test complet du déploiement pour tous les services..."
        
        $testResults = @{
            "micro" = Test-Qwen3Deployment -service "micro"
            "mini" = Test-Qwen3Deployment -service "mini"
            "medium" = Test-Qwen3Deployment -service "medium"
        }
        
        $allTestsPassed = ($testResults.Values | Where-Object { -not $_ } | Measure-Object).Count -eq 0
        
        if ($allTestsPassed) {
            Write-Log "INFO" "Tous les tests de déploiement ont réussi."
        }
        else {
            Write-Log "WARNING" "Certains tests de déploiement ont échoué:"
            foreach ($service in $testResults.Keys) {
                $result = if ($testResults[$service]) { "Réussi" } else { "Échoué" }
                Write-Log "WARNING" "  Service ${service}: $result"
            }
        }
    }
    
    Write-Log "INFO" "Déploiement des services vLLM Qwen3 avec la nouvelle image refactorisée terminé."
    return 0
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
            Write-Host "Usage: .\deploy-qwen3-services.ps1 [--skip-tests] [--force-restart] [--help]"
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