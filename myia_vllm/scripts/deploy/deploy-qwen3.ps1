# deploy-qwen3.ps1 - Script principal de déploiement des services vLLM Qwen3
#
# Version modernisée utilisant l'image officielle vllm/vllm-openai:v0.9.2
# Aligné sur la stratégie documentée dans 00_MASTER_CONFIGURATION_GUIDE.md
#
# Auteur: Roo Code (refactorisation septembre 2025)
# Compatible avec: Image Docker officielle vLLM v0.9.2

param(
    [switch]$Help,
    [switch]$Verbose,
    [switch]$DryRun,
    [ValidateSet("micro", "mini", "medium", "all")]
    [string]$Profile = "all",
    [switch]$SkipHealthCheck
)

# Définition des couleurs pour les messages
$RED = [System.ConsoleColor]::Red
$GREEN = [System.ConsoleColor]::Green
$YELLOW = [System.ConsoleColor]::Yellow
$BLUE = [System.ConsoleColor]::Blue
$CYAN = [System.ConsoleColor]::Cyan

# Chemin du script et configuration
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_ROOT = Split-Path -Parent (Split-Path -Parent $SCRIPT_DIR)
$ENV_FILE = Join-Path $PROJECT_ROOT ".env"
$LOG_FILE = Join-Path $SCRIPT_DIR "deploy-qwen3.log"

# Configuration des profils selon le document maître
$PROFILES = @{
    "micro" = @{
        "compose_file" = "docker-compose-micro-qwen3.yml"
        "service_name" = "vllm-micro"
        "model" = "Qwen/Qwen2-1.5B-Instruct-AWQ"
        "port" = "5000"
        "gpu" = "2"
        "description" = "Qwen3 Micro (1.7B) - GPU unique, optimisé FP8"
    }
    "mini" = @{
        "compose_file" = "docker-compose-mini-qwen3.yml"
        "service_name" = "vllm-mini"
        "model" = "Qwen/Qwen2-7B-Instruct-AWQ"
        "port" = "5001"
        "gpu" = "2"
        "description" = "Qwen3 Mini (8B) - GPU unique, quantification AWQ"
    }
    "medium" = @{
        "compose_file" = "docker-compose-medium-qwen3.yml"
        "service_name" = "vllm-medium"
        "model" = "Qwen/Qwen3-32B-AWQ"
        "port" = "5002"
        "gpu" = "0,1"
        "description" = "Qwen3 Medium (32B) - Dual GPU, tensor-parallel-size=2"
    }
}

# Fonction d'affichage de l'aide
function Show-Help {
    Write-Host ""
    Write-Host "=== SCRIPT DE DÉPLOIEMENT QWEN3 MODERNISÉ ===" -ForegroundColor $CYAN
    Write-Host ""
    Write-Host "UTILISATION:" -ForegroundColor $YELLOW
    Write-Host "  .\deploy-qwen3.ps1 [-Profile <profil>] [-Verbose] [-DryRun] [-SkipHealthCheck]"
    Write-Host ""
    Write-Host "PARAMÈTRES:" -ForegroundColor $YELLOW
    Write-Host "  -Profile      Profil à déployer: micro|mini|medium|all (défaut: all)"
    Write-Host "  -Verbose      Mode verbeux avec informations détaillées"
    Write-Host "  -DryRun       Simulation sans déploiement réel"
    Write-Host "  -SkipHealthCheck  Ignorer la vérification de santé post-déploiement"
    Write-Host "  -Help         Afficher cette aide"
    Write-Host ""
    Write-Host "EXEMPLES:" -ForegroundColor $YELLOW
    Write-Host "  .\deploy-qwen3.ps1                    # Déploie tous les profils"
    Write-Host "  .\deploy-qwen3.ps1 -Profile medium    # Déploie uniquement le modèle Medium"
    Write-Host "  .\deploy-qwen3.ps1 -DryRun -Verbose   # Simulation avec détails"
    Write-Host ""
    Write-Host "PROFILS DISPONIBLES:" -ForegroundColor $YELLOW
    foreach ($profile in $PROFILES.Keys) {
        $config = $PROFILES[$profile]
        Write-Host "  $profile".PadRight(8) "- $($config.description)" -ForegroundColor $GREEN
    }
    Write-Host ""
    Write-Host "PRÉREQUIS:" -ForegroundColor $YELLOW
    Write-Host "  - Docker et Docker Compose installés"
    Write-Host "  - Fichier .env configuré avec les variables requises"
    Write-Host "  - Image officielle vllm/vllm-openai:v0.9.2"
    Write-Host ""
    exit 0
}

# Fonction de journalisation
function Write-Log {
    param (
        [string]$Level,
        [string]$Message,
        [switch]$NoNewLine
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = $GREEN
    
    switch ($Level) {
        "INFO" { $color = $GREEN }
        "WARN" { $color = $YELLOW }
        "ERROR" { $color = $RED }
        "DEBUG" { $color = $BLUE }
    }
    
    $logEntry = "[$timestamp] [$Level] $Message"
    
    if ($NoNewLine) {
        Write-Host -ForegroundColor $color $logEntry -NoNewline
    } else {
        Write-Host -ForegroundColor $color $logEntry
    }
    
    # Log vers fichier
    Add-Content -Path $LOG_FILE -Value $logEntry
}

# Vérification des prérequis
function Test-Prerequisites {
    Write-Log "INFO" "Vérification des prérequis..."
    
    # Vérifier Docker
    try {
        $dockerVersion = docker --version
        Write-Log "INFO" "Docker détecté: $dockerVersion"
    } catch {
        Write-Log "ERROR" "Docker n'est pas installé ou accessible"
        return $false
    }
    
    # Vérifier Docker Compose
    try {
        $composeVersion = docker-compose --version
        Write-Log "INFO" "Docker Compose détecté: $composeVersion"
    } catch {
        Write-Log "ERROR" "Docker Compose n'est pas installé ou accessible"
        return $false
    }
    
    # Vérifier le fichier .env
    if (-not (Test-Path $ENV_FILE)) {
        Write-Log "ERROR" "Fichier .env manquant: $ENV_FILE"
        Write-Log "ERROR" "Créez le fichier .env basé sur .env.example"
        return $false
    }
    
    Write-Log "INFO" "Fichier .env trouvé: $ENV_FILE"
    return $true
}

# Charger les variables d'environnement
function Load-EnvironmentVariables {
    Write-Log "INFO" "Chargement des variables d'environnement..."
    
    if (Test-Path $ENV_FILE) {
        Get-Content $ENV_FILE | Where-Object { $_ -match '^[^#].*=' } | ForEach-Object {
            $key, $value = $_ -split '=', 2
            [System.Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim(), "Process")
            
            if ($Verbose) {
                # Masquer les tokens sensibles
                $displayValue = if ($key -match "(TOKEN|KEY|SECRET)") { 
                    $value.Substring(0, [Math]::Min(8, $value.Length)) + "***" 
                } else { 
                    $value 
                }
                Write-Log "DEBUG" "Chargé: $key = $displayValue"
            }
        }
        Write-Log "INFO" "Variables d'environnement chargées avec succès"
    } else {
        Write-Log "ERROR" "Impossible de charger le fichier .env"
        return $false
    }
    return $true
}

# Déployer un profil spécifique
function Deploy-Profile {
    param (
        [string]$ProfileName
    )
    
    $config = $PROFILES[$ProfileName]
    if (-not $config) {
        Write-Log "ERROR" "Profil inconnu: $ProfileName"
        return $false
    }
    
    Write-Log "INFO" "🚀 Déploiement du profil: $ProfileName"
    Write-Log "INFO" "   Description: $($config.description)"
    Write-Log "INFO" "   Modèle: $($config.model)"
    Write-Log "INFO" "   Port: $($config.port)"
    Write-Log "INFO" "   GPU(s): $($config.gpu)"
    
    $composeFilePath = Join-Path $PROJECT_ROOT $config.compose_file
    
    if (-not (Test-Path $composeFilePath)) {
        Write-Log "ERROR" "Fichier Docker Compose manquant: $composeFilePath"
        return $false
    }
    
    if ($DryRun) {
        Write-Log "INFO" "[DRY-RUN] docker-compose -f $composeFilePath up -d"
        return $true
    }
    
    try {
        Write-Log "INFO" "Démarrage du service $($config.service_name)..."
        $result = docker-compose -f $composeFilePath up -d 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Log "INFO" "✅ Service $($config.service_name) démarré avec succès"
            return $true
        } else {
            Write-Log "ERROR" "❌ Échec du démarrage de $($config.service_name)"
            Write-Log "ERROR" $result
            return $false
        }
    } catch {
        Write-Log "ERROR" "Erreur lors du déploiement de $ProfileName : $($_.Exception.Message)"
        return $false
    }
}

# Vérification de santé des services
function Test-ServiceHealth {
    param (
        [string]$ProfileName
    )
    
    if ($SkipHealthCheck) {
        Write-Log "INFO" "Vérification de santé ignorée pour $ProfileName"
        return $true
    }
    
    $config = $PROFILES[$ProfileName]
    $healthUrl = "http://localhost:$($config.port)/health"
    
    Write-Log "INFO" "Vérification de santé: $healthUrl"
    
    $maxRetries = 10
    $retryDelay = 10
    
    for ($i = 1; $i -le $maxRetries; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $healthUrl -Method GET -TimeoutSec 5 -UseBasicParsing
            if ($response.StatusCode -eq 200) {
                Write-Log "INFO" "✅ Service $ProfileName en bonne santé (tentative $i/$maxRetries)"
                return $true
            }
        } catch {
            Write-Log "WARN" "Tentative $i/$maxRetries échouée pour $ProfileName (attente ${retryDelay}s)"
            if ($i -lt $maxRetries) {
                Start-Sleep -Seconds $retryDelay
            }
        }
    }
    
    Write-Log "ERROR" "❌ Service $ProfileName non accessible après $maxRetries tentatives"
    return $false
}

# Fonction principale
function Main {
    if ($Help) {
        Show-Help
    }
    
    Write-Log "INFO" "=== DÉPLOIEMENT QWEN3 - IMAGE OFFICIELLE vLLM v0.9.2 ==="
    Write-Log "INFO" "Profil sélectionné: $Profile"
    
    if ($DryRun) {
        Write-Log "INFO" "🔍 MODE SIMULATION ACTIVÉ - Aucune action réelle"
    }
    
    # Vérifications initiales
    if (-not (Test-Prerequisites)) {
        Write-Log "ERROR" "Prérequis non satisfaits"
        exit 1
    }
    
    if (-not (Load-EnvironmentVariables)) {
        Write-Log "ERROR" "Impossible de charger les variables d'environnement"
        exit 1
    }
    
    # Déploiement
    $success = $true
    $profilesToDeploy = if ($Profile -eq "all") { $PROFILES.Keys } else { @($Profile) }
    
    foreach ($profileName in $profilesToDeploy) {
        if (-not (Deploy-Profile $profileName)) {
            $success = $false
        }
        
        # Pause entre les déploiements pour éviter les conflits
        if ($profilesToDeploy.Count -gt 1) {
            Start-Sleep -Seconds 5
        }
    }
    
    if (-not $DryRun -and $success) {
        Write-Log "INFO" "Attente de stabilisation des services (30s)..."
        Start-Sleep -Seconds 30
        
        # Vérification de santé
        foreach ($profileName in $profilesToDeploy) {
            Test-ServiceHealth $profileName | Out-Null
        }
    }
    
    if ($success) {
        Write-Log "INFO" "🎉 Déploiement terminé avec succès!"
        Write-Log "INFO" "Consultez les logs: $LOG_FILE"
    } else {
        Write-Log "ERROR" "❌ Déploiement échoué. Consultez les logs: $LOG_FILE"
        exit 1
    }
}

# Point d'entrée
Main