#Requires -Version 5.1
<#
.SYNOPSIS
    Test script for Qwen3-Coder-Next vLLM configuration validation.

.DESCRIPTION
    This script validates the Docker deployment of Qwen3-Coder-Next:
    1. Checks Docker configuration syntax
    2. Validates environment variables
    3. Starts the container with detailed logging
    4. Monitors startup progress
    5. Tests API health endpoint

.PARAMETER LogPath
    Path for startup logs. Default: logs/coder_next_startup.log

.PARAMETER Timeout
    Maximum wait time for service health in seconds. Default: 900 (15 min)

.PARAMETER SkipStart
    Only validate configuration, don't start the container.

.EXAMPLE
    .\test_coder_next_config.ps1

.EXAMPLE
    .\test_coder_next_config.ps1 -Timeout 1200 -LogPath C:\logs\startup.log
#>

param(
    [string]$LogPath = "logs/coder_next_startup.log",
    [int]$Timeout = 900,
    [switch]$SkipStart
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptRoot)
$ProfilePath = Join-Path $ProjectRoot "configs/docker/profiles/medium-coder.yml"

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "Qwen3-Coder-Next Configuration Test" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""

# Step 1: Check profile exists
Write-Host "[1/6] Checking Docker profile..." -ForegroundColor Yellow
if (-not (Test-Path $ProfilePath)) {
    Write-Host "ERROR: Profile not found: $ProfilePath" -ForegroundColor Red
    exit 1
}
Write-Host "  Profile found: $ProfilePath" -ForegroundColor Green

# Step 2: Validate YAML syntax
Write-Host "[2/6] Validating Docker Compose syntax..." -ForegroundColor Yellow
try {
    $result = docker compose -f $ProfilePath config --quiet 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Invalid Docker Compose syntax:" -ForegroundColor Red
        Write-Host $result -ForegroundColor Red
        exit 1
    }
    Write-Host "  Syntax valid" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Docker Compose validation failed: $_" -ForegroundColor Red
    exit 1
}

# Step 3: Check environment variables
Write-Host "[3/6] Checking environment variables..." -ForegroundColor Yellow
$envFile = Join-Path $ProjectRoot ".env"
$requiredVars = @(
    "HUGGING_FACE_HUB_TOKEN",
    "VLLM_API_KEY_MEDIUM"
)
$missingVars = @()

if (Test-Path $envFile) {
    $envContent = Get-Content $envFile -Raw
    foreach ($var in $requiredVars) {
        if ($envContent -notmatch "^$var=.+") {
            $missingVars += $var
        }
    }
} else {
    Write-Host "  WARNING: .env file not found at $envFile" -ForegroundColor Yellow
    $missingVars = $requiredVars
}

if ($missingVars.Count -gt 0) {
    Write-Host "  WARNING: Missing or empty variables:" -ForegroundColor Yellow
    foreach ($var in $missingVars) {
        Write-Host "    - $var" -ForegroundColor Yellow
    }
} else {
    Write-Host "  All required variables present" -ForegroundColor Green
}

# Step 4: Check GPU availability
Write-Host "[4/6] Checking GPU availability..." -ForegroundColor Yellow
try {
    $gpuInfo = nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader 2>&1
    if ($LASTEXITCODE -eq 0) {
        $gpus = $gpuInfo -split "`n" | Where-Object { $_ -match "\S" }
        Write-Host "  Found $($gpus.Count) GPU(s):" -ForegroundColor Green
        foreach ($gpu in $gpus) {
            Write-Host "    $gpu" -ForegroundColor Gray
        }
        if ($gpus.Count -lt 3) {
            Write-Host "  WARNING: Qwen3-Coder-Next requires 3 GPUs (TP=3)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  WARNING: nvidia-smi failed: $gpuInfo" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  WARNING: Could not check GPUs: $_" -ForegroundColor Yellow
}

# Step 5: Check model path
Write-Host "[5/6] Checking model path..." -ForegroundColor Yellow
$modelPath = $env:VLLM_MODEL_CODER
if (-not $modelPath) {
    $modelPath = "./models/Qwen3-Coder-Next-W4A16"
}
$fullModelPath = Join-Path $ProjectRoot $modelPath
if (Test-Path $fullModelPath) {
    $modelSize = (Get-ChildItem $fullModelPath -Recurse | Measure-Object -Property Length -Sum).Sum / 1GB
    Write-Host "  Model found: $fullModelPath ({0:N1} GB)" -f $modelSize -ForegroundColor Green
} else {
    Write-Host "  WARNING: Model not found at $fullModelPath" -ForegroundColor Yellow
    Write-Host "  Run quantization script first:" -ForegroundColor Yellow
    Write-Host "    python scripts/quantization/quantize_qwen3_coder_next.py" -ForegroundColor Gray
}

if ($SkipStart) {
    Write-Host ""
    Write-Host "[6/6] Skipping container start (-SkipStart)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Configuration validation complete!" -ForegroundColor Green
    exit 0
}

# Step 6: Start container and monitor
Write-Host "[6/6] Starting container with monitoring..." -ForegroundColor Yellow

# Create log directory
$logDir = Split-Path -Parent $LogPath
if ($logDir -and -not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# Create container (don't start yet)
Write-Host "  Creating container..." -ForegroundColor Gray
docker compose -f $ProfilePath up --no-start 2>&1 | Out-Null

# Start container
Write-Host "  Starting container..." -ForegroundColor Gray
docker compose -f $ProfilePath start 2>&1 | Out-Null

# Monitor logs in background, write to file
Write-Host "  Monitoring startup (timeout: $Timeout seconds)..." -ForegroundColor Gray
Write-Host "  Log file: $LogPath" -ForegroundColor Gray
Write-Host ""

$containerName = "myia_vllm-medium-coder"
$startTime = Get-Date
$healthy = $false

# Start log capture job
$logJob = Start-Job -ScriptBlock {
    param($container, $logFile)
    docker logs -f $container 2>&1 | Tee-Object -FilePath $logFile
} -ArgumentList $containerName, $LogPath

while (((Get-Date) - $startTime).TotalSeconds -lt $Timeout) {
    # Check container health
    $health = docker inspect --format='{{.State.Health.Status}}' $containerName 2>&1

    if ($health -eq "healthy") {
        $healthy = $true
        break
    }

    # Check if container exited
    $state = docker inspect --format='{{.State.Status}}' $containerName 2>&1
    if ($state -eq "exited") {
        Write-Host "  ERROR: Container exited unexpectedly" -ForegroundColor Red
        Write-Host "  Check logs: docker logs $containerName" -ForegroundColor Yellow
        Stop-Job $logJob
        Remove-Job $logJob
        exit 1
    }

    # Progress indicator
    $elapsed = [int]((Get-Date) - $startTime).TotalSeconds
    Write-Host "`r  Status: $health | Elapsed: ${elapsed}s / ${Timeout}s" -NoNewline

    Start-Sleep -Seconds 10
}

Stop-Job $logJob -ErrorAction SilentlyContinue
Remove-Job $logJob -ErrorAction SilentlyContinue

Write-Host ""

if ($healthy) {
    Write-Host ""
    Write-Host "=" * 60 -ForegroundColor Green
    Write-Host "SUCCESS: Qwen3-Coder-Next is running!" -ForegroundColor Green
    Write-Host "=" * 60 -ForegroundColor Green
    Write-Host ""
    Write-Host "API endpoint: http://localhost:$($env:VLLM_PORT_CODER ?? 5002)/v1" -ForegroundColor Cyan
    Write-Host "Health check: http://localhost:$($env:VLLM_PORT_CODER ?? 5002)/health" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Test with:" -ForegroundColor Gray
    Write-Host "  python scripts/testing/benchmark_coder_next.py" -ForegroundColor Gray
} else {
    Write-Host ""
    Write-Host "=" * 60 -ForegroundColor Red
    Write-Host "TIMEOUT: Service did not become healthy in $Timeout seconds" -ForegroundColor Red
    Write-Host "=" * 60 -ForegroundColor Red
    Write-Host ""
    Write-Host "Check logs for errors:" -ForegroundColor Yellow
    Write-Host "  docker logs $containerName" -ForegroundColor Gray
    Write-Host "  cat $LogPath" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Common issues:" -ForegroundColor Yellow
    Write-Host "  - OOM: Reduce --max-model-len or --gpu-memory-utilization" -ForegroundColor Gray
    Write-Host "  - FP8 bug: Remove --kv-cache-dtype fp8 (issue #26646)" -ForegroundColor Gray
    Write-Host "  - Model not found: Run quantization script first" -ForegroundColor Gray
    exit 1
}
