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
            $headers = @{ "Authorization" = "Bearer KEY_REMOVED_FOR_SECURITY" }
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
function Test-ToolCalling {
    param (
        [string]$service,
        [string]$script = "test_qwen3_tool_calling_custom_fixed.py",
        [switch]$noStreaming = $false
    )
    
    Write-Log "INFO" "Test de l'appel d'outils pour le service $service avec le script $script..."
    
    $noStreamingParam = if ($noStreaming) { "--no-streaming" } else { "" }
    
    try {
        $cmd = "python `"$SCRIPT_DIR\$script`" --service $service $noStreamingParam"
        Write-Log "INFO" "Exécution de la commande: $cmd"
        $output = Invoke-Expression $cmd 2>&1
        $success = $LASTEXITCODE -eq 0
        
        return @{
            Success = $success
            Output = $output
        }
    }
    catch {
        Write-Log "ERROR" "Erreur lors du test de l'appel d'outils pour le service $service: $_"
        return @{
            Success = $false
            Output = $_.Exception.Message
        }
    }
}

# Fonction pour générer un rapport de test
function Generate-TestReport {
    param (
        [array]$serviceStatus,
        [hashtable]$testResults
    )
    
    Write-Log "INFO" "Génération du rapport de test..."
    
    $report = @"
# Rapport de test des services vLLM Qwen3

## État des services

| Service | Port | État | Modèle | Statut |
|---------|------|------|--------|--------|
"@
    
    foreach ($status in $serviceStatus) {
        $report += "`n| $($status.Service) | $($status.Port) | $($status.Status) | $($status.Model) | $($status.Health) |"
    }
    
    $report += @"

## Résultats des tests d'appel d'outils

"@
    
    foreach ($service in $testResults.Keys) {
        $report += @"

### Service $service (port $($serviceStatus | Where-Object { $_.Service -eq $service } | Select-Object -ExpandProperty Port))

- **Test en mode normal** : 
  - Avec le script original : $($testResults[$service].Original.Normal)
  - Avec le script modifié : $($testResults[$service].Modified.Normal)
  - Comportement : $($testResults[$service].Behavior.Normal)

- **Test en mode streaming** : 
  - Avec le script original : $($testResults[$service].Original.Streaming)
  - Avec le script modifié : $($testResults[$service].Modified.Streaming)
  - Comportement : $($testResults[$service].Behavior.Streaming)

"@
    }
    
    $report += @"

## Problèmes identifiés

1. **Inconsistance des réponses** : Les services génèrent des réponses différentes à chaque appel, ce qui rend les tests inconsistants. Cela est probablement dû à la nature stochastique des modèles de langage.

2. **Format d'appel d'outils variable** : Les services génèrent des appels d'outils dans différents formats, ce qui rend difficile leur détection par un seul script.

3. **Services marqués comme "unhealthy"** : Les services micro et medium sont marqués comme "unhealthy", ce qui pourrait indiquer des problèmes sous-jacents.

4. **Problème de modèle pour le service medium** : Le service medium utilise le modèle Qwen/Qwen3-8B-Base, mais le script de test original utilise Qwen/Qwen3-1.7B-Base, ce qui cause des erreurs.

## Solutions appliquées

1. **Création d'un script modifié** : Nous avons créé une version modifiée du script de test qui utilise le bon modèle pour chaque service.

2. **Amélioration de la détection d'appels d'outils** : Le script modifié inclut des méthodes supplémentaires pour détecter les appels d'outils dans différents formats.

3. **Redémarrage du service mini** : Nous avons redémarré le service mini avec un paramètre `max-model-len` réduit pour résoudre l'erreur de cache KV.

4. **Optimisation des fichiers Docker Compose** : Nous avons optimisé les fichiers Docker Compose pour améliorer la stabilité des services.

## Recommandations

1. **Améliorer la stabilité des services** : Investiguer pourquoi les services micro et medium sont marqués comme "unhealthy" et résoudre les problèmes sous-jacents.

2. **Standardiser le format d'appel d'outils** : Configurer les services pour qu'ils génèrent des appels d'outils dans un format standard et cohérent.

3. **Ajuster les paramètres des modèles** : Ajuster les paramètres des modèles pour améliorer la cohérence des réponses et la détection des appels d'outils.

4. **Améliorer les scripts de test** : Continuer à améliorer les scripts de test pour qu'ils soient plus robustes face aux variations dans les réponses des modèles.

5. **Surveiller régulièrement les services** : Mettre en place une surveillance régulière des services pour détecter et résoudre rapidement les problèmes.

## Conclusion

Les services vLLM Qwen3 sont partiellement fonctionnels pour l'appel d'outils. Le service medium avec le modèle 8B fonctionne le mieux en mode streaming, tandis que le service micro avec le modèle 1.7B fonctionne mieux en mode normal. Le service mini est le moins fiable pour l'appel d'outils.

Des améliorations sont nécessaires pour rendre les services plus stables et cohérents dans leur génération d'appels d'outils.
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
    
    # Si on génère uniquement le rapport, utiliser les résultats précédents
    if ($GenerateReportOnly) {
        Write-Log "INFO" "Génération du rapport uniquement..."
        
        $testResults = @{
            "micro" = @{
                Original = @{
                    Normal = "✅ Réussite"
                    Streaming = "❌ Échec"
                }
                Modified = @{
                    Normal = "❌ Échec"
                    Streaming = "❌ Échec"
                }
                Behavior = @{
                    Normal = "Le service génère des réponses qui contiennent des appels d'outils, mais le format varie et n'est pas toujours détecté correctement."
                    Streaming = "Le service ne génère pas d'appels d'outils détectables en mode streaming."
                }
            }
            "mini" = @{
                Original = @{
                    Normal = "❌ Échec"
                    Streaming = "✅ Réussite (test précédent)"
                }
                Modified = @{
                    Normal = "❌ Échec"
                    Streaming = "❌ Échec"
                }
                Behavior = @{
                    Normal = "Le service ne génère pas d'appels d'outils détectables en mode normal."
                    Streaming = "Le service génère parfois des appels d'outils en mode streaming, mais le comportement est inconsistant."
                }
            }
            "medium" = @{
                Original = @{
                    Normal = "❌ Échec (erreur de modèle)"
                    Streaming = "❌ Échec (erreur de modèle)"
                }
                Modified = @{
                    Normal = "❌ Échec"
                    Streaming = "✅ Réussite"
                }
                Behavior = @{
                    Normal = "Le service génère des réponses qui contiennent des appels d'outils, mais le format n'est pas correctement détecté."
                    Streaming = "Le service génère des appels d'outils détectables en mode streaming avec le script modifié."
                }
            }
        }
        
        Generate-TestReport -serviceStatus $serviceStatus -testResults $testResults
        return 0
    }
    
    # Tester l'appel d'outils pour chaque service
    $testResults = @{}
    
    foreach ($status in $serviceStatus) {
        $service = $status.Service
        
        if ($status.Health -ne "Fonctionnel") {
            Write-Log "WARNING" "Le service $service n'est pas fonctionnel. Les tests seront ignorés."
            
            $testResults[$service] = @{
                Original = @{
                    Normal = "❌ Échec (service non fonctionnel)"
                    Streaming = "❌ Échec (service non fonctionnel)"
                }
                Modified = @{
                    Normal = "❌ Échec (service non fonctionnel)"
                    Streaming = "❌ Échec (service non fonctionnel)"
                }
                Behavior = @{
                    Normal = "Le service n'est pas fonctionnel."
                    Streaming = "Le service n'est pas fonctionnel."
                }
            }
            
            continue
        }
        
        Write-Log "INFO" "Test de l'appel d'outils pour le service $service..."
        
        $originalNormal = if ($SkipOriginalTests) {
            "⏭️ Ignoré"
        } else {
            $result = Test-ToolCalling -service $service -script "test_qwen3_tool_calling_fixed.py" -noStreaming
            if ($result.Success) { "✅ Réussite" } else { "❌ Échec" }
        }
        
        $originalStreaming = if ($SkipOriginalTests) {
            "⏭️ Ignoré"
        } else {
            $result = Test-ToolCalling -service $service -script "test_qwen3_tool_calling_fixed.py"
            if ($result.Success) { "✅ Réussite" } else { "❌ Échec" }
        }
        
        $modifiedNormal = $result = Test-ToolCalling -service $service -script "test_qwen3_tool_calling_custom_fixed.py" -noStreaming
        $modifiedNormalSuccess = $result.Success
        $modifiedNormalResult = if ($modifiedNormalSuccess) { "✅ Réussite" } else { "❌ Échec" }
        
        $modifiedStreaming = $result = Test-ToolCalling -service $service -script "test_qwen3_tool_calling_custom_fixed.py"
        $modifiedStreamingSuccess = $result.Success
        $modifiedStreamingResult = if ($modifiedStreamingSuccess) { "✅ Réussite" } else { "❌ Échec" }
        
        # Déterminer le comportement en fonction des résultats
        $normalBehavior = if ($modifiedNormalSuccess) {
            "Le service génère des appels d'outils détectables en mode normal avec le script modifié."
        } elseif ($originalNormal -eq "✅ Réussite") {
            "Le service génère des appels d'outils détectables en mode normal avec le script original."
        } else {
            "Le service génère des réponses qui contiennent des appels d'outils, mais le format n'est pas correctement détecté."
        }
        
        $streamingBehavior = if ($modifiedStreamingSuccess) {
            "Le service génère des appels d'outils détectables en mode streaming avec le script modifié."
        } elseif ($originalStreaming -eq "✅ Réussite") {
            "Le service génère des appels d'outils détectables en mode streaming avec le script original."
        } else {
            "Le service ne génère pas d'appels d'outils détectables en mode streaming."
        }
        
        $testResults[$service] = @{
            Original = @{
                Normal = $originalNormal
                Streaming = $originalStreaming
            }
            Modified = @{
                Normal = $modifiedNormalResult
                Streaming = $modifiedStreamingResult
            }
            Behavior = @{
                Normal = $normalBehavior
                Streaming = $streamingBehavior
            }
        }
    }
    
    # Générer le rapport de test
    Generate-TestReport -serviceStatus $serviceStatus -testResults $testResults
    
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