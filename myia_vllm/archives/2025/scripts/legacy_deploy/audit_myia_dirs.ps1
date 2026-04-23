# Audit des répertoires myia*
$basePath = "D:\vllm"
$dirs = @("myia_vllm", "myia_vvllm", "myia-vllm")

Write-Host "=== AUDIT RÉPERTOIRES MYIA* ===" -ForegroundColor Cyan
Write-Host ""

foreach ($dirName in $dirs) {
    $fullPath = Join-Path $basePath $dirName
    
    if (Test-Path $fullPath) {
        Write-Host "Répertoire: $dirName" -ForegroundColor Yellow
        Write-Host "  Chemin: $fullPath"
        
        $dir = Get-Item $fullPath
        Write-Host "  Créé: $($dir.CreationTime.ToString('yyyy-MM-dd HH:mm:ss'))"
        
        $fileCount = (Get-ChildItem -Path $fullPath -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
        Write-Host "  Nombre de fichiers: $fileCount"
        
        $totalSize = (Get-ChildItem -Path $fullPath -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $sizeMB = [math]::Round($totalSize / 1MB, 2)
        Write-Host "  Taille totale: $sizeMB MB"
        
        Write-Host ""
    } else {
        Write-Host "Répertoire: $dirName - N'EXISTE PAS" -ForegroundColor Red
        Write-Host ""
    }
}