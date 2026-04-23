# test-vllm-services.ps1 - Script pour tester les services vLLM
# 
# Ce script:
# - Vérifie que les services vLLM sont en cours d'exécution
# - Teste les API des services vLLM pour s'assurer qu'ils fonctionnent correctement

# Définition des couleurs pour les messages
$RED = [System.ConsoleColor]::Red
$GREEN = [System.ConsoleColor]::Green
$YELLOW = [System.ConsoleColor]::Yellow
$BLUE = [System.ConsoleColor]::Blue

# Chemin du script et du répertoire de configuration
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$LOG_FILE = Join-Path $SCRIPT_DIR "test-vllm-services.log"

# Variables globales
$VERBOSE = $false
$DETAILED_TEST = $false

# Fonction pour afficher l'aide
function Show-Help {
    Write-Host "Usage: $($MyInvocation.MyCommand.Name) [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Help                Affiche cette aide"
    Write-Host "  -Verbose             Mode verbeux (affiche plus de détails)"
    Write-Host "  -DetailedTest        Effectue des tests détaillés des API"
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
        $container_id = docker ps -q -f "name=*${service}*"
        if (-not $container_id) {
            $stopped_services += $service_port
            Write-Log "WARNING" "Le service $service n'est pas en cours d'exécution."
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
    
    # Retourner les services en cours d'exécution
    return $running_services
}

# Fonction pour tester l'API d'un service vLLM
function Test-VllmApi {
    param (
        [string]$service_port
    )
    
    $service, $port = $service_port -split ':'
    Write-Log "INFO" "Test de l'API du service $service sur le port $port..."
    
    # Test 1: Vérifier que le service répond
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:$port/v1/models" -Method Get -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            Write-Log "INFO" "Le service $service répond correctement à /v1/models."
            
            if ($VERBOSE) {
                $models = $response.Content | ConvertFrom-Json
                Write-Log "INFO" "  - Modèles disponibles: $($models.data.Count)"
                foreach ($model in $models.data) {
                    Write-Log "INFO" "    - $($model.id)"
                }
            }
            
            # Test 2: Vérifier que le service peut générer du texte
            if ($DETAILED_TEST) {
                Write-Log "INFO" "Test de génération de texte pour le service $service..."
                
                $request_body = @{
                    model = "Qwen/Qwen3-1.7B-Base"
                    messages = @(
                        @{
                            role = "user"
                            content = "Bonjour, comment vas-tu ?"
                        }
                    )
                    max_tokens = 50
                } | ConvertTo-Json
                
                try {
                    $chat_response = Invoke-WebRequest -Uri "http://localhost:$port/v1/chat/completions" -Method Post -Body $request_body -ContentType "application/json" -UseBasicParsing
                    if ($chat_response.StatusCode -eq 200) {
                        $chat_result = $chat_response.Content | ConvertFrom-Json
                        Write-Log "INFO" "Le service $service a généré du texte avec succès."
                        if ($VERBOSE) {
                            Write-Log "INFO" "  - Réponse: $($chat_result.choices[0].message.content)"
                        }
                        return $true
                    }
                    else {
                        Write-Log "ERROR" "Le service $service n'a pas pu générer de texte (code HTTP: $($chat_response.StatusCode))."
                        return $false
                    }
                }
                catch {
                    $errorMsg = $_.Exception.Message
                    Write-Log "ERROR" "Erreur lors du test de génération de texte pour le service $service" -f $service
                    Write-Log "ERROR" "Message d'erreur: $errorMsg"
                    return $false
                }
            }
            
            return $true
        }
        else {
            Write-Log "ERROR" "Le service $service ne répond pas correctement à /v1/models (code HTTP: $($response.StatusCode))."
            return $false
        }
    }
    catch {
        $errorMsg = $_.Exception.Message
        Write-Log "ERROR" "Erreur lors du test de l'API du service $service" -f $service
        Write-Log "ERROR" "Message d'erreur: $errorMsg"
        return $false
    }
}

# Fonction principale
function Main {
    param (
        [switch]$Help,
        [switch]$Verbose,
        [switch]$DetailedTest
    )
    
    if ($Help) {
        Show-Help
        return
    }
    
    $script:VERBOSE = $Verbose
    $script:DETAILED_TEST = $DetailedTest
    
    Write-Log "INFO" "Démarrage du script de test des services vLLM..."
    
    # Vérifier l'état des services vLLM
    $running_services = Check-ServicesStatus
    
    if ($running_services.Count -eq 0) {
        Write-Log "ERROR" "Aucun service vLLM n'est en cours d'exécution."
        return 1
    }
    
    # Tester les API des services en cours d'exécution
    $test_failures = 0
    foreach ($service_port in $running_services) {
        if (-not (Test-VllmApi -service_port $service_port)) {
            $test_failures++
        }
    }
    
    if ($test_failures -gt 0) {
        Write-Log "ERROR" "Échec du test de $test_failures service(s)."
        return 1
    }
    
    Write-Log "INFO" "Tous les services vLLM fonctionnent correctement."
    return 0
}

# Traitement des arguments en ligne de commande
$params = @{}
if ($PSBoundParameters.ContainsKey('Help')) { $params['Help'] = $true }
if ($PSBoundParameters.ContainsKey('Verbose')) { $params['Verbose'] = $true }
if ($PSBoundParameters.ContainsKey('DetailedTest')) { $params['DetailedTest'] = $true }

# Exécuter la fonction principale
Main @params