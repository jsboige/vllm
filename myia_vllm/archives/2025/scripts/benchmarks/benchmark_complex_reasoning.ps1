# ============================================
# BENCHMARK REASONING COMPLEXE
# Phase 2.3 - Mission 11 Phase 8
# ============================================

<#
.SYNOPSIS
    Benchmark de capacités de raisonnement complexe du modèle Qwen3-32B

.DESCRIPTION
    Ce script teste les capacités de raisonnement du modèle sur 3 tâches spécialisées:
    1. Planification multi-étapes (10 étapes pour todo app)
    2. Raisonnement logique (problème mathématique)
    3. Analyse code Python (5 optimisations)
    
    Métriques collectées:
    - TTFT (Time To First Token)
    - Durée génération totale
    - Tokens générés
    - Tokens/seconde
    - Évaluation qualité (subjective)

.PARAMETER ApiUrl
    URL de l'API vLLM (défaut: http://localhost:5002/v1/chat/completions)

.PARAMETER OutputFile
    Chemin du fichier de sortie JSON

.EXAMPLE
    .\benchmark_complex_reasoning.ps1
    
.EXAMPLE
    .\benchmark_complex_reasoning.ps1 -OutputFile "custom_output.json"
#>

param(
    [string]$ApiUrl = "http://localhost:5002/v1/chat/completions",
    [string]$OutputFile = "myia_vllm/test_results/complex_reasoning_benchmark_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
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
Write-Host "BENCHMARK REASONING COMPLEXE" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan
Write-Host "🎯 Objectif : Tester capacités raisonnement Qwen3-32B" -ForegroundColor Yellow
Write-Host "📊 Tâches : 3 (Planification, Logique, Analyse Code)" -ForegroundColor Yellow
Write-Host "🌐 API URL : $ApiUrl`n" -ForegroundColor Yellow

# ============================================
# FONCTION : MESURER REQUÊTE DE REASONING
# ============================================
function Measure-ReasoningTask {
    param(
        [string]$Prompt,
        [int]$TaskId,
        [string]$TaskName,
        [int]$MaxTokens = 1000
    )
    
    $messages = @(
        @{
            role = "user"
            content = $Prompt
        }
    )
    
    $body = @{
        model = $Model
        messages = $messages
        max_tokens = $MaxTokens
        temperature = 0.3  # Température basse pour cohérence
        stream = $false
    } | ConvertTo-Json -Depth 10
    
    Write-Host "🔄 Exécution Tâche ${TaskId}: $TaskName..." -ForegroundColor Yellow
    
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
            -TimeoutSec 120  # 2 min timeout pour reasoning complexe
        
        $elapsed = $stopwatch.Elapsed.TotalMilliseconds
        $stopwatch.Stop()
        
        $responseData = $response.Content | ConvertFrom-Json
        $responseContent = $responseData.choices[0].message.content
        $tokensGenerated = if ($responseData.usage) { $responseData.usage.completion_tokens } else { 0 }
        $tokensPerSec = if ($elapsed -gt 0) { [math]::Round(($tokensGenerated / $elapsed) * 1000, 2) } else { 0 }
        
        Write-Host "  ✅ Complété en $([math]::Round($elapsed, 0))ms" -ForegroundColor Green
        Write-Host "  📝 Tokens générés: $tokensGenerated (${tokensPerSec} tok/sec)" -ForegroundColor Gray
        
        return @{
            Success = $true
            TaskId = $TaskId
            TaskName = $TaskName
            TTFT_ms = [math]::Round($elapsed, 2)
            TotalDuration_ms = [math]::Round($elapsed, 2)
            TokensGenerated = $tokensGenerated
            TokensPerSec = $tokensPerSec
            Response = $responseContent
            Prompt = $Prompt
        }
        
    } catch {
        Write-Host "  ❌ ERREUR: $($_.Exception.Message)" -ForegroundColor Red
        return @{
            Success = $false
            TaskId = $TaskId
            TaskName = $TaskName
            Error = $_.Exception.Message
            Prompt = $Prompt
        }
    }
}

# ============================================
# FONCTION : ÉVALUER QUALITÉ RÉPONSE
# ============================================
function Evaluate-ResponseQuality {
    param(
        [string]$Response,
        [int]$TaskId,
        [hashtable]$Criteria
    )
    
    Write-Host "`n📋 Évaluation qualité Tâche ${TaskId}:" -ForegroundColor Cyan
    
    $scores = @()
    $notes = @()
    
    foreach ($criterion in $Criteria.Keys) {
        $pattern = $Criteria[$criterion]
        $match = $Response -match $pattern
        
        if ($match) {
            Write-Host "  ✅ $criterion : Présent" -ForegroundColor Green
            $scores += 1
        } else {
            Write-Host "  ⚠️  $criterion : Absent" -ForegroundColor Yellow
            $scores += 0
        }
    }
    
    $scoreTotal = ($scores | Measure-Object -Sum).Sum
    $scoreMax = $Criteria.Count
    $scorePct = [math]::Round(($scoreTotal / $scoreMax) * 100, 0)
    
    # Déterminer qualité globale
    $quality = if ($scorePct -ge 80) {
        "excellent"
    } elseif ($scorePct -ge 60) {
        "bon"
    } elseif ($scorePct -ge 40) {
        "acceptable"
    } else {
        "insuffisant"
    }
    
    Write-Host "  📊 Score: ${scoreTotal}/${scoreMax} (${scorePct}%) - Qualité: $quality" -ForegroundColor $(
        if ($quality -eq "excellent") { "Green" }
        elseif ($quality -eq "bon") { "Yellow" }
        else { "Red" }
    )
    
    return @{
        Score = $scoreTotal
        ScoreMax = $scoreMax
        ScorePct = $scorePct
        Quality = $quality
        Details = $notes
    }
}

# ============================================
# DÉFINITION DES TÂCHES
# ============================================

# TÂCHE 1: Planification Multi-Étapes
$task1Prompt = @"
Créer un plan détaillé en 10 étapes pour développer une application web complète de gestion de tâches (todo app) avec authentification, base de données PostgreSQL, et déploiement sur AWS. 

Pour chaque étape, tu dois inclure:
1. L'objectif de l'étape
2. Les technologies recommandées
3. La durée estimée en heures

Présente le plan de manière structurée et numérotée.
"@

$task1Criteria = @{
    "10 étapes identifiables" = "(?:(?:étape|step)\s*(?:\d+|[a-z]+).*?){10,}"
    "Technologies mentionnées" = "(?:react|vue|angular|node|express|postgresql|aws|docker|nginx)"
    "Durées estimées" = "(?:heure|hour|jour|day|semaine|week)"
    "Structure cohérente" = "(?:authentification|auth|database|déploiement|deploy|test)"
}

# TÂCHE 2: Raisonnement Logique
$task2Prompt = @"
Résoudre ce problème logique étape par étape:

Si A > B et B > C, et C = 5, et A = 2*C, quelle est la valeur de B?

Détaille ton raisonnement en expliquant:
1. Les données connues
2. Les relations entre les variables
3. Le calcul pour trouver B
4. La vérification de la solution
"@

$task2Criteria = @{
    "Identification des données" = "(?:C\s*=\s*5|A\s*=\s*2.*C|A\s*=\s*10)"
    "Calcul de A" = "(?:A\s*=\s*10|2\s*\*\s*5\s*=\s*10)"
    "Déduction intervalle B" = "(?:5\s*<\s*B\s*<\s*10|B.*entre.*5.*10)"
    "Solution correcte" = "(?:B\s*=\s*[6-9]|B.*(?:6|7|8|9))"
}

# TÂCHE 3: Analyse Code Python
$task3Prompt = @"
Analyser ce code Python et identifier 5 optimisations possibles avec justifications:

```python
def process_data(items):
    result = []
    for item in items:
        if item['active'] == True:
            temp = {}
            temp['id'] = item['id']
            temp['name'] = item['name'].upper()
            temp['score'] = item['score'] * 2
            result.append(temp)
    return result
```

Pour chaque optimisation, fournis:
1. Le problème identifié
2. La solution proposée
3. Le code amélioré
4. Le gain attendu (performance/lisibilité)
"@

$task3Criteria = @{
    "List comprehension" = "(?:list\s+comprehension|compréhension.*liste)"
    "Dict literal" = "(?:dict.*literal|\{)"
    "Comparaison booléenne" = "(?:if\s+item.*:|== True.*inutile|is True)"
    "Filter ou map" = "(?:filter\s*\(|map\s*\()"
    "Code amélioré fourni" = "(?:```python|def\s+process_data)"
}

# ============================================
# EXÉCUTION DES BENCHMARKS
# ============================================

$allResults = @{
    test_date = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
    config = "chunked_only_safe"
    model = $Model
    tasks = @()
}

$tasks = @(
    @{
        Id = 1
        Name = "Planification Multi-Étapes"
        Prompt = $task1Prompt
        MaxTokens = 1200
        Criteria = $task1Criteria
    },
    @{
        Id = 2
        Name = "Raisonnement Logique"
        Prompt = $task2Prompt
        MaxTokens = 800
        Criteria = $task2Criteria
    },
    @{
        Id = 3
        Name = "Analyse Code Python"
        Prompt = $task3Prompt
        MaxTokens = 1500
        Criteria = $task3Criteria
    }
)

foreach ($task in $tasks) {
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "TÂCHE $($task.Id): $($task.Name)" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    
    # Exécuter la tâche
    $result = Measure-ReasoningTask `
        -Prompt $task.Prompt `
        -TaskId $task.Id `
        -TaskName $task.Name `
        -MaxTokens $task.MaxTokens
    
    if ($result.Success) {
        # Évaluer qualité
        $evaluation = Evaluate-ResponseQuality `
            -Response $result.Response `
            -TaskId $task.Id `
            -Criteria $task.Criteria
        
        # Ajouter évaluation au résultat
        $result.QualityAssessment = $evaluation.Quality
        $result.QualityScore = $evaluation.Score
        $result.QualityScoreMax = $evaluation.ScoreMax
        $result.QualityScorePct = $evaluation.ScorePct
        
        # Ajouter notes supplémentaires basées sur la tâche
        $notes = switch ($task.Id) {
            1 { 
                if ($result.TokensGenerated -ge 800) {
                    "Plan détaillé et complet"
                } else {
                    "Plan pourrait être plus détaillé"
                }
            }
            2 {
                if ($result.Response -match "(?:B\s*=\s*[6-9]|entre.*5.*10)") {
                    "Solution correcte identifiée"
                } else {
                    "Solution incomplète ou incorrecte"
                }
            }
            3 {
                $optCount = ([regex]::Matches($result.Response, "(?:optimisation|amélioration)", "IgnoreCase")).Count
                if ($optCount -ge 5) {
                    "$optCount optimisations proposées"
                } else {
                    "Seulement $optCount optimisations identifiées"
                }
            }
        }
        
        $result.Notes = $notes
    }
    
    # Ajouter aux résultats globaux
    $allResults.tasks += $result
    
    # Pause entre tâches
    if ($task.Id -lt $tasks.Count) {
        Write-Host "`nPause 2 secondes avant tâche suivante..." -ForegroundColor Gray
        Start-Sleep -Seconds 2
    }
}

# ============================================
# CALCUL STATISTIQUES GLOBALES
# ============================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "ANALYSE GLOBALE" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$successTasks = $allResults.tasks | Where-Object { $_.Success }

if ($successTasks.Count -gt 0) {
    $ttftAvg = [math]::Round(($successTasks | Measure-Object -Property TTFT_ms -Average).Average, 2)
    $tokensPerSecAvg = [math]::Round(($successTasks | Measure-Object -Property TokensPerSec -Average).Average, 2)
    
    # Calcul qualité globale
    $qualityCounts = @{}
    foreach ($task in $successTasks) {
        $quality = $task.QualityAssessment
        if ($qualityCounts.ContainsKey($quality)) {
            $qualityCounts[$quality]++
        } else {
            $qualityCounts[$quality] = 1
        }
    }
    
    # Déterminer qualité dominante
    $qualityOverall = ($qualityCounts.GetEnumerator() | Sort-Object -Property Value -Descending | Select-Object -First 1).Name
    
    $allResults.summary = @{
        ttft_avg = $ttftAvg
        tokens_per_sec_avg = $tokensPerSecAvg
        quality_overall = $qualityOverall
        successful_tasks = $successTasks.Count
        failed_tasks = $tasks.Count - $successTasks.Count
    }
    
    Write-Host "📈 Métriques Globales :" -ForegroundColor Cyan
    Write-Host "   TTFT moyen             : ${ttftAvg}ms" -ForegroundColor White
    Write-Host "   Tokens/sec moyen       : ${tokensPerSecAvg}" -ForegroundColor White
    Write-Host "   Qualité globale        : $qualityOverall" -ForegroundColor $(
        if ($qualityOverall -eq "excellent") { "Green" }
        elseif ($qualityOverall -eq "bon") { "Yellow" }
        else { "Red" }
    )
    Write-Host "   Tâches réussies        : $($successTasks.Count)/$($tasks.Count)" -ForegroundColor White
    
    # Résumé par tâche
    Write-Host "`n📊 Résumé par Tâche :" -ForegroundColor Cyan
    foreach ($task in $successTasks) {
        $color = if ($task.QualityAssessment -eq "excellent") { "Green" } 
                 elseif ($task.QualityAssessment -eq "bon") { "Yellow" } 
                 else { "Red" }
        Write-Host "   Tâche $($task.TaskId) ($($task.TaskName)):" -ForegroundColor Gray
        Write-Host "      TTFT: $($task.TTFT_ms)ms | Tokens: $($task.TokensGenerated) | Qualité: $($task.QualityAssessment)" -ForegroundColor $color
    }
}

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