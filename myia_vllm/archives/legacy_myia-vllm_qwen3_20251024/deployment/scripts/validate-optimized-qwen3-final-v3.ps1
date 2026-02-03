# Script de validation des configurations optimisées pour Qwen3
# Ce script teste les performances des modèles Qwen3 après optimisation

Write-Host "Validation des configurations optimisées pour Qwen3..." -ForegroundColor Green

# Chargement des variables d'environnement depuis le fichier .env
Write-Host "Chargement des variables d'environnement..." -ForegroundColor Yellow
$envFile = "myia-vllm/qwen3/.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, [System.EnvironmentVariableTarget]::Process)
        }
    }
    Write-Host "Variables d'environnement chargées avec succès." -ForegroundColor Green
} else {
    Write-Host "Fichier .env non trouvé: $envFile" -ForegroundColor Red
    exit 1
}

# Afficher les variables clés pour vérification
Write-Host "`nVérification des variables clés:" -ForegroundColor Yellow
Write-Host "VLLM_PORT_MEDIUM: $env:VLLM_PORT_MEDIUM" -ForegroundColor Cyan
Write-Host "VLLM_PORT_MINI: $env:VLLM_PORT_MINI" -ForegroundColor Cyan
Write-Host "VLLM_PORT_MICRO: $env:VLLM_PORT_MICRO" -ForegroundColor Cyan
Write-Host "VLLM_API_KEY_MEDIUM: $env:VLLM_API_KEY_MEDIUM" -ForegroundColor Cyan
Write-Host "VLLM_API_KEY_MINI: $env:VLLM_API_KEY_MINI" -ForegroundColor Cyan
Write-Host "VLLM_API_KEY_MICRO: $env:VLLM_API_KEY_MICRO" -ForegroundColor Cyan

# Fonction pour tester un modèle
function Test-Model {
    param (
        [string]$ModelName,
        [string]$Port,
        [string]$ApiKey,
        [string]$ModelId
    )
    
    Write-Host "Test du modèle $ModelName sur le port $Port..." -ForegroundColor Cyan
    
    # Vérification que le service est en cours d'exécution
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:$Port/v1/models" -Headers @{Authorization = "Bearer $ApiKey"} -ErrorAction Stop
        $statusCode = $response.StatusCode
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        if (-not $statusCode) {
            $statusCode = 0
        }
    }
    
    if ($statusCode -eq 200) {
        Write-Host "  [OK] Service en ligne" -ForegroundColor Green
        
        # Test de génération simple
        $startTime = Get-Date
        try {
            $body = @{
                model = $ModelId
                messages = @(
                    @{
                        role = "user"
                        content = "Explique-moi brièvement ce qu'est l'intelligence artificielle."
                    }
                )
                max_tokens = 100
            } | ConvertTo-Json -Depth 10 -Compress
            
            $response = Invoke-WebRequest -Uri "http://localhost:$Port/v1/chat/completions" `
                -Method Post `
                -Headers @{
                    "Content-Type" = "application/json"
                    "Authorization" = "Bearer $ApiKey"
                } `
                -Body $body `
                -ErrorAction Stop
                
            $endTime = Get-Date
            $duration = ($endTime - $startTime).TotalSeconds
            
            Write-Host "  [OK] Génération simple: $duration secondes" -ForegroundColor Green
            
            # Test d'utilisation de la mémoire GPU
            try {
                $gpuStats = & nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits
                Write-Host "  [OK] Utilisation GPU:" -ForegroundColor Green
                Write-Host $gpuStats
            } catch {
                Write-Host "  [AVERTISSEMENT] Impossible d'obtenir les statistiques GPU: $_" -ForegroundColor Yellow
            }
            
            # Test de génération longue (avec une requête plus simple)
            $startTime = Get-Date
            $body = @{
                model = $ModelId
                messages = @(
                    @{
                        role = "user"
                        content = "Écris un court paragraphe sur l'intelligence artificielle."
                    }
                )
                max_tokens = 200
            } | ConvertTo-Json -Depth 10 -Compress
            
            $response = Invoke-WebRequest -Uri "http://localhost:$Port/v1/chat/completions" `
                -Method Post `
                -Headers @{
                    "Content-Type" = "application/json"
                    "Authorization" = "Bearer $ApiKey"
                } `
                -Body $body `
                -ErrorAction Stop
                
            $endTime = Get-Date
            $duration = ($endTime - $startTime).TotalSeconds
            
            Write-Host "  [OK] Génération longue: $duration secondes" -ForegroundColor Green
            
            # Récupérer et afficher la réponse
            $responseContent = $response.Content | ConvertFrom-Json
            $generatedText = $responseContent.choices[0].message.content
            Write-Host "  [OK] Texte généré: " -ForegroundColor Green
            Write-Host $generatedText -ForegroundColor Gray
            
            return $true
        } catch {
            Write-Host "  [ERREUR] Échec de la génération: $_" -ForegroundColor Red
            return $false
        }
    } else {
        Write-Host "  [ERREUR] Service non disponible (code HTTP: $statusCode)" -ForegroundColor Red
        return $false
    }
}

# Vérifier l'état des conteneurs
Write-Host "`nVérification de l'état des conteneurs..." -ForegroundColor Yellow
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | findstr "vllm"

# Définir les ports et clés API explicitement
$portMedium = $env:VLLM_PORT_MEDIUM
$portMini = $env:VLLM_PORT_MINI
$portMicro = $env:VLLM_PORT_MICRO
$keyMedium = $env:VLLM_API_KEY_MEDIUM
$keyMini = $env:VLLM_API_KEY_MINI
$keyMicro = $env:VLLM_API_KEY_MICRO

Write-Host "`nUtilisation des ports: MEDIUM=$portMedium, MINI=$portMini, MICRO=$portMicro" -ForegroundColor Yellow

# Test des modèles avec les IDs corrects
$mediumSuccess = Test-Model -ModelName "MEDIUM (32B)" -Port $portMedium -ApiKey $keyMedium -ModelId "Qwen/Qwen3-32B-AWQ"
$miniSuccess = Test-Model -ModelName "MINI (8B)" -Port $portMini -ApiKey $keyMini -ModelId "Qwen/Qwen3-8B-AWQ"
$microSuccess = Test-Model -ModelName "MICRO (1.7B)" -Port $portMicro -ApiKey $keyMicro -ModelId "Qwen/Qwen3-1.7B-FP8"

# Résumé des tests
Write-Host "`nRésumé des tests:" -ForegroundColor Yellow
Write-Host "MEDIUM (32B): $(if ($mediumSuccess) { '[OK]' } else { '[ECHEC]' })" -ForegroundColor $(if ($mediumSuccess) { "Green" } else { "Red" })
Write-Host "MINI (8B): $(if ($miniSuccess) { '[OK]' } else { '[ECHEC]' })" -ForegroundColor $(if ($miniSuccess) { "Green" } else { "Red" })
Write-Host "MICRO (1.7B): $(if ($microSuccess) { '[OK]' } else { '[ECHEC]' })" -ForegroundColor $(if ($microSuccess) { "Green" } else { "Red" })

# Recommandations finales
Write-Host "`nRecommandations:" -ForegroundColor Yellow
if ($mediumSuccess -and $miniSuccess -and $microSuccess) {
    Write-Host "Tous les modèles fonctionnent correctement avec les configurations optimisées." -ForegroundColor Green
    Write-Host "Surveillez les performances sur une période prolongée pour confirmer la stabilité." -ForegroundColor Green
} else {
    Write-Host "Certains modèles présentent des problèmes. Vérifiez les logs Docker pour plus de détails:" -ForegroundColor Red
    Write-Host "docker logs docker-compose-vllm-medium-qwen3-1" -ForegroundColor Cyan
    Write-Host "docker logs myia-vllm-mini-qwen3" -ForegroundColor Cyan
    Write-Host "docker logs myia-vllm-micro-qwen3" -ForegroundColor Cyan
}

Write-Host "`nValidation terminée." -ForegroundColor Green