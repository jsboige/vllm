# Script PowerShell pour tester la sauvegarde des secrets vLLM
# Ce script exécute manuellement le script de sauvegarde et vérifie les résultats

Write-Host "Test de la sauvegarde des secrets vLLM" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan

# Chemin du script de sauvegarde
$scriptPath = Join-Path -Path $PSScriptRoot -ChildPath "backup-env-to-gdrive.ps1"
$scriptPath = [System.IO.Path]::GetFullPath($scriptPath)

# Vérifier si le script de sauvegarde existe
if (-not (Test-Path $scriptPath)) {
    Write-Host "Le script de sauvegarde n'existe pas: $scriptPath" -ForegroundColor Red
    exit 1
}

# Vérifier si le fichier .env existe
$rootDir = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path -Path $rootDir -ChildPath ".env"

if (-not (Test-Path $envFile)) {
    Write-Host "Le fichier .env n'existe pas: $envFile" -ForegroundColor Red
    Write-Host "Veuillez créer ce fichier avant de tester la sauvegarde." -ForegroundColor Yellow
    exit 1
}

# Vérifier si le répertoire Google Drive est accessible
$gdriveDir = "G:\Mon Drive\MyIA\IA\LLMs\vllm-secrets"
if (-not (Test-Path $gdriveDir)) {
    Write-Host "Le répertoire Google Drive n'est pas accessible: $gdriveDir" -ForegroundColor Red
    Write-Host "Veuillez vérifier que Google Drive est correctement monté." -ForegroundColor Yellow
    exit 1
}

# Exécuter le script de sauvegarde
Write-Host "`nExécution du script de sauvegarde..." -ForegroundColor Cyan
try {
    & $scriptPath
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`nLe script de sauvegarde s'est exécuté avec succès." -ForegroundColor Green
        
        # Vérifier les fichiers de sauvegarde
        Write-Host "`nVérification des fichiers de sauvegarde..." -ForegroundColor Cyan
        
        # Vérifier si latest.env existe
        if (Test-Path "$gdriveDir\latest.env") {
            $latestEnv = Get-Item "$gdriveDir\latest.env"
            Write-Host "  - latest.env existe (modifié le $(Get-Date $latestEnv.LastWriteTime -Format 'yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Green
        } else {
            Write-Host "  - latest.env n'existe pas!" -ForegroundColor Red
        }
        
        # Vérifier les sauvegardes
        $backups = Get-ChildItem -Path $gdriveDir -Filter "env_backup_*.env" | Sort-Object LastWriteTime -Descending
        if ($backups.Count -gt 0) {
            Write-Host "  - $($backups.Count) sauvegardes trouvées" -ForegroundColor Green
            Write-Host "  - Dernière sauvegarde: $($backups[0].Name) ($(Get-Date $backups[0].LastWriteTime -Format 'yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Green
        } else {
            Write-Host "  - Aucune sauvegarde trouvée!" -ForegroundColor Red
        }
        
        # Vérifier les journaux
        $logDir = Join-Path -Path $PSScriptRoot -ChildPath "logs"
        $logFiles = Get-ChildItem -Path $logDir -Filter "backup-env-log-*.txt" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
        
        if ($logFiles.Count -gt 0) {
            Write-Host "  - Fichiers journaux trouvés: $($logFiles.Count)" -ForegroundColor Green
            Write-Host "  - Dernier journal: $($logFiles[0].Name)" -ForegroundColor Green
            
            # Afficher les 5 dernières lignes du journal
            Write-Host "`nDernières entrées du journal:" -ForegroundColor Cyan
            Get-Content -Path $logFiles[0].FullName -Tail 5 | ForEach-Object {
                Write-Host "    $_" -ForegroundColor White
            }
        } else {
            Write-Host "  - Aucun fichier journal trouvé!" -ForegroundColor Yellow
        }
    } else {
        Write-Host "`nLe script de sauvegarde a échoué avec le code de sortie $LASTEXITCODE." -ForegroundColor Red
    }
}
catch {
    Write-Host "`nErreur lors de l'exécution du script de sauvegarde: $_" -ForegroundColor Red
}

# Instructions pour vérifier la tâche planifiée
$taskName = "vLLM_Secrets_Backup"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($task) {
    Write-Host "`nInformations sur la tâche planifiée:" -ForegroundColor Cyan
    $task | Select-Object TaskName, State, LastRunTime, NextRunTime | Format-Table -AutoSize
} else {
    Write-Host "`nLa tâche planifiée '$taskName' n'existe pas encore." -ForegroundColor Yellow
    Write-Host "Exécutez le script setup-scheduled-backup-task.ps1 pour la configurer." -ForegroundColor Yellow
}