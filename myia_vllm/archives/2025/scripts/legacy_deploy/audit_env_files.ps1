# Audit des fichiers .env
$envFiles = Get-ChildItem -Path D:\vllm -Recurse -Filter ".env" -File -Force -ErrorAction SilentlyContinue

Write-Host "=== AUDIT FICHIERS .env ===" -ForegroundColor Cyan
Write-Host ""

foreach ($file in $envFiles) {
    Write-Host "Fichier: $($file.FullName)" -ForegroundColor Yellow
    Write-Host "  Taille: $([math]::Round($file.Length/1KB, 2)) KB"
    Write-Host "  Modifié: $($file.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'))"
    Write-Host ""
}

Write-Host "Total: $($envFiles.Count) fichiers .env trouvés" -ForegroundColor Green