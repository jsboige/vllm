<#
.SYNOPSIS
    Surveille le statut de santé d'un container Docker jusqu'à ce qu'il soit healthy
.DESCRIPTION
    Script de monitoring pour attendre qu'un container Docker atteigne l'état healthy
.PARAMETER ContainerName
    Nom du container à surveiller
.PARAMETER Timeout
    Timeout en secondes (défaut: 600s = 10min)
.PARAMETER Interval
    Intervalle de vérification en secondes (défaut: 15s)
.EXAMPLE
    .\wait_for_container_healthy.ps1 -ContainerName "myia_vllm-medium-qwen3"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$ContainerName,
    
    [Parameter(Mandatory=$false)]
    [int]$Timeout = 600,
    
    [Parameter(Mandatory=$false)]
    [int]$Interval = 15
)

$elapsed = 0
$startTime = Get-Date

Write-Host "=== Surveillance Health Status ===" -ForegroundColor Cyan
Write-Host "Container: $ContainerName"
Write-Host "Timeout: $Timeout secondes"
Write-Host "Intervalle: $Interval secondes"
Write-Host ""

while ($elapsed -lt $Timeout) {
    $status = docker ps --filter "name=$ContainerName" --format '{{.Status}}'
    
    if (-not $status) {
        Write-Host "[$elapsed s] ❌ Container non trouvé" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "[$elapsed s] Status: $status" -ForegroundColor Yellow
    
    if ($status -like '*healthy*') {
        Write-Host ""
        Write-Host "✅ Container HEALTHY après $elapsed secondes" -ForegroundColor Green
        exit 0
    }
    
    Start-Sleep -Seconds $Interval
    $elapsed = [math]::Round(((Get-Date) - $startTime).TotalSeconds)
}

Write-Host ""
Write-Host "❌ TIMEOUT après $Timeout secondes" -ForegroundColor Red
Write-Host "Status final: $status" -ForegroundColor Red
exit 1