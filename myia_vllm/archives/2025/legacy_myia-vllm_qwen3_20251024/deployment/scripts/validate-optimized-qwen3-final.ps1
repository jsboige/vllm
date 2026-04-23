# Script de validation des configurations optimisées pour Qwen3
# Ce script teste les performances des modèles Qwen3 après optimisation

Write-Host "Validation des configurations optimisées pour Qwen3..." -ForegroundColor Green

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
            } | ConvertTo-Json
            
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
            
            # Test de génération avec contexte long
            $startTime = Get-Date
            $body = @{
                model = $ModelId
                messages = @(
                    @{
                        role = "user"
                        content = "Écris un essai de 500 mots sur l'impact de l'intelligence artificielle sur la société moderne."
                    }
                )
                max_tokens = 500
            } | ConvertTo-Json
            
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
            
            # Test d'utilisation de la mémoire GPU
            $gpuStats = & nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits
            Write-Host "  [OK] Utilisation GPU:" -ForegroundColor Green
            Write-Host $gpuStats
            
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

# Attente pour s'assurer que les services sont démarrés
Write-Host "Attente du démarrage complet des services (30 secondes)..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

# Test des modèles avec les IDs corrects
$mediumSuccess = Test-Model -ModelName "MEDIUM (32B)" -Port $env:VLLM_PORT_MEDIUM -ApiKey $env:VLLM_API_KEY_MEDIUM -ModelId "Qwen/Qwen3-32B-AWQ"
$miniSuccess = Test-Model -ModelName "MINI (8B)" -Port $env:VLLM_PORT_MINI -ApiKey $env:VLLM_API_KEY_MINI -ModelId "Qwen/Qwen3-8B-AWQ"
$microSuccess = Test-Model -ModelName "MICRO (1.7B)" -Port $env:VLLM_PORT_MICRO -ApiKey $env:VLLM_API_KEY_MICRO -ModelId "Qwen/Qwen3-1.7B-FP8"

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