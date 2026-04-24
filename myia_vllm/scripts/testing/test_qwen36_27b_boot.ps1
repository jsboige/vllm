#Requires -Version 5.1
<#
.SYNOPSIS
    Boot + validate Qwen3.6-27B dense VLM with TurboQuant KV cache on GPU 2.

.DESCRIPTION
    1. Stops current GPU 2 service (OmniCoder)
    2. Builds and starts mini-qwen36-27b.yml
    3. Tails vLLM logs, extracts the KV cache memory report (answers our
       hybrid-vs-dense uncertainty: actual KB/token measured)
    4. Waits for /health OK
    5. Runs 3 sanity API calls: chat (nothink), chat (think), tool call
    6. Measures GPU 2 VRAM actual usage
    7. Prints summary — go/no-go decision prompt

.PARAMETER Timeout
    Max seconds to wait for service health. Default 1200 (20 min: model download ~15 GB + fresh compile).

.PARAMETER SkipBuild
    Skip `docker compose build` — use existing image.

.PARAMETER RollbackOnFailure
    On failure, automatically start OmniCoder back. Default: off (leave inspectable state).

.EXAMPLE
    pwsh .\test_qwen36_27b_boot.ps1
    pwsh .\test_qwen36_27b_boot.ps1 -SkipBuild
#>

param(
    [int]$Timeout = 1200,
    [switch]$SkipBuild,
    [switch]$RollbackOnFailure
)

$ErrorActionPreference = 'Stop'
$ScriptRoot   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot  = Split-Path -Parent (Split-Path -Parent $ScriptRoot)
$NewProfile   = Join-Path $ProjectRoot 'configs/docker/profiles/mini-qwen36-27b.yml'
$OldProfile   = Join-Path $ProjectRoot 'configs/docker/profiles/mini-omnicoder.yml'
$EnvFile      = Join-Path $ProjectRoot '.env'
$Container    = 'myia_vllm-mini-qwen36-27b'
$Port         = 5001
$ModelName    = 'qwen3.6-27b'

function Write-Section($title) {
    Write-Host ''
    Write-Host ('=' * 70) -ForegroundColor Cyan
    Write-Host "  $title" -ForegroundColor Cyan
    Write-Host ('=' * 70) -ForegroundColor Cyan
}

function Read-ApiKey {
    if (-not (Test-Path $EnvFile)) { throw ".env not found at $EnvFile" }
    $line = Select-String -Path $EnvFile -Pattern '^VLLM_API_KEY_MINI=' | Select-Object -First 1
    if (-not $line) { throw 'VLLM_API_KEY_MINI missing from .env' }
    ($line.Line -split '=', 2)[1].Trim('"').Trim()
}

# ---------- Step 1: preconditions ----------
Write-Section '1. Preconditions'
if (-not (Test-Path $NewProfile)) { throw "Profile not found: $NewProfile" }
Write-Host "Profile: $NewProfile" -ForegroundColor Green

$apiKey = Read-ApiKey
Write-Host "API key loaded (length=$($apiKey.Length))" -ForegroundColor Green

$running = docker ps --filter "name=myia_vllm-mini-" --format '{{.Names}}'
if ($running) {
    Write-Host "Currently running on GPU 2: $running" -ForegroundColor Yellow
} else {
    Write-Host 'GPU 2 currently free' -ForegroundColor Green
}

# ---------- Step 2: stop current + start new ----------
Write-Section '2. Stop OmniCoder, start Qwen3.6-27B'
docker compose -f $OldProfile --env-file $EnvFile down 2>&1 | Out-Host

if (-not $SkipBuild) {
    Write-Host 'Building image (vllm-qwen36-27b:v0.20.0-t5) — can take 2-5 min for pip install...'
    docker compose -f $NewProfile --env-file $EnvFile build 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'docker build failed' }
}

Write-Host 'Starting container...'
docker compose -f $NewProfile --env-file $EnvFile up -d 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'docker up failed' }

# ---------- Step 3: tail logs, extract KV cache report ----------
Write-Section '3. Waiting for vLLM KV cache report (answers hybrid-vs-dense uncertainty)'
$started = Get-Date
$kvCacheLine = $null
$maxLenLine  = $null
$archLine    = $null
$healthOk    = $false
$lastLogSize = 0

while (((Get-Date) - $started).TotalSeconds -lt $Timeout) {
    # Poll the container log for key indicators
    $logs = docker logs $Container 2>&1 | Out-String

    if (-not $archLine) {
        $m = [regex]::Match($logs, 'num_hidden_layers[^\r\n]*')
        if ($m.Success) { $archLine = $m.Value; Write-Host "ARCH: $archLine" -ForegroundColor Green }
    }
    if (-not $kvCacheLine) {
        $m = [regex]::Match($logs, 'KV cache[^\r\n]*(required|available|memory)[^\r\n]*')
        if ($m.Success) { $kvCacheLine = $m.Value; Write-Host "KV:   $kvCacheLine" -ForegroundColor Green }
    }
    if (-not $maxLenLine) {
        $m = [regex]::Match($logs, 'max.?model.?len[^\r\n]*could be[^\r\n]*')
        if ($m.Success) { $maxLenLine = $m.Value; Write-Host "MAX:  $maxLenLine" -ForegroundColor Green }
    }

    # Health check
    try {
        $hc = Invoke-WebRequest -Uri "http://localhost:$Port/health" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($hc.StatusCode -eq 200) { $healthOk = $true; break }
    } catch {}

    # Bail fast on obvious fatal errors
    foreach ($err in @('CUDA out of memory', 'ValueError:', 'ImportError:', 'EngineDeadError', 'Traceback \(most recent call last\)')) {
        if ($logs -match $err) {
            # Show only new log lines since last poll
            $tail = ($logs -split "`n")[-80..-1] -join "`n"
            Write-Host ''
            Write-Host "FATAL error detected ($err):" -ForegroundColor Red
            Write-Host $tail -ForegroundColor Yellow
            if ($RollbackOnFailure) {
                Write-Host 'Rolling back to OmniCoder...' -ForegroundColor Yellow
                docker compose -f $NewProfile --env-file $EnvFile down 2>&1 | Out-Null
                docker compose -f $OldProfile --env-file $EnvFile up -d 2>&1 | Out-Null
            }
            throw "vLLM boot failed: $err"
        }
    }

    Start-Sleep -Seconds 10
    $elapsed = [int]((Get-Date) - $started).TotalSeconds
    Write-Host "  waiting... ${elapsed}s / ${Timeout}s" -ForegroundColor DarkGray
}

if (-not $healthOk) {
    Write-Host 'Timeout waiting for /health — container still alive but not healthy yet.' -ForegroundColor Yellow
    Write-Host 'Recent logs:' -ForegroundColor Yellow
    docker logs --tail 50 $Container 2>&1 | Out-Host
    throw "Boot timeout after ${Timeout}s"
}

Write-Host "/health OK in $([int]((Get-Date) - $started).TotalSeconds)s" -ForegroundColor Green

# ---------- Step 4: sanity API calls ----------
Write-Section '4. Sanity API calls'
$headers = @{ 'Authorization' = "Bearer $apiKey"; 'Content-Type' = 'application/json' }

function Test-Chat($label, $body) {
    Write-Host "[$label] " -NoNewline
    $t0 = Get-Date
    try {
        $r = Invoke-RestMethod -Uri "http://localhost:$Port/v1/chat/completions" -Method Post `
             -Headers $headers -Body ($body | ConvertTo-Json -Depth 10) -TimeoutSec 120
        $dur = [math]::Round(((Get-Date) - $t0).TotalSeconds, 2)
        $ctok = $r.usage.completion_tokens
        $rate = if ($dur -gt 0) { [math]::Round($ctok / $dur, 1) } else { 0 }
        $msg = $r.choices[0].message
        $hasReasoning = [bool]$msg.reasoning
        $hasTool = [bool]$msg.tool_calls
        Write-Host "OK ${dur}s ${ctok}tok (${rate} tok/s) reasoning=$hasReasoning tool=$hasTool" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "FAIL: $_" -ForegroundColor Red
        return $false
    }
}

$ok1 = Test-Chat 'nothink' @{
    model = $ModelName
    messages = @(@{ role = 'user'; content = 'Write a one-line Python lambda that squares its input.' })
    max_tokens = 80
    temperature = 0.1
    chat_template_kwargs = @{ enable_thinking = $false }
}

$ok2 = Test-Chat 'think' @{
    model = $ModelName
    messages = @(@{ role = 'user'; content = 'What is 47*53? Think step by step then give the result.' })
    max_tokens = 400
    temperature = 0.6
}

$ok3 = Test-Chat 'tool' @{
    model = $ModelName
    messages = @(@{ role = 'user'; content = 'What is the weather in Paris today?' })
    tools = @(@{
        type = 'function'
        function = @{
            name = 'get_weather'
            description = 'Get current weather for a city'
            parameters = @{
                type = 'object'
                properties = @{ city = @{ type = 'string' } }
                required = @('city')
            }
        }
    })
    max_tokens = 200
    temperature = 0.1
}

# ---------- Step 5: VRAM snapshot ----------
Write-Section '5. GPU 2 VRAM snapshot'
$vram = nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader,nounits |
        Where-Object { $_ -match '^2,' }
Write-Host "GPU 2 VRAM: $vram (MiB used / total)" -ForegroundColor Green

# ---------- Step 6: summary ----------
Write-Section '6. Summary'
Write-Host "Profile:        $NewProfile"
Write-Host "Container:      $Container"
Write-Host "Port:           $Port"
Write-Host "Model:          cyankiwi/Qwen3.6-27B-AWQ-INT4"
Write-Host "KV dtype:       turboquant_k8v4"
Write-Host "Max ctx:        131072 (config)"
Write-Host ''
Write-Host 'vLLM boot report:'
Write-Host ('  ARCH: ' + ($archLine    ?? '(not captured — check `docker logs myia_vllm-mini-qwen36-27b`)'))
Write-Host ('  KV:   ' + ($kvCacheLine ?? '(not captured)'))
Write-Host ('  MAX:  ' + ($maxLenLine  ?? '(not captured)'))
Write-Host ''
Write-Host "API tests: nothink=$ok1 think=$ok2 tool=$ok3"
Write-Host ''
$allOk = $ok1 -and $ok2 -and $ok3
if ($allOk) {
    Write-Host 'ALL SANITY CHECKS PASSED' -ForegroundColor Green
    Write-Host ''
    Write-Host 'Next steps:'
    Write-Host '  - If KV budget headroom >3 GB → try `turboquant_3bit_nc` + max-model-len 262144'
    Write-Host '  - Benchmark vs OmniCoder: python myia_vllm/scripts/testing/benchmark_coder_next.py --model qwen3.6-27b'
    Write-Host '  - To rollback: docker compose -f mini-qwen36-27b.yml down; docker compose -f mini-omnicoder.yml up -d'
} else {
    Write-Host 'SOME SANITY CHECKS FAILED — inspect `docker logs myia_vllm-mini-qwen36-27b`' -ForegroundColor Red
    if ($RollbackOnFailure) {
        Write-Host 'Rolling back to OmniCoder...' -ForegroundColor Yellow
        docker compose -f $NewProfile --env-file $EnvFile down 2>&1 | Out-Null
        docker compose -f $OldProfile --env-file $EnvFile up -d 2>&1 | Out-Null
    }
    exit 1
}
