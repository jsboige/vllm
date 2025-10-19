# Script temporaire pour archiver les configurations Docker obsolètes
$source = "d:/vllm/myia_vllm/configs/docker"
$dest = "d:/vllm/myia_vllm/archived/docker_configs_20251016"

Write-Host "=== Archivage des configurations Docker obsolètes ===" -ForegroundColor Cyan

$files = Get-ChildItem -Path $source -File -Filter "*.yml" | Where-Object { $_.Name -notlike "*profiles*" }

Write-Host "Fichiers à archiver: $($files.Count)" -ForegroundColor Yellow

foreach ($file in $files) {
    Write-Host "  - $($file.Name)" -ForegroundColor Gray
    Move-Item -Path $file.FullName -Destination $dest -Force
}

Write-Host "`n✅ Archivage terminé: $($files.Count) fichiers déplacés" -ForegroundColor Green