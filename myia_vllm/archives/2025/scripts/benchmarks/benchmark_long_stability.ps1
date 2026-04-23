<#
.SYNOPSIS
    Benchmark de stabilité longue durée pour Qwen3 vLLM

.DESCRIPTION
    Script de benchmark automatisé pour tester la stabilité du service vLLM medium
    sur une durée étendue avec 20 requêtes espacées. Détecte memory leaks,
    dégradations de performance, et timeouts.
    
    Alternance requêtes:
    - Courtes (50-100 tokens): Réponses rapides
    - Longues (500-800 tokens): Génération étendue
    
    Métriques collectées:
    - TTFT, durée totale, tokens/sec par requête
    - Monitoring GPU (si -MonitorGPU): Utilization, VRAM, température
    - Détection anomalies: Dégradation TTFT, memory leaks, timeouts

.PARAMETER TotalRequests
    Nombre total de requêtes à exécuter (défaut: 20)

.PARAMETER IntervalSeconds
    Pause entre requêtes en secondes (défaut: 5, utiliser 90 pour ~30min totales)

.PARAMETER ApiUrl
    URL de l'API vLLM (défaut: http://localhost:5002/v1/chat/completions)

.PARAMETER OutputFile
    Chemin du fichier JSON de sortie pour les résultats

.PARAMETER MonitorGPU
    Si activé, lance nvidia-smi monitoring en parallèle toutes les 10s

.EXAMPLE
    .\benchmark_long_stability.ps1

.EXAMPLE
    .\benchmark_long_stability.ps1 -TotalRequests 20 -IntervalSeconds 5 -MonitorGPU

.EXAMPLE
    .\benchmark_long_stability.ps1 -TotalRequests 40 -IntervalSeconds 90

.NOTES
    Auteur: Roo Code
    Mission: 11 Phase 8 - Sous-tâche 2 (Phase 2.5)
    Prérequis: Service vLLM medium démarré et healthy
    API Key: Variable d'environnement VLLM_MEDIUM_API_KEY
    GPU Monitoring: Nécessite nvidia-smi (CUDA Toolkit)
#>

param(
    [int]$TotalRequests = 20,
    [int]$IntervalSeconds = 5,
    [string]$ApiUrl = "http://localhost:5002/v1/chat/completions",
    [string]$OutputFile = "myia_vllm/test_results/long_stability_benchmark_$(Get-Date -Format 'yyyyMMdd_HHmmss').json",
    [switch]$MonitorGPU
)

# ============================================================================
# CONFIGURATION
# ============================================================================

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Récupérer API Key
$ApiKey = $env:VLLM_MEDIUM_API_KEY
if (-not $ApiKey) {
    Write-Host "❌ ERREUR: Variable VLLM_MEDIUM_API_KEY non définie" -ForegroundColor Red
    exit 1
}

$Headers = @{
    "Content-Type" = "application/json"
    "Authorization" = "Bearer $ApiKey"
}

# Pattern de requêtes (cycle 4 requêtes)
$RequestPatterns = @(
    @{ type = "short"; content = "Explique la photosynthèse en 2 phrases"; max_tokens = 100 }
    @{ type = "long"; content = "Décris en détail le processus complet de développement logiciel Agile avec exemples"; max_tokens = 800 }
    @{ type = "short"; content = "Quelle est la capitale du Japon ?"; max_tokens = 50 }
    @{ type = "long"; content = "Analyse les avantages et inconvénients de React vs Vue.js avec code examples"; max_tokens = 900 }
)

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "  BENCHMARK STABILITÉ LONGUE DURÉE - Phase 2.5" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  • Total requêtes    : $TotalRequests"
Write-Host "  • Intervalle        : $IntervalSeconds secondes"
Write-Host "  • Durée estimée     : $([math]::Round($TotalRequests * $IntervalSeconds / 60, 1)) minutes"
Write-Host "  • API URL           : $ApiUrl"
Write-Host "  • Output File       : $OutputFile"
Write-Host "  • GPU Monitoring    : $MonitorGPU"
Write-Host "  • Date              : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

# ============================================================================
# VALIDATION API
# ============================================================================

Write-Host "[1/4] Validation disponibilité API..." -ForegroundColor Cyan
try {
    $healthUrl = $ApiUrl -replace '/v1/chat/completions', '/health'
    $healthCheck = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 10
    Write-Host "✅ API accessible" -ForegroundColor Green
} catch {
    Write-Host "❌ API non accessible: $_" -ForegroundColor Red
    exit 1
}

# ============================================================================
# INITIALISATION GPU MONITORING (si activé)
# ============================================================================

$GpuMonitoring = @()
$MonitoringJob = $null

if ($MonitorGPU) {
    Write-Host ""
    Write-Host "[2/4] Initialisation GPU monitoring..." -ForegroundColor Cyan
    
    # Vérifier nvidia-smi disponible
    try {
        $nvidiaTest = nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "⚠️  nvidia-smi non disponible, monitoring GPU désactivé" -ForegroundColor Yellow
            $MonitorGPU = $false
        } else {
            Write-Host "✅ nvidia-smi détecté, monitoring GPU activé" -ForegroundColor Green
            
            # Lancer monitoring en background
            $MonitoringJob = Start-Job -ScriptBlock {
                param($Interval)
                $results = @()
                while ($true) {
                    try {
                        $timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
                        $gpuUtil = nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | Select-Object -First 1
                        $vramUsed = nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | Select-Object -First 1
                        $vramTotal = nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | Select-Object -First 1
                        $temp = nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits | Select-Object -First 1
                        
                        $results += @{
                            timestamp = $timestamp
                            gpu_utilization_pct = [int]$gpuUtil
                            vram_used_mb = [int]$vramUsed
                            vram_total_mb = [int]$vramTotal
                            temperature_c = [int]$temp
                        }
                    } catch {
                        # Ignorer erreurs GPU monitoring
                    }
                    Start-Sleep -Seconds $Interval
                }
                return $results
            } -ArgumentList 10  # Monitoring toutes les 10s
            
            Write-Host "   Monitoring démarré (échantillonnage toutes les 10s)" -ForegroundColor Gray
        }
    } catch {
        Write-Host "⚠️  Erreur initialisation GPU monitoring: $_" -ForegroundColor Yellow
        $MonitorGPU = $false
    }
} else {
    Write-Host ""
    Write-Host "[2/4] GPU monitoring désactivé (utiliser -MonitorGPU pour activer)" -ForegroundColor Cyan
}

# ============================================================================
# EXÉCUTION BENCHMARKS
# ============================================================================

Write-Host ""
Write-Host "[3/4] Exécution benchmark ($TotalRequests requêtes)..." -ForegroundColor Cyan
Write-Host ""

$Requests = @()
$StartTimeBenchmark = Get-Date

for ($i = 1; $i -le $TotalRequests; $i++) {
    # Sélectionner pattern (cycle de 4)
    $patternIndex = ($i - 1) % $RequestPatterns.Count
    $pattern = $RequestPatterns[$patternIndex]
    
    $progress = [math]::Round(($i / $TotalRequests) * 100)
    $eta = [math]::Round((($TotalRequests - $i) * $IntervalSeconds) / 60, 1)
    
    Write-Host "  [$i/$TotalRequests] ($progress%) - Type: $($pattern.type) | ETA: $eta min" -ForegroundColor Cyan
    
    # Préparer payload
    $payload = @{
        model = "Qwen/Qwen3-32B-AWQ"
        messages = @(
            @{
                role = "user"
                content = $pattern.content
            }
        )
        temperature = 0.7
        max_tokens = $pattern.max_tokens
    } | ConvertTo-Json -Depth 5
    
    # Exécuter requête
    $requestStart = Get-Date
    $requestTimestamp = $requestStart.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $status = 200
    $errorMsg = $null
    
    try {
        $response = Invoke-RestMethod -Uri $ApiUrl -Method Post -Headers $Headers -Body $payload -TimeoutSec 60
        $requestEnd = Get-Date
        $duration = ($requestEnd - $requestStart).TotalMilliseconds
        
        # Extraire métriques
        $tokensGenerated = $response.usage.completion_tokens
        $tokensPerSec = if ($duration -gt 0) { [math]::Round(($tokensGenerated / $duration) * 1000, 2) } else { 0 }
        
        # Approximation TTFT (pas de streaming, donc TTFT ≈ durée totale)
        $ttft = [int]$duration
        
        Write-Host "     ✅ Complété: TTFT=${ttft}ms | Tokens=$tokensGenerated | Tok/s=$tokensPerSec" -ForegroundColor Green
        
    } catch {
        $requestEnd = Get-Date
        $duration = ($requestEnd - $requestStart).TotalMilliseconds
        $status = if ($_.Exception.Response) { $_.Exception.Response.StatusCode.value__ } else { 500 }
        $errorMsg = $_.Exception.Message
        $tokensGenerated = 0
        $tokensPerSec = 0
        $ttft = [int]$duration
        
        Write-Host "     ❌ Erreur: $errorMsg (Status: $status)" -ForegroundColor Red
    }
    
    # Enregistrer résultat
    $Requests += @{
        request_id = $i
        type = $pattern.type
        ttft_ms = $ttft
        total_duration_ms = [int]$duration
        tokens = $tokensGenerated
        tokens_per_sec = $tokensPerSec
        status = $status
        timestamp = $requestTimestamp
        error = $errorMsg
    }
    
    # Pause avant prochaine requête (sauf dernière)
    if ($i -lt $TotalRequests) {
        Start-Sleep -Seconds $IntervalSeconds
    }
}

$EndTimeBenchmark = Get-Date
$TotalDurationMinutes = [math]::Round(($EndTimeBenchmark - $StartTimeBenchmark).TotalMinutes, 2)

Write-Host ""
Write-Host "✅ Toutes les requêtes exécutées ($TotalDurationMinutes minutes)" -ForegroundColor Green

# ============================================================================
# ARRÊT GPU MONITORING
# ============================================================================

if ($MonitorGPU -and $MonitoringJob) {
    Write-Host ""
    Write-Host "Arrêt GPU monitoring..." -ForegroundColor Cyan
    Stop-Job -Job $MonitoringJob
    $GpuMonitoring = Receive-Job -Job $MonitoringJob
    Remove-Job -Job $MonitoringJob
    Write-Host "✅ $($GpuMonitoring.Count) échantillons GPU collectés" -ForegroundColor Green
}

# ============================================================================
# ANALYSE ANOMALIES
# ============================================================================

Write-Host ""
Write-Host "[4/4] Analyse tendances et détection anomalies..." -ForegroundColor Cyan

# Calculer moyennes par tranches
$Requests1_5 = $Requests | Select-Object -First 5
$Requests16_20 = $Requests | Select-Object -Last 5

$TtftAvg1_5 = [int]($Requests1_5 | Where-Object { $_.status -eq 200 } | Measure-Object -Property ttft_ms -Average).Average
$TtftAvg16_20 = [int]($Requests16_20 | Where-Object { $_.status -eq 200 } | Measure-Object -Property ttft_ms -Average).Average

# Dégradation TTFT
$degradationPct = if ($TtftAvg1_5 -gt 0) {
    [math]::Round((($TtftAvg16_20 - $TtftAvg1_5) / $TtftAvg1_5) * 100, 1)
} else { 0 }

# VRAM évolution
$VramStart = 0
$VramEnd = 0
$VramIncrease = 0

if ($GpuMonitoring.Count -gt 0) {
    $VramStart = ($GpuMonitoring | Select-Object -First 3 | Measure-Object -Property vram_used_mb -Average).Average
    $VramEnd = ($GpuMonitoring | Select-Object -Last 3 | Measure-Object -Property vram_used_mb -Average).Average
    $VramIncrease = [int]($VramEnd - $VramStart)
}

# Timeouts et erreurs
$Timeouts = ($Requests | Where-Object { $_.total_duration_ms -gt 60000 }).Count
$Errors500 = ($Requests | Where-Object { $_.status -eq 500 }).Count

# Statut stabilité
$StabilityStatus = "stable"
$Alerts = @()

if ($degradationPct -gt 20) {
    $StabilityStatus = "degraded"
    $Alerts += "Dégradation TTFT > 20% ($degradationPct%)"
}

if ($VramIncrease -gt 500) {
    $StabilityStatus = "memory_leak"
    $Alerts += "Augmentation VRAM > 500MB ($VramIncrease MB)"
}

if ($Timeouts -gt 2) {
    $StabilityStatus = "unstable"
    $Alerts += "Trop de timeouts ($Timeouts)"
}

if ($Errors500 -gt 1) {
    $StabilityStatus = "unstable"
    $Alerts += "Erreurs HTTP 500 détectées ($Errors500)"
}

# Créer objet analyse
$Analysis = @{
    ttft_avg_requests_1_5 = $TtftAvg1_5
    ttft_avg_requests_16_20 = $TtftAvg16_20
    degradation_pct = $degradationPct
    vram_start_mb = [int]$VramStart
    vram_end_mb = [int]$VramEnd
    vram_increase_mb = $VramIncrease
    timeouts = $Timeouts
    errors_500 = $Errors500
    stability_status = $StabilityStatus
}

# Afficher résultats analyse
Write-Host ""
Write-Host "Analyse Tendances:" -ForegroundColor Yellow
Write-Host "  • TTFT moyen (req 1-5)    : $TtftAvg1_5 ms"
Write-Host "  • TTFT moyen (req 16-20)  : $TtftAvg16_20 ms"
Write-Host "  • Dégradation             : $degradationPct%"
if ($MonitorGPU) {
    Write-Host "  • VRAM début              : $([int]$VramStart) MB"
    Write-Host "  • VRAM fin                : $([int]$VramEnd) MB"
    Write-Host "  • Augmentation VRAM       : $VramIncrease MB"
}
Write-Host "  • Timeouts                : $Timeouts"
Write-Host "  • Erreurs 500             : $Errors500"
Write-Host ""

if ($Alerts.Count -gt 0) {
    Write-Host "⚠️  ALERTES DÉTECTÉES:" -ForegroundColor Yellow
    foreach ($alert in $Alerts) {
        Write-Host "   - $alert" -ForegroundColor Red
    }
} else {
    Write-Host "✅ Aucune anomalie détectée - Système STABLE" -ForegroundColor Green
}

Write-Host ""
Write-Host "Statut Stabilité: $($StabilityStatus.ToUpper())" -ForegroundColor $(if ($StabilityStatus -eq "stable") { "Green" } else { "Red" })

# ============================================================================
# SAUVEGARDE RÉSULTATS
# ============================================================================

Write-Host ""
Write-Host "Sauvegarde résultats..." -ForegroundColor Cyan

# Créer répertoire
$OutputDir = Split-Path -Parent $OutputFile
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# Structure finale
$Results = @{
    test_date = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    config = "chunked_only_safe"
    total_requests = $TotalRequests
    interval_seconds = $IntervalSeconds
    total_duration_minutes = $TotalDurationMinutes
    requests = $Requests
    gpu_monitoring = if ($MonitorGPU) { $GpuMonitoring } else { @() }
    analysis = $Analysis
    alerts = $Alerts
}

# Sauvegarder
$Results | ConvertTo-Json -Depth 10 | Out-File -FilePath $OutputFile -Encoding UTF8

Write-Host "✅ Résultats sauvegardés: $OutputFile" -ForegroundColor Green

# ============================================================================
# AFFICHAGE RÉSUMÉ
# ============================================================================

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "  RÉSUMÉ BENCHMARK STABILITÉ LONGUE DURÉE" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Métriques Globales:" -ForegroundColor Yellow
Write-Host "  • Requêtes exécutées      : $TotalRequests"
Write-Host "  • Requêtes réussies       : $(($Requests | Where-Object { $_.status -eq 200 }).Count)"
Write-Host "  • Durée totale            : $TotalDurationMinutes minutes"
Write-Host "  • TTFT moyen global       : $([int](($Requests | Where-Object { $_.status -eq 200 } | Measure-Object -Property ttft_ms -Average).Average)) ms"
Write-Host "  • Tokens/sec moyen        : $([math]::Round(($Requests | Where-Object { $_.status -eq 200 } | Measure-Object -Property tokens_per_sec -Average).Average, 2))"
Write-Host ""
Write-Host "Stabilité:" -ForegroundColor Yellow
Write-Host "  • Dégradation TTFT        : $degradationPct% (seuil: 20%)"
Write-Host "  • Augmentation VRAM       : $VramIncrease MB (seuil: 500MB)"
Write-Host "  • Timeouts                : $Timeouts (seuil: 2)"
Write-Host "  • Erreurs 500             : $Errors500 (seuil: 1)"
Write-Host "  • Statut                  : $($StabilityStatus.ToUpper())"
Write-Host ""

if ($Alerts.Count -gt 0) {
    Write-Host "⚠️  $($Alerts.Count) alerte(s) détectée(s)" -ForegroundColor Red
} else {
    Write-Host "✅ Système stable - Aucune anomalie détectée" -ForegroundColor Green
}

Write-Host ""
Write-Host "Benchmark stabilité longue durée complété avec succès! 🎉" -ForegroundColor Green
Write-Host ""