# Script PowerShell pour configurer une tâche planifiée Windows
# Ce script configure une tâche planifiée pour exécuter automatiquement le script de sauvegarde

# Vérifier si le script est exécuté en tant qu'administrateur
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Ce script doit être exécuté en tant qu'administrateur." -ForegroundColor Red
    Write-Host "Veuillez redémarrer PowerShell en tant qu'administrateur et réexécuter ce script." -ForegroundColor Red
    exit 1
}

# Configuration de la tâche
$taskName = "vLLM_Secrets_Backup"
$taskDescription = "Sauvegarde automatique des secrets vLLM vers Google Drive"
$scriptPath = Join-Path -Path $PSScriptRoot -ChildPath "backup-env-to-gdrive.ps1"
$scriptPath = [System.IO.Path]::GetFullPath($scriptPath)

# Vérifier si le script de sauvegarde existe
if (-not (Test-Path $scriptPath)) {
    Write-Host "Le script de sauvegarde n'existe pas: $scriptPath" -ForegroundColor Red
    exit 1
}

Write-Host "Configuration de la tâche planifiée pour exécuter: $scriptPath" -ForegroundColor Cyan

# Demander les informations d'identification pour exécuter la tâche
Write-Host "Veuillez entrer les informations d'identification pour exécuter la tâche planifiée." -ForegroundColor Yellow
Write-Host "Ces informations sont nécessaires pour que la tâche s'exécute même lorsque l'utilisateur n'est pas connecté." -ForegroundColor Yellow
$credential = Get-Credential -Message "Entrez les informations d'identification pour la tâche planifiée"

# Créer l'action à exécuter
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

# Créer le déclencheur (tous les jours à 23h00)
$trigger = New-ScheduledTaskTrigger -Daily -At "23:00"

# Configurer les paramètres de la tâche
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew

# Créer le principal (sécurité)
$principal = New-ScheduledTaskPrincipal -UserId $credential.UserName -LogonType Password -RunLevel Highest

# Vérifier si la tâche existe déjà
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Write-Host "La tâche '$taskName' existe déjà. Suppression de la tâche existante..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Créer la tâche planifiée
try {
    $task = Register-ScheduledTask -TaskName $taskName -Description $taskDescription -Action $action -Trigger $trigger -Settings $settings -Principal $principal -User $credential.UserName -Password $credential.GetNetworkCredential().Password
    
    if ($task) {
        Write-Host "La tâche planifiée '$taskName' a été créée avec succès." -ForegroundColor Green
        Write-Host "Détails de la tâche:" -ForegroundColor Cyan
        Write-Host "  - Nom: $taskName" -ForegroundColor White
        Write-Host "  - Description: $taskDescription" -ForegroundColor White
        Write-Host "  - Script: $scriptPath" -ForegroundColor White
        Write-Host "  - Exécution: Quotidienne à 23:00" -ForegroundColor White
        Write-Host "  - Utilisateur: $($credential.UserName)" -ForegroundColor White
    } else {
        Write-Host "Erreur lors de la création de la tâche planifiée." -ForegroundColor Red
    }
}
catch {
    Write-Host "Erreur lors de la création de la tâche planifiée: $_" -ForegroundColor Red
    exit 1
}

# Instructions pour tester la tâche
Write-Host "`nPour tester la tâche immédiatement, exécutez la commande suivante:" -ForegroundColor Yellow
Write-Host "Start-ScheduledTask -TaskName `"$taskName`"" -ForegroundColor White

# Instructions pour vérifier le statut de la tâche
Write-Host "`nPour vérifier le statut de la tâche, exécutez la commande suivante:" -ForegroundColor Yellow
Write-Host "Get-ScheduledTask -TaskName `"$taskName`" | Select-Object TaskName, State, LastRunTime, NextRunTime | Format-Table -AutoSize" -ForegroundColor White