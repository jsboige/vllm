<#
.SYNOPSIS
    Tests complets de validation pour Mission 15 - Configuration Optimale
.DESCRIPTION
    Exécute une suite de tests pour valider la configuration chunked_only_safe (x3.22)
    - Health Check
    - Test Raisonnement
    - Test Tool Calling
    - Benchmark KV Cache
.PARAMETER ApiKey
    Clé API pour authentification (défaut: variable d'environnement VLLM_API_KEY_MEDIUM)
.PARAMETER BaseUrl
    URL de base de l'API (défaut: http://localhost:8000)
.PARAMETER OutputFile
    Fichier JSON pour sauvegarder les résultats (optionnel)
.EXAMPLE
    .\mission15_validation_tests.ps1 -ApiKey "YOUR_API_KEY"
#>

param(
    [Parameter(Mandatory=$false)]
    [string]$ApiKey = $env:VLLM_API_KEY_MEDIUM,
    
    [Parameter(Mandatory=$false)]
    [string]$BaseUrl = "http://localhost:8000",
    
    [Parameter(Mandatory=$false)]
    [string]$OutputFile
)

# Timestamp de début
$startTime = Get-Date
$timestamp = $startTime.ToString("yyyyMMdd_HHmmss")

Write-Host "=== MISSION 15 - TESTS DE VALIDATION ===" -ForegroundColor Cyan
Write-Host "Configuration: chunked_only_safe (x3.22)"
Write-Host "Timestamp: $timestamp"
Write-Host ""

# Structure des résultats
$results = @{
    timestamp = $timestamp
    configuration = "chunked_only_safe"
    base_url = $BaseUrl
    tests = @{}
}

# ======================
# TEST 1: HEALTH CHECK
# ======================
Write-Host "📋 TEST 1: Health Check" -ForegroundColor Yellow
try {
    $healthResponse = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get -TimeoutSec 10
    $healthStatus = if ($healthResponse.status -eq "ok" -or $healthResponse) { "OK" } else { "ÉCHEC" }
    
    $results.tests.health_check = @{
        status = $healthStatus
        response = $healthResponse
        error = $null
    }
    
    Write-Host "✅ Health Check: $healthStatus" -ForegroundColor Green
    Write-Host "   Réponse: $($healthResponse | ConvertTo-Json -Compress)" -ForegroundColor Gray
} catch {
    $results.tests.health_check = @{
        status = "ÉCHEC"
        response = $null
        error = $_.Exception.Message
    }
    Write-Host "❌ Health Check ÉCHEC: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# ======================
# TEST 2: RAISONNEMENT
# ======================
Write-Host "🧠 TEST 2: Test Raisonnement" -ForegroundColor Yellow
try {
    $headers = @{
        'Authorization' = "Bearer $ApiKey"
        'Content-Type' = 'application/json'
    }
    
    $body = @{
        model = 'Qwen/Qwen3-32B-AWQ'
        messages = @(
            @{
                role = 'user'
                content = 'Résous cette énigme: Si 2+2=4 et 3+3=6, combien font 4+4?'
            }
        )
        max_tokens = 100
    } | ConvertTo-Json -Depth 10
    
    $reasoningStart = Get-Date
    $reasoningResponse = Invoke-RestMethod -Uri "$BaseUrl/v1/chat/completions" -Method Post -Headers $headers -Body $body -TimeoutSec 30
    $reasoningTime = ((Get-Date) - $reasoningStart).TotalMilliseconds
    
    $answer = $reasoningResponse.choices[0].message.content
    $containsCorrectAnswer = $answer -match '8'
    $status = if ($containsCorrectAnswer) { "OK" } else { "ÉCHEC" }
    
    $results.tests.reasoning = @{
        status = $status
        prompt = 'Si 2+2=4 et 3+3=6, combien font 4+4?'
        response = $answer
        contains_correct_answer = $containsCorrectAnswer
        response_time_ms = [math]::Round($reasoningTime, 2)
        error = $null
    }
    
    Write-Host "✅ Test Raisonnement: $status" -ForegroundColor Green
    Write-Host "   Réponse: $answer" -ForegroundColor Gray
    Write-Host "   Temps: $([math]::Round($reasoningTime, 2)) ms" -ForegroundColor Gray
} catch {
    $results.tests.reasoning = @{
        status = "ÉCHEC"
        prompt = 'Si 2+2=4 et 3+3=6, combien font 4+4?'
        response = $null
        contains_correct_answer = $false
        response_time_ms = 0
        error = $_.Exception.Message
    }
    Write-Host "❌ Test Raisonnement ÉCHEC: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# ======================
# TEST 3: TOOL CALLING
# ======================
Write-Host "🔧 TEST 3: Tool Calling" -ForegroundColor Yellow
try {
    $headers = @{
        'Authorization' = "Bearer $ApiKey"
        'Content-Type' = 'application/json'
    }
    
    $body = @{
        model = 'Qwen/Qwen3-32B-AWQ'
        messages = @(
            @{
                role = 'user'
                content = 'Quelle est la météo à Paris?'
            }
        )
        tools = @(
            @{
                type = 'function'
                function = @{
                    name = 'get_weather'
                    description = "Obtenir la météo d'une ville"
                    parameters = @{
                        type = 'object'
                        properties = @{
                            city = @{
                                type = 'string'
                                description = 'Nom de la ville'
                            }
                        }
                        required = @('city')
                    }
                }
            }
        )
        max_tokens = 100
    } | ConvertTo-Json -Depth 10
    
    $toolStart = Get-Date
    $toolResponse = Invoke-RestMethod -Uri "$BaseUrl/v1/chat/completions" -Method Post -Headers $headers -Body $body -TimeoutSec 30
    $toolTime = ((Get-Date) - $toolStart).TotalMilliseconds
    
    $toolCalls = $toolResponse.choices[0].message.tool_calls
    $hasToolCall = $null -ne $toolCalls -and $toolCalls.Count -gt 0
    $correctTool = $false
    $correctParam = $false
    
    if ($hasToolCall) {
        $correctTool = $toolCalls[0].function.name -eq 'get_weather'
        $arguments = $toolCalls[0].function.arguments | ConvertFrom-Json
        $correctParam = $arguments.city -like '*Paris*'
    }
    
    $status = if ($hasToolCall -and $correctTool -and $correctParam) { "OK" } else { "ÉCHEC" }
    
    $results.tests.tool_calling = @{
        status = $status
        has_tool_call = $hasToolCall
        tool_name = if ($hasToolCall) { $toolCalls[0].function.name } else { $null }
        tool_arguments = if ($hasToolCall) { $toolCalls[0].function.arguments } else { $null }
        correct_tool = $correctTool
        correct_param = $correctParam
        response_time_ms = [math]::Round($toolTime, 2)
        error = $null
    }
    
    Write-Host "✅ Test Tool Calling: $status" -ForegroundColor Green
    Write-Host "   Tool détecté: $($toolCalls[0].function.name)" -ForegroundColor Gray
    Write-Host "   Arguments: $($toolCalls[0].function.arguments)" -ForegroundColor Gray
    Write-Host "   Temps: $([math]::Round($toolTime, 2)) ms" -ForegroundColor Gray
} catch {
    $results.tests.tool_calling = @{
        status = "ÉCHEC"
        has_tool_call = $false
        tool_name = $null
        tool_arguments = $null
        correct_tool = $false
        correct_param = $false
        response_time_ms = 0
        error = $_.Exception.Message
    }
    Write-Host "❌ Test Tool Calling ÉCHEC: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# ======================
# TEST 4: KV CACHE BENCHMARK
# ======================
Write-Host "⚡ TEST 4: Benchmark KV Cache" -ForegroundColor Yellow
try {
    $headers = @{
        'Authorization' = "Bearer $ApiKey"
        'Content-Type' = 'application/json'
    }
    
    # Premier message (CACHE MISS)
    Write-Host "   📤 Message 1 (CACHE MISS)..." -ForegroundColor Gray
    $body1 = @{
        model = 'Qwen/Qwen3-32B-AWQ'
        messages = @(
            @{
                role = 'user'
                content = "Bonjour, peux-tu m'expliquer ce qu'est l'intelligence artificielle en détail?"
            }
        )
        max_tokens = 50
    } | ConvertTo-Json -Depth 10
    
    $start1 = Get-Date
    $response1 = Invoke-RestMethod -Uri "$BaseUrl/v1/chat/completions" -Method Post -Headers $headers -Body $body1 -TimeoutSec 60
    $ttft1 = ((Get-Date) - $start1).TotalMilliseconds
    
    Write-Host "   ✓ TTFT CACHE MISS: $([math]::Round($ttft1, 2)) ms" -ForegroundColor Gray
    
    # Pause courte
    Start-Sleep -Milliseconds 500
    
    # Deuxième message (CACHE HIT)
    Write-Host "   📥 Message 2 (CACHE HIT)..." -ForegroundColor Gray
    $body2 = @{
        model = 'Qwen/Qwen3-32B-AWQ'
        messages = @(
            @{
                role = 'user'
                content = "Bonjour, peux-tu m'expliquer ce qu'est l'intelligence artificielle en détail?"
            }
            @{
                role = 'assistant'
                content = $response1.choices[0].message.content
            }
            @{
                role = 'user'
                content = "Merci, et quels sont ses principaux domaines d'application?"
            }
        )
        max_tokens = 50
    } | ConvertTo-Json -Depth 10
    
    $start2 = Get-Date
    $response2 = Invoke-RestMethod -Uri "$BaseUrl/v1/chat/completions" -Method Post -Headers $headers -Body $body2 -TimeoutSec 60
    $ttft2 = ((Get-Date) - $start2).TotalMilliseconds
    
    Write-Host "   ✓ TTFT CACHE HIT: $([math]::Round($ttft2, 2)) ms" -ForegroundColor Gray
    
    $acceleration = if ($ttft2 -gt 0) { [math]::Round($ttft1 / $ttft2, 2) } else { 0 }
    $expectedAccel = 3.22
    $deviation = [math]::Abs(($acceleration - $expectedAccel) / $expectedAccel * 100)
    
    $status = if ($acceleration -ge 2.5) { "OK" } else { "ÉCHEC" }
    
    $results.tests.kv_cache_benchmark = @{
        status = $status
        ttft_cache_miss_ms = [math]::Round($ttft1, 2)
        ttft_cache_hit_ms = [math]::Round($ttft2, 2)
        acceleration = $acceleration
        expected_acceleration = $expectedAccel
        deviation_percent = [math]::Round($deviation, 2)
        error = $null
    }
    
    Write-Host "✅ Benchmark KV Cache: $status" -ForegroundColor Green
    Write-Host "   Accélération: x$acceleration (attendu: x$expectedAccel)" -ForegroundColor Gray
    Write-Host "   Écart: ±$([math]::Round($deviation, 2))%" -ForegroundColor Gray
} catch {
    $results.tests.kv_cache_benchmark = @{
        status = "ÉCHEC"
        ttft_cache_miss_ms = 0
        ttft_cache_hit_ms = 0
        acceleration = 0
        expected_acceleration = 3.22
        deviation_percent = 0
        error = $_.Exception.Message
    }
    Write-Host "❌ Benchmark KV Cache ÉCHEC: $($_.Exception.Message)" -ForegroundColor Red
}
Write-Host ""

# ======================
# RÉSUMÉ FINAL
# ======================
$endTime = Get-Date
$totalDuration = ($endTime - $startTime).TotalSeconds

$allPassed = ($results.tests.health_check.status -eq "OK") -and
             ($results.tests.reasoning.status -eq "OK") -and
             ($results.tests.tool_calling.status -eq "OK") -and
             ($results.tests.kv_cache_benchmark.status -eq "OK")

$results.summary = @{
    all_tests_passed = $allPassed
    total_duration_seconds = [math]::Round($totalDuration, 2)
    timestamp_end = $endTime.ToString("yyyy-MM-dd HH:mm:ss")
}

Write-Host "=== RÉSUMÉ ===" -ForegroundColor Cyan
Write-Host "Tests passés: $(if ($allPassed) { '✅ TOUS' } else { '❌ ÉCHECS PARTIELS' })" -ForegroundColor $(if ($allPassed) { 'Green' } else { 'Red' })
Write-Host "Durée totale: $([math]::Round($totalDuration, 2)) secondes" -ForegroundColor Gray
Write-Host ""

# Sauvegarde des résultats si demandé
if ($OutputFile) {
    $results | ConvertTo-Json -Depth 10 | Out-File -FilePath $OutputFile -Encoding UTF8
    Write-Host "📁 Résultats sauvegardés: $OutputFile" -ForegroundColor Green
}

# Retourne les résultats
return $results