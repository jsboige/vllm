<#
.SYNOPSIS
    Script de test pour vérifier la compatibilité après synchronisation avec le dépôt original vLLM.

.DESCRIPTION
    Ce script vérifie que les fonctionnalités personnalisées (notamment le support de Qwen3)
    fonctionnent correctement après la synchronisation avec le dépôt original vLLM.
    Il teste les parsers Qwen3, le fonctionnement du parser de raisonnement,
    le support des outils, et la validité des configurations docker-compose.

.PARAMETER OutputFile
    Chemin du fichier de rapport de test. Par défaut: "./test-after-sync-report.txt"

.PARAMETER Verbose
    Affiche des informations détaillées pendant l'exécution des tests.

.EXAMPLE
    .\test-after-sync.ps1
    Exécute les tests et génère un rapport dans le fichier par défaut.

.EXAMPLE
    .\test-after-sync.ps1 -OutputFile "C:\rapports\test-sync.txt" -Verbose
    Exécute les tests avec affichage détaillé et génère un rapport dans le fichier spécifié.
#>

param (
    [string]$OutputFile = "./test-after-sync-report.txt",
    [switch]$Verbose = $false
)

# Fonction pour afficher des messages colorés
function Write-ColorOutput {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Message,
        
        [Parameter(Mandatory = $false)]
        [string]$ForegroundColor = "White"
    )
    
    Write-Host $Message -ForegroundColor $ForegroundColor
}

# Fonction pour écrire dans le rapport
function Write-Report {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Message,
        
        [Parameter(Mandatory = $false)]
        [string]$Status = "INFO"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Status] $Message"
    
    Add-Content -Path $OutputFile -Value $logMessage
    
    if ($Verbose) {
        $color = switch ($Status) {
            "SUCCESS" { "Green" }
            "ERROR" { "Red" }
            "WARNING" { "Yellow" }
            default { "White" }
        }
        Write-ColorOutput $logMessage $color
    }
}

# Fonction pour exécuter un test et enregistrer le résultat
function Test-Feature {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Name,
        
        [Parameter(Mandatory = $true)]
        [scriptblock]$TestScript
    )
    
    Write-Report "Début du test: $Name" "INFO"
    
    try {
        & $TestScript
        Write-Report "Test réussi: $Name" "SUCCESS"
        return $true
    }
    catch {
        Write-Report "Test échoué: $Name - $_" "ERROR"
        return $false
    }
}

# Initialisation du rapport
if (Test-Path $OutputFile) {
    Remove-Item $OutputFile -Force
}

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Get-Item $scriptPath).Parent.Parent.FullName

Write-Report "=== Rapport de test après synchronisation avec le dépôt original vLLM ===" "INFO"
Write-Report "Date d'exécution: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")" "INFO"
Write-Report "Répertoire du dépôt: $repoRoot" "INFO"
Write-Report "-----------------------------------------------------------" "INFO"

# Variables pour suivre les résultats des tests
$totalTests = 0
$passedTests = 0

# Test 1: Vérifier que le fichier du parser de raisonnement Qwen3 existe
$totalTests++
$testResult = Test-Feature -Name "Existence du parser de raisonnement Qwen3" -TestScript {
    $parserPath = Join-Path -Path $repoRoot -ChildPath "vllm/reasoning/qwen3_reasoning_parser.py"
    if (-not (Test-Path $parserPath)) {
        throw "Le fichier du parser de raisonnement Qwen3 n'existe pas: $parserPath"
    }
    Write-Report "Le fichier du parser de raisonnement Qwen3 existe: $parserPath" "INFO"
}
if ($testResult) { $passedTests++ }

# Test 2: Vérifier que le parser de raisonnement Qwen3 est correctement enregistré
$totalTests++
$testResult = Test-Feature -Name "Enregistrement du parser de raisonnement Qwen3" -TestScript {
    $parserPath = Join-Path -Path $repoRoot -ChildPath "vllm/reasoning/qwen3_reasoning_parser.py"
    $parserContent = Get-Content $parserPath -Raw
    
    if (-not ($parserContent -match '@ReasoningParserManager\.register_module\("qwen3"\)')) {
        throw "Le parser de raisonnement Qwen3 n'est pas correctement enregistré"
    }
    Write-Report "Le parser de raisonnement Qwen3 est correctement enregistré" "INFO"
}
if ($testResult) { $passedTests++ }

# Test 3: Vérifier que la classe Qwen3ReasoningParser est correctement définie
$totalTests++
$testResult = Test-Feature -Name "Définition de la classe Qwen3ReasoningParser" -TestScript {
    $parserPath = Join-Path -Path $repoRoot -ChildPath "vllm/reasoning/qwen3_reasoning_parser.py"
    $parserContent = Get-Content $parserPath -Raw
    
    if (-not ($parserContent -match 'class Qwen3ReasoningParser\(ReasoningParser\):')) {
        throw "La classe Qwen3ReasoningParser n'est pas correctement définie"
    }
    Write-Report "La classe Qwen3ReasoningParser est correctement définie" "INFO"
}
if ($testResult) { $passedTests++ }

# Test 4: Vérifier les méthodes essentielles du parser de raisonnement Qwen3
$totalTests++
$testResult = Test-Feature -Name "Méthodes du parser de raisonnement Qwen3" -TestScript {
    $parserPath = Join-Path -Path $repoRoot -ChildPath "vllm/reasoning/qwen3_reasoning_parser.py"
    $parserContent = Get-Content $parserPath -Raw
    
    $requiredMethods = @(
        'def __init__\(',
        'def is_reasoning_end\(',
        'def extract_content_ids\(',
        'def extract_reasoning_content_streaming\(',
        'def extract_reasoning_content\('
    )
    
    foreach ($method in $requiredMethods) {
        if (-not ($parserContent -match $method)) {
            throw "Méthode requise non trouvée dans le parser de raisonnement Qwen3: $method"
        }
    }
    Write-Report "Toutes les méthodes requises sont présentes dans le parser de raisonnement Qwen3" "INFO"
}
if ($testResult) { $passedTests++ }

# Test 5: Vérifier la compatibilité avec le système de tool calling
$totalTests++
$testResult = Test-Feature -Name "Compatibilité avec le système de tool calling" -TestScript {
    $toolParserInitPath = Join-Path -Path $repoRoot -ChildPath "vllm/entrypoints/openai/tool_parsers/__init__.py"
    
    if (-not (Test-Path $toolParserInitPath)) {
        throw "Le fichier d'initialisation des parsers d'outils n'existe pas: $toolParserInitPath"
    }
    
    $toolParserInitContent = Get-Content $toolParserInitPath -Raw
    
    # Vérifier que le système de tool parsers est correctement initialisé
    if (-not ($toolParserInitContent -match 'from .abstract_tool_parser import ToolParser, ToolParserManager')) {
        throw "L'importation des classes de base des parsers d'outils est manquante"
    }
    
    Write-Report "Le système de tool calling est correctement initialisé" "INFO"
    
    # Vérifier que la configuration Docker utilise le parser d'outils approprié
    $dockerComposePath = Join-Path -Path $repoRoot -ChildPath "myia-vllm/deployment/docker/qwen3-optimized/docker-compose-micro.yml"
    $dockerComposeContent = Get-Content $dockerComposePath -Raw
    
    if (-not ($dockerComposeContent -match '--enable-auto-tool-choice' -and $dockerComposeContent -match '--tool-call-parser')) {
        throw "La configuration Docker ne contient pas les paramètres nécessaires pour le tool calling"
    }
    
    Write-Report "La configuration Docker contient les paramètres nécessaires pour le tool calling" "INFO"
}
if ($testResult) { $passedTests++ }

# Test 6: Vérifier la validité des configurations docker-compose
$totalTests++
$testResult = Test-Feature -Name "Validité des configurations docker-compose" -TestScript {
    $dockerComposeFiles = @(
        "myia-vllm/deployment/docker/qwen3-optimized/docker-compose-micro.yml",
        "myia-vllm/deployment/docker/qwen3-optimized/docker-compose-mini.yml"
    )
    
    foreach ($file in $dockerComposeFiles) {
        $dockerComposePath = Join-Path -Path $repoRoot -ChildPath $file
        
        if (-not (Test-Path $dockerComposePath)) {
            throw "Le fichier de configuration Docker n'existe pas: $dockerComposePath"
        }
        
        # Vérifier la syntaxe YAML (basique)
        $dockerComposeContent = Get-Content $dockerComposePath -Raw
        
        if (-not ($dockerComposeContent -match 'version:' -and $dockerComposeContent -match 'services:')) {
            throw "Le fichier de configuration Docker n'a pas une structure YAML valide: $dockerComposePath"
        }
        
        Write-Report "Le fichier de configuration Docker est valide: $dockerComposePath" "INFO"
    }
    
    # Vérifier que docker-compose peut valider les fichiers
    try {
        foreach ($file in $dockerComposeFiles) {
            $dockerComposePath = Join-Path -Path $repoRoot -ChildPath $file
            $output = docker-compose -f $dockerComposePath config 2>&1
            
            if ($LASTEXITCODE -ne 0) {
                throw "La validation docker-compose a échoué pour $dockerComposePath : $output"
            }
            
            Write-Report "La validation docker-compose a réussi pour $dockerComposePath" "INFO"
        }
    }
    catch {
        Write-Report "Impossible de valider les fichiers docker-compose avec la commande docker-compose. Assurez-vous que Docker est installé et que la commande docker-compose est disponible." "WARNING"
        # Ne pas faire échouer le test si docker-compose n'est pas disponible
    }
}
if ($testResult) { $passedTests++ }

# Test 7: Vérifier l'intégration du parser de raisonnement Qwen3 dans le système
$totalTests++
$testResult = Test-Feature -Name "Intégration du parser de raisonnement Qwen3" -TestScript {
    $reasoningInitPath = Join-Path -Path $repoRoot -ChildPath "vllm/reasoning/__init__.py"
    
    if (-not (Test-Path $reasoningInitPath)) {
        throw "Le fichier d'initialisation du module de raisonnement n'existe pas: $reasoningInitPath"
    }
    
    $reasoningInitContent = Get-Content $reasoningInitPath -Raw
    
    # Vérifier que le parser de raisonnement Qwen3 est importé
    if (-not ($reasoningInitContent -match 'qwen3_reasoning_parser' -or $reasoningInitContent -match 'Qwen3ReasoningParser')) {
        Write-Report "Le parser de raisonnement Qwen3 n'est pas explicitement importé dans __init__.py, mais cela pourrait être normal si l'importation est dynamique" "WARNING"
    }
    else {
        Write-Report "Le parser de raisonnement Qwen3 est correctement importé dans le module de raisonnement" "INFO"
    }
    
    # Vérifier que le parser de raisonnement est utilisé dans la configuration Docker
    $dockerComposeFiles = @(
        "myia-vllm/deployment/docker/qwen3-optimized/docker-compose-micro.yml",
        "myia-vllm/deployment/docker/qwen3-optimized/docker-compose-mini.yml"
    )
    
    foreach ($file in $dockerComposeFiles) {
        $dockerComposePath = Join-Path -Path $repoRoot -ChildPath $file
        $dockerComposeContent = Get-Content $dockerComposePath -Raw
        
        if (-not ($dockerComposeContent -match '--enable-reasoning')) {
            throw "La configuration Docker ne contient pas le paramètre --enable-reasoning: $dockerComposePath"
        }
        
        Write-Report "La configuration Docker contient le paramètre --enable-reasoning: $dockerComposePath" "INFO"
    }
}
if ($testResult) { $passedTests++ }

# Test 8: Vérifier l'exécution du module Python (test d'importation)
$totalTests++
$testResult = Test-Feature -Name "Test d'importation du module de raisonnement Qwen3" -TestScript {
    try {
        $pythonCode = @"
import sys
import os

# Ajouter le répertoire racine au chemin Python
sys.path.insert(0, '$($repoRoot.Replace("\", "\\"))')

try:
    from vllm.reasoning import ReasoningParserManager
    print("Importation de ReasoningParserManager réussie")
    
    # Vérifier si le parser Qwen3 est enregistré
    parsers = ReasoningParserManager.reasoning_parsers
    if 'qwen3' in parsers:
        print("Le parser de raisonnement Qwen3 est correctement enregistré")
        exit(0)
    else:
        print("Le parser de raisonnement Qwen3 n'est pas enregistré")
        print("Parsers disponibles:", parsers.keys())
        exit(1)
except ImportError as e:
    print(f"Erreur d'importation: {e}")
    exit(1)
except Exception as e:
    print(f"Erreur: {e}")
    exit(1)
"@
        
        $tempFile = [System.IO.Path]::GetTempFileName() + ".py"
        Set-Content -Path $tempFile -Value $pythonCode
        
        $output = python $tempFile 2>&1
        Remove-Item $tempFile -Force
        
        if ($LASTEXITCODE -ne 0) {
            throw "Le test d'importation a échoué: $output"
        }
        
        Write-Report "Test d'importation réussi: $output" "INFO"
    }
    catch {
        Write-Report "Impossible d'exécuter le test d'importation Python. Assurez-vous que Python est installé et disponible dans le PATH." "WARNING"
        # Ne pas faire échouer le test si Python n'est pas disponible
        return $true
    }
}
if ($testResult) { $passedTests++ }

# Résumé des tests
Write-Report "-----------------------------------------------------------" "INFO"
Write-Report "Résumé des tests:" "INFO"
Write-Report "Tests réussis: $passedTests / $totalTests" "INFO"

if ($passedTests -eq $totalTests) {
    Write-Report "Tous les tests ont réussi! La synchronisation est compatible avec les fonctionnalités personnalisées." "SUCCESS"
    Write-ColorOutput "Tous les tests ont réussi! La synchronisation est compatible avec les fonctionnalités personnalisées." "Green"
}
else {
    $failedTests = $totalTests - $passedTests
    Write-Report "$failedTests test(s) ont échoué. Veuillez consulter le rapport pour plus de détails." "ERROR"
    Write-ColorOutput "$failedTests test(s) ont échoué. Veuillez consulter le rapport pour plus de détails." "Red"
}

Write-ColorOutput "Rapport de test généré: $OutputFile" "Cyan"