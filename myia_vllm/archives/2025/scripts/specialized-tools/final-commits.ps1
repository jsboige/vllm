# Script PowerShell pour effectuer les derniers commits du projet

# Vérifier si des modifications sont en attente
$status = git status --porcelain
if ([string]::IsNullOrEmpty($status)) {
    Write-Host "Aucune modification à commiter." -ForegroundColor Yellow
    exit 0
}

# Ajouter les fichiers docker-compose
Write-Host "Ajout des fichiers docker-compose..." -ForegroundColor Cyan
git add vllm-configs/docker-compose/docker-compose-micro-qwen3.yml
git add vllm-configs/docker-compose/docker-compose-mini-qwen3.yml
git add vllm-configs/docker-compose/docker-compose-medium-qwen3.yml
git commit -m "fix: standardize Docker Compose project prefix to myia-vllm"

# Ajouter les scripts de déploiement
Write-Host "Ajout des scripts de déploiement..." -ForegroundColor Cyan
git add vllm-configs/scripts/deploy-all.sh
git add vllm-configs/scripts/deploy-all.ps1
git commit -m "feat: add deployment scripts for all containers"

# Ajouter la documentation
Write-Host "Ajout de la documentation..." -ForegroundColor Cyan
git add vllm-configs/DEPLOYMENT-VERIFICATION.md
git add myia-vllm/README.md
git commit -m "docs: add comprehensive README with deployment instructions"

# Ajouter ce script lui-même
git add vllm-configs/scripts/final-commits.sh
git add vllm-configs/scripts/final-commits.ps1
git commit -m "chore: final cleanup of intermediate files"

Write-Host "Tous les commits ont été effectués avec succès." -ForegroundColor Green