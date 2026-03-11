# ============================================
# SCRIPT D'EXÉCUTION COMPLÈTE DES TESTS
# Service Medium - Qwen3-32B-AWQ
# ============================================

param(
    [string]$OutputDir = "./myia_vllm/test_results",
    [string]$ReportFile = "./myia_vllm/test_results_20251016.md",
    [int]$TimeoutSeconds = 60
)

$ErrorActionPreference = "Continue"
$BaseUrl = "http://localhost:5002"
$Model = "Qwen/Qwen3-32B-AWQ"
$ApiKey = $env:VLLM_API_KEY_MEDIUM

# Créer le répertoire de sortie
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# Initialiser les résultats
$TestResults = @()
$StartTime = Get-Date

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "EXÉCUTION COMPLÈTE DES TESTS - SERVICE MEDIUM" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan
Write-Host "URL de base : $BaseUrl" -ForegroundColor Yellow
Write-Host "Modèle : $Model" -ForegroundColor Yellow
Write-Host "Début : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n" -ForegroundColor Yellow

# ============================================
# FONCTION HELPER - TEST HTTP
# ============================================
function Test-HttpEndpoint {
    param(
        [string]$TestName,
        [string]$Url,
        [string]$Method = "GET",
        [hashtable]$Body = $null,
        [int]$Timeout = 60
    )
    
    Write-Host "[TEST] $TestName..." -ForegroundColor Cyan
    
    try {
        $params = @{
            Uri = $Url
            Method = $Method
            TimeoutSec = $Timeout
            ContentType = "application/json"
            Headers = @{
                "Authorization" = "Bearer $ApiKey"
            }
        }
        
        if ($Body) {
            $params.Body = ($Body | ConvertTo-Json -Depth 10)
        }
        
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        $response = Invoke-WebRequest @params
        $stopwatch.Stop()
        
        $result = @{
            Name = $TestName
            Status = "✅ PASS"
            StatusCode = $response.StatusCode
            Duration = $stopwatch.Elapsed.TotalSeconds
            Response = $response.Content
            Error = $null
        }
        
        Write-Host "  ✅ PASS - $($response.StatusCode) - $($stopwatch.Elapsed.TotalSeconds)s" -ForegroundColor Green
        
        return $result
        
    } catch {
        $result = @{
            Name = $TestName
            Status = "❌ FAIL"
            StatusCode = $null
            Duration = $null
            Response = $null
            Error = $_.Exception.Message
        }
        
        Write-Host "  ❌ FAIL - $($_.Exception.Message)" -ForegroundColor Red
        
        return $result
    }
}

# ============================================
# TESTS DE BASE (3 tests)
# ============================================
Write-Host "`n=== TESTS DE BASE ===" -ForegroundColor Yellow

# Test 1: Health Check
$result = Test-HttpEndpoint -TestName "Test 1: Health Check" -Url "$BaseUrl/health"
$TestResults += $result

# Test 2: Liste Modèles
$result = Test-HttpEndpoint -TestName "Test 2: Liste Modèles" -Url "$BaseUrl/v1/models"
$TestResults += $result

# Test 3: Chat Completion Simple
$body = @{
    model = $Model
    messages = @(
        @{
            role = "user"
            content = "Qu'est-ce que l'intelligence artificielle en une phrase ?"
        }
    )
    max_tokens = 100
    temperature = 0.7
}
$result = Test-HttpEndpoint -TestName "Test 3: Chat Completion Simple" -Url "$BaseUrl/v1/chat/completions" -Method "POST" -Body $body
$TestResults += $result

# ============================================
# TESTS DE RAISONNEMENT (2 tests)
# ============================================
Write-Host "`n=== TESTS DE RAISONNEMENT ===" -ForegroundColor Yellow

# Test 4: Chain-of-Thought Simple
$body = @{
    model = $Model
    messages = @(
        @{
            role = "user"
            content = "Résous ce problème étape par étape : Si j'ai 5 pommes et que j'en mange 2, combien me reste-t-il de pommes ? Explique ton raisonnement."
        }
    )
    max_tokens = 200
    temperature = 0.1
}
$result = Test-HttpEndpoint -TestName "Test 4: Chain-of-Thought Simple" -Url "$BaseUrl/v1/chat/completions" -Method "POST" -Body $body -Timeout 90
$TestResults += $result

# Test 5: Raisonnement Complexe (Problème des trains)
$body = @{
    model = $Model
    messages = @(
        @{
            role = "user"
            content = @"
Résous ce problème étape par étape :

Un train part de Paris à 10h00 à 120 km/h.
Un autre train part de Lyon (450 km de Paris) à 10h30 à 150 km/h vers Paris.
À quelle heure se croisent-ils ?

Pense étape par étape :
1. Distance initiale
2. Vitesses relatives
3. Calcul du temps
4. Heure de croisement
"@
        }
    )
    max_tokens = 500
    temperature = 0.1
}
$result = Test-HttpEndpoint -TestName "Test 5: Raisonnement Complexe (Trains)" -Url "$BaseUrl/v1/chat/completions" -Method "POST" -Body $body -Timeout 90
$TestResults += $result

# ============================================
# TESTS TOOL CALLING (1 test)
# ============================================
Write-Host "`n=== TESTS TOOL CALLING ===" -ForegroundColor Yellow

# Test 6: Tool Calling Basique
$body = @{
    model = $Model
    messages = @(
        @{
            role = "user"
            content = "Quelle est la météo à Paris aujourd'hui ?"
        }
    )
    tools = @(
        @{
            type = "function"
            function = @{
                name = "get_weather"
                description = "Obtenir la météo actuelle pour une ville"
                parameters = @{
                    type = "object"
                    properties = @{
                        city = @{
                            type = "string"
                            description = "Le nom de la ville"
                        }
                    }
                    required = @("city")
                }
            }
        }
    )
    max_tokens = 200
}
$result = Test-HttpEndpoint -TestName "Test 6: Tool Calling Basique" -Url "$BaseUrl/v1/chat/completions" -Method "POST" -Body $body -Timeout 90
$TestResults += $result

# ============================================
# TESTS PERFORMANCE (3 tests)
# ============================================
Write-Host "`n=== TESTS PERFORMANCE ===" -ForegroundColor Yellow

# Test 7: TTFT - Time To First Token (5 essais)
Write-Host "[TEST] Test 7: TTFT (5 essais)..." -ForegroundColor Cyan
$ttftResults = @()
for ($i = 1; $i -le 5; $i++) {
    try {
        $body = @{
            model = $Model
            messages = @(@{ role = "user"; content = "Bonjour" })
            max_tokens = 10
            stream = $true
        }
        
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        $response = Invoke-WebRequest -Uri "$BaseUrl/v1/chat/completions" -Method POST -Body ($body | ConvertTo-Json -Depth 10) -ContentType "application/json" -Headers @{"Authorization" = "Bearer $ApiKey"} -TimeoutSec 30
        $ttft = $stopwatch.Elapsed.TotalSeconds
        $stopwatch.Stop()
        
        $ttftResults += $ttft
        Write-Host "  Essai $i : $($ttft)s" -ForegroundColor Gray
    } catch {
        Write-Host "  Essai $i : ERREUR" -ForegroundColor Red
    }
}

if ($ttftResults.Count -gt 0) {
    $avgTtft = ($ttftResults | Measure-Object -Average).Average
    $result = @{
        Name = "Test 7: TTFT (Time To First Token)"
        Status = "✅ PASS"
        Duration = $avgTtft
        Response = "Moyenne TTFT: $($avgTtft)s sur $($ttftResults.Count) essais"
        Error = $null
    }
    Write-Host "  ✅ PASS - TTFT moyen: $($avgTtft)s" -ForegroundColor Green
} else {
    $result = @{
        Name = "Test 7: TTFT (Time To First Token)"
        Status = "❌ FAIL"
        Error = "Aucun essai réussi"
    }
    Write-Host "  ❌ FAIL" -ForegroundColor Red
}
$TestResults += $result

# Test 8: Throughput
$body = @{
    model = $Model
    messages = @(
        @{
            role = "user"
            content = "Écris un paragraphe de 200 mots sur l'intelligence artificielle."
        }
    )
    max_tokens = 300
}
$result = Test-HttpEndpoint -TestName "Test 8: Throughput" -Url "$BaseUrl/v1/chat/completions" -Method "POST" -Body $body -Timeout 120
$TestResults += $result

# Test 9: Charge Concurrente (10 requêtes)
Write-Host "[TEST] Test 9: Charge Concurrente (10 requêtes)..." -ForegroundColor Cyan
$jobs = @()
$jobResults = @()

for ($i = 1; $i -le 10; $i++) {
    $scriptBlock = {
        param($Url, $Model, $ApiKey, $i)
        
        try {
            $body = @{
                model = $Model
                messages = @(@{ role = "user"; content = "Test concurrent $i" })
                max_tokens = 50
            } | ConvertTo-Json -Depth 10
            
            $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
            $response = Invoke-WebRequest -Uri $Url -Method POST -Body $body -ContentType "application/json" -Headers @{"Authorization" = "Bearer $ApiKey"} -TimeoutSec 60
            $duration = $stopwatch.Elapsed.TotalSeconds
            
            return @{
                Success = $true
                Duration = $duration
                StatusCode = $response.StatusCode
            }
        } catch {
            return @{
                Success = $false
                Error = $_.Exception.Message
            }
        }
    }
    
    $jobs += Start-Job -ScriptBlock $scriptBlock -ArgumentList "$BaseUrl/v1/chat/completions", $Model, $ApiKey, $i
}

Write-Host "  Attente des 10 requêtes..." -ForegroundColor Gray
$jobs | Wait-Job -Timeout 120 | Out-Null

foreach ($job in $jobs) {
    $jobResult = Receive-Job -Job $job
    $jobResults += $jobResult
    Remove-Job -Job $job
}

$successCount = ($jobResults | Where-Object { $_.Success }).Count
if ($successCount -ge 8) {
    $result = @{
        Name = "Test 9: Charge Concurrente (10 requêtes)"
        Status = "✅ PASS"
        Response = "$successCount/10 requêtes réussies"
        Error = $null
    }
    Write-Host "  ✅ PASS - $successCount/10 requêtes réussies" -ForegroundColor Green
} else {
    $result = @{
        Name = "Test 9: Charge Concurrente (10 requêtes)"
        Status = "❌ FAIL"
        Error = "Seulement $successCount/10 requêtes réussies"
    }
    Write-Host "  ❌ FAIL - Seulement $successCount/10 requêtes réussies" -ForegroundColor Red
}
$TestResults += $result

# ============================================
# TESTS CONTEXTE LONG (3 tests)
# ============================================
Write-Host "`n=== TESTS CONTEXTE LONG ===" -ForegroundColor Yellow

# Test 10: Contexte 8k tokens
$longContext8k = "Le deep learning est une branche de l'intelligence artificielle. " * 800
$body = @{
    model = $Model
    messages = @(@{ role = "user"; content = "$longContext8k Résume ce texte en une phrase." })
    max_tokens = 100
}
$result = Test-HttpEndpoint -TestName "Test 10: Contexte 8k tokens" -Url "$BaseUrl/v1/chat/completions" -Method "POST" -Body $body -Timeout 120
$TestResults += $result

# Test 11: Contexte 32k tokens
$longContext32k = "L'intelligence artificielle transforme notre monde. " * 3000
$body = @{
    model = $Model
    messages = @(@{ role = "user"; content = "$longContext32k Résume ce texte en une phrase." })
    max_tokens = 100
}
$result = Test-HttpEndpoint -TestName "Test 11: Contexte 32k tokens" -Url "$BaseUrl/v1/chat/completions" -Method "POST" -Body $body -Timeout 180
$TestResults += $result

# Test 12: Contexte 64k tokens
$longContext64k = "Les modèles de langage sont fascinants. " * 6000
$body = @{
    model = $Model
    messages = @(@{ role = "user"; content = "$longContext64k Résume ce texte en une phrase." })
    max_tokens = 100
}
$result = Test-HttpEndpoint -TestName "Test 12: Contexte 64k tokens" -Url "$BaseUrl/v1/chat/completions" -Method "POST" -Body $body -Timeout 240
$TestResults += $result

# ============================================
# TESTS ROBUSTESSE (2 tests)
# ============================================
Write-Host "`n=== TESTS ROBUSTESSE ===" -ForegroundColor Yellow

# Test 13: Requêtes Invalides
Write-Host "[TEST] Test 13: Requêtes Invalides..." -ForegroundColor Cyan
$invalidTests = @()

# 13a: Modèle invalide
try {
    $body = @{
        model = "invalid-model"
        messages = @(@{ role = "user"; content = "test" })
    }
    $response = Invoke-WebRequest -Uri "$BaseUrl/v1/chat/completions" -Method POST -Body ($body | ConvertTo-Json) -ContentType "application/json" -Headers @{"Authorization" = "Bearer $ApiKey"} -TimeoutSec 30
    $invalidTests += @{ Test = "Modèle invalide"; Success = $response.StatusCode -ge 400 }
} catch {
    $invalidTests += @{ Test = "Modèle invalide"; Success = $true }
}

# 13b: Messages vides
try {
    $body = @{
        model = $Model
        messages = @()
    }
    $response = Invoke-WebRequest -Uri "$BaseUrl/v1/chat/completions" -Method POST -Body ($body | ConvertTo-Json) -ContentType "application/json" -Headers @{"Authorization" = "Bearer $ApiKey"} -TimeoutSec 30
    $invalidTests += @{ Test = "Messages vides"; Success = $response.StatusCode -ge 400 }
} catch {
    $invalidTests += @{ Test = "Messages vides"; Success = $true }
}

$invalidSuccessCount = ($invalidTests | Where-Object { $_.Success }).Count
if ($invalidSuccessCount -eq 2) {
    $result = @{
        Name = "Test 13: Requêtes Invalides"
        Status = "✅ PASS"
        Response = "Erreurs gérées correctement ($invalidSuccessCount/2)"
        Error = $null
    }
    Write-Host "  ✅ PASS - Erreurs gérées correctement" -ForegroundColor Green
} else {
    $result = @{
        Name = "Test 13: Requêtes Invalides"
        Status = "⚠️ PARTIAL"
        Response = "$invalidSuccessCount/2 erreurs gérées"
        Error = $null
    }
    Write-Host "  ⚠️ PARTIAL - $invalidSuccessCount/2 erreurs gérées" -ForegroundColor Yellow
}
$TestResults += $result

# Test 14: Streaming
$body = @{
    model = $Model
    messages = @(@{ role = "user"; content = "Raconte une courte histoire." })
    max_tokens = 150
    stream = $true
}
$result = Test-HttpEndpoint -TestName "Test 14: Streaming" -Url "$BaseUrl/v1/chat/completions" -Method "POST" -Body $body -Timeout 90
$TestResults += $result

# ============================================
# GÉNÉRATION DU RAPPORT
# ============================================
$EndTime = Get-Date
$TotalDuration = ($EndTime - $StartTime).TotalSeconds

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "GÉNÉRATION DU RAPPORT" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$PassCount = ($TestResults | Where-Object { $_.Status -eq "✅ PASS" }).Count
$FailCount = ($TestResults | Where-Object { $_.Status -eq "❌ FAIL" }).Count
$PartialCount = ($TestResults | Where-Object { $_.Status -eq "⚠️ PARTIAL" }).Count
$TotalTests = $TestResults.Count
$SuccessRate = [math]::Round(($PassCount / $TotalTests) * 100, 1)

# Créer le rapport Markdown
$report = @"
# 📊 RAPPORT DE TESTS - SERVICE MEDIUM QWEN3-32B-AWQ

**Date d'exécution** : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  
**Durée totale** : $([math]::Round($TotalDuration, 2))s  
**Modèle testé** : $Model  
**URL de base** : $BaseUrl

---

## 📈 RÉSULTATS GLOBAUX

| Métrique | Valeur |
|----------|--------|
| **Tests exécutés** | $TotalTests |
| **Tests réussis** | $PassCount ✅ |
| **Tests échoués** | $FailCount ❌ |
| **Tests partiels** | $PartialCount ⚠️ |
| **Taux de réussite** | **$SuccessRate%** |

---

## 📋 TABLEAU RÉCAPITULATIF DES TESTS

| # | Test | Statut | Durée | Détails |
|---|------|--------|-------|---------|
"@

$testNumber = 1
foreach ($result in $TestResults) {
    $duration = if ($result.Duration) { "$([math]::Round($result.Duration, 2))s" } else { "N/A" }
    $details = if ($result.Error) { $result.Error } elseif ($result.Response -and $result.Response.Length -lt 50) { $result.Response } else { "OK" }
    $report += "| $testNumber | $($result.Name) | $($result.Status) | $duration | $details |`n"
    $testNumber++
}

$report += @"

---

## 📊 DÉTAILS DES TESTS

"@

foreach ($result in $TestResults) {
    $report += @"

### $($result.Name)

- **Statut** : $($result.Status)
- **Durée** : $($result.Duration)s
"@
    
    if ($result.Error) {
        $report += "- **Erreur** : ``$($result.Error)```n"
    }
    
    if ($result.Response -and $result.Response.Length -lt 500) {
        $report += @"
- **Réponse** :
``````
$($result.Response)
``````

"@
    }
}

$report += @"

---

## 🎯 RECOMMANDATIONS PRODUCTION

### ✅ Points Forts
"@

if ($PassCount -ge 10) {
    $report += @"

- Taux de réussite élevé : $SuccessRate%
- Service stable et opérationnel
"@
}

$report += @"


### ⚠️ Points d'Attention
"@

if ($FailCount -gt 0) {
    $report += @"

- $FailCount test(s) échoué(s) nécessitent investigation
"@
}

$report += @"


### 🚀 Recommandations

"@

if ($SuccessRate -ge 90) {
    $report += "- ✅ **PRÊT POUR PRODUCTION** - Le service passe tous les tests critiques`n"
} elseif ($SuccessRate -ge 70) {
    $report += "- ⚠️ **VALIDATION NÉCESSAIRE** - Corriger les tests échoués avant production`n"
} else {
    $report += "- ❌ **NON RECOMMANDÉ POUR PRODUCTION** - Trop de tests échoués`n"
}

$report += @"

---

## 📝 NOTES

- Tests exécutés automatiquement via PowerShell
- Tous les tests ont un timeout de 60-240s selon complexité
- Container testé : myia_vllm-medium-qwen3
- Port : 5002

**Fin du rapport**
"@

# Sauvegarder le rapport
$report | Out-File -FilePath $ReportFile -Encoding UTF8

Write-Host "✅ Rapport généré : $ReportFile" -ForegroundColor Green
Write-Host "`nRÉSUMÉ FINAL :" -ForegroundColor Cyan
Write-Host "  Tests réussis : $PassCount/$TotalTests ($SuccessRate%)" -ForegroundColor $(if ($SuccessRate -ge 80) { "Green" } else { "Yellow" })
Write-Host "  Durée totale : $([math]::Round($TotalDuration, 2))s`n" -ForegroundColor Gray