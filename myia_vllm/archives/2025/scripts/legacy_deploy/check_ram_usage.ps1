# Check RAM Usage - Temporary Script for Grid Search Pre-Flight
$procs = Get-Process | Where-Object {$_.WorkingSet64 -gt 10GB}

if ($procs) {
    Write-Host "`nProcessus consommant >10GB RAM:" -ForegroundColor Yellow
    $procs | ForEach-Object {
        $ramGB = [math]::Round($_.WorkingSet64/1GB, 2)
        Write-Host ("{0,-30} PID:{1,8}  RAM:{2,8:N2} GB" -f $_.Name, $_.Id, $ramGB)
    }
} else {
    Write-Host "`n✅ Aucun processus >10GB RAM détecté" -ForegroundColor Green
}