# test-qwen3-services.ps1 - Script pour tester les services vLLM Qwen3
# 
# Ce script:
# - Vérifie que les services vLLM Qwen3 sont en cours d'exécution
# - Teste l'appel d'outils pour chaque service
# - Génère un rapport de test détaillé

# Définition des couleurs pour les messages
$RED = [System.ConsoleColor]::Red
$GREEN = [System.ConsoleColor]::Green
$YELLOW = [System.ConsoleColor]::Yellow
$BLUE = [System.ConsoleColor]::Blue

# Chemin du script et du répertoire de configuration
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$LOG_FILE = Join-Path $SCRIPT_DIR "test-qwen3-services.log"
$REPORT_FILE = Join-Path $SCRIPT_DIR "rapport-test-qwen3.md"

# Fonction de journalisation
function Write-Log {
    param (
        [string]$level,
        [string]$message
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $color = $null
    
    switch ($level) {
        "INFO" { $color = $GREEN }
        "WARNING" { $color = $YELLOW }
        "ERROR" { $color = $RED }
        "DEBUG" { $color = $BLUE }
    }
    
    # Affichage dans la console
    Write-Host -ForegroundColor $color "[$timestamp] [$level] $message"
    
    # Journalisation dans le fichier de log
    Add-Content -Path $LOG_FILE -Value "[$timestamp] [$level] $message"
}

# Fonction pour vérifier l'état des services
function Check-ServicesStatus {
    Write-Log "INFO" "Vérification de l'état des services vLLM Qwen3..."
    
    $services = @(
        @{Name="vllm-micro-qwen3"; Port="5000"; Model="Qwen/Qwen3-1.7B-Base"},
        @{Name="vllm-mini-qwen3"; Port="5001"; Model="Qwen/Qwen3-1.7B-Base"},
        @{Name="vllm-medium-qwen3"; Port="5002"; Model="Qwen/Qwen3-8B-Base"}
    )
    
    $results = @()
    
    foreach ($service in $services) {
        $serviceName = $service.Name
        $port = $service.Port
        $model = $service.Model
        
        Write-Log "INFO" "Vérification du service $serviceName sur le port $port..."
        
        # Vérifier si le conteneur est en cours d'exécution
        $containerName = "myia-vllm_$serviceName"
        $containerStatus = docker ps -q -f "name=$containerName"
        
        if (-not $containerStatus) {
            Write-Log "WARNING" "Le conteneur $containerName n'est pas en cours d'exécution."
            $results += @{
                Service = $serviceName.Replace("vllm-", "").Replace("-qwen3", "")
                Port = $port
                Status = "Non démarré"
                Model = $model
                Health = "N/A"
            }
            continue
        }
        
        # Vérifier l'état de santé du conteneur
        $healthStatus = docker inspect --format "{{.State.Health.Status}}" $containerName 2>$null
        
        # Vérifier si le service répond à l'API
        $apiStatus = "Non fonctionnel"
        try {
            $headers = @{ "Authorization" = "Bearer 32885271D7845A3839F1AE0274676D87" }
            $response = Invoke-WebRequest -Uri "http://localhost:$port/v1/models" -Method Get -Headers $headers -UseBasicParsing -TimeoutSec 10
            
            if ($response.StatusCode -eq 200) {
                $apiStatus = "Fonctionnel"
            }
        }
        catch {
            # Ne rien faire, le statut reste "Non fonctionnel"
        }
        
        $results += @{
            Service = $serviceName.Replace("vllm-", "").Replace("-qwen3", "")
            Port = $port
            Status = "En cours d'exécution" + $(if ($healthStatus -ne "healthy") { " ($healthStatus)" } else { "" })
            Model = $model
            Health = $apiStatus
        }
    }
    
    return $results
}

# Fonction pour tester l'appel d'outils
function Run-PythonTest {
    param (
        [string]$service,
        [string]$script,
        [string]$arguments
    )
    
    Write-Log "INFO" "Exécution du test '$script' pour le service '$service'..."
    
    try {
        $test_script_path = Join-Path $SCRIPT_DIR '..\' 'python\tests' $script
        $cmd = "python `"$test_script_path`" --service $service $arguments"
        Write-Log "DEBUG" "Commande: $cmd"
        
        $output = Invoke-Expression $cmd 2>&1
        $success = $LASTEXITCODE -eq 0
        
        if ($success) {
            Write-Log "INFO" "  -> ✅ Succès"
        } else {
            Write-Log "ERROR" "  -> ❌ Échec"
            Write-Log "DEBUG" "Sortie: $output"
        }

        return $success
    }
    catch {
        Write-Log "ERROR" "Exception lors de l'exécution du test '$script' pour le service '$service': $_"
        return $false
    }
}

# Fonction pour générer un rapport de test
function Generate-TestReport {
    param (
        [array]$serviceStatus,
        [hashtable]$testResults,
        [array]$testSuite
    )
    
    Write-Log "INFO" "Génération du rapport de test..."
    
    # Entête du rapport
    $report = @"
# Rapport de test des services vLLM Qwen3

Date du test : $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

## État des services

| Service | Port | État | Modèle | Statut API |
|---------|------|------|--------|------------|
"@
    
    foreach ($status in $serviceStatus) {
        $report += "`n| $($status.Service) | $($status.Port) | $($status.Status) | $($status.Model) | $($status.Health) |"
    }
    
    # Tableau des résultats de la suite de tests
    $report += @"

## Résultats de la suite de tests

"@
    
    # Construire l'en-tête du tableau de résultats
    $header = "| Service |"
    $separator = "|---------|"
    foreach ($test in $testSuite) {
        $header += " $($test.Name) |"
        $separator += "------------|"
    }
    $report += "`n$header"
    $report += "`n$separator"
    
    # Remplir les lignes de résultats
    foreach ($serviceName in $testResults.Keys) {
        $line = "| $serviceName |"
        foreach ($test in $testSuite) {
            $result = $testResults[$serviceName][$test.Name]
            $line += " $result |"
        }
        $report += "`n$line"
    }
    
    $report += @"

## Légende

- ✅ **Succès**: Le test s'est terminé sans erreur.
- ❌ **Échec**: Le test a rencontré une erreur ou n'a pas produit le résultat attendu.
- ⏭️ **Ignoré**: Le test n'a pas été exécuté car le service n'était pas fonctionnel.

"@
    
    Set-Content -Path $REPORT_FILE -Value $report
    
    Write-Log "INFO" "Rapport de test généré avec succès: $REPORT_FILE"
}

# Fonction principale
function Main {
    param (
        [switch]$SkipOriginalTests = $false,
        [switch]$GenerateReportOnly = $false
    )
    
    Write-Log "INFO" "Démarrage du script de test des services vLLM Qwen3..."
    
    # Vérifier l'état des services
    $serviceStatus = Check-ServicesStatus
    
    # Afficher l'état des services
    Write-Log "INFO" "État des services vLLM Qwen3:"
    foreach ($status in $serviceStatus) {
        Write-Log "INFO" "  Service $($status.Service) (port $($status.Port)): $($status.Status), $($status.Health)"
    }
    
    if ($GenerateReportOnly) {
        Write-Log "WARNING" "L'option --report-only est obsolète et sera ignorée."
    }
    
    # Définir la suite de tests
    $testSuite = @(
        @{ Name = "Déploiement"; Script = "test_qwen3_deployment.py"; Arguments = "" },
        @{ Name = "Tool Calling"; Script = "test_qwen3_tool_calling.py"; Arguments = "" },
        @{ Name = "Tool Calling (Custom)"; Script = "test_qwen3_tool_calling_custom.py"; Arguments = "" },
        @{ Name = "Raisonnement"; Script = "test_reasoning.py"; Arguments = "" },
        @{ Name = "Taille du Contexte"; Script = "test_context_size.py"; Arguments = "" },
        @{ Name = "Santé Globale"; Script = "test_vllm_services.py"; Arguments = "--all" }
    )

    # Exécuter la suite de tests pour chaque service fonctionnel
    $testResults = @{}
    foreach ($status in $serviceStatus) {
        $serviceName = $status.Service
        $testResults[$serviceName] = @{}

        if ($status.Health -ne "Fonctionnel") {
            Write-Log "WARNING" "Le service $serviceName n'est pas fonctionnel. Tests ignorés."
            foreach ($test in $testSuite) {
                $testResults[$serviceName][$test.Name] = "⏭️ Ignoré (service non fonctionnel)"
            }
            continue
        }

        Write-Log "INFO" "Démarrage de la suite de tests pour le service '$serviceName'..."
        foreach ($test in $testSuite) {
            $result = Run-PythonTest -service $serviceName -script $test.Script -arguments $test.Arguments
            $testResults[$serviceName][$test.Name] = if ($result) { "✅ Succès" } else { "❌ Échec" }
        }
    }
    
    # Générer le rapport de test
    Generate-TestReport -serviceStatus $serviceStatus -testResults $testResults -testSuite $testSuite
    
    Write-Log "INFO" "Tests terminés. Consultez le rapport pour plus de détails: $REPORT_FILE"
    return 0
}

# Analyser les arguments de la ligne de commande
$skipOriginalTests = $false
$generateReportOnly = $false

for ($i = 0; $i -lt $args.Count; $i++) {
    switch ($args[$i]) {
        "--skip-original" {
            $skipOriginalTests = $true
        }
        "--report-only" {
            $generateReportOnly = $true
        }
        "--help" {
            Write-Host "Usage: .\test-qwen3-services.ps1 [--skip-original] [--report-only] [--help]"
            Write-Host "  --skip-original   Ignorer les tests avec le script original"
            Write-Host "  --report-only     Générer uniquement le rapport sans exécuter les tests"
            Write-Host "  --help            Afficher cette aide"
            exit 0
        }
    }
}

# Exécuter la fonction principale
Main -SkipOriginalTests:$skipOriginalTests -GenerateReportOnly:$generateReportOnly
exit $LASTEXITCODE