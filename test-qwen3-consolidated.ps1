# Script PowerShell pour tester la branche consolidée Qwen3
# Ce script effectue une série de tests pour vérifier que la branche consolidée fonctionne correctement

# Fonction pour afficher les messages avec des couleurs
function Write-ColorOutput {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Message,
        
        [Parameter(Mandatory=$false)]
        [string]$ForegroundColor = "White"
    )
    
    Write-Host $Message -ForegroundColor $ForegroundColor
}

# Fonction pour exécuter une commande et vérifier son résultat
function Invoke-Command {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Command,
        
        [Parameter(Mandatory=$false)]
        [string]$ErrorMessage = "Erreur lors de l'exécution de la commande"
    )
    
    Write-ColorOutput "Exécution de: $Command" -ForegroundColor Cyan
    
    try {
        $output = Invoke-Expression "$Command 2>&1"
        if ($LASTEXITCODE -ne 0) {
            Write-ColorOutput "$ErrorMessage`n$output" -ForegroundColor Red
            return $false, $output
        }
        return $true, $output
    }
    catch {
        Write-ColorOutput "$ErrorMessage`n$_" -ForegroundColor Red
        return $false, $_
    }
}

# Fonction pour vérifier si un fichier existe
function Test-FileExists {
    param(
        [Parameter(Mandatory=$true)]
        [string]$FilePath,
        
        [Parameter(Mandatory=$false)]
        [string]$ErrorMessage = "Le fichier n'existe pas"
    )
    
    if (Test-Path $FilePath) {
        Write-ColorOutput "Le fichier $FilePath existe" -ForegroundColor Green
        return $true
    }
    else {
        Write-ColorOutput "$ErrorMessage : $FilePath" -ForegroundColor Red
        return $false
    }
}

# Fonction pour tester les parsers Qwen3
function Test-Qwen3Parsers {
    Write-ColorOutput "Test des parsers Qwen3" -ForegroundColor Magenta
    
    # Vérifier l'existence des fichiers de parser
    $parserFiles = @(
        "vllm/reasoning/qwen3_reasoning_parser.py",
        "vllm/reasoning/qwen3_reasoning_parser_improved.py",
        "entrypoints/openai/tool_parsers/qwen3_tool_parser.py"
    )
    
    $allFilesExist = $true
    foreach ($file in $parserFiles) {
        if (-not (Test-FileExists $file)) {
            $allFilesExist = $false
        }
    }
    
    if (-not $allFilesExist) {
        Write-ColorOutput "Certains fichiers de parser sont manquants" -ForegroundColor Red
        return $false
    }
    
    # Exécuter les tests unitaires pour les parsers
    Write-ColorOutput "Exécution des tests unitaires pour les parsers" -ForegroundColor Cyan
    
    $testCommand = "python -m unittest vllm/reasoning/test_qwen3_parsers.py"
    $testResult, $testOutput = Invoke-Command $testCommand "Erreur lors de l'exécution des tests unitaires"
    
    if (-not $testResult) {
        Write-ColorOutput "Les tests unitaires ont échoué" -ForegroundColor Red
        return $false
    }
    
    Write-ColorOutput "Tests des parsers Qwen3 réussis" -ForegroundColor Green
    return $true
}

# Fonction pour tester les configurations Docker
function Test-DockerConfigurations {
    Write-ColorOutput "Test des configurations Docker" -ForegroundColor Magenta
    
    # Vérifier l'existence des fichiers de configuration Docker
    $dockerFiles = @(
        "vllm-configs/docker-compose/docker-compose-medium-qwen3-fixed.yml",
        "vllm-configs/docker-compose/docker-compose-micro-qwen3.yml",
        "vllm-configs/docker-compose/docker-compose-mini-qwen3.yml"
    )
    
    $allFilesExist = $true
    foreach ($file in $dockerFiles) {
        if (-not (Test-FileExists $file)) {
            $allFilesExist = $false
        }
    }
    
    if (-not $allFilesExist) {
        Write-ColorOutput "Certains fichiers de configuration Docker sont manquants" -ForegroundColor Red
        return $false
    }
    
    # Vérifier la syntaxe des fichiers Docker Compose
    Write-ColorOutput "Vérification de la syntaxe des fichiers Docker Compose" -ForegroundColor Cyan
    
    foreach ($file in $dockerFiles) {
        $validateCommand = "docker-compose -f $file config"
        $validateResult, $validateOutput = Invoke-Command $validateCommand "Erreur de syntaxe dans le fichier $file"
        
        if (-not $validateResult) {
            Write-ColorOutput "Le fichier $file contient des erreurs de syntaxe" -ForegroundColor Red
            return $false
        }
    }
    
    Write-ColorOutput "Tests des configurations Docker réussis" -ForegroundColor Green
    return $true
}

# Fonction pour tester les scripts de démarrage
function Test-StartupScripts {
    Write-ColorOutput "Test des scripts de démarrage" -ForegroundColor Magenta
    
    # Vérifier l'existence des scripts de démarrage
    $scriptFiles = @(
        "vllm-configs/start-with-qwen3-parser-fixed.sh",
        "qwen3/parsers/register_qwen3_parser.py"
    )
    
    $allFilesExist = $true
    foreach ($file in $scriptFiles) {
        if (-not (Test-FileExists $file)) {
            $allFilesExist = $false
        }
    }
    
    if (-not $allFilesExist) {
        Write-ColorOutput "Certains scripts de démarrage sont manquants" -ForegroundColor Red
        return $false
    }
    
    # Vérifier la syntaxe du script Python
    Write-ColorOutput "Vérification de la syntaxe du script Python" -ForegroundColor Cyan
    
    $validateCommand = "python -m py_compile qwen3/parsers/register_qwen3_parser.py"
    $validateResult, $validateOutput = Invoke-Command $validateCommand "Erreur de syntaxe dans le script register_qwen3_parser.py"
    
    if (-not $validateResult) {
        Write-ColorOutput "Le script register_qwen3_parser.py contient des erreurs de syntaxe" -ForegroundColor Red
        return $false
    }
    
    Write-ColorOutput "Tests des scripts de démarrage réussis" -ForegroundColor Green
    return $true
}

# Fonction pour tester le déploiement Docker
function Test-DockerDeployment {
    param(
        [Parameter(Mandatory=$false)]
        [switch]$SkipDeployment = $false
    )
    
    Write-ColorOutput "Test du déploiement Docker" -ForegroundColor Magenta
    
    if ($SkipDeployment) {
        Write-ColorOutput "Déploiement Docker ignoré" -ForegroundColor Yellow
        return $true
    }
    
    # Vérifier si Docker est installé
    $dockerCommand = "docker --version"
    $dockerResult, $dockerOutput = Invoke-Command $dockerCommand "Docker n'est pas installé ou n'est pas accessible"
    
    if (-not $dockerResult) {
        Write-ColorOutput "Docker n'est pas installé ou n'est pas accessible" -ForegroundColor Red
        return $false
    }
    
    # Vérifier si Docker Compose est installé
    $composeCommand = "docker-compose --version"
    $composeResult, $composeOutput = Invoke-Command $composeCommand "Docker Compose n'est pas installé ou n'est pas accessible"
    
    if (-not $composeResult) {
        Write-ColorOutput "Docker Compose n'est pas installé ou n'est pas accessible" -ForegroundColor Red
        return $false
    }
    
    # Demander à l'utilisateur s'il souhaite déployer un conteneur Docker pour les tests
    $response = Read-Host "Voulez-vous déployer un conteneur Docker pour les tests? (O/N)"
    if ($response -ne "O" -and $response -ne "o") {
        Write-ColorOutput "Déploiement Docker ignoré" -ForegroundColor Yellow
        return $true
    }
    
    # Déployer un conteneur Docker pour les tests
    Write-ColorOutput "Déploiement d'un conteneur Docker pour les tests" -ForegroundColor Cyan
    
    $deployCommand = "docker-compose -f vllm-configs/docker-compose/docker-compose-micro-qwen3.yml up -d"
    $deployResult, $deployOutput = Invoke-Command $deployCommand "Erreur lors du déploiement du conteneur Docker"
    
    if (-not $deployResult) {
        Write-ColorOutput "Erreur lors du déploiement du conteneur Docker" -ForegroundColor Red
        return $false
    }
    
    # Attendre que le conteneur soit prêt
    Write-ColorOutput "Attente du démarrage du conteneur..." -ForegroundColor Cyan
    Start-Sleep -Seconds 10
    
    # Vérifier si le conteneur est en cours d'exécution
    $checkCommand = "docker-compose -f vllm-configs/docker-compose/docker-compose-micro-qwen3.yml ps"
    $checkResult, $checkOutput = Invoke-Command $checkCommand "Erreur lors de la vérification du conteneur Docker"
    
    if (-not $checkResult) {
        Write-ColorOutput "Erreur lors de la vérification du conteneur Docker" -ForegroundColor Red
        return $false
    }
    
    # Arrêter le conteneur Docker
    Write-ColorOutput "Arrêt du conteneur Docker" -ForegroundColor Cyan
    
    $stopCommand = "docker-compose -f vllm-configs/docker-compose/docker-compose-micro-qwen3.yml down"
    $stopResult, $stopOutput = Invoke-Command $stopCommand "Erreur lors de l'arrêt du conteneur Docker"
    
    if (-not $stopResult) {
        Write-ColorOutput "Erreur lors de l'arrêt du conteneur Docker" -ForegroundColor Red
        return $false
    }
    
    Write-ColorOutput "Tests du déploiement Docker réussis" -ForegroundColor Green
    return $true
}

# Fonction principale pour exécuter tous les tests
function Start-Qwen3Tests {
    param(
        [Parameter(Mandatory=$false)]
        [string]$BranchToTest = "qwen3-consolidated",
        
        [Parameter(Mandatory=$false)]
        [switch]$SkipDockerDeployment = $false
    )
    
    Write-ColorOutput "Début des tests pour la branche $BranchToTest" -ForegroundColor Green
    
    # Vérifier si la branche existe
    $branchCommand = "git branch --list $BranchToTest"
    $branchResult, $branchOutput = Invoke-Command $branchCommand "Erreur lors de la vérification de la branche $BranchToTest"
    
    if (-not $branchResult -or $branchOutput -eq "") {
        Write-ColorOutput "La branche $BranchToTest n'existe pas" -ForegroundColor Red
        return $false
    }
    
    # Checkout de la branche à tester
    $checkoutCommand = "git checkout $BranchToTest"
    $checkoutResult, $checkoutOutput = Invoke-Command $checkoutCommand "Erreur lors du checkout de la branche $BranchToTest"
    
    if (-not $checkoutResult) {
        Write-ColorOutput "Erreur lors du checkout de la branche $BranchToTest" -ForegroundColor Red
        return $false
    }
    
    # Exécuter les tests
    $testResults = @{
        "Parsers" = Test-Qwen3Parsers
        "DockerConfigurations" = Test-DockerConfigurations
        "StartupScripts" = Test-StartupScripts
        "DockerDeployment" = Test-DockerDeployment -SkipDeployment:$SkipDockerDeployment
    }
    
    # Afficher le résumé des tests
    Write-ColorOutput "`nRésumé des tests:" -ForegroundColor Magenta
    
    $allTestsPassed = $true
    foreach ($test in $testResults.Keys) {
        $status = if ($testResults[$test]) { "Réussi" } else { "Échoué"; $allTestsPassed = $false }
        $color = if ($testResults[$test]) { "Green" } else { "Red" }
        Write-ColorOutput "- Test $test : $status" -ForegroundColor $color
    }
    
    if ($allTestsPassed) {
        Write-ColorOutput "`nTous les tests ont réussi!" -ForegroundColor Green
        Write-ColorOutput "La branche $BranchToTest est prête à être fusionnée dans main" -ForegroundColor Green
    }
    else {
        Write-ColorOutput "`nCertains tests ont échoué!" -ForegroundColor Red
        Write-ColorOutput "Veuillez corriger les problèmes avant de fusionner la branche $BranchToTest dans main" -ForegroundColor Red
    }
    
    return $allTestsPassed
}

# Exécution de la fonction principale
Write-ColorOutput "Script de test de la branche consolidée Qwen3" -ForegroundColor Cyan
Write-ColorOutput "Ce script va tester la branche consolidée pour s'assurer qu'elle fonctionne correctement" -ForegroundColor Cyan
Write-ColorOutput "Les tests suivants seront effectués:" -ForegroundColor Cyan
Write-ColorOutput "1. Test des parsers Qwen3" -ForegroundColor Cyan
Write-ColorOutput "2. Test des configurations Docker" -ForegroundColor Cyan
Write-ColorOutput "3. Test des scripts de démarrage" -ForegroundColor Cyan
Write-ColorOutput "4. Test du déploiement Docker (optionnel)" -ForegroundColor Cyan

$branchToTest = Read-Host "Quelle branche souhaitez-vous tester? (par défaut: qwen3-consolidated)"
if ([string]::IsNullOrEmpty($branchToTest)) {
    $branchToTest = "qwen3-consolidated"
}

$skipDocker = Read-Host "Voulez-vous ignorer le test de déploiement Docker? (O/N) (par défaut: N)"
$skipDockerDeployment = ($skipDocker -eq "O" -or $skipDocker -eq "o")

Start-Qwen3Tests -BranchToTest $branchToTest -SkipDockerDeployment:$skipDockerDeployment