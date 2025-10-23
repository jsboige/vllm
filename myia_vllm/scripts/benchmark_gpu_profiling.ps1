<#
.SYNOPSIS
    Benchmark GPU Profiling - Monitoring continu GPU/VRAM/CPU pendant benchmarks vLLM

.DESCRIPTION
    Script PowerShell pour Phase 2.6 - Mission 11 Phase 8
    
    Fonctionnalités :
    - Monitoring GPU continu via nvidia-smi (utilization, VRAM, température, power)
    - Monitoring CPU/RAM via Get-Counter
    - Génération requêtes API continues (alternance court/long)
    - Corrélation métriques GPU avec états API (IDLE vs PROCESSING)
    - Détection alertes (VRAM >95%, température >85°C, GPU util <50%)
    - Export JSON avec statistiques détaillées

.PARAMETER DurationMinutes
    Durée monitoring en minutes (défaut: 5 = 300 échantillons à 1s interval)

.PARAMETER SamplingIntervalSeconds
    Fréquence échantillonnage en secondes (défaut: 1s)

.PARAMETER SimultaneousRequests
    Nombre requêtes parallèles (1-3, défaut: 1)

.PARAMETER ApiUrl
    URL endpoint API vLLM (défaut: http://localhost:5002/v1/chat/completions)

.PARAMETER OutputFile
    Chemin fichier JSON sortie (défaut: test_results/gpu_profiling_[timestamp].json)

.EXAMPLE
    .\benchmark_gpu_profiling.ps1 -DurationMinutes 5 -SimultaneousRequests 1
    
.EXAMPLE
    $env:VLLM_MEDIUM_API_KEY = "YOUR_API_KEY"
    .\benchmark_gpu_profiling.ps1 -DurationMinutes 10 -SamplingIntervalSeconds 2

.NOTES
    Auteur: Roo Code
    Version: 1.0
    Date: 2025-10-22
    Prérequis: nvidia-smi installé, API vLLM accessible
#>

param(
    [int]$DurationMinutes = 5,
    [int]$SamplingIntervalSeconds = 1,
    [int]$SimultaneousRequests = 1,
    [string]$ApiUrl = "http://localhost:5002/v1/chat/completions",
    [string]$OutputFile = ""
)

# Configuration
$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

# Générer nom fichier sortie si non fourni
if ([string]::IsNullOrEmpty($OutputFile)) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputFile = "myia_vllm/test_results/gpu_profiling_$timestamp.json"
}

# Créer répertoire si nécessaire
$outputDir = Split-Path $OutputFile -Parent
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

Write-Host "╔═══════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║          BENCHMARK GPU PROFILING - Phase 2.6                     ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  - Durée monitoring: $DurationMinutes minutes" -ForegroundColor White
Write-Host "  - Intervalle échantillonnage: $SamplingIntervalSeconds seconde(s)" -ForegroundColor White
Write-Host "  - Requêtes simultanées: $SimultaneousRequests" -ForegroundColor White
Write-Host "  - API URL: $ApiUrl" -ForegroundColor White
Write-Host "  - Fichier sortie: $OutputFile" -ForegroundColor White
Write-Host ""

# Vérifier nvidia-smi disponible
Write-Host "[1/7] Vérification nvidia-smi..." -ForegroundColor Yellow
try {
    $nvidiaSmiTest = nvidia-smi --query-gpu=name --format=csv,noheader,nounits 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "nvidia-smi non disponible"
    }
    Write-Host "  ✓ nvidia-smi opérationnel" -ForegroundColor Green
    Write-Host "  GPU détecté: $nvidiaSmiTest" -ForegroundColor Gray
} catch {
    Write-Host "  ✗ ERREUR: nvidia-smi non trouvé" -ForegroundColor Red
    Write-Host "  Vérifiez CUDA/drivers NVIDIA installés" -ForegroundColor Red
    exit 1
}

# Vérifier API Key
Write-Host "`n[2/7] Vérification API Key..." -ForegroundColor Yellow
$apiKey = $env:VLLM_MEDIUM_API_KEY
if ([string]::IsNullOrEmpty($apiKey)) {
    Write-Host "  ✗ ERREUR: Variable VLLM_MEDIUM_API_KEY non définie" -ForegroundColor Red
    Write-Host "  Définir avec: `$env:VLLM_MEDIUM_API_KEY = 'YOUR_KEY'" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ API Key trouvée (${apiKey.Substring(0, [Math]::Min(8, $apiKey.Length))}...)" -ForegroundColor Green

# Test connectivité API
Write-Host "`n[3/7] Test connectivité API..." -ForegroundColor Yellow
$headers = @{
    "Authorization" = "Bearer $apiKey"
    "Content-Type" = "application/json"
}
try {
    $testBody = @{
        model = "qwen3"
        messages = @(
            @{
                role = "user"
                content = "Test"
            }
        )
        max_tokens = 10
        temperature = 0.7
    } | ConvertTo-Json -Depth 10

    $testResponse = Invoke-RestMethod -Uri $ApiUrl -Method Post -Headers $headers -Body $testBody -TimeoutSec 30
    Write-Host "  ✓ API accessible et fonctionnelle" -ForegroundColor Green
} catch {
    Write-Host "  ✗ ERREUR: API non accessible" -ForegroundColor Red
    Write-Host "  Détails: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Initialisation structures données
Write-Host "`n[4/7] Initialisation monitoring..." -ForegroundColor Yellow
$samples = @()
$totalSamples = $DurationMinutes * 60 / $SamplingIntervalSeconds
$currentSample = 0
$startTime = Get-Date

Write-Host "  - Échantillons attendus: $totalSamples" -ForegroundColor Gray
Write-Host "  - Début: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Gray

# Prompts pour alternance court/long
$shortPrompts = @(
    "Explique en 2 phrases ce qu'est l'IA.",
    "Donne 3 avantages du cloud computing.",
    "Quelle est la capitale de la France?"
)

$longPrompts = @(
    "Décris en détail (800 mots) les implications éthiques de l'intelligence artificielle dans le domaine médical, en abordant la vie privée, la responsabilité, et l'équité.",
    "Explique le fonctionnement des réseaux de neurones convolutifs (CNN) avec exemples concrets d'applications en vision par ordinateur. Détaille l'architecture typique sur 900 mots.",
    "Analyse comparative approfondie (850 mots) entre architectures transformer et LSTM pour traitement langage naturel, avec avantages, limitations, et cas d'usage."
)

# Variables pour corrélation activité API
$currentApiState = "IDLE"
$apiRequestStart = $null

# Fonction pour récupérer métriques GPU
function Get-GpuMetrics {
    try {
        $gpuData = nvidia-smi --query-gpu=timestamp,index,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits
        
        if ($gpuData -match '^(.+?), (\d+), (\d+), (\d+), (\d+), (\d+), ([\d.]+)$') {
            return @{
                timestamp = $matches[1]
                gpu_index = [int]$matches[2]
                gpu_utilization = [int]$matches[3]
                vram_used_mb = [int]$matches[4]
                vram_total_mb = [int]$matches[5]
                temperature_c = [int]$matches[6]
                power_draw_w = [decimal]$matches[7]
            }
        }
        return $null
    } catch {
        Write-Host "  ⚠ Erreur lecture nvidia-smi: $($_.Exception.Message)" -ForegroundColor Yellow
        return $null
    }
}

# Fonction pour récupérer métriques CPU/RAM
function Get-SystemMetrics {
    try {
        $cpuCounter = Get-Counter '\Processor(_Total)\% Processor Time' -ErrorAction Stop
        $ramCounter = Get-Counter '\Memory\Available MBytes' -ErrorAction Stop
        
        $cpuUtil = [Math]::Round($cpuCounter.CounterSamples[0].CookedValue, 2)
        $ramAvailableMb = [int]$ramCounter.CounterSamples[0].CookedValue
        
        # Calculer RAM totale (approximatif via WMI)
        $ramTotalMb = [Math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1MB)
        $ramUsedMb = $ramTotalMb - $ramAvailableMb
        
        return @{
            cpu_utilization_pct = $cpuUtil
            ram_used_mb = $ramUsedMb
            ram_available_mb = $ramAvailableMb
            ram_total_mb = $ramTotalMb
        }
    } catch {
        Write-Host "  ⚠ Erreur lecture compteurs système: $($_.Exception.Message)" -ForegroundColor Yellow
        return @{
            cpu_utilization_pct = 0
            ram_used_mb = 0
            ram_available_mb = 0
            ram_total_mb = 0
        }
    }
}

# Fonction pour générer requête API (asynchrone)
$global:activeRequests = @()
function Start-ApiRequest {
    param([bool]$IsLong)
    
    $promptList = if ($IsLong) { $longPrompts } else { $shortPrompts }
    $prompt = $promptList | Get-Random
    $maxTokens = if ($IsLong) { 900 } else { 100 }
    
    $requestBody = @{
        model = "qwen3"
        messages = @(
            @{
                role = "user"
                content = $prompt
            }
        )
        max_tokens = $maxTokens
        temperature = 0.7
        stream = $false
    } | ConvertTo-Json -Depth 10
    
    $requestStart = Get-Date
    
    # Lancer requête en background (PowerShell Job)
    $job = Start-Job -ScriptBlock {
        param($Url, $Headers, $Body)
        try {
            $response = Invoke-RestMethod -Uri $Url -Method Post -Headers $Headers -Body $Body -TimeoutSec 120
            return @{
                success = $true
                ttft_ms = $null
                tokens = $response.usage.completion_tokens
                error = $null
            }
        } catch {
            return @{
                success = $false
                ttft_ms = $null
                tokens = 0
                error = $_.Exception.Message
            }
        }
    } -ArgumentList $ApiUrl, $headers, $requestBody
    
    $global:activeRequests += @{
        job = $job
        start_time = $requestStart
        is_long = $IsLong
    }
}

# Boucle monitoring principale
Write-Host "`n[5/7] Démarrage monitoring GPU + génération requêtes..." -ForegroundColor Yellow
Write-Host "  Progression:" -ForegroundColor Gray

$requestCounter = 0
$nextRequestTime = $startTime

while ($currentSample -lt $totalSamples) {
    $loopStart = Get-Date
    
    # Récupérer métriques GPU
    $gpuMetrics = Get-GpuMetrics
    
    # Récupérer métriques système
    $systemMetrics = Get-SystemMetrics
    
    # Déterminer état API
    $hasActiveRequests = ($global:activeRequests | Where-Object { $_.job.State -eq 'Running' }).Count -gt 0
    $apiState = if ($hasActiveRequests) { "PROCESSING" } else { "IDLE" }
    
    # Créer échantillon
    if ($gpuMetrics) {
        $sample = @{
            timestamp = (Get-Date).ToString("o")
            gpu_utilization_pct = $gpuMetrics.gpu_utilization
            vram_used_mb = $gpuMetrics.vram_used_mb
            vram_total_mb = $gpuMetrics.vram_total_mb
            vram_used_pct = [Math]::Round(($gpuMetrics.vram_used_mb / $gpuMetrics.vram_total_mb) * 100, 2)
            temperature_c = $gpuMetrics.temperature_c
            power_draw_w = $gpuMetrics.power_draw_w
            cpu_utilization_pct = $systemMetrics.cpu_utilization_pct
            ram_used_mb = $systemMetrics.ram_used_mb
            api_state = $apiState
        }
        
        $samples += $sample
    }
    
    # Lancer nouvelle requête si interval atteint et pas trop de requêtes actives
    $activeCount = ($global:activeRequests | Where-Object { $_.job.State -eq 'Running' }).Count
    if ($loopStart -ge $nextRequestTime -and $activeCount -lt $SimultaneousRequests) {
        $isLongRequest = ($requestCounter % 2) -eq 1  # Alterner court/long
        Start-ApiRequest -IsLong $isLongRequest
        $requestCounter++
        $nextRequestTime = $loopStart.AddSeconds(10)  # Nouvelle requête toutes les 10s
    }
    
    # Nettoyer jobs terminés
    $global:activeRequests = $global:activeRequests | Where-Object { $_.job.State -eq 'Running' }
    
    $currentSample++
    
    # Progress bar
    if ($currentSample % 10 -eq 0 -or $currentSample -eq $totalSamples) {
        $percentComplete = [Math]::Round(($currentSample / $totalSamples) * 100, 1)
        Write-Progress -Activity "Monitoring GPU" -Status "$percentComplete% - Échantillon $currentSample/$totalSamples - Requêtes actives: $activeCount" -PercentComplete $percentComplete
    }
    
    # Attendre interval avant prochain échantillon
    $elapsed = ((Get-Date) - $loopStart).TotalSeconds
    $sleepTime = [Math]::Max(0, $SamplingIntervalSeconds - $elapsed)
    if ($sleepTime -gt 0) {
        Start-Sleep -Seconds $sleepTime
    }
}

Write-Progress -Activity "Monitoring GPU" -Completed

# Nettoyer jobs restants
Write-Host "`n[6/7] Finalisation (attente jobs en cours)..." -ForegroundColor Yellow
$global:activeRequests | ForEach-Object {
    Wait-Job -Job $_.job -Timeout 30 | Out-Null
    Remove-Job -Job $_.job -Force
}

# Calculer statistiques
Write-Host "`n[7/7] Calcul statistiques..." -ForegroundColor Yellow

$gpuUtilValues = $samples | ForEach-Object { $_.gpu_utilization_pct }
$vramUsedValues = $samples | ForEach-Object { $_.vram_used_mb }
$tempValues = $samples | ForEach-Object { $_.temperature_c }
$powerValues = $samples | ForEach-Object { $_.power_draw_w }
$cpuValues = $samples | ForEach-Object { $_.cpu_utilization_pct }
$ramValues = $samples | ForEach-Object { $_.ram_used_mb }

function Get-Stats {
    param([array]$Values)
    
    if ($Values.Count -eq 0) {
        return @{
            avg = 0
            max = 0
            min = 0
            stddev = 0
        }
    }
    
    $avg = ($Values | Measure-Object -Average).Average
    $max = ($Values | Measure-Object -Maximum).Maximum
    $min = ($Values | Measure-Object -Minimum).Minimum
    
    # Calcul écart-type
    $variance = ($Values | ForEach-Object { [Math]::Pow($_ - $avg, 2) } | Measure-Object -Average).Average
    $stddev = [Math]::Sqrt($variance)
    
    return @{
        avg = [Math]::Round($avg, 2)
        max = $max
        min = $min
        stddev = [Math]::Round($stddev, 2)
    }
}

$gpuStats = Get-Stats -Values $gpuUtilValues
$vramStats = Get-Stats -Values $vramUsedValues
$tempStats = Get-Stats -Values $tempValues
$powerStats = Get-Stats -Values $powerValues
$cpuStats = Get-Stats -Values $cpuValues
$ramStats = Get-Stats -Values $ramValues

$statistics = @{
    gpu = @{
        utilization_avg = $gpuStats.avg
        utilization_max = $gpuStats.max
        utilization_min = $gpuStats.min
        utilization_stddev = $gpuStats.stddev
        vram_used_avg_mb = $vramStats.avg
        vram_used_max_mb = $vramStats.max
        vram_used_min_mb = $vramStats.min
        temperature_avg_c = $tempStats.avg
        temperature_max_c = $tempStats.max
        power_draw_avg_w = $powerStats.avg
    }
    cpu = @{
        utilization_avg = $cpuStats.avg
        utilization_max = $cpuStats.max
        utilization_min = $cpuStats.min
    }
    ram = @{
        used_avg_mb = $ramStats.avg
        used_max_mb = $ramStats.max
        used_min_mb = $ramStats.min
    }
}

# Détection alertes
$alerts = @()

if ($gpuStats.avg -lt 50) {
    $alerts += @{
        type = "GPU_UNDERUTILIZATION"
        severity = "WARNING"
        message = "GPU utilization moyenne < 50% ($($gpuStats.avg)%) - Sous-utilisation détectée"
    }
}

if ($gpuStats.max -gt 98) {
    $alerts += @{
        type = "GPU_SATURATION"
        severity = "WARNING"
        message = "GPU utilization max > 98% ($($gpuStats.max)%) - Saturation détectée"
    }
}

if ($vramStats.max -gt 23000) {
    $alerts += @{
        type = "VRAM_HIGH"
        severity = "CRITICAL"
        message = "VRAM max > 23000 MB ($($vramStats.max)MB) - Risque OOM (95% des 24GB)"
    }
}

if ($tempStats.max -gt 85) {
    $alerts += @{
        type = "TEMPERATURE_HIGH"
        severity = "CRITICAL"
        message = "Température max > 85°C ($($tempStats.max)°C) - Alerte thermique"
    }
}

if ($powerStats.avg -gt 250) {
    $alerts += @{
        type = "POWER_HIGH"
        severity = "WARNING"
        message = "Power draw moyen > 250W ($($powerStats.avg)W) - Consommation excessive"
    }
}

# Construire objet JSON final
$result = @{
    test_date = $startTime.ToString("o")
    config = "chunked_only_safe"
    duration_minutes = $DurationMinutes
    sampling_interval_seconds = $SamplingIntervalSeconds
    total_samples = $samples.Count
    samples = $samples
    statistics = $statistics
    alerts = $alerts
}

# Sauvegarder JSON
$jsonOutput = $result | ConvertTo-Json -Depth 10
$jsonOutput | Out-File -FilePath $OutputFile -Encoding utf8

Write-Host "`n╔═══════════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║                    BENCHMARK TERMINÉ                              ║" -ForegroundColor Green
Write-Host "╚═══════════════════════════════════════════════════════════════════╝" -ForegroundColor Green

Write-Host "`nStatistiques GPU:" -ForegroundColor Yellow
Write-Host "  - Utilization: $($gpuStats.avg)% (min: $($gpuStats.min)%, max: $($gpuStats.max)%)" -ForegroundColor White
Write-Host "  - VRAM: $($vramStats.avg)MB avg (max: $($vramStats.max)MB)" -ForegroundColor White
Write-Host "  - Température: $($tempStats.avg)°C avg (max: $($tempStats.max)°C)" -ForegroundColor White
Write-Host "  - Power: $($powerStats.avg)W avg" -ForegroundColor White

Write-Host "`nStatistiques Système:" -ForegroundColor Yellow
Write-Host "  - CPU: $($cpuStats.avg)% avg (max: $($cpuStats.max)%)" -ForegroundColor White
Write-Host "  - RAM: $($ramStats.avg)MB avg (max: $($ramStats.max)MB)" -ForegroundColor White

if ($alerts.Count -gt 0) {
    Write-Host "`nAlertes détectées ($($alerts.Count)):" -ForegroundColor Red
    foreach ($alert in $alerts) {
        $color = if ($alert.severity -eq "CRITICAL") { "Red" } else { "Yellow" }
        Write-Host "  ⚠ [$($alert.type)] $($alert.message)" -ForegroundColor $color
    }
} else {
    Write-Host "`n✓ Aucune alerte détectée" -ForegroundColor Green
}

Write-Host "`nFichier sauvegardé: $OutputFile" -ForegroundColor Cyan
Write-Host "Échantillons collectés: $($samples.Count)" -ForegroundColor Gray
Write-Host ""