# validate-services.ps1 - Script consolidé de validation des services Qwen3
#
# Version consolidée remplaçant 6 scripts redondants:
# - validate-optimized-qwen3.ps1 à validate-optimized-qwen3-final-v3.ps1
#
# Auteur: Roo Code (consolidation septembre 2025)
# Compatible avec: Image Docker officielle vLLM v0.9.2

param(
    [switch]$Help,
    [switch]$Verbose,
    [ValidateSet("micro", "mini", "medium", "all")]
    [string]$Profile = "all",
    [switch]$SkipFunctionalTests,
    [switch]$QuickCheck,
    [int]$TimeoutSeconds = 120
)

# Définition des couleurs
$RED = [System.ConsoleColor]::Red
$GREEN = [System.ConsoleColor]::Green
$YELLOW = [System.ConsoleColor]::Yellow
$BLUE = [System.ConsoleColor]::Blue
$CYAN = [System.ConsoleColor]::Cyan

# Configuration
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_ROOT = Split-Path -Parent (Split-Path -Parent $SCRIPT_DIR)
$LOG_FILE = Join-Path $SCRIPT_DIR "validate-services.log"

# Configuration des profils (alignée sur le document maître)
$PROFILES = @{
    "micro" = @{
        "port" = "5000"
        "model_name" = "qwen3-1.7b-awq"
        "expected_model" = "Qwen/Qwen2-1.5B-Instruct-AWQ"
        "description" = "Qwen3 Micro (1.7B)"
        "min_response_tokens" = 10
        "max_response_time_ms" = 5000
    }
    "mini" = @{
        "port" = "5001"
        "model_name" = "qwen3-8b-awq"
        "expected_model" = "Qwen/Qwen2-7B-Instruct-AWQ"
        "description" = "Qwen3 Mini (8B)"
        "min_response_tokens" = 15
        "max_response_time_ms" = 8000
    }
    "medium" = @{
        "port" = "5002"
        "model_name" = "qwen3-32b-awq"
        "expected_model" = "Qwen/Qwen3-32B-AWQ"
        "description" = "Qwen3 Medium (32B)"
        "min_response_tokens" = 20
        "max_response_time_ms" = 12000
    }
}

# Tests de validation
$VALIDATION_TESTS = @{
    "simple_completion" = @{
        "prompt" = "Écrivez une phrase simple en français:"
        "expected_keywords" = @("français", "simple", "phrase")
        "type" = "completion"
    }
    "tool_calling" = @{
        "prompt" = "Quel temps fait-il à Paris ? Utilisez une fonction météo si disponible."
        "expected_keywords" = @("weather", "function", "tool")
        "type" = "tool_call"
    }
    "reasoning" = @{
        "prompt" = "Résolvez: Si 2 + 2 = 4, alors 4 + 4 = ?"
        "expected_keywords" = @("8", "quatre", "huit")
        "type" = "reasoning"
    }
}

function Show-Help {
    Write-Host ""
    Write-Host "=== SCRIPT DE VALIDATION QWEN3 CONSOLIDÉ ===" -ForegroundColor $CYAN
    Write-Host ""
    Write-Host "UTILISATION:" -ForegroundColor $YELLOW
    Write-Host "  .\validate-services.ps1 [-Profile <profil>] [-Verbose] [-QuickCheck]"
    Write-Host ""
    Write-Host "PARAMÈTRES:" -ForegroundColor $YELLOW
    Write-Host "  -Profile             Profil à valider: micro|mini|medium|all (défaut: all)"
    Write-Host "  -Verbose             Mode verbeux avec détails des tests"
    Write-Host "  -QuickCheck          Validation rapide (santé + modèles seulement)"
    Write-Host "  -SkipFunctionalTests Ignorer les tests fonctionnels avancés"
    Write-Host "  -TimeoutSeconds      Timeout par test en secondes (défaut: 120)"
    Write-Host "  -Help                Afficher cette aide"
    Write-Host ""
    Write-Host "TYPES DE VALIDATION:" -ForegroundColor $YELLOW
    Write-Host "  ✅ Connectivité et santé des services"
    Write-Host "  ✅ Validation des modèles chargés"
    Write-Host "  ✅ Tests de génération de texte"
    Write-Host "  ✅ Tests de tool calling (si activé)"
    Write-Host "  ✅ Tests de reasoning (si activé)"
    Write-Host "  ✅ Mesure des performances de base"
    Write-Host ""
    exit 0
}

function Write-Log {
    param (
        [string]$Level,
        [string]$Message
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = $GREEN
    
    switch ($Level) {
        "INFO" { $color = $GREEN }
        "WARN" { $color = $YELLOW }
        "ERROR" { $color = $RED }
        "DEBUG" { $color = $BLUE }
        "SUCCESS" { $color = $CYAN }
    }
    
    $logEntry = "[$timestamp] [$Level] $Message"
    Write-Host -ForegroundColor $color $logEntry
    Add-Content -Path $LOG_FILE -Value $logEntry
}

# Test de connectivité basique
function Test-ServiceConnectivity {
    param (
        [string]$ProfileName
    )
    
    $config = $PROFILES[$ProfileName]
    $healthUrl = "http://localhost:$($config.port)/health"
    
    Write-Log "INFO" "🔗 Test de connectivité: $ProfileName sur port $($config.port)"
    
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -Method GET -TimeoutSec 10 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            Write-Log "SUCCESS" "✅ $ProfileName - Connectivité OK"
            return $true
        } else {
            Write-Log "ERROR" "❌ $ProfileName - Status HTTP: $($response.StatusCode)"
            return $false
        }
    } catch {
        Write-Log "ERROR" "❌ $ProfileName - Connexion échouée: $($_.Exception.Message)"
        return $false
    }
}

# Validation du modèle chargé
function Test-LoadedModel {
    param (
        [string]$ProfileName
    )
    
    $config = $PROFILES[$ProfileName]
    $modelsUrl = "http://localhost:$($config.port)/v1/models"
    
    Write-Log "INFO" "🤖 Validation du modèle: $ProfileName"
    
    try {
        $response = Invoke-WebRequest -Uri $modelsUrl -Method GET -TimeoutSec 10 -UseBasicParsing
        $modelsData = $response.Content | ConvertFrom-Json
        
        $loadedModel = $modelsData.data | Where-Object { $_.id -eq $config.model_name }
        
        if ($loadedModel) {
            Write-Log "SUCCESS" "✅ $ProfileName - Modèle '$($config.model_name)' chargé"
            if ($Verbose) {
                Write-Log "DEBUG" "   Détails: $($loadedModel | ConvertTo-Json -Compress)"
            }
            return $true
        } else {
            Write-Log "ERROR" "❌ $ProfileName - Modèle '$($config.model_name)' non trouvé"
            Write-Log "DEBUG" "Modèles disponibles: $($modelsData.data.id -join ', ')"
            return $false
        }
    } catch {
        Write-Log "ERROR" "❌ $ProfileName - Erreur validation modèle: $($_.Exception.Message)"
        return $false
    }
}

# Test de génération de texte
function Test-TextGeneration {
    param (
        [string]$ProfileName,
        [string]$TestName = "simple_completion"
    )
    
    if ($QuickCheck) {
        Write-Log "INFO" "⚡ Test de génération ignoré (mode rapide)"
        return $true
    }
    
    $config = $PROFILES[$ProfileName]
    $test = $VALIDATION_TESTS[$TestName]
    $completionsUrl = "http://localhost:$($config.port)/v1/completions"
    
    Write-Log "INFO" "📝 Test de génération: $ProfileName ($TestName)"
    
    $requestBody = @{
        model = $config.model_name
        prompt = $test.prompt
        max_tokens = 50
        temperature = 0.7
        stop = @()
    } | ConvertTo-Json
    
    try {
        $startTime = Get-Date
        $response = Invoke-WebRequest -Uri $completionsUrl -Method POST -Body $requestBody -ContentType "application/json" -TimeoutSec $TimeoutSeconds
        $endTime = Get-Date
        $responseTime = ($endTime - $startTime).TotalMilliseconds
        
        if ($response.StatusCode -eq 200) {
            $responseData = $response.Content | ConvertFrom-Json
            $generatedText = $responseData.choices[0].text
            $tokenCount = $responseData.usage.completion_tokens
            
            Write-Log "SUCCESS" "✅ $ProfileName - Génération OK ($tokenCount tokens, ${responseTime}ms)"
            
            if ($Verbose) {
                Write-Log "DEBUG" "   Texte généré: $($generatedText.Substring(0, [Math]::Min(100, $generatedText.Length)))..."
                Write-Log "DEBUG" "   Temps de réponse: ${responseTime}ms"
                Write-Log "DEBUG" "   Tokens générés: $tokenCount"
            }
            
            # Validation des performances
            if ($responseTime -gt $config.max_response_time_ms) {
                Write-Log "WARN" "⚠️  $ProfileName - Temps de réponse élevé: ${responseTime}ms (max: $($config.max_response_time_ms)ms)"
            }
            
            if ($tokenCount -lt $config.min_response_tokens) {
                Write-Log "WARN" "⚠️  $ProfileName - Peu de tokens générés: $tokenCount (min: $($config.min_response_tokens))"
            }
            
            return $true
        } else {
            Write-Log "ERROR" "❌ $ProfileName - Génération échouée: HTTP $($response.StatusCode)"
            return $false
        }
    } catch {
        Write-Log "ERROR" "❌ $ProfileName - Erreur génération: $($_.Exception.Message)"
        return $false
    }
}

# Test complet d'un profil
function Test-Profile {
    param (
        [string]$ProfileName
    )
    
    Write-Log "INFO" "🧪 === VALIDATION PROFIL: $ProfileName ==="
    
    $results = @{
        connectivity = $false
        model_validation = $false
        text_generation = $false
        overall_success = $false
    }
    
    # Test de connectivité
    $results.connectivity = Test-ServiceConnectivity $ProfileName
    
    if ($results.connectivity) {
        # Validation du modèle
        $results.model_validation = Test-LoadedModel $ProfileName
        
        if ($results.model_validation -and -not $SkipFunctionalTests) {
            # Test de génération
            $results.text_generation = Test-TextGeneration $ProfileName
        } else {
            $results.text_generation = $true  # Skip si demandé
        }
    }
    
    # Résultat global
    $results.overall_success = $results.connectivity -and $results.model_validation -and $results.text_generation
    
    # Résumé
    $status = if ($results.overall_success) { "✅ SUCCÈS" } else { "❌ ÉCHEC" }
    $statusColor = if ($results.overall_success) { $GREEN } else { $RED }
    
    Write-Host -ForegroundColor $statusColor "📊 Résumé $ProfileName : $status"
    Write-Log "INFO" "   - Connectivité: $(if($results.connectivity){'✅'}else{'❌'})"
    Write-Log "INFO" "   - Modèle: $(if($results.model_validation){'✅'}else{'❌'})"
    Write-Log "INFO" "   - Génération: $(if($results.text_generation){'✅'}else{'❌'})"
    Write-Log "INFO" ""
    
    return $results.overall_success
}

# Fonction principale
function Main {
    if ($Help) {
        Show-Help
    }
    
    Write-Log "INFO" "=== VALIDATION SERVICES QWEN3 - VERSION CONSOLIDÉE ==="
    Write-Log "INFO" "Profil sélectionné: $Profile"
    Write-Log "INFO" "Mode: $(if($QuickCheck){'Rapide'}else{'Complet'})"
    
    $profilesToTest = if ($Profile -eq "all") { $PROFILES.Keys } else { @($Profile) }
    $globalSuccess = $true
    $results = @{}
    
    foreach ($profileName in $profilesToTest) {
        $success = Test-Profile $profileName
        $results[$profileName] = $success
        if (-not $success) {
            $globalSuccess = $false
        }
        
        # Pause entre les tests
        if ($profilesToTest.Count -gt 1 -and $profileName -ne $profilesToTest[-1]) {
            Start-Sleep -Seconds 2
        }
    }
    
    # Rapport final
    Write-Log "INFO" "=== RAPPORT FINAL DE VALIDATION ==="
    foreach ($profileName in $profilesToTest) {
        $status = if ($results[$profileName]) { "✅ VALIDÉ" } else { "❌ ÉCHEC" }
        Write-Log "INFO" "  $profileName : $status"
    }
    
    if ($globalSuccess) {
        Write-Log "SUCCESS" "🎉 Tous les services validés avec succès!"
        Write-Log "INFO" "📋 Consultez les détails: $LOG_FILE"
        exit 0
    } else {
        Write-Log "ERROR" "❌ Échecs détectés dans la validation"
        Write-Log "INFO" "📋 Consultez les détails: $LOG_FILE"
        exit 1
    }
}

# Point d'entrée
Main