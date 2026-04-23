# MONITORING GRID SEARCH - SAFETY CHECKS
param(
    [int]$IntervalSeconds = 60,  # Vérification toutes les 60s
    [int]$MaxFailedChecks = 3    # Arrêt si 3 échecs consécutifs
)

$failedChecks = 0
$lastConfigNumber = 0

Write-Host "🔍 Grid Search Safety Monitor Started" -ForegroundColor Cyan
Write-Host "Checking every ${IntervalSeconds}s | Max failed checks: ${MaxFailedChecks}" -ForegroundColor Yellow

while ($true) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    
    # CHECK 1: Container exists and running
    $container = docker ps --filter "name=myia_vllm-medium-qwen3" --format "{{.Names}}|{{.Status}}" | Select-Object -First 1
    
    if (-not $container) {
        # Vérifier si grid search terminé (dernier log = "Grid search completed")
        $logFiles = Get-ChildItem "logs/grid_search_execution_*.log" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($logFiles) {
            $lastLog = Get-Content $logFiles.FullName -Tail 5 | Out-String
            if ($lastLog -match "Grid search completed|All configurations tested") {
                Write-Host "✅ [$timestamp] Grid Search COMPLETED - Stopping monitor" -ForegroundColor Green
                exit 0
            }
        }
        
        $failedChecks++
        Write-Host "❌ [$timestamp] Container NOT FOUND (failed checks: $failedChecks/$MaxFailedChecks)" -ForegroundColor Red
        
        if ($failedChecks -ge $MaxFailedChecks) {
            Write-Host "🚨 CRITICAL: Container absent $MaxFailedChecks times - STOPPING GRID SEARCH" -ForegroundColor Red
            # Tenter cleanup
            docker compose -p myia_vllm -f configs/docker/docker-compose.yml -f configs/docker/profiles/medium.yml down --remove-orphans 2>&1 | Out-Null
            Write-Host "🛑 Grid search stopped. Check logs/grid_search_execution_*.log for errors" -ForegroundColor Yellow
            exit 1
        }
    } else {
        $failedChecks = 0  # Reset counter
        $status = $container.Split("|")[1]
        
        # CHECK 2: Status Exited = FAILED
        if ($status -match "Exited") {
            Write-Host "🚨 [$timestamp] Container CRASHED: $status" -ForegroundColor Red
            Write-Host "Last 30 log lines:" -ForegroundColor Yellow
            $logFiles = Get-ChildItem "logs/grid_search_execution_*.log" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
            if ($logFiles) {
                Get-Content $logFiles.FullName -Tail 30
            }
            exit 1
        }
        
        Write-Host "✅ [$timestamp] Container OK: $status" -ForegroundColor Green
    }
    
    # CHECK 3: Progress tracking
    $logFiles = Get-ChildItem "logs/grid_search_execution_*.log" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($logFiles) {
        $recentLogs = Get-Content $logFiles.FullName -Tail 50 | Out-String
        if ($recentLogs -match "CONFIGURATION (\d+)/12") {
            $currentConfig = [int]$matches[1]
            if ($currentConfig -ne $lastConfigNumber) {
                $percentComplete = [math]::Round(($currentConfig / 12) * 100, 1)
                Write-Host "📊 [$timestamp] Progress: Config $currentConfig/12 ($percentComplete%)" -ForegroundColor Cyan
                $lastConfigNumber = $currentConfig
            }
        }
    }
    
    # CHECK 4: Memory usage
    $memoryUsage = Get-Process | Where-Object {$_.ProcessName -eq "docker" -or $_.ProcessName -eq "dockerd"} | 
                   Measure-Object WorkingSet64 -Sum | 
                   Select-Object @{Name="RAM_GB";Expression={[math]::Round($_.Sum/1GB,2)}}
    
    if ($memoryUsage.RAM_GB -gt 80) {
        Write-Host "⚠️  [$timestamp] High RAM usage: $($memoryUsage.RAM_GB)GB (Docker processes)" -ForegroundColor Yellow
    }
    
    Start-Sleep -Seconds $IntervalSeconds
}