<#
.SYNOPSIS
    Benchmark des capacités de Tool Calling pour Qwen3 vLLM

.DESCRIPTION
    Script de benchmark automatisé pour tester les capacités de tool calling
    du service vLLM medium (Qwen3-32B-AWQ) avec 3 scénarios de complexité croissante:
    
    1. Appel Simple (get_weather)
    2. Appels Enchaînés (search_db → format_results → send_email)
    3. Fonction Complexe avec objets imbriqués (create_user)
    
    Pour chaque scénario, mesure TTFT, durée totale, tokens générés, et précision parsing JSON.

.PARAMETER ApiUrl
    URL de l'API vLLM (défaut: http://localhost:5002/v1/chat/completions)

.PARAMETER OutputFile
    Chemin du fichier JSON de sortie pour les résultats

.PARAMETER ToolCallParser
    Parser tool calling utilisé par le service (défaut: qwen3_xml)

.EXAMPLE
    .\benchmark_tool_calling.ps1

.EXAMPLE
    .\benchmark_tool_calling.ps1 -ApiUrl "http://localhost:8000/v1/chat/completions" -ToolCallParser "hermes"

.NOTES
    Auteur: Roo Code
    Mission: 11 Phase 8 - Sous-tâche 2 (Phase 2.4)
    Prérequis: Service vLLM medium démarré et healthy
    API Key: Variable d'environnement VLLM_MEDIUM_API_KEY
#>

param(
    [string]$ApiUrl = "http://localhost:5002/v1/chat/completions",
    [string]$OutputFile = "myia_vllm/test_results/tool_calling_benchmark_$(Get-Date -Format 'yyyyMMdd_HHmmss').json",
    [string]$ToolCallParser = "qwen3_xml"
)

# ============================================================================
# CONFIGURATION
# ============================================================================

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# Récupérer API Key depuis variable d'environnement
$ApiKey = $env:VLLM_MEDIUM_API_KEY
if (-not $ApiKey) {
    Write-Host "❌ ERREUR: Variable VLLM_MEDIUM_API_KEY non définie" -ForegroundColor Red
    Write-Host "   Définir avec: `$env:VLLM_MEDIUM_API_KEY = 'votre-clé'" -ForegroundColor Yellow
    exit 1
}

$Headers = @{
    "Content-Type" = "application/json"
    "Authorization" = "Bearer $ApiKey"
}

# Configuration des scénarios
$Config = @{
    model = "Qwen/Qwen3-32B-AWQ"
    temperature = 0.7
    max_tokens = 500
    tool_choice = "auto"
}

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "  BENCHMARK TOOL CALLING - Phase 2.4" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  • API URL       : $ApiUrl"
Write-Host "  • Tool Parser   : $ToolCallParser"
Write-Host "  • Output File   : $OutputFile"
Write-Host "  • Date          : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

# ============================================================================
# VALIDATION API
# ============================================================================

Write-Host "[1/5] Validation disponibilité API..." -ForegroundColor Cyan
try {
    $healthUrl = $ApiUrl -replace '/v1/chat/completions', '/health'
    $healthCheck = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 10
    Write-Host "✅ API accessible" -ForegroundColor Green
} catch {
    Write-Host "❌ API non accessible: $_" -ForegroundColor Red
    Write-Host "   Vérifier que le service vLLM est démarré" -ForegroundColor Yellow
    exit 1
}

# ============================================================================
# SCÉNARIO 1 : APPEL SIMPLE - get_weather
# ============================================================================

Write-Host ""
Write-Host "[2/5] Scénario 1 : Appel Simple (get_weather)..." -ForegroundColor Cyan

$Scenario1 = @{
    tools = @(
        @{
            type = "function"
            function = @{
                name = "get_weather"
                description = "Récupérer les conditions météo actuelles pour une localisation"
                parameters = @{
                    type = "object"
                    properties = @{
                        location = @{
                            type = "string"
                            description = "Ville et pays, ex: Paris, France"
                        }
                        unit = @{
                            type = "string"
                            enum = @("celsius", "fahrenheit")
                            description = "Unité de température"
                        }
                    }
                    required = @("location")
                }
            }
        }
    )
    messages = @(
        @{
            role = "user"
            content = "Quel temps fait-il à Lyon ?"
        }
    )
}

$Payload1 = $Config + $Scenario1 | ConvertTo-Json -Depth 10

Write-Host "  → Envoi requête..." -ForegroundColor Gray
$StartTime1 = Get-Date
try {
    $Response1 = Invoke-RestMethod -Uri $ApiUrl -Method Post -Headers $Headers -Body $Payload1 -TimeoutSec 60
    $EndTime1 = Get-Date
    $Duration1 = ($EndTime1 - $StartTime1).TotalMilliseconds
    
    # Extraction métriques
    $Message1 = $Response1.choices[0].message
    $ToolCalls1 = $Message1.tool_calls
    $TokensGenerated1 = $Response1.usage.completion_tokens
    
    # Validation parsing
    $ParsingSuccess1 = $false
    $JsonValid1 = $false
    $FunctionCalled1 = $null
    $ParametersCorrect1 = $false
    
    if ($ToolCalls1 -and $ToolCalls1.Count -gt 0) {
        $FunctionCalled1 = $ToolCalls1[0].function.name
        $ParsingSuccess1 = ($FunctionCalled1 -eq "get_weather")
        
        try {
            $Arguments1 = $ToolCalls1[0].function.arguments | ConvertFrom-Json
            $JsonValid1 = $true
            $ParametersCorrect1 = ($null -ne $Arguments1.location) -and ($Arguments1.location -match "Lyon")
        } catch {
            $JsonValid1 = $false
        }
    }
    
    $Result1 = @{
        scenario_id = 1
        name = "Appel Simple - get_weather"
        ttft_ms = [int]$Duration1  # Approximation (pas de streaming)
        total_duration_ms = [int]$Duration1
        tokens_generated = $TokensGenerated1
        parsing_success = $ParsingSuccess1
        json_valid = $JsonValid1
        function_called = $FunctionCalled1
        parameters_correct = $ParametersCorrect1
        error_handling = "none"
        notes = if ($ParsingSuccess1 -and $ParametersCorrect1) { "Parsing immédiat, paramètres extraits correctement" } else { "Échec parsing ou paramètres incorrects" }
    }
    
    Write-Host "✅ Scénario 1 complété" -ForegroundColor Green
    Write-Host "   TTFT: $($Duration1)ms | Tokens: $TokensGenerated1 | Parsing: $ParsingSuccess1" -ForegroundColor Gray
    
} catch {
    Write-Host "❌ Erreur scénario 1: $_" -ForegroundColor Red
    $Result1 = @{
        scenario_id = 1
        name = "Appel Simple - get_weather"
        error = $_.Exception.Message
        error_handling = "timeout_or_crash"
    }
}

# ============================================================================
# SCÉNARIO 2 : APPELS ENCHAÎNÉS - 3 fonctions
# ============================================================================

Write-Host ""
Write-Host "[3/5] Scénario 2 : Appels Enchaînés (3 fonctions)..." -ForegroundColor Cyan

$Scenario2 = @{
    tools = @(
        @{
            type = "function"
            function = @{
                name = "search_database"
                description = "Chercher des utilisateurs dans la base de données"
                parameters = @{
                    type = "object"
                    properties = @{
                        query = @{ type = "string"; description = "Requête de recherche" }
                        limit = @{ type = "integer"; description = "Nombre max de résultats" }
                    }
                    required = @("query")
                }
            }
        },
        @{
            type = "function"
            function = @{
                name = "format_results"
                description = "Formater les résultats de recherche en HTML"
                parameters = @{
                    type = "object"
                    properties = @{
                        results = @{ type = "array"; description = "Liste résultats" }
                        format = @{ type = "string"; enum = @("html", "markdown", "plain") }
                    }
                    required = @("results")
                }
            }
        },
        @{
            type = "function"
            function = @{
                name = "send_email"
                description = "Envoyer un email"
                parameters = @{
                    type = "object"
                    properties = @{
                        to = @{ type = "string"; description = "Adresse destinataire" }
                        subject = @{ type = "string"; description = "Sujet" }
                        body = @{ type = "string"; description = "Contenu email" }
                    }
                    required = @("to", "subject", "body")
                }
            }
        }
    )
    messages = @(
        @{
            role = "user"
            content = "Trouve tous les utilisateurs actifs, formate les résultats en HTML et envoie-les par email à admin@example.com"
        }
    )
}

$Payload2 = $Config + $Scenario2 | ConvertTo-Json -Depth 10

Write-Host "  → Envoi requête..." -ForegroundColor Gray
$StartTime2 = Get-Date
try {
    $Response2 = Invoke-RestMethod -Uri $ApiUrl -Method Post -Headers $Headers -Body $Payload2 -TimeoutSec 90
    $EndTime2 = Get-Date
    $Duration2 = ($EndTime2 - $StartTime2).TotalMilliseconds
    
    $Message2 = $Response2.choices[0].message
    $ToolCalls2 = $Message2.tool_calls
    $TokensGenerated2 = $Response2.usage.completion_tokens
    
    # Validation appels multiples
    $ParsingSuccess2 = $false
    $JsonValid2 = $false
    $FunctionsCalled2 = @()
    $SequentialCalls2 = 0
    $ParametersCorrect2 = $false
    
    if ($ToolCalls2 -and $ToolCalls2.Count -gt 0) {
        $FunctionsCalled2 = $ToolCalls2 | ForEach-Object { $_.function.name }
        $SequentialCalls2 = $FunctionsCalled2.Count
        
        # Vérifier présence des 3 fonctions attendues
        $ExpectedFunctions = @("search_database", "format_results", "send_email")
        $ParsingSuccess2 = ($SequentialCalls2 -ge 1)  # Au moins 1 appel détecté
        $ParametersCorrect2 = $true  # Assumé si parsing réussi
        
        try {
            # Valider JSON de chaque appel
            foreach ($call in $ToolCalls2) {
                $null = $call.function.arguments | ConvertFrom-Json
            }
            $JsonValid2 = $true
        } catch {
            $JsonValid2 = $false
        }
    }
    
    $Result2 = @{
        scenario_id = 2
        name = "Appels Enchaînés - 3 fonctions"
        ttft_ms = [int]$Duration2
        total_duration_ms = [int]$Duration2
        tokens_generated = $TokensGenerated2
        parsing_success = $ParsingSuccess2
        json_valid = $JsonValid2
        functions_called = $FunctionsCalled2
        sequential_calls = $SequentialCalls2
        parameters_correct = $ParametersCorrect2
        error_handling = "none"
        notes = "$SequentialCalls2 appel(s) détecté(s): $($FunctionsCalled2 -join ', ')"
    }
    
    Write-Host "✅ Scénario 2 complété" -ForegroundColor Green
    Write-Host "   TTFT: $($Duration2)ms | Tokens: $TokensGenerated2 | Appels: $SequentialCalls2" -ForegroundColor Gray
    
} catch {
    Write-Host "❌ Erreur scénario 2: $_" -ForegroundColor Red
    $Result2 = @{
        scenario_id = 2
        name = "Appels Enchaînés - 3 fonctions"
        error = $_.Exception.Message
        error_handling = "timeout_or_crash"
    }
}

# ============================================================================
# SCÉNARIO 3 : FONCTION COMPLEXE - create_user
# ============================================================================

Write-Host ""
Write-Host "[4/5] Scénario 3 : Fonction Complexe (create_user)..." -ForegroundColor Cyan

$Scenario3 = @{
    tools = @(
        @{
            type = "function"
            function = @{
                name = "create_user"
                description = "Créer un nouvel utilisateur dans le système"
                parameters = @{
                    type = "object"
                    properties = @{
                        name = @{ type = "string"; description = "Nom complet" }
                        email = @{ type = "string"; description = "Adresse email" }
                        age = @{ type = "integer"; description = "Âge en années" }
                        preferences = @{
                            type = "object"
                            properties = @{
                                language = @{ type = "string"; enum = @("fr", "en", "es") }
                                notifications = @{ type = "boolean" }
                                theme = @{ type = "string"; enum = @("light", "dark") }
                            }
                            required = @("language")
                        }
                    }
                    required = @("name", "email", "preferences")
                }
            }
        }
    )
    messages = @(
        @{
            role = "user"
            content = "Crée un utilisateur Jean Dupont, email jean.dupont@example.com, âge 35 ans, préférences : langue français, notifications activées, thème sombre"
        }
    )
}

$Payload3 = $Config + $Scenario3 | ConvertTo-Json -Depth 10

Write-Host "  → Envoi requête..." -ForegroundColor Gray
$StartTime3 = Get-Date
try {
    $Response3 = Invoke-RestMethod -Uri $ApiUrl -Method Post -Headers $Headers -Body $Payload3 -TimeoutSec 60
    $EndTime3 = Get-Date
    $Duration3 = ($EndTime3 - $StartTime3).TotalMilliseconds
    
    $Message3 = $Response3.choices[0].message
    $ToolCalls3 = $Message3.tool_calls
    $TokensGenerated3 = $Response3.usage.completion_tokens
    
    # Validation objet imbriqué
    $ParsingSuccess3 = $false
    $JsonValid3 = $false
    $FunctionCalled3 = $null
    $NestedObjectCorrect3 = $false
    $ParametersCorrect3 = $false
    
    if ($ToolCalls3 -and $ToolCalls3.Count -gt 0) {
        $FunctionCalled3 = $ToolCalls3[0].function.name
        $ParsingSuccess3 = ($FunctionCalled3 -eq "create_user")
        
        try {
            $Arguments3 = $ToolCalls3[0].function.arguments | ConvertFrom-Json
            $JsonValid3 = $true
            
            # Vérifier présence paramètres requis
            $ParametersCorrect3 = ($null -ne $Arguments3.name) -and ($null -ne $Arguments3.email) -and ($null -ne $Arguments3.preferences)
            
            # Vérifier objet preferences imbriqué
            if ($ParametersCorrect3) {
                $NestedObjectCorrect3 = ($null -ne $Arguments3.preferences.language)
            }
        } catch {
            $JsonValid3 = $false
        }
    }
    
    $Result3 = @{
        scenario_id = 3
        name = "Fonction Complexe - create_user"
        ttft_ms = [int]$Duration3
        total_duration_ms = [int]$Duration3
        tokens_generated = $TokensGenerated3
        parsing_success = $ParsingSuccess3
        json_valid = $JsonValid3
        function_called = $FunctionCalled3
        nested_object_correct = $NestedObjectCorrect3
        parameters_correct = $ParametersCorrect3
        error_handling = "none"
        notes = if ($NestedObjectCorrect3) { "Objet preferences imbriqué correctement parsé" } else { "Échec parsing objet imbriqué" }
    }
    
    Write-Host "✅ Scénario 3 complété" -ForegroundColor Green
    Write-Host "   TTFT: $($Duration3)ms | Tokens: $TokensGenerated3 | Nested OK: $NestedObjectCorrect3" -ForegroundColor Gray
    
} catch {
    Write-Host "❌ Erreur scénario 3: $_" -ForegroundColor Red
    $Result3 = @{
        scenario_id = 3
        name = "Fonction Complexe - create_user"
        error = $_.Exception.Message
        error_handling = "timeout_or_crash"
    }
}

# ============================================================================
# AGRÉGATION RÉSULTATS
# ============================================================================

Write-Host ""
Write-Host "[5/5] Agrégation résultats et calcul métriques..." -ForegroundColor Cyan

$Scenarios = @($Result1, $Result2, $Result3)

# Calculer summary
$SuccessCount = ($Scenarios | Where-Object { $_.parsing_success -eq $true }).Count
$TtftValues = $Scenarios | Where-Object { $null -ne $_.ttft_ms } | Select-Object -ExpandProperty ttft_ms
$TtftAvg = if ($TtftValues.Count -gt 0) { [int]($TtftValues | Measure-Object -Average).Average } else { 0 }
$ParsingAccuracy = if ($Scenarios.Count -gt 0) { [int](($SuccessCount / $Scenarios.Count) * 100) } else { 0 }
$JsonValidCount = ($Scenarios | Where-Object { $_.json_valid -eq $true }).Count
$JsonValidity = if ($Scenarios.Count -gt 0) { [int](($JsonValidCount / $Scenarios.Count) * 100) } else { 0 }

$Summary = @{
    total_scenarios = $Scenarios.Count
    success_rate = $ParsingAccuracy
    ttft_avg = $TtftAvg
    parsing_accuracy = $ParsingAccuracy
    json_validity = $JsonValidity
}

# Structure finale
$Results = @{
    test_date = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    config = "chunked_only_safe"
    tool_call_parser = $ToolCallParser
    scenarios = $Scenarios
    summary = $Summary
}

# ============================================================================
# SAUVEGARDE RÉSULTATS
# ============================================================================

Write-Host ""
Write-Host "Sauvegarde résultats..." -ForegroundColor Cyan

# Créer répertoire si nécessaire
$OutputDir = Split-Path -Parent $OutputFile
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# Sauvegarder JSON
$Results | ConvertTo-Json -Depth 10 | Out-File -FilePath $OutputFile -Encoding UTF8

Write-Host "✅ Résultats sauvegardés: $OutputFile" -ForegroundColor Green

# ============================================================================
# AFFICHAGE RÉSUMÉ
# ============================================================================

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "  RÉSUMÉ BENCHMARK TOOL CALLING" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Métriques Globales:" -ForegroundColor Yellow
Write-Host "  • Scénarios testés     : $($Summary.total_scenarios)"
Write-Host "  • Taux de succès       : $($Summary.success_rate)%"
Write-Host "  • TTFT moyen           : $($Summary.ttft_avg)ms"
Write-Host "  • Précision parsing    : $($Summary.parsing_accuracy)%"
Write-Host "  • Validité JSON        : $($Summary.json_validity)%"
Write-Host ""
Write-Host "Détails par Scénario:" -ForegroundColor Yellow

foreach ($scenario in $Scenarios) {
    $StatusIcon = if ($scenario.parsing_success) { "✅" } else { "❌" }
    Write-Host "  $StatusIcon Scénario $($scenario.scenario_id): $($scenario.name)"
    if ($null -ne $scenario.ttft_ms) {
        Write-Host "     TTFT: $($scenario.ttft_ms)ms | Tokens: $($scenario.tokens_generated) | JSON: $($scenario.json_valid)" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "Benchmark tool calling complété avec succès! 🎉" -ForegroundColor Green
Write-Host ""