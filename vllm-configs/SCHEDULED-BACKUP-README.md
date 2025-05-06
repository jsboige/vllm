# Sauvegarde Automatique des Secrets vLLM

Ce document explique comment configurer et vérifier la tâche planifiée Windows pour la sauvegarde automatique des secrets vLLM vers Google Drive.

## Prérequis

- Windows 10/11
- PowerShell 5.1 ou supérieur
- Google Drive installé et configuré (avec le dossier synchronisé localement)
- Droits d'administrateur pour configurer la tâche planifiée

## Structure des fichiers

- `backup-env-to-gdrive.ps1` : Script principal de sauvegarde
- `setup-scheduled-backup-task.ps1` : Script pour configurer la tâche planifiée
- `test-backup-task.ps1` : Script pour tester la sauvegarde
- `logs/` : Dossier contenant les journaux de sauvegarde

## Configuration de la tâche planifiée

### Étape 1 : Vérifier les chemins dans le script de sauvegarde

Avant de configurer la tâche planifiée, vérifiez que les chemins dans le script `backup-env-to-gdrive.ps1` sont corrects :

- Le chemin du fichier `.env` à sauvegarder
- Le chemin du répertoire Google Drive de destination

### Étape 2 : Exécuter le script de configuration

1. Ouvrez PowerShell en tant qu'administrateur
2. Naviguez vers le répertoire contenant les scripts
3. Exécutez le script de configuration :

```powershell
cd D:\vllm\vllm-configs
.\setup-scheduled-backup-task.ps1
```

4. Entrez les informations d'identification demandées (nom d'utilisateur et mot de passe)
   - Ces informations sont nécessaires pour que la tâche s'exécute même lorsque l'utilisateur n'est pas connecté
   - Assurez-vous d'utiliser un compte avec des droits suffisants pour accéder aux fichiers et au dossier Google Drive

### Étape 3 : Vérifier la configuration de la tâche

Après avoir exécuté le script de configuration, vous pouvez vérifier que la tâche a été correctement créée :

```powershell
Get-ScheduledTask -TaskName "vLLM_Secrets_Backup" | Select-Object TaskName, State, LastRunTime, NextRunTime | Format-Table -AutoSize
```

## Test de la sauvegarde

Pour tester immédiatement la sauvegarde sans attendre l'heure planifiée, vous pouvez :

### Option 1 : Exécuter le script de test

```powershell
cd D:\vllm\vllm-configs
.\test-backup-task.ps1
```

Ce script va :
- Vérifier que tous les prérequis sont satisfaits
- Exécuter le script de sauvegarde
- Vérifier les résultats (fichiers de sauvegarde et journaux)
- Afficher les informations sur la tâche planifiée

### Option 2 : Exécuter manuellement la tâche planifiée

```powershell
Start-ScheduledTask -TaskName "vLLM_Secrets_Backup"
```

## Vérification des sauvegardes

Les sauvegardes sont stockées dans le dossier Google Drive configuré (`G:\Mon Drive\MyIA\IA\LLMs\vllm-secrets\` par défaut) :

- `latest.env` : Toujours la version la plus récente du fichier `.env`
- `env_backup_YYYYMMDD_HHMMSS.env` : Sauvegardes horodatées (les 10 plus récentes sont conservées)

Pour lister les sauvegardes disponibles :

```powershell
Get-ChildItem -Path "G:\Mon Drive\MyIA\IA\LLMs\vllm-secrets" -Filter "env_backup_*.env" | Sort-Object LastWriteTime -Descending | Format-Table Name, LastWriteTime
```

## Journalisation

Les journaux de sauvegarde sont stockés dans le dossier `logs` :

```powershell
Get-ChildItem -Path "D:\vllm\vllm-configs\logs" -Filter "backup-env-log-*.txt" | Sort-Object LastWriteTime -Descending
```

Pour afficher le contenu du dernier journal :

```powershell
Get-Content -Path (Get-ChildItem -Path "D:\vllm\vllm-configs\logs" -Filter "backup-env-log-*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
```

## Modification de la tâche planifiée

Si vous souhaitez modifier la tâche planifiée (par exemple, changer l'heure d'exécution), vous pouvez :

1. Supprimer la tâche existante :
```powershell
Unregister-ScheduledTask -TaskName "vLLM_Secrets_Backup" -Confirm:$false
```

2. Exécuter à nouveau le script de configuration :
```powershell
.\setup-scheduled-backup-task.ps1
```

## Dépannage

### La tâche ne s'exécute pas

1. Vérifiez l'état de la tâche :
```powershell
Get-ScheduledTask -TaskName "vLLM_Secrets_Backup"
```

2. Vérifiez l'historique d'exécution de la tâche :
```powershell
Get-ScheduledTaskInfo -TaskName "vLLM_Secrets_Backup"
```

3. Vérifiez les journaux d'événements Windows :
```powershell
Get-WinEvent -LogName Microsoft-Windows-TaskScheduler/Operational | Where-Object { $_.Message -like "*vLLM_Secrets_Backup*" } | Select-Object TimeCreated, Message | Format-List
```

### Erreurs de sauvegarde

1. Vérifiez les journaux de sauvegarde dans le dossier `logs`
2. Assurez-vous que Google Drive est correctement monté et accessible
3. Vérifiez que le fichier `.env` existe et est accessible
4. Exécutez le script de test pour diagnostiquer les problèmes

## Restauration des sauvegardes

Pour restaurer une sauvegarde, copiez le fichier de sauvegarde souhaité vers l'emplacement du fichier `.env` :

```powershell
# Pour restaurer la dernière sauvegarde
Copy-Item -Path "G:\Mon Drive\MyIA\IA\LLMs\vllm-secrets\latest.env" -Destination "D:\vllm\.env" -Force

# Pour restaurer une sauvegarde spécifique
Copy-Item -Path "G:\Mon Drive\MyIA\IA\LLMs\vllm-secrets\env_backup_YYYYMMDD_HHMMSS.env" -Destination "D:\vllm\.env" -Force