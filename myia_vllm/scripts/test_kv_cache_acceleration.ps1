# ============================================
# TEST KV CACHE ACCELERATION
# Mesure l'accélération sur continuations de conversation
# ============================================

param(
    [int]$ConversationTurns = 5,
    [int]$WarmupTurns = 2,
    [string]$OutputFile = "./myia_vllm/test_results/kv_cache_test.md"
)

$ErrorActionPreference = "Stop"
$BaseUrl = "http://localhost:5002"
$Model = "Qwen/Qwen3-32B-AWQ"
$ApiKey = "Y7PSM158SR952HCAARSLQ344RRPJTDI3"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "TEST KV CACHE ACCELERATION" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan
Write-Host "🎯 Objectif : Mesurer l'accélération par KV Cache" -ForegroundColor Yellow
Write-Host "📊 Tours de conversation : $ConversationTurns" -ForegroundColor Yellow
Write-Host "🔥 Tours de warmup : $WarmupTurns`n" -ForegroundColor Yellow

# ============================================
# FONCTION : MESURER TTFT
# ============================================
function Measure-TTFT {
    param(
        [array]$Messages,
        [string]$TestName
    )
    
    $body = @{
        model = $Model
        messages = $Messages
        max_tokens = 50
        temperature = 0.7
        stream = $false
    } | ConvertTo-Json -Depth 10
    
    try {
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        
        $response = Invoke-WebRequest `
            -Uri "$BaseUrl/v1/chat/completions" `
            -Method POST `
            -Body $body `
            -ContentType "application/json" `
            -Headers @{"Authorization" = "Bearer $ApiKey"} `
            -TimeoutSec 30
        
        $ttft = $stopwatch.Elapsed.TotalMilliseconds
        $stopwatch.Stop()
        
        Write-Host "  [$TestName] TTFT: $([math]::Round($ttft, 2))ms" -ForegroundColor $(if ($ttft -lt 500) { "Green" } elseif ($ttft -lt 1000) { "Yellow" } else { "Red" })
        
        return @{
            Success = $true
            TTFT_ms = $ttft
            Response = $response.Content
        }
        
    } catch {
        Write-Host "  [$TestName] ERREUR: $($_.Exception.Message)" -ForegroundColor Red
        return @{
            Success = $false
            TTFT_ms = $null
            Error = $_.Exception.Message
        }
    }
}

# ============================================
# TEST 1: CONVERSATION UNIQUE (KV Cache Hit)
# ============================================
Write-Host "`n=== TEST 1: CONVERSATION UNIQUE (KV CACHE) ===" -ForegroundColor Cyan
Write-Host "Simulation d'une conversation continue pour mesurer l'accélération du cache`n" -ForegroundColor Gray

$conversationMessages = @()
$results_conversation = @()

# Premier message (CACHE MISS)
Write-Host "[Tour 1] Premier message (CACHE MISS attendu)..." -ForegroundColor Yellow
$conversationMessages += @{
    role = "user"
    content = "Bonjour ! Je m'appelle Alice. Peux-tu te présenter ?"
}
$result = Measure-TTFT -Messages $conversationMessages -TestName "Tour 1 - MISS"
$results_conversation += $result

if ($result.Success) {
    # Ajouter la réponse de l'assistant
    try {
        $responseData = $result.Response | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($responseData.choices -and $responseData.choices[0].message) {
            $conversationMessages += @{
                role = "assistant"
                content = $responseData.choices[0].message.content
            }
        }
    } catch {
        Write-Host "  Avertissement: Impossible de parser la réponse" -ForegroundColor Yellow
    }
}

Start-Sleep -Seconds 1

# Tours suivants (CACHE HIT attendu)
for ($i = 2; $i -le $ConversationTurns; $i++) {
    Write-Host "[Tour $i] Continuation (CACHE HIT attendu)..." -ForegroundColor Yellow
    
    $userMessages = @(
        "Quelle est ta couleur préférée ?",
        "Parle-moi de l'intelligence artificielle.",
        "Quel est ton modèle de langage ?",
        "Que penses-tu de la technologie ?",
        "Raconte-moi une blague.",
        "Quel temps fait-il aujourd'hui ?",
        "Quelle est la capitale de la France ?",
        "Peux-tu compter jusqu'à 5 ?"
    )
    
    $conversationMessages += @{
        role = "user"
        content = $userMessages[($i - 2) % $userMessages.Count]
    }
    
    $result = Measure-TTFT -Messages $conversationMessages -TestName "Tour $i - HIT"
    $results_conversation += $result
    
    if ($result.Success) {
        # Ajouter la réponse de l'assistant
        try {
            $responseData = $result.Response | ConvertFrom-Json -ErrorAction SilentlyContinue
            if ($responseData.choices -and $responseData.choices[0].message) {
                $conversationMessages += @{
                    role = "assistant"
                    content = $responseData.choices[0].message.content
                }
            }
        } catch {
            # Ignorer les erreurs de parsing
        }
    }
    
    Start-Sleep -Milliseconds 500
}

# ============================================
# TEST 2: MESSAGES INDÉPENDANTS (Pas de cache)
# ============================================
Write-Host "`n=== TEST 2: MESSAGES INDÉPENDANTS (PAS DE CACHE) ===" -ForegroundColor Cyan
Write-Host "Envoi de messages indépendants pour comparaison (pas de continuité)`n" -ForegroundColor Gray

$results_independent = @()

$independentMessages = @(
    "Quelle est la capitale de l'Allemagne ?",
    "Explique la photosynthèse en une phrase.",
    "Quel est le plus haut sommet du monde ?",
    "Qui a peint la Joconde ?",
    "Combien font 7 multiplié par 8 ?"
)

for ($i = 0; $i -lt [Math]::Min($ConversationTurns, $independentMessages.Count); $i++) {
    Write-Host "[Message $($i+1)] Requête indépendante (CACHE MISS attendu)..." -ForegroundColor Yellow
    
    $singleMessage = @(
        @{
            role = "user"
            content = $independentMessages[$i]
        }
    )
    
    $result = Measure-TTFT -Messages $singleMessage -TestName "Indép $($i+1) - MISS"
    $results_independent += $result
    
    Start-Sleep -Milliseconds 500
}

# ============================================
# TEST 3: PREFILL CACHE (Contexte préchargé)
# ============================================
Write-Host "`n=== TEST 3: PREFILL CACHE (CONTEXTE PRÉCHARGÉ) ===" -ForegroundColor Cyan
Write-Host "Test avec un contexte initial large pour voir l'impact du cache`n" -ForegroundColor Gray

$results_prefill = @()

# Contexte initial volumineux
$systemContext = @"
Tu es un assistant IA expert en technologie, science et histoire. 
Voici quelques informations de contexte importantes :
- L'intelligence artificielle a connu des progrès remarquables ces dernières années
- Les modèles de langage comme GPT et Qwen sont des transformers
- La France est un pays d'Europe occidentale
- Paris est la capitale de la France
- Le machine learning est une branche de l'IA
"@

$prefillMessages = @(
    @{
        role = "system"
        content = $systemContext
    },
    @{
        role = "user"
        content = "Bonjour, peux-tu m'aider ?"
    }
)

Write-Host "[Prefill 1] Premier message avec contexte (CACHE MISS)..." -ForegroundColor Yellow
$result = Measure-TTFT -Messages $prefillMessages -TestName "Prefill 1 - MISS"
$results_prefill += $result

# Ajouter continuations
if ($result.Success) {
    try {
        $responseData = $result.Response | ConvertFrom-Json -ErrorAction SilentlyContinue
        if ($responseData.choices -and $responseData.choices[0].message) {
            $prefillMessages += @{
                role = "assistant"
                content = $responseData.choices[0].message.content
            }
        }
    } catch {
        # Ignorer les erreurs de parsing
    }
}

Start-Sleep -Seconds 1

# Continuation avec même contexte (CACHE HIT attendu)
for ($i = 2; $i -le 3; $i++) {
    Write-Host "[Prefill $i] Continuation avec contexte (CACHE HIT attendu)..." -ForegroundColor Yellow
    
    $prefillMessages += @{
        role = "user"
        content = "Dis-moi quelque chose d'intéressant sur l'IA."
    }
    
    $result = Measure-TTFT -Messages $prefillMessages -TestName "Prefill $i - HIT"
    $results_prefill += $result
    
    if ($result.Success) {
        try {
            $responseData = $result.Response | ConvertFrom-Json -ErrorAction SilentlyContinue
            if ($responseData.choices -and $responseData.choices[0].message) {
                $prefillMessages += @{
                    role = "assistant"
                    content = $responseData.choices[0].message.content
                }
            }
        } catch {
            # Ignorer les erreurs de parsing
        }
    }
    
    Start-Sleep -Milliseconds 500
}

# ============================================
# ANALYSE ET RAPPORT
# ============================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "ANALYSE DES RÉSULTATS" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Calculs conversation
$conv_success = $results_conversation | Where-Object { $_.Success }
$conv_first_ttft = $conv_success[0].TTFT_ms
$conv_subsequent_ttft = ($conv_success[1..($conv_success.Count-1)] | Measure-Object -Property TTFT_ms -Average).Average
$conv_speedup = if ($conv_subsequent_ttft -gt 0) { [math]::Round($conv_first_ttft / $conv_subsequent_ttft, 2) } else { 0 }

# Calculs indépendants
$indep_success = $results_independent | Where-Object { $_.Success }
$indep_avg_ttft = ($indep_success | Measure-Object -Property TTFT_ms -Average).Average

# Calculs prefill
$prefill_success = $results_prefill | Where-Object { $_.Success }
$prefill_first_ttft = if ($prefill_success.Count -gt 0) { $prefill_success[0].TTFT_ms } else { 0 }
$prefill_subsequent_ttft = if ($prefill_success.Count -gt 1) { 
    ($prefill_success[1..($prefill_success.Count-1)] | Measure-Object -Property TTFT_ms -Average).Average 
} else { 0 }
$prefill_speedup = if ($prefill_subsequent_ttft -gt 0) { [math]::Round($prefill_first_ttft / $prefill_subsequent_ttft, 2) } else { 0 }

Write-Host "📊 RÉSUMÉ :" -ForegroundColor Cyan
Write-Host "`n1️⃣  CONVERSATION CONTINUE (KV Cache actif)" -ForegroundColor Yellow
Write-Host "   Premier message (MISS) : $([math]::Round($conv_first_ttft, 2))ms" -ForegroundColor White
Write-Host "   Messages suivants (HIT) : $([math]::Round($conv_subsequent_ttft, 2))ms" -ForegroundColor White
Write-Host "   🚀 Accélération : x$conv_speedup" -ForegroundColor $(if ($conv_speedup -ge 2) { "Green" } elseif ($conv_speedup -ge 1.5) { "Yellow" } else { "Red" })

Write-Host "`n2️⃣  MESSAGES INDÉPENDANTS (Pas de cache)" -ForegroundColor Yellow
Write-Host "   TTFT moyen : $([math]::Round($indep_avg_ttft, 2))ms" -ForegroundColor White

Write-Host "`n3️⃣  PREFILL CACHE (Contexte préchargé)" -ForegroundColor Yellow
Write-Host "   Premier message (MISS) : $([math]::Round($prefill_first_ttft, 2))ms" -ForegroundColor White
Write-Host "   Messages suivants (HIT) : $([math]::Round($prefill_subsequent_ttft, 2))ms" -ForegroundColor White
Write-Host "   🚀 Accélération : x$prefill_speedup" -ForegroundColor $(if ($prefill_speedup -ge 2) { "Green" } elseif ($prefill_speedup -ge 1.5) { "Yellow" } else { "Red" })

# ============================================
# GÉNÉRATION RAPPORT MARKDOWN
# ============================================
$report = @"
# 🚀 TEST KV CACHE ACCELERATION - QWEN3-32B-AWQ

**Date d'exécution** : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  
**Modèle testé** : $Model  
**Tours de conversation** : $ConversationTurns

---

## 📊 RÉSULTATS GLOBAUX

### 1️⃣ Conversation Continue (KV Cache actif)

| Métrique | Valeur |
|----------|--------|
| **Premier message (CACHE MISS)** | $([math]::Round($conv_first_ttft, 2))ms |
| **Messages suivants (CACHE HIT)** | $([math]::Round($conv_subsequent_ttft, 2))ms |
| **🚀 Accélération** | **x$conv_speedup** |
| **Gain de performance** | $([math]::Round((1 - ($conv_subsequent_ttft / $conv_first_ttft)) * 100, 1))% |

### 2️⃣ Messages Indépendants (Pas de cache)

| Métrique | Valeur |
|----------|--------|
| **TTFT moyen** | $([math]::Round($indep_avg_ttft, 2))ms |

### 3️⃣ Prefill Cache (Contexte préchargé)

| Métrique | Valeur |
|----------|--------|
| **Premier message (CACHE MISS)** | $([math]::Round($prefill_first_ttft, 2))ms |
| **Messages suivants (CACHE HIT)** | $([math]::Round($prefill_subsequent_ttft, 2))ms |
| **🚀 Accélération** | **x$prefill_speedup** |
| **Gain de performance** | $([math]::Round((1 - ($prefill_subsequent_ttft / $prefill_first_ttft)) * 100, 1))% |

---

## 📈 DÉTAILS DES MESURES

### Conversation Continue

| Tour | Type | TTFT (ms) | Statut |
|------|------|-----------|--------|
"@

$tourNum = 1
foreach ($result in $results_conversation) {
    $type = if ($tourNum -eq 1) { "MISS" } else { "HIT" }
    $ttft = if ($result.Success) { [math]::Round($result.TTFT_ms, 2) } else { "ERREUR" }
    $status = if ($result.Success) { "✅" } else { "❌" }
    $report += "| $tourNum | $type | $ttft | $status |`n"
    $tourNum++
}

$report += @"

### Messages Indépendants

| Message | TTFT (ms) | Statut |
|---------|-----------|--------|
"@

$msgNum = 1
foreach ($result in $results_independent) {
    $ttft = if ($result.Success) { [math]::Round($result.TTFT_ms, 2) } else { "ERREUR" }
    $status = if ($result.Success) { "✅" } else { "❌" }
    $report += "| $msgNum | $ttft | $status |`n"
    $msgNum++
}

$report += @"

### Prefill Cache

| Tour | Type | TTFT (ms) | Statut |
|------|------|-----------|--------|
"@

$tourNum = 1
foreach ($result in $results_prefill) {
    $type = if ($tourNum -eq 1) { "MISS" } else { "HIT" }
    $ttft = if ($result.Success) { [math]::Round($result.TTFT_ms, 2) } else { "ERREUR" }
    $status = if ($result.Success) { "✅" } else { "❌" }
    $report += "| $tourNum | $type | $ttft | $status |`n"
    $tourNum++
}

$report += @"

---

## 🎯 CONCLUSIONS

### Efficacité du KV Cache

"@

if ($conv_speedup -ge 2) {
    $report += "✅ **EXCELLENT** - Le KV Cache offre une accélération **x$conv_speedup** sur les continuations.`n"
} elseif ($conv_speedup -ge 1.5) {
    $report += "⚠️ **BON** - Le KV Cache offre une accélération **x$conv_speedup** sur les continuations.`n"
} else {
    $report += "❌ **FAIBLE** - Le KV Cache offre seulement une accélération **x$conv_speedup**.`n"
}

$report += @"

### Recommandations

"@

if ($conv_speedup -ge 2) {
    $report += @"
- ✅ Le KV Cache est très efficace pour les conversations continues
- ✅ Privilégier les sessions avec contexte partagé
- ✅ Le système est bien configuré pour les dialogues multi-tours
"@
} else {
    $report += @"
- ⚠️ Vérifier la configuration du KV Cache (`--enable-prefix-caching`)
- ⚠️ Augmenter `--gpu-memory-utilization` si possible
- ⚠️ Vérifier que le cache n'est pas éjecté trop rapidement
"@
}

$report += @"


### Métriques Clés

- **Premier TTFT (cold)** : $([math]::Round($conv_first_ttft, 2))ms
- **TTFT optimisé (warm)** : $([math]::Round($conv_subsequent_ttft, 2))ms
- **Gain absolu** : $([math]::Round($conv_first_ttft - $conv_subsequent_ttft, 2))ms
- **Accélération** : x$conv_speedup

---

**Fin du rapport**
"@

# Sauvegarder le rapport
New-Item -ItemType Directory -Force -Path (Split-Path $OutputFile) | Out-Null
$report | Out-File -FilePath $OutputFile -Encoding UTF8

Write-Host "`n✅ Rapport sauvegardé : $OutputFile" -ForegroundColor Green
Write-Host "`n🎉 TEST TERMINÉ`n" -ForegroundColor Cyan