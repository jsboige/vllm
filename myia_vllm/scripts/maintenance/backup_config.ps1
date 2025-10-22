<#
.SYNOPSIS
    Backup automatisé de la configuration vLLM medium avant modifications

.DESCRIPTION
    Crée une copie horodatée du fichier de configuration medium.yml dans le répertoire backups.
    Ce script doit être exécuté AVANT toute modification de la configuration vLLM.
    
    Fonctionnalités :
    - Horodatage systématique (format: medium_yyyyMMdd_HHmmss.yml)
    - Création automatique du répertoire backups
    - Vérification de l'existence du fichier source
    - Output clair du chemin backup créé
    - Support backup de fichiers additionnels (.env, docker-compose.yml)

.PARAMETER SourceFile
    Chemin du fichier à sauvegarder (défaut: configs/docker/profiles/medium.yml)

.PARAMETER BackupDir
    Répertoire de destination pour les backups (défaut: configs/docker/profiles/backups)

.PARAMETER IncludeEnv
    Inclure également le fichier .env dans le backup

.PARAMETER IncludeCompose
    Inclure également le fichier docker-compose.yml dans le backup

.PARAMETER Comment
    Commentaire optionnel à ajouter au nom du fichier backup

.EXAMPLE
    .\backup_config.ps1
    Backup simple de medium.yml avec horodatage

.EXAMPLE
    .\backup_config.ps1 -IncludeEnv -IncludeCompose
    Backup complet (medium.yml + .env + docker-compose.yml)

.EXAMPLE
    .\backup_config.ps1 -Comment "before_gpu_tuning"
    Backup avec commentaire descriptif

.NOTES
    Version: 1.0.0
    Date: 2025-10-22
    Auteur: Roo Code (Mode)
    Fréquence recommandée: Avant chaque modification de configuration
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$SourceFile = "configs/docker/profiles/medium.yml",
    
    [Parameter(Mandatory=$false)]
    [string]$BackupDir = "configs/docker/profiles/backups",
    
    [Parameter(Mandatory=$false)]
    [switch]$IncludeEnv,
    
    [Parameter(Mandatory=$false)]
    [switch]$IncludeCompose,
    
    [Parameter(Mandatory=$false)]
    [string]$Comment = ""
)

# =============================================================================
# CONFIGURATION
# =============================================================================

$ErrorActionPreference = "Stop"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$DateDisplay = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# Chemins
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptRoot)
$SourcePath = Join-Path $ProjectRoot $SourceFile
$BackupPath = Join-Path $ProjectRoot $BackupDir

# =============================================================================
# FONCTIONS
# =============================================================================

function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $logEntry = "[$DateDisplay] [$Level] $Message"
    
    $color = switch ($Level) {
        "SUCCESS" { "Green" }
        "WARNING" { "Yellow" }
        "ERROR" { "Red" }
        "INFO" { "Cyan" }
        default { "White" }
    }
    Write-Host $logEntry -ForegroundColor $color
}

function Test-FileExists {
    param(
        [string]$FilePath
    )
    
    if (-not (Test-Path $FilePath)) {
        Write-Log "Fichier non trouvé: $FilePath" "ERROR"
        return $false
    }
    return $true
}

function Backup-File {
    param(
        [string]$Source,
        [string]$DestinationDir,
        [string]$Prefix = "",
        [string]$Suffix = ""
    )
    
    try {
        # Vérifier existence du fichier source
        if (-not (Test-FileExists $Source)) {
            return $null
        }
        
        # Extraire nom et extension
        $fileName = [System.IO.Path]::GetFileNameWithoutExtension($Source)
        $fileExt = [System.IO.Path]::GetExtension($Source)
        
        # Construire nom du backup avec horodatage
        $backupName = if ($Comment) {
            "${fileName}_${Timestamp}_${Comment}${fileExt}"
        } else {
            "${fileName}_${Timestamp}${fileExt}"
        }
        
        $destination = Join-Path $DestinationDir $backupName
        
        # Copier le fichier
        Copy-Item -Path $Source -Destination $destination -Force
        
        # Vérifier la copie
        if (Test-Path $destination) {
            $fileSize = (Get-Item $destination).Length
            $fileSizeKB = [math]::Round($fileSize / 1KB, 2)
            Write-Log "✓ Backup créé: $backupName ($fileSizeKB KB)" "SUCCESS"
            return $destination
        } else {
            Write-Log "Échec de la création du backup: $backupName" "ERROR"
            return $null
        }
    }
    catch {
        Write-Log "Erreur lors du backup de $Source : $_" "ERROR"
        return $null
    }
}

function Show-BackupSummary {
    param(
        [array]$BackupFiles
    )
    
    Write-Log "" "INFO"
    Write-Log "=== RÉSUMÉ BACKUP ===" "INFO"
    Write-Log "Nombre de fichiers sauvegardés: $($BackupFiles.Count)" "INFO"
    Write-Log "" "INFO"
    
    foreach ($file in $BackupFiles) {
        Write-Log "  $file" "SUCCESS"
    }
    
    Write-Log "" "INFO"
    Write-Log "Répertoire backups: $BackupPath" "INFO"
}

# =============================================================================
# MAIN
# =============================================================================

Write-Log "=== BACKUP CONFIGURATION vLLM MEDIUM ===" "INFO"
Write-Log "Date: $DateDisplay" "INFO"
Write-Log "" "INFO"

# Créer le répertoire backups s'il n'existe pas
if (-not (Test-Path $BackupPath)) {
    try {
        New-Item -ItemType Directory -Force -Path $BackupPath | Out-Null
        Write-Log "✓ Répertoire backups créé: $BackupPath" "SUCCESS"
    }
    catch {
        Write-Log "Impossible de créer le répertoire backups: $_" "ERROR"
        exit 1
    }
}

Write-Log "" "INFO"

# Liste des fichiers à sauvegarder
$backupResults = @()

# 1. Backup principal: medium.yml
Write-Log "--- Backup Fichier Principal ---" "INFO"
$mediumBackup = Backup-File -Source $SourcePath -DestinationDir $BackupPath
if ($mediumBackup) {
    $backupResults += $mediumBackup
}
Write-Log "" "INFO"

# 2. Backup .env (optionnel)
if ($IncludeEnv) {
    Write-Log "--- Backup Fichier .env ---" "INFO"
    $envPath = Join-Path $ProjectRoot ".env"
    $envBackup = Backup-File -Source $envPath -DestinationDir $BackupPath
    if ($envBackup) {
        $backupResults += $envBackup
    }
    Write-Log "" "INFO"
}

# 3. Backup docker-compose.yml (optionnel)
if ($IncludeCompose) {
    Write-Log "--- Backup Fichier docker-compose.yml ---" "INFO"
    $composePath = Join-Path $ProjectRoot "configs/docker/docker-compose.yml"
    $composeBackup = Backup-File -Source $composePath -DestinationDir $BackupPath
    if ($composeBackup) {
        $backupResults += $composeBackup
    }
    Write-Log "" "INFO"
}

# Afficher le résumé
Show-BackupSummary -BackupFiles $backupResults

# Code de sortie
if ($backupResults.Count -gt 0) {
    Write-Log "✓ Backup configuration terminé avec succès" "SUCCESS"
    exit 0
} else {
    Write-Log "✗ Aucun fichier n'a été sauvegardé" "ERROR"
    exit 1
}