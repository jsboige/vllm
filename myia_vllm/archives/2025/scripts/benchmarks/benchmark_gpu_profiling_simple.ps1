<#
.SYNOPSIS
    Script simplifié de profiling GPU pour Mission 11 Phase 8
.DESCRIPTION
    Collecte métriques GPU pendant 5 minutes avec requêtes API concurrentes
#>

param(
    [int]$DurationMinutes = 5,
    [int]$SamplingIntervalSeconds = 5
)

$ErrorActionPreference = "Continue"
$apiKey = $env:VLLM_API_KEY_MEDIUM
$apiUrl = "http://localhost:5002/v1/chat/completions"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outputJson = "myia_vllm/test_results/gpu_profiling_$timestamp.json"
$outputMd = "myia_vllm/test_results/GPU_PROFILING_REPORT_$timestamp.md"

# Créer répertoire
New-Item -ItemType Directory -Path "myia_vllm/test_results" -Force | Out-Null

Write-Host "`n╔═══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     PROFILING GPU SIMPLIFIÉ - Mission 11 Phase 8            ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════════════════╝`n" -ForegroundColor Cyan

Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Durée: $DurationMinutes minutes" -ForegroundColor White
Write-Host "  Intervalle: $SamplingIntervalSeconds secondes" -ForegroundColor White
Write-Host "  Outputs: $outputJson, $outputMd`n" -ForegroundColor White

# Fonction requête API en arrière-plan
function Send-BackgroundRequest {
    param([string]$prompt)
    
    $headers = @{
        "Authorization" = "Bearer $apiKey"
        "Content-Type" = "application/json"
    }
    
    $body = @{
        model = "Qwen/Qwen3-32B-AWQ"
        messages = @(@{role = "user"; content = $prompt})
        max_tokens = 100
        temperature = 0.7
    } | ConvertTo-Json -Depth 10
    
    try {
        $response = Invoke-RestMethod -Uri $apiUrl -Method Post -Headers $headers -Body $body -TimeoutSec 60
        Write-Host "  ✓ Requête API réussie" -ForegroundColor Green
    } catch {
        Write-Host "  ⚠ Requête API échouée: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# Collecter métriques GPU
$samples = @()
$totalSamples = ($DurationMinutes * 60) / $SamplingIntervalSeconds
$startTime = Get-Date

Write-Host "[1/3] Démarrage monitoring GPU ($totalSamples échantillons)...`n" -ForegroundColor Yellow

# Lancer quelques requêtes en arrière-plan
$prompts = @(
    "Explique brièvement l'IA en 50 mots",
    "Décris les avantages du cloud computing",
    "Quelle est l'importance de la cybersécurité?",
    "Explique le machine learning simplement"
)

for ($i = 0; $i -lt $totalSamples; $i++) {
    $elapsed = ((Get-Date) - $startTime).TotalSeconds
    
    # Lancer requête API tous les 4 échantillons
    if ($i % 4 -eq 0 -and $i -gt 0) {
        $promptIndex = $i % $prompts.Count
        Write-Host "  Lancement requête API #$($i/4)..." -ForegroundColor Cyan
        Start-Job -ScriptBlock {
            param($url, $key, $prompt)
            $headers = @{"Authorization" = "Bearer $key"; "Content-Type" = "application/json"}
            $body = @{model = "Qwen/Qwen3-32B-AWQ"; messages = @(@{role = "user"; content = $prompt}); max_tokens = 100} | ConvertTo-Json
            Invoke-RestMethod -Uri $url -Method Post -Headers $headers -Body $body -TimeoutSec 60
        } -ArgumentList $apiUrl, $apiKey, $prompts[$promptIndex] | Out-Null
    }
    
    # Collecter métriques GPU
    try {
        $gpuRaw = nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader,nounits
        
        $gpuMetrics = @()
        foreach ($line in $gpuRaw) {
            if ($line -match '(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)') {
                $gpuMetrics += @{
                    index = [int]$matches[1]
                    utilization_pct = [int]$matches[2]
                    vram_used_mb = [int]$matches[3]
                    vram_total_mb = [int]$matches[4]
                    temperature_c = [int]$matches[5]
                    power_w = [decimal]$matches[6]
                }
            }
        }
        
        $samples += @{
            timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
            elapsed_sec = [int]$elapsed
            gpus = $gpuMetrics
        }
        
        $progress = [int](($i / $totalSamples) * 100)
        Write-Progress -Activity "Profiling GPU" -Status "$progress% - $i/$totalSamples échantillons" -PercentComplete $progress
        
    } catch {
        Write-Host "  ⚠ Erreur collecte GPU: $($_.Exception.Message)" -ForegroundColor Yellow
    }
    
    Start-Sleep -Seconds $SamplingIntervalSeconds
}

Write-Progress -Activity "Profiling GPU" -Completed

# Attendre fin jobs
Write-Host "`n[2/3] Attente fin requêtes API..." -ForegroundColor Yellow
Get-Job | Wait-Job -Timeout 30 | Out-Null
Get-Job | Remove-Job -Force

# Calculer statistiques
Write-Host "[3/3] Génération rapport..." -ForegroundColor Yellow

$allGpu0Utils = $samples | ForEach-Object { $_.gpus[0].utilization_pct }
$allGpu0Vram = $samples | ForEach-Object { $_.gpus[0].vram_used_mb }
$allGpu0Temp = $samples | ForEach-Object { $_.gpus[0].temperature_c }
$allGpu0Power = $samples | ForEach-Object { $_.gpus[0].power_w }

$stats = @{
    gpu_utilization = @{
        mean = [Math]::Round(($allGpu0Utils | Measure-Object -Average).Average, 2)
        max = ($allGpu0Utils | Measure-Object -Maximum).Maximum
        min = ($allGpu0Utils | Measure-Object -Minimum).Minimum
        p95 = [Math]::Round(($allGpu0Utils | Sort-Object)[($allGpu0Utils.Count * 0.95)], 2)
        p99 = [Math]::Round(($allGpu0Utils | Sort-Object)[($allGpu0Utils.Count * 0.99)], 2)
    }
    vram_mb = @{
        mean = [Math]::Round(($allGpu0Vram | Measure-Object -Average).Average, 0)
        max = ($allGpu0Vram | Measure-Object -Maximum).Maximum
        min = ($allGpu0Vram | Measure-Object -Minimum).Minimum
    }
    temperature_c = @{
        mean = [Math]::Round(($allGpu0Temp | Measure-Object -Average).Average, 1)
        max = ($allGpu0Temp | Measure-Object -Maximum).Maximum
        min = ($allGpu0Temp | Measure-Object -Minimum).Minimum
    }
    power_w = @{
        mean = [Math]::Round(($allGpu0Power | Measure-Object -Average).Average, 1)
        max = ($allGpu0Power | Measure-Object -Maximum).Maximum
        min = ($allGpu0Power | Measure-Object -Minimum).Minimum
    }
}

# Export JSON
$report = @{
    metadata = @{
        timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        duration_minutes = $DurationMinutes
        sample_count = $samples.Count
        service = "myia-vllm-medium-qwen3"
        configuration = "chunked_only_safe"
    }
    statistics = $stats
    samples = $samples
}

$report | ConvertTo-Json -Depth 10 | Out-File -FilePath $outputJson -Encoding UTF8

# Export Markdown
$mdContent = @"
# 📊 PROFILING GPU - Mission 11 Phase 8

**Date**: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
**Service**: myia-vllm-medium-qwen3
**Configuration**: chunked_only_safe
**Durée**: $DurationMinutes minutes ($($samples.Count) échantillons)

---

## 📈 Statistiques GPU (GPU 0)

### Utilisation GPU

| Métrique | Valeur |
|----------|--------|
| **Moyenne** | $($stats.gpu_utilization.mean)% |
| **Maximum** | $($stats.gpu_utilization.max)% |
| **Minimum** | $($stats.gpu_utilization.min)% |
| **P95** | $($stats.gpu_utilization.p95)% |
| **P99** | $($stats.gpu_utilization.p99)% |

### VRAM

| Métrique | Valeur |
|----------|--------|
| **Moyenne** | $($stats.vram_mb.mean) MB |
| **Maximum** | $($stats.vram_mb.max) MB |
| **Minimum** | $($stats.vram_mb.min) MB |

### Température

| Métrique | Valeur |
|----------|--------|
| **Moyenne** | $($stats.temperature_c.mean)°C |
| **Maximum** | $($stats.temperature_c.max)°C |
| **Minimum** | $($stats.temperature_c.min)°C |

### Power Draw

| Métrique | Valeur |
|----------|--------|
| **Moyenne** | $($stats.power_w.mean) W |
| **Maximum** | $($stats.power_w.max) W |
| **Minimum** | $($stats.power_w.min) W |

---

## ✅ Validation

- **GPU Utilization**: $(if($stats.gpu_utilization.mean -ge 85 -and $stats.gpu_utilization.mean -le 95){"✅ OPTIMAL (85-95%)"} else{"⚠️ Hors plage optimale"})
- **VRAM Usage**: $(if($stats.vram_mb.max -lt 20000){"✅ OPTIMAL (<20GB)"} else{"⚠️ Risque OOM"})
- **Température**: $(if($stats.temperature_c.max -lt 85){"✅ OPTIMAL (<85°C)"} else{"⚠️ Alerte thermique"})
- **Power Draw**: $(if($stats.power_w.mean -lt 350){"✅ OPTIMAL (<350W)"} else{"⚠️ Consommation élevée"})

---

**Fichiers générés**:
- JSON: ``$outputJson``
- Rapport: ``$outputMd``
"@

$mdContent | Out-File -FilePath $outputMd -Encoding UTF8

Write-Host "`n✅ PROFILING COMPLÉTÉ" -ForegroundColor Green
Write-Host "`nRésultats:" -ForegroundColor Yellow
Write-Host "  GPU Utilization: $($stats.gpu_utilization.mean)% (P95: $($stats.gpu_utilization.p95)%)" -ForegroundColor White
Write-Host "  VRAM: $($stats.vram_mb.mean) MB (Max: $($stats.vram_mb.max) MB)" -ForegroundColor White
Write-Host "  Température: $($stats.temperature_c.mean)°C (Max: $($stats.temperature_c.max)°C)" -ForegroundColor White
Write-Host "  Power: $($stats.power_w.mean) W (Max: $($stats.power_w.max) W)" -ForegroundColor White
Write-Host "`nFichiers:" -ForegroundColor Yellow
Write-Host "  - $outputJson" -ForegroundColor Cyan
Write-Host "  - $outputMd" -ForegroundColor Cyan