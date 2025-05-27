# Script PowerShell pour rechercher toutes les références à '--parser qwen3' ou similaires dans le projet
# Cela nous aidera à identifier d'autres fichiers qui pourraient nécessiter des corrections

Write-Host "Recherche de références à '--parser qwen3' ou similaires dans le projet..." -ForegroundColor Green

# Extensions de fichiers à rechercher
$fileExtensions = @("*.yml", "*.yaml", "*.sh", "*.ps1", "*.md")

# Rechercher les occurrences de '--parser qwen3'
Write-Host "`n=== Fichiers contenant '--parser qwen3' ===" -ForegroundColor Yellow
foreach ($ext in $fileExtensions) {
    Get-ChildItem -Path . -Recurse -Filter $ext | Select-String -Pattern "--parser qwen3" | ForEach-Object {
        Write-Host "$($_.Path):$($_.LineNumber): $($_.Line)" -ForegroundColor Cyan
    }
}

# Rechercher les occurrences de 'parser qwen3' (sans les tirets)
Write-Host "`n=== Fichiers contenant 'parser qwen3' ===" -ForegroundColor Yellow
foreach ($ext in $fileExtensions) {
    Get-ChildItem -Path . -Recurse -Filter $ext | Select-String -Pattern "parser qwen3" | ForEach-Object {
        Write-Host "$($_.Path):$($_.LineNumber): $($_.Line)" -ForegroundColor Cyan
    }
}

# Rechercher les occurrences de 'parser.*qwen3'
Write-Host "`n=== Fichiers contenant des références à 'parser' et 'qwen3' à proximité ===" -ForegroundColor Yellow
foreach ($ext in $fileExtensions) {
    Get-ChildItem -Path . -Recurse -Filter $ext | Select-String -Pattern "parser.*qwen3" | ForEach-Object {
        Write-Host "$($_.Path):$($_.LineNumber): $($_.Line)" -ForegroundColor Cyan
    }
}

# Rechercher les occurrences de 'tool.*parser.*qwen3'
Write-Host "`n=== Fichiers contenant des références à 'tool', 'parser' et 'qwen3' à proximité ===" -ForegroundColor Yellow
foreach ($ext in $fileExtensions) {
    Get-ChildItem -Path . -Recurse -Filter $ext | Select-String -Pattern "tool.*parser.*qwen3" | ForEach-Object {
        Write-Host "$($_.Path):$($_.LineNumber): $($_.Line)" -ForegroundColor Cyan
    }
}

# Rechercher les occurrences de 'tool-call-parser'
Write-Host "`n=== Fichiers contenant déjà 'tool-call-parser' (référence correcte) ===" -ForegroundColor Yellow
foreach ($ext in $fileExtensions) {
    Get-ChildItem -Path . -Recurse -Filter $ext | Select-String -Pattern "tool-call-parser" | ForEach-Object {
        Write-Host "$($_.Path):$($_.LineNumber): $($_.Line)" -ForegroundColor Cyan
    }
}

Write-Host "`nRecherche terminée." -ForegroundColor Green
Write-Host "Si d'autres fichiers contiennent des références incorrectes, ils devront également être corrigés." -ForegroundColor Yellow