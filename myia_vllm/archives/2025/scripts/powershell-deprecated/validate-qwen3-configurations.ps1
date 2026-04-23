#!/usr/bin/env pwsh
# Script de validation des configurations Qwen3 pour vLLM
# Ce script vérifie l'intégrité et la cohérence de toutes les configurations Qwen3

Write-Host "=== VALIDATION DES CONFIGURATIONS QWEN3 ===" -ForegroundColor Green

$ErrorCount = 0
$WarningCount = 0

function Test-FileExists {
    param([string]$Path, [string]$Description)
    if (Test-Path $Path) {
        Write-Host "✓ $Description : TROUVÉ" -ForegroundColor Green
        return $true
    } else {
        Write-Host "✗ $Description : MANQUANT" -ForegroundColor Red
        $script:ErrorCount++
        return $false
    }
}

function Test-PythonSyntax {
    param([string]$Path, [string]$Description)
    if (Test-Path $Path) {
        $result = python -m py_compile $Path 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ $Description : SYNTAXE VALIDE" -ForegroundColor Green
            return $true
        } else {
            Write-Host "✗ $Description : ERREUR DE SYNTAXE" -ForegroundColor Red
            Write-Host "  Détails: $result" -ForegroundColor Yellow
            $script:ErrorCount++
            return $false
        }
    } else {
        Write-Host "✗ $Description : FICHIER MANQUANT" -ForegroundColor Red
        $script:ErrorCount++
        return $false
    }
}

function Test-DockerComposeSyntax {
    param([string]$Path, [string]$Description)
    if (Test-Path $Path) {
        Push-Location (Split-Path $Path)
        $filename = Split-Path $Path -Leaf
        $result = docker-compose -f $filename config 2>&1
        Pop-Location
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ $Description : SYNTAXE DOCKER COMPOSE VALIDE" -ForegroundColor Green
            return $true
        } else {
            Write-Host "✗ $Description : ERREUR DOCKER COMPOSE" -ForegroundColor Red
            $script:ErrorCount++
            return $false
        }
    } else {
        Write-Host "✗ $Description : FICHIER MANQUANT" -ForegroundColor Red
        $script:ErrorCount++
        return $false
    }
}

function Test-ParserConfiguration {
    param([string]$Path, [string]$Description)
    if (Test-Path $Path) {
        $content = Get-Content $Path -Raw
        if ($content -match "--tool-call-parser qwen3") {
            Write-Host "✓ $Description : PARSER QWEN3 CONFIGURÉ" -ForegroundColor Green
            return $true
        } elseif ($content -match "--tool-call-parser llama3_json") {
            Write-Host "⚠ $Description : UTILISE PARSER LLAMA3_JSON" -ForegroundColor Yellow
            $script:WarningCount++
            return $false
        } else {
            Write-Host "✗ $Description : PARSER NON CONFIGURÉ" -ForegroundColor Red
            $script:ErrorCount++
            return $false
        }
    } else {
        Write-Host "✗ $Description : FICHIER MANQUANT" -ForegroundColor Red
        $script:ErrorCount++
        return $false
    }
}

Write-Host "`n1. VÉRIFICATION DES PARSERS QWEN3" -ForegroundColor Cyan
Test-FileExists "qwen3/parsers/qwen3_tool_parser.py" "Parser principal Qwen3"
Test-FileExists "qwen3/parsers/register_qwen3_parser.py" "Script d'enregistrement"
Test-FileExists "qwen3/parsers/qwen3_reasoning_parser.py" "Parser de raisonnement"

Write-Host "`n2. VALIDATION DE LA SYNTAXE PYTHON" -ForegroundColor Cyan
Test-PythonSyntax "qwen3/parsers/qwen3_tool_parser.py" "Parser principal"
Test-PythonSyntax "qwen3/parsers/register_qwen3_parser.py" "Script d'enregistrement"
Test-PythonSyntax "vllm-configs/test_qwen3_tool_calling.py" "Script de test"

Write-Host "`n3. VÉRIFICATION DES FICHIERS DOCKER COMPOSE" -ForegroundColor Cyan
Test-FileExists "vllm-configs/docker-compose/docker-compose-medium-qwen3-memory-optimized.yml" "Docker Compose 32B AWQ"
Test-FileExists "vllm-configs/docker-compose/docker-compose-micro-qwen3.yml" "Docker Compose 8B AWQ"
Test-FileExists "vllm-configs/docker-compose/docker-compose-mini-qwen3.yml" "Docker Compose 1.7B FP8"

Write-Host "`n4. VALIDATION DE LA SYNTAXE DOCKER COMPOSE" -ForegroundColor Cyan
Test-DockerComposeSyntax "vllm-configs/docker-compose/docker-compose-medium-qwen3-memory-optimized.yml" "32B AWQ"
Test-DockerComposeSyntax "vllm-configs/docker-compose/docker-compose-micro-qwen3.yml" "8B AWQ"
Test-DockerComposeSyntax "vllm-configs/docker-compose/docker-compose-mini-qwen3.yml" "1.7B FP8"

Write-Host "`n5. VÉRIFICATION DE LA CONFIGURATION DES PARSERS" -ForegroundColor Cyan
Test-ParserConfiguration "vllm-configs/docker-compose/docker-compose-micro-qwen3.yml" "Docker Compose 8B"
Test-ParserConfiguration "vllm-configs/docker-compose/docker-compose-mini-qwen3.yml" "Docker Compose 1.7B"
Test-ParserConfiguration "vllm-configs/start-with-qwen3-parser.sh" "Script de démarrage principal"
Test-ParserConfiguration "vllm-configs/start-with-qwen3-parser-fixed.sh" "Script de démarrage fixé"
Test-ParserConfiguration "vllm-configs/start-with-qwen3-parser-memory-optimized.sh" "Script optimisé mémoire"

Write-Host "`n6. VÉRIFICATION DES SCRIPTS DE DÉMARRAGE" -ForegroundColor Cyan
Test-FileExists "vllm-configs/start-with-qwen3-parser.sh" "Script de démarrage principal"
Test-FileExists "vllm-configs/start-with-qwen3-parser-fixed.sh" "Script de démarrage fixé"
Test-FileExists "vllm-configs/start-with-qwen3-parser-memory-optimized.sh" "Script optimisé mémoire"

Write-Host "`n7. VÉRIFICATION DES SCRIPTS DE TEST" -ForegroundColor Cyan
Test-FileExists "vllm-configs/test_qwen3_tool_calling.py" "Test tool calling"
Test-FileExists "vllm-configs/test_qwen3_parsers_new.py" "Test parsers"
Test-PythonSyntax "vllm-configs/test_qwen3_parsers_new.py" "Test parsers"

Write-Host "`n8. VÉRIFICATION DES FICHIERS DE CONFIGURATION" -ForegroundColor Cyan
Test-FileExists "vllm-configs/.env.example" "Exemple de fichier d'environnement"

Write-Host "`n=== RÉSUMÉ DE LA VALIDATION ===" -ForegroundColor Green
if ($ErrorCount -eq 0 -and $WarningCount -eq 0) {
    Write-Host "✓ TOUTES LES CONFIGURATIONS SONT VALIDES" -ForegroundColor Green
    exit 0
} elseif ($ErrorCount -eq 0) {
    Write-Host "⚠ CONFIGURATIONS VALIDES AVEC $WarningCount AVERTISSEMENT(S)" -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "✗ $ErrorCount ERREUR(S) ET $WarningCount AVERTISSEMENT(S) DETECTES" -ForegroundColor Red
    exit 1
}