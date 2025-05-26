# update-qwen3-services.ps1 - Script pour mettre à jour les services vLLM Qwen3
# 
# Ce script:
# - Arrête les services vLLM Qwen3 existants
# - Met à jour les configurations Docker Compose
# - Redémarre les services avec les nouvelles configurations
# - Vérifie que les services fonctionnent correctement

# Définition des couleurs pour les messages
$RED = [System.ConsoleColor]::Red
$GREEN = [System.ConsoleColor]::Green
$YELLOW = [System.ConsoleColor]::Yellow
$BLUE = [System.ConsoleColor]::Blue

# Chemin du script et du répertoire de configuration
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$LOG_FILE = Join-Path $SCRIPT_DIR "update-qwen3-services.log"

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
            Write-Log "INFO" "Dernières lignes des logs du conteneur ${containerName}:"
            docker logs --tail 20 $containerName
        }
    }
    
    return $allHealthy
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
        Write-Log "ERROR" "Erreur lors du test de l'appel d'outils pour le service ${service}: $_"
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
        [switch]$DryRun = $false
    )
    
    Write-Log "INFO" "Démarrage du script de mise à jour des services vLLM Qwen3..."
    
    # Définir les variables d'environnement
    Set-EnvironmentVariables
    
    # Vérifier si l'image Docker existe
    $imageName = "vllm/vllm-openai:qwen3"
    if (-not (Test-DockerImage -imageName $imageName)) {
        Write-Log "ERROR" "L'image Docker $imageName n'existe pas. Veuillez exécuter le script finalize-qwen3-integration.ps1 pour créer l'image."
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
    
    # Si c'est un dry run, ne pas exécuter les commandes
    if ($DryRun) {
        Write-Log "INFO" "Mode dry run activé. Les commandes ne seront pas exécutées."
        Write-Log "INFO" "Les services vLLM Qwen3 seraient arrêtés et redémarrés avec les nouvelles configurations."
        return 0
    }
    
    # Arrêter les services vLLM Qwen3
    if (-not (Stop-Qwen3Services)) {
        Write-Log "ERROR" "Échec de l'arrêt des services vLLM Qwen3. Mise à jour annulée."
        return 1
    }
    
    # Démarrer les services vLLM Qwen3
    if (-not (Start-Qwen3Services)) {
        Write-Log "ERROR" "Échec du démarrage des services vLLM Qwen3. Mise à jour annulée."
        return 1
    }
    
    # Vérifier la santé des services
    if (-not (Check-ServicesHealth -maxRetries 15 -retryInterval 20)) {
        Write-Log "WARNING" "Certains services ne sont pas en bonne santé après la mise à jour."
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
                Write-Log "WARNING" "  Service ${service}: $result"
            }
        }
    }
    
    Write-Log "INFO" "Mise à jour des services vLLM Qwen3 terminée."
    return 0
}

# Analyser les arguments de la ligne de commande
$skipTests = $false
$dryRun = $false

for ($i = 0; $i -lt $args.Count; $i++) {
    switch ($args[$i]) {
        "--skip-tests" {
            $skipTests = $true
        }
        "--dry-run" {
            $dryRun = $true
        }
        "--help" {
            Write-Host "Usage: .\update-qwen3-services.ps1 [--skip-tests] [--dry-run] [--help]"
            Write-Host "  --skip-tests      Ignorer les tests d'appel d'outils"
            Write-Host "  --dry-run         Simuler les actions sans les exécuter"
            Write-Host "  --help            Afficher cette aide"
            exit 0
        }
    }
}

# Exécuter la fonction principale
Main -SkipTests:$skipTests -DryRun:$dryRun
exit $LASTEXITCODE