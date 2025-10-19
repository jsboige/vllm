# Script de Déploiement avec Monitoring - Service Medium vLLM
# Mission 9 SDDD - Redéploiement Service Medium
# Date: 2025-10-16

<#
.SYNOPSIS
    Déploiement complet du service medium avec monitoring intégré

.DESCRIPTION
    1. Nettoie les conteneurs existants
    2. Redéploie le service medium Qwen3-32B-AWQ
    3. Lance le monitoring automatique jusqu'à l'état healthy
    
    Ce script combine déploiement et surveillance pour un workflow complet.

.PARAMETER SkipCleanup
    Ne pas nettoyer les conteneurs existants (défaut: false)

.PARAMETER MonitorInterval
    Intervalle de monitoring en secondes (défaut: 10)

.PARAMETER MonitorTimeout
    Timeout monitoring en minutes (défaut: 10)

.EXAMPLE
    .\deploy_medium_monitored.ps1
    # Déploiement complet avec nettoyage et monitoring

.EXAMPLE
    .\deploy_medium_monitored.ps1 -SkipCleanup -MonitorTimeout 15
    # Sans nettoyage, avec timeout étendu
#>

param(
    [switch]$SkipCleanup = $false,
    [int]$MonitorInterval = 10,
    [int]$MonitorTimeout = 10
)

# Configuration
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptPath
$composeProfile = Join-Path $projectRoot "configs\docker\profiles\medium.yml"
$monitorScript = Join-Path $scriptPath "monitor_medium.ps1"
$containerName = "myia-vllm-medium-qwen3"

# Fonction pour afficher avec couleurs
function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

# Fonction pour vérifier les prérequis
function Test-Prerequisites {
    Write-ColorOutput "`n🔍 Vérification des prérequis..." -Color Cyan
    
    # Docker
    try {
        $dockerVersion = docker --version
        Write-ColorOutput "   ✅ Docker: $dockerVersion" -Color Green
    }
    catch {
        Write-ColorOutput "   ❌ Docker non trouvé" -Color Red
        return $false
    }
    
    # Docker Compose
    try {
        $composeVersion = docker compose version
        Write-ColorOutput "   ✅ Docker Compose: $composeVersion" -Color Green
    }
    catch {
        Write-ColorOutput "   ❌ Docker Compose non trouvé" -Color Red
        return $false
    }
    
    # Fichiers de configuration
    if (-not (Test-Path $composeProfile)) {
        Write-ColorOutput "   ❌ Profil medium manquant: $composeProfile" -Color Red
        return $false
    }
    Write-ColorOutput "   ✅ Profil medium: $composeProfile" -Color Green
    
    # Fichier .env
    $envFile = Join-Path $projectRoot ".env"
    if (-not (Test-Path $envFile)) {
        Write-ColorOutput "   ⚠️  Fichier .env manquant: $envFile" -Color Yellow
        Write-ColorOutput "      Certaines variables devront être définies manuellement" -Color Yellow
    }
    else {
        Write-ColorOutput "   ✅ Fichier .env: $envFile" -Color Green
        
        # Vérifier token HuggingFace (sans l'afficher)
        $envContent = Get-Content $envFile -Raw
        if ($envContent -match "HUGGING_FACE_HUB_TOKEN\s*=\s*hf_\w+") {
            Write-ColorOutput "   ✅ Token HuggingFace présent" -Color Green
        }
        else {
            Write-ColorOutput "   ⚠️  Token HuggingFace non détecté dans .env" -Color Yellow
        }
    }
    
    # Script de monitoring
    if (-not (Test-Path $monitorScript)) {
        Write-ColorOutput "   ⚠️  Script monitoring manquant: $monitorScript" -Color Yellow
        Write-ColorOutput "      Monitoring automatique désactivé" -Color Yellow
    }
    else {
        Write-ColorOutput "   ✅ Script monitoring: $monitorScript" -Color Green
    }
    
    # GPUs NVIDIA
    try {
        $gpuInfo = nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader 2>$null
        if ($gpuInfo) {
            Write-ColorOutput "   ✅ GPUs NVIDIA:" -Color Green
            $gpuInfo -split "`n" | ForEach-Object {
                if ($_.Trim()) {
                    Write-ColorOutput "      $_" -Color White
                }
            }
        }
        else {
            Write-ColorOutput "   ⚠️  Aucun GPU NVIDIA détecté" -Color Yellow
        }
    }
    catch {
        Write-ColorOutput "   ⚠️  nvidia-smi non disponible" -Color Yellow
    }
    
    return $true
}

# En-tête
Write-ColorOutput "`n===============================================" -Color Cyan
Write-ColorOutput "🚀 DÉPLOIEMENT SERVICE MEDIUM - Qwen3-32B-AWQ" -Color Cyan
Write-ColorOutput "===============================================" -Color Cyan
Write-ColorOutput "Mission    : SDDD Mission 9" -Color White
Write-ColorOutput "Date       : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -Color White
Write-ColorOutput "Profil     : Medium (32B, 2 GPUs, 128k context)" -Color White
Write-ColorOutput "===============================================" -Color Cyan

# Vérifier prérequis
if (-not (Test-Prerequisites)) {
    Write-ColorOutput "`n❌ Prérequis non satisfaits - Arrêt du déploiement" -Color Red
    exit 1
}

# PHASE 1: Nettoyage
if (-not $SkipCleanup) {
    Write-ColorOutput "`n=== PHASE 1: Nettoyage des conteneurs existants ===" -Color Cyan
    
    try {
        $existing = docker ps -a --filter "name=$containerName" --format "{{.ID}}" 2>$null
        
        if ($existing) {
            Write-ColorOutput "📦 Conteneur existant détecté: $containerName" -Color Yellow
            Write-ColorOutput "🗑️  Nettoyage en cours..." -Color Yellow
            
            # Arrêt propre via docker compose
            docker compose -f $composeProfile --env-file $envFile down --remove-orphans 2>&1 | Out-Null
            
            Write-ColorOutput "✅ Nettoyage terminé" -Color Green
        }
        else {
            Write-ColorOutput "✅ Aucun conteneur existant à nettoyer" -Color Green
        }
    }
    catch {
        Write-ColorOutput "⚠️  Erreur lors du nettoyage: $_" -Color Yellow
        Write-ColorOutput "   Continuation du déploiement..." -Color Yellow
    }
}
else {
    Write-ColorOutput "`n=== PHASE 1: Nettoyage ignoré (SkipCleanup activé) ===" -Color Yellow
}

# PHASE 2: Déploiement
Write-ColorOutput "`n=== PHASE 2: Déploiement du service ===" -Color Cyan

Write-ColorOutput "📋 Configuration de déploiement:" -Color White
Write-ColorOutput "   Profil  : $composeProfile" -Color Gray
Write-ColorOutput "   Options : --build --force-recreate --detach" -Color Gray

Write-ColorOutput "`n🚀 Lancement du déploiement..." -Color Cyan

try {
    # Fichier .env
    $envFile = Join-Path $projectRoot ".env"
    
    # Déploiement avec docker compose
    $deployOutput = docker compose -f $composeProfile --env-file $envFile up -d --build --force-recreate 2>&1
    
    # Vérifier si le déploiement a réussi
    $containerExists = docker ps -a --filter "name=$containerName" --format "{{.ID}}" 2>$null
    
    if ($containerExists) {
        Write-ColorOutput "`n✅ Déploiement lancé avec succès" -Color Green
        Write-ColorOutput "📦 Conteneur: $containerName" -Color White
        Write-ColorOutput "🆔 ID: $containerExists" -Color White
        
        # Afficher quelques lignes de sortie docker compose
        Write-ColorOutput "`n📜 Sortie Docker Compose:" -Color Cyan
        $deployOutput | Select-Object -Last 5 | ForEach-Object {
            Write-ColorOutput "   $_" -Color Gray
        }
    }
    else {
        Write-ColorOutput "`n❌ Échec du déploiement - Conteneur non créé" -Color Red
        Write-ColorOutput "`n📜 Sortie Docker Compose complète:" -Color Red
        $deployOutput | ForEach-Object {
            Write-ColorOutput "   $_" -Color Red
        }
        exit 1
    }
}
catch {
    Write-ColorOutput "`n❌ Erreur lors du déploiement: $_" -Color Red
    exit 1
}

# Petite pause pour laisser le conteneur démarrer
Write-ColorOutput "`n⏳ Pause de 5 secondes avant monitoring..." -Color Yellow
Start-Sleep -Seconds 5

# PHASE 3: Monitoring
Write-ColorOutput "`n=== PHASE 3: Monitoring automatique ===" -Color Cyan

if (Test-Path $monitorScript) {
    Write-ColorOutput "🔍 Lancement du monitoring:" -Color White
    Write-ColorOutput "   Intervalle : $MonitorInterval secondes" -Color Gray
    Write-ColorOutput "   Timeout    : $MonitorTimeout minutes" -Color Gray
    Write-ColorOutput "   Script     : $monitorScript" -Color Gray
    
    Write-ColorOutput "`n" -Color White
    
    try {
        # Lancer le script de monitoring
        & $monitorScript -IntervalSeconds $MonitorInterval -TimeoutMinutes $MonitorTimeout
        
        $monitorExitCode = $LASTEXITCODE
        
        if ($monitorExitCode -eq 0) {
            Write-ColorOutput "`n🎉 ===============================================" -Color Green
            Write-ColorOutput "🎉 DÉPLOIEMENT RÉUSSI AVEC SUCCÈS" -Color Green
            Write-ColorOutput "🎉 ===============================================" -Color Green
            Write-ColorOutput "`n✅ Le service medium est opérationnel" -Color Green
            Write-ColorOutput "✅ État: HEALTHY" -Color Green
            Write-ColorOutput "`n📊 Informations de connexion:" -Color Cyan
            Write-ColorOutput "   Base URL : http://localhost:5002" -Color White
            Write-ColorOutput "   Health   : http://localhost:5002/health" -Color White
            Write-ColorOutput "   Models   : http://localhost:5002/v1/models" -Color White
            Write-ColorOutput "   Chat API : http://localhost:5002/v1/chat/completions" -Color White
            
            Write-ColorOutput "`n📚 Prochaines étapes:" -Color Cyan
            Write-ColorOutput "   1. Tester l'endpoint: curl http://localhost:5002/health" -Color White
            Write-ColorOutput "   2. Lister les modèles: curl http://localhost:5002/v1/models" -Color White
            Write-ColorOutput "   3. Tests tool calling: python tests/scripts/tests/test_qwen3_tool_calling.py" -Color White
            Write-ColorOutput "   4. Consulter docs: docs/deployment/MEDIUM_SERVICE.md" -Color White
            
            exit 0
        }
        else {
            Write-ColorOutput "`n❌ ===============================================" -Color Red
            Write-ColorOutput "❌ DÉPLOIEMENT ÉCHOUÉ" -Color Red
            Write-ColorOutput "❌ ===============================================" -Color Red
            Write-ColorOutput "`n⚠️  Le monitoring a détecté des problèmes" -Color Yellow
            Write-ColorOutput "    Code retour: $monitorExitCode" -Color Red
            
            Write-ColorOutput "`n🔍 Diagnostics suggérés:" -Color Yellow
            Write-ColorOutput "   1. Logs complets: docker logs $containerName" -Color White
            Write-ColorOutput "   2. Status GPU: nvidia-smi" -Color White
            Write-ColorOutput "   3. Vérifier .env: HUGGING_FACE_HUB_TOKEN, CUDA_VISIBLE_DEVICES" -Color White
            Write-ColorOutput "   4. Guide troubleshooting: docs/deployment/MEDIUM_SERVICE.md" -Color White
            
            exit 1
        }
    }
    catch {
        Write-ColorOutput "`n❌ Erreur lors du monitoring: $_" -Color Red
        Write-ColorOutput "📜 Logs disponibles via: docker logs $containerName" -Color Yellow
        exit 1
    }
}
else {
    Write-ColorOutput "⚠️  Script de monitoring non disponible" -Color Yellow
    Write-ColorOutput "✅ Déploiement lancé, mais monitoring manuel requis" -Color Yellow
    Write-ColorOutput "`n📋 Commandes de monitoring manuel:" -Color Cyan
    Write-ColorOutput "   docker ps --filter 'name=$containerName'" -Color White
    Write-ColorOutput "   docker logs -f $containerName" -Color White
    Write-ColorOutput "   curl http://localhost:5002/health" -Color White
    
    exit 0
}