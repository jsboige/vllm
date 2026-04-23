# Script PowerShell pour corriger l'option du parser d'outils Qwen3
# Ce script remplace '--parser qwen3' par '--tool-call-parser qwen3' dans les fichiers de configuration

Write-Host "Correction de l'option du parser d'outils Qwen3..." -ForegroundColor Green

# Chemin vers les fichiers à modifier
$DOCKER_COMPOSE_FILE = "docker-compose/qwen3/docker-compose-qwen3-32b-awq.yml"
$README_FILE = "docker-compose/qwen3/README-32B-AWQ.md"

# Vérifier si les fichiers existent
if (-not (Test-Path $DOCKER_COMPOSE_FILE)) {
    Write-Host "Erreur: Le fichier $DOCKER_COMPOSE_FILE n'existe pas." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $README_FILE)) {
    Write-Host "Erreur: Le fichier $README_FILE n'existe pas." -ForegroundColor Red
    exit 1
}

# Faire une sauvegarde des fichiers originaux
Copy-Item $DOCKER_COMPOSE_FILE -Destination "${DOCKER_COMPOSE_FILE}.bak"
Copy-Item $README_FILE -Destination "${README_FILE}.bak"

Write-Host "Sauvegarde des fichiers originaux créée." -ForegroundColor Green

# Lire le contenu des fichiers
$dockerComposeContent = Get-Content $DOCKER_COMPOSE_FILE -Raw
$readmeContent = Get-Content $README_FILE -Raw

# Modifier le contenu
$dockerComposeContentModified = $dockerComposeContent -replace '--parser qwen3', '--tool-call-parser qwen3'
$readmeContentModified = $readmeContent -replace '\| parser \| qwen3 \| Parser', '| tool-call-parser | qwen3 | Parser'

# Écrire le contenu modifié dans les fichiers
Set-Content -Path $DOCKER_COMPOSE_FILE -Value $dockerComposeContentModified
Set-Content -Path $README_FILE -Value $readmeContentModified

Write-Host "Modifications appliquées avec succès." -ForegroundColor Green

# Afficher les différences
Write-Host "`nDifférences dans le fichier Docker Compose:" -ForegroundColor Yellow
$diffDockerCompose = Compare-Object (Get-Content "${DOCKER_COMPOSE_FILE}.bak") (Get-Content $DOCKER_COMPOSE_FILE)
if ($diffDockerCompose) {
    $diffDockerCompose | ForEach-Object {
        if ($_.SideIndicator -eq "=>") {
            Write-Host "+ $($_.InputObject)" -ForegroundColor Green
        } else {
            Write-Host "- $($_.InputObject)" -ForegroundColor Red
        }
    }
} else {
    Write-Host "Aucune différence détectée." -ForegroundColor Yellow
}

Write-Host "`nDifférences dans le fichier README:" -ForegroundColor Yellow
$diffReadme = Compare-Object (Get-Content "${README_FILE}.bak") (Get-Content $README_FILE)
if ($diffReadme) {
    $diffReadme | ForEach-Object {
        if ($_.SideIndicator -eq "=>") {
            Write-Host "+ $($_.InputObject)" -ForegroundColor Green
        } else {
            Write-Host "- $($_.InputObject)" -ForegroundColor Red
        }
    }
} else {
    Write-Host "Aucune différence détectée." -ForegroundColor Yellow
}

Write-Host "`nPour redéployer le container avec les modifications:" -ForegroundColor Cyan
Write-Host "cd docker-compose/qwen3"
Write-Host ".\deploy-qwen3-32b-awq.ps1"

Write-Host "`nTerminé." -ForegroundColor Green