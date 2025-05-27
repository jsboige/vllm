# Script PowerShell pour sauvegarder le fichier .env vers Google Drive
# Version améliorée pour l'automatisation via tâche planifiée

# Configuration de la journalisation
$logDir = "D:\vllm\vllm-configs\logs"
$logFile = Join-Path -Path $logDir -ChildPath "backup-env-log-$(Get-Date -Format 'yyyyMMdd').txt"

# Fonction de journalisation
function Write-Log {
    param (
        [Parameter(Mandatory=$true)]
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    
    # Afficher dans la console
    Write-Host $logMessage
    
    # Écrire dans le fichier journal
    try {
        if (-not (Test-Path $logDir)) {
            New-Item -Path $logDir -ItemType Directory -Force | Out-Null
        }
        Add-Content -Path $logFile -Value $logMessage -ErrorAction Stop
    }
    catch {
        Write-Host "ERREUR: Impossible d'écrire dans le fichier journal: $_" -ForegroundColor Red
    }
}

# Bloc try-catch global pour capturer toutes les erreurs
try {
    Write-Log "Démarrage de la sauvegarde du fichier .env vers Google Drive"
    
    # Chemins des fichiers (chemins absolus)
    $scriptPath = $MyInvocation.MyCommand.Path
    $scriptDir = Split-Path -Parent $scriptPath
    $rootDir = Split-Path -Parent $scriptDir
    $envFile = Join-Path -Path $rootDir -ChildPath ".env"
    $gdriveDir = "G:\Mon Drive\MyIA\IA\LLMs\vllm-secrets"
    
    Write-Log "Chemin du fichier .env: $envFile"
    Write-Log "Chemin du répertoire Google Drive: $gdriveDir"
    
    # Vérifier si le fichier .env existe
    if (-not (Test-Path $envFile)) {
        Write-Log "Le fichier .env n'existe pas. Veuillez exécuter save-secrets.sh d'abord." "ERROR"
        exit 1
    }
    
    # Créer un nom de fichier avec la date et l'heure
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupFilename = "env_backup_${timestamp}.env"
    
    # Vérifier si le répertoire de destination existe, sinon le créer
    if (-not (Test-Path $gdriveDir)) {
        Write-Log "Création du répertoire $gdriveDir..."
        try {
            New-Item -Path $gdriveDir -ItemType Directory -Force -ErrorAction Stop | Out-Null
            Write-Log "Répertoire créé avec succès"
        }
        catch {
            Write-Log "Erreur lors de la création du répertoire: $_" "ERROR"
            exit 1
        }
    }
    
    # Copier le fichier .env vers Google Drive
    Write-Log "Sauvegarde du fichier .env vers Google Drive local..."
    try {
        Copy-Item -Path $envFile -Destination "$gdriveDir\$backupFilename" -ErrorAction Stop
        Write-Log "Sauvegarde réussie: $gdriveDir\$backupFilename"
        
        # Créer un fichier latest.env qui pointe vers la dernière sauvegarde
        Write-Log "Mise à jour du fichier latest.env..."
        Copy-Item -Path $envFile -Destination "$gdriveDir\latest.env" -ErrorAction Stop
        
        # Lister les sauvegardes disponibles
        Write-Log "Sauvegardes disponibles sur Google Drive:"
        $backups = Get-ChildItem -Path $gdriveDir -Filter "env_backup_*.env" | Sort-Object LastWriteTime -Descending
        foreach ($backup in $backups) {
            Write-Log "  - $($backup.Name) ($(Get-Date $backup.LastWriteTime -Format 'yyyy-MM-dd HH:mm:ss'))"
        }
        
        # Nettoyer les anciennes sauvegardes (garder les 10 dernières)
        Write-Log "Vérification des anciennes sauvegardes..."
        if ($backups.Count -gt 10) {
            Write-Log "Suppression des sauvegardes anciennes (conservation des 10 plus récentes)..."
            $backups | Select-Object -Skip 10 | ForEach-Object {
                Write-Log "Suppression de $($_.Name)..."
                Remove-Item -Path $_.FullName -ErrorAction Stop
            }
        }
        else {
            Write-Log "Nombre total de sauvegardes: $($backups.Count) (pas besoin de nettoyage)"
        }
    }
    catch {
        Write-Log "Erreur lors de la sauvegarde vers Google Drive: $_" "ERROR"
        exit 1
    }
    
    Write-Log "Sauvegarde terminée avec succès"
}
catch {
    Write-Log "Erreur non gérée: $_" "ERROR"
    exit 1
}