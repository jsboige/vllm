# Script PowerShell pour vérifier le statut et les logs des containers vLLM

# Fonction pour afficher l'aide
function Show-Help {
    Write-Host "Usage: .\check-containers.ps1 [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Help                Afficher cette aide"
    Write-Host "  -Status              Vérifier uniquement le statut des containers"
    Write-Host "  -Logs                Afficher uniquement les logs des containers"
    Write-Host "  -Test                Effectuer des tests d'appel d'outils"
    Write-Host "  -Container NAME      Vérifier uniquement le container spécifié (micro, mini, medium)"
    Write-Host "  -Lines N             Nombre de lignes de logs à afficher (défaut: 20)"
    Write-Host ""
    Write-Host "Exemples:"
    Write-Host "  .\check-containers.ps1                    # Vérifier le statut et les logs de tous les containers"
    Write-Host "  .\check-containers.ps1 -Container micro   # Vérifier uniquement le container micro"
    Write-Host "  .\check-containers.ps1 -Test              # Effectuer des tests d'appel d'outils"
}

# Paramètres
param (
    [switch]$Help,
    [switch]$Status,
    [switch]$Logs,
    [switch]$Test,
    [string]$Container = "",
    [int]$Lines = 20
)

# Afficher l'aide si demandé
if ($Help) {
    Show-Help
    exit 0
}

# Si aucune option n'est spécifiée, activer status et logs par défaut
if (-not $Status -and -not $Logs -and -not $Test) {
    $Status = $true
    $Logs = $true
}

# Fonction pour vérifier le statut des containers
function Check-Status {
    param (
        [string]$Container
    )
    
    Write-Host "=== Vérification du statut des containers ===" -ForegroundColor Cyan
    
    if ($Container) {
        Write-Host "Statut du container myia-vllm-$Container-qwen3:" -ForegroundColor Yellow
        docker ps --filter "name=myia-vllm-$Container-qwen3" --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"
    }
    else {
        Write-Host "Statut de tous les containers:" -ForegroundColor Yellow
        docker ps --filter "name=myia-vllm" --format "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"
    }
    
    Write-Host ""
}

# Fonction pour afficher les logs des containers
function Check-Logs {
    param (
        [string]$Container,
        [int]$Lines
    )
    
    Write-Host "=== Vérification des logs des containers ===" -ForegroundColor Cyan
    
    if ($Container) {
        Write-Host "Logs du container myia-vllm-$Container-qwen3:" -ForegroundColor Yellow
        docker logs myia-vllm-$Container-qwen3 --tail $Lines
    }
    else {
        Write-Host "Logs du container myia-vllm-micro-qwen3:" -ForegroundColor Yellow
        docker logs myia-vllm-micro-qwen3 --tail $Lines
        Write-Host ""
        
        Write-Host "Logs du container myia-vllm-mini-qwen3:" -ForegroundColor Yellow
        docker logs myia-vllm-mini-qwen3 --tail $Lines
        Write-Host ""
        
        Write-Host "Logs du container myia-vllm-medium-qwen3:" -ForegroundColor Yellow
        docker logs myia-vllm-medium-qwen3 --tail $Lines
    }
    
    Write-Host ""
}

# Fonction pour tester les appels d'outils
function Run-Tests {
    param (
        [string]$Container
    )
    
    Write-Host "=== Test des appels d'outils ===" -ForegroundColor Cyan
    
    # Déterminer le port en fonction du container
    $port = 8000  # Par défaut, utiliser le port du container micro
    $containerName = "micro"
    
    if ($Container) {
        switch ($Container) {
            "micro" { $port = 8000; $containerName = "micro" }
            "mini" { $port = 5001; $containerName = "mini" }
            "medium" { $port = 5002; $containerName = "medium" }
        }
    }
    
    Write-Host "Test d'appel d'outil sur le container myia-vllm-$containerName-qwen3 (port $port)..." -ForegroundColor Yellow
    
    # Créer un fichier temporaire pour la requête
    $tempFile = [System.IO.Path]::GetTempFileName()
    
    $requestBody = @"
{
  "model": "Qwen/Qwen3-7B-Instruct",
  "messages": [
    {"role": "user", "content": "Quelle est la météo à Paris aujourd'hui? Utilise l'outil get_weather pour obtenir cette information."}
  ],
  "tools": [{
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "Obtenir la météo pour une ville donnée",
      "parameters": {
        "type": "object",
        "properties": {
          "location": {
            "type": "string",
            "description": "La ville pour laquelle obtenir la météo"
          },
          "unit": {
            "type": "string",
            "enum": ["celsius", "fahrenheit"],
            "description": "L'unité de température"
          }
        },
        "required": ["location"]
      }
    }
  }],
  "tool_choice": "auto",
  "temperature": 0.7,
  "max_tokens": 1024
}
"@
    
    Set-Content -Path $tempFile -Value $requestBody
    
    # Envoyer la requête
    Write-Host "Envoi de la requête..." -ForegroundColor Yellow
    
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:$port/v1/chat/completions" `
            -Method Post `
            -Headers @{"Content-Type" = "application/json"} `
            -InFile $tempFile
        
        # Afficher la réponse formatée
        $response | ConvertTo-Json -Depth 10
    }
    catch {
        Write-Host "Erreur lors de l'envoi de la requête: $_" -ForegroundColor Red
    }
    
    # Supprimer le fichier temporaire
    Remove-Item -Path $tempFile
    
    Write-Host ""
}

# Exécuter les actions demandées
if ($Status) {
    Check-Status -Container $Container
}

if ($Logs) {
    Check-Logs -Container $Container -Lines $Lines
}

if ($Test) {
    Run-Tests -Container $Container
}

Write-Host "Vérification terminée!" -ForegroundColor Green