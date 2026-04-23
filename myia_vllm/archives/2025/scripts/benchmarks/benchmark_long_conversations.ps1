# ============================================
# BENCHMARK CONVERSATIONS LONGUES (15 TOURS)
# Phase 2.2 - Mission 11 Phase 8
# ============================================

<#
.SYNOPSIS
    Benchmark de conversations longues pour valider stabilité cache KV sur durée étendue

.DESCRIPTION
    Ce script teste des conversations de 15 tours sur plusieurs itérations pour:
    - Mesurer l'évolution du TTFT au fil des tours
    - Détecter les dégradations de performance
    - Valider la stabilité du cache KV sur conversations étendues
    
    Métriques collectées:
    - TTFT par tour (focus tours 1, 5, 10, 15)
    - Tokens/seconde moyens
    - Tendance dégradation (stable/linéaire)
    - Durée totale conversation

.PARAMETER ConversationTurns
    Nombre de tours par conversation (défaut: 15)

.PARAMETER Iterations
    Nombre d'itérations complètes (défaut: 3)

.PARAMETER ApiUrl
    URL de l'API vLLM (défaut: http://localhost:5002/v1/chat/completions)

.PARAMETER OutputFile
    Chemin du fichier de sortie JSON

.EXAMPLE
    .\benchmark_long_conversations.ps1 -Iterations 3
    
.EXAMPLE
    .\benchmark_long_conversations.ps1 -ConversationTurns 20 -Iterations 5
#>

param(
    [int]$ConversationTurns = 15,
    [int]$Iterations = 3,
    [string]$ApiUrl = "http://localhost:5002/v1/chat/completions",
    [string]$OutputFile = "myia_vllm/test_results/long_conversation_benchmark_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
)

$ErrorActionPreference = "Stop"

# ============================================
# CONFIGURATION
# ============================================

# Charger API Key depuis .env
$envFile = "myia_vllm/.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^VLLM_API_KEY_MEDIUM=(.+)$') {
            $ApiKey = $matches[1]
        }
    }
}

if (-not $ApiKey) {
    Write-Host "❌ ERREUR: VLLM_API_KEY_MEDIUM non trouvée dans .env" -ForegroundColor Red
    exit 1
}

$Model = "Qwen/Qwen3-32B-AWQ"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "BENCHMARK CONVERSATIONS LONGUES" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan
Write-Host "🎯 Objectif : Valider stabilité cache KV sur 15 tours" -ForegroundColor Yellow
Write-Host "📊 Tours par conversation : $ConversationTurns" -ForegroundColor Yellow
Write-Host "🔄 Itérations : $Iterations" -ForegroundColor Yellow
Write-Host "🌐 API URL : $ApiUrl`n" -ForegroundColor Yellow

# ============================================
# FONCTION : MESURER REQUÊTE COMPLÈTE
# ============================================
function Measure-ChatRequest {
    param(
        [array]$Messages,
        [int]$TurnNumber,
        [string]$ContextId
    )
    
    $body = @{
        model = $Model
        messages = $Messages
        max_tokens = 150
        temperature = 0.7
        stream = $false
    } | ConvertTo-Json -Depth 10
    
    try {
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        
        $response = Invoke-WebRequest `
            -Uri $ApiUrl `
            -Method POST `
            -Body $body `
            -ContentType "application/json" `
            -Headers @{
                "Authorization" = "Bearer $ApiKey"
            } `
            -TimeoutSec 60
        
        $elapsed = $stopwatch.Elapsed.TotalMilliseconds
        $stopwatch.Stop()
        
        $responseData = $response.Content | ConvertFrom-Json
        $tokensGenerated = if ($responseData.usage) { $responseData.usage.completion_tokens } else { 0 }
        $tokensPerSec = if ($elapsed -gt 0) { [math]::Round(($tokensGenerated / $elapsed) * 1000, 2) } else { 0 }
        
        $color = if ($elapsed -lt 2000) { "Green" } elseif ($elapsed -lt 4000) { "Yellow" } else { "Red" }
        Write-Host "  [Tour $TurnNumber] TTFT: $([math]::Round($elapsed, 0))ms | Tokens: $tokensGenerated | Tok/sec: $tokensPerSec" -ForegroundColor $color
        
        return @{
            Success = $true
            Turn = $TurnNumber
            TTFT_ms = [math]::Round($elapsed, 2)
            Tokens = $tokensGenerated
            TokensPerSec = $tokensPerSec
            ResponseContent = $responseData.choices[0].message.content
        }
        
    } catch {
        Write-Host "  [Tour $TurnNumber] ❌ ERREUR: $($_.Exception.Message)" -ForegroundColor Red
        return @{
            Success = $false
            Turn = $TurnNumber
            TTFT_ms = $null
            Error = $_.Exception.Message
        }
    }
}

# ============================================
# PROMPTS DE CONVERSATION VARIÉS
# ============================================
$conversationPrompts = @(
    "Bonjour ! Je m'appelle Alice et j'aimerais discuter de technologie avec toi.",
    "Peux-tu m'expliquer ce qu'est l'intelligence artificielle en termes simples ?",
    "Quelles sont les principales applications de l'IA dans notre vie quotidienne ?",
    "Comment fonctionne un modèle de langage comme toi ?",
    "Quelle est la différence entre machine learning et deep learning ?",
    "Parle-moi des transformers en IA. Pourquoi sont-ils importants ?",
    "Quels sont les défis éthiques liés à l'IA ?",
    "Comment l'IA pourrait-elle évoluer dans les 10 prochaines années ?",
    "Quelles sont les limites actuelles de l'intelligence artificielle ?",
    "Peux-tu me donner un exemple concret d'utilisation de l'IA dans la santé ?",
    "Comment les modèles de langage sont-ils entraînés ?",
    "Quelle est la différence entre IA générative et IA discriminative ?",
    "Parle-moi du rôle de l'IA dans le changement climatique.",
    "Quels sont les métiers qui pourraient être transformés par l'IA ?",
    "Pour conclure, quel conseil donnerais-tu à quelqu'un qui veut apprendre l'IA ?"
)

# ============================================
# EXÉCUTION DES BENCHMARKS
# ============================================
$allResults = @{
    test_date = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
    config = "chunked_only_safe"
    conversation_turns = $ConversationTurns
    iterations_count = $Iterations
    iterations = @()
}

for ($iter = 1; $iter -le $Iterations; $iter++) {
    Write-Host "`n=== ITÉRATION $iter/$Iterations ===" -ForegroundColor Cyan
    Write-Host "Démarrage conversation de $ConversationTurns tours...`n" -ForegroundColor Gray
    
    $conversationMessages = @()
    $turnsResults = @()
    $contextId = [guid]::NewGuid().ToString()
    
    # Boucle sur les tours de conversation
    for ($turn = 1; $turn -le $ConversationTurns; $turn++) {
        $promptIndex = ($turn - 1) % $conversationPrompts.Count
        $userPrompt = $conversationPrompts[$promptIndex]
        
        # Ajouter message utilisateur
        $conversationMessages += @{
            role = "user"
            content = $userPrompt
        }
        
        # Mesurer requête
        $result = Measure-ChatRequest -Messages $conversationMessages -TurnNumber $turn -ContextId $contextId
        $turnsResults += $result
        
        # Ajouter réponse assistant si succès
        if ($result.Success -and $result.ResponseContent) {
            $conversationMessages += @{
                role = "assistant"
                content = $result.ResponseContent
            }
        }
        
        # Pause courte entre tours
        Start-Sleep -Milliseconds 300
    }
    
    # Calculer statistiques de l'itération
    $successTurns = $turnsResults | Where-Object { $_.Success }
    
    if ($successTurns.Count -gt 0) {
        # Calculs par tranches
        $turns1_5 = $successTurns | Where-Object { $_.Turn -le 5 }
        $turns6_10 = $successTurns | Where-Object { $_.Turn -ge 6 -and $_.Turn -le 10 }
        $turns11_15 = $successTurns | Where-Object { $_.Turn -ge 11 }
        
        $ttftAvg1_5 = if ($turns1_5) { [math]::Round(($turns1_5 | Measure-Object -Property TTFT_ms -Average).Average, 2) } else { 0 }
        $ttftAvg6_10 = if ($turns6_10) { [math]::Round(($turns6_10 | Measure-Object -Property TTFT_ms -Average).Average, 2) } else { 0 }
        $ttftAvg11_15 = if ($turns11_15) { [math]::Round(($turns11_15 | Measure-Object -Property TTFT_ms -Average).Average, 2) } else { 0 }
        
        # Calcul dégradation
        $firstTTFT = $successTurns[0].TTFT_ms
        $lastTTFT = $successTurns[-1].TTFT_ms
        $degradationPct = if ($firstTTFT -gt 0) { [math]::Round((($lastTTFT - $firstTTFT) / $firstTTFT) * 100, 1) } else { 0 }
        
        $totalDuration = ($successTurns | Measure-Object -Property TTFT_ms -Sum).Sum
        $tokensPerSecAvg = [math]::Round(($successTurns | Measure-Object -Property TokensPerSec -Average).Average, 2)
        
        Write-Host "`n📊 Résumé Itération $iter :" -ForegroundColor Yellow
        Write-Host "   TTFT moyen tours 1-5   : ${ttftAvg1_5}ms" -ForegroundColor White
        Write-Host "   TTFT moyen tours 6-10  : ${ttftAvg6_10}ms" -ForegroundColor White
        Write-Host "   TTFT moyen tours 11-15 : ${ttftAvg11_15}ms" -ForegroundColor White
        Write-Host "   Dégradation totale     : ${degradationPct}%" -ForegroundColor $(if ([math]::Abs($degradationPct) -lt 20) { "Green" } else { "Red" })
        Write-Host "   Durée totale           : $([math]::Round($totalDuration / 1000, 1))s" -ForegroundColor White
        
        $iterationSummary = @{
            iteration = $iter
            turns = $turnsResults
            summary = @{
                ttft_avg_turns_1_5 = $ttftAvg1_5
                ttft_avg_turns_6_10 = $ttftAvg6_10
                ttft_avg_turns_11_15 = $ttftAvg11_15
                total_duration_ms = [math]::Round($totalDuration, 0)
                degradation_pct = $degradationPct
                tokens_per_sec_avg = $tokensPerSecAvg
                successful_turns = $successTurns.Count
                failed_turns = $ConversationTurns - $successTurns.Count
            }
        }
        
        $allResults.iterations += $iterationSummary
    }
    
    # Pause entre itérations
    if ($iter -lt $Iterations) {
        Write-Host "`nPause 3 secondes avant itération suivante..." -ForegroundColor Gray
        Start-Sleep -Seconds 3
    }
}

# ============================================
# CALCUL STATISTIQUES GLOBALES
# ============================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "ANALYSE GLOBALE" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$allTTFTs = @()
$allTokensPerSec = @()

foreach ($iteration in $allResults.iterations) {
    $allTTFTs += $iteration.summary.ttft_avg_turns_1_5
    $allTTFTs += $iteration.summary.ttft_avg_turns_6_10
    $allTTFTs += $iteration.summary.ttft_avg_turns_11_15
    $allTokensPerSec += $iteration.summary.tokens_per_sec_avg
}

$ttftGlobalAvg = [math]::Round(($allTTFTs | Measure-Object -Average).Average, 2)
$ttftStdDev = [math]::Round([math]::Sqrt((($allTTFTs | ForEach-Object { [math]::Pow($_ - $ttftGlobalAvg, 2) }) | Measure-Object -Average).Average), 2)
$tokensPerSecGlobalAvg = [math]::Round(($allTokensPerSec | Measure-Object -Average).Average, 2)

# Détection stabilité
$maxDegradation = ($allResults.iterations | ForEach-Object { [math]::Abs($_.summary.degradation_pct) } | Measure-Object -Maximum).Maximum
$isStable = $maxDegradation -lt 20

$allResults.global_summary = @{
    ttft_avg_all = $ttftGlobalAvg
    ttft_stddev = $ttftStdDev
    tokens_per_sec_avg = $tokensPerSecGlobalAvg
    max_degradation_pct = [math]::Round($maxDegradation, 1)
    stable = $isStable
}

Write-Host "📈 Métriques Globales :" -ForegroundColor Cyan
Write-Host "   TTFT moyen global      : ${ttftGlobalAvg}ms (±${ttftStdDev}ms)" -ForegroundColor White
Write-Host "   Tokens/sec moyen       : ${tokensPerSecGlobalAvg}" -ForegroundColor White
Write-Host "   Dégradation max        : $([math]::Round($maxDegradation, 1))%" -ForegroundColor $(if ($isStable) { "Green" } else { "Red" })
Write-Host "   Stabilité              : $(if ($isStable) { '✅ STABLE' } else { '⚠️ INSTABLE' })" -ForegroundColor $(if ($isStable) { "Green" } else { "Red" })

# ============================================
# SAUVEGARDE RÉSULTATS
# ============================================
$outputDir = Split-Path $OutputFile -Parent
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

$allResults | ConvertTo-Json -Depth 10 | Out-File -FilePath $OutputFile -Encoding UTF8

Write-Host "`n✅ Résultats sauvegardés : $OutputFile" -ForegroundColor Green
Write-Host "`n🎉 BENCHMARK COMPLÉTÉ`n" -ForegroundColor Cyan