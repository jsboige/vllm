# Sauvegarde des secrets vers Google Drive

Ce document explique comment utiliser les scripts de sauvegarde et de restauration des secrets vers/depuis Google Drive.

## Prérequis

### Installation de rclone

Ces scripts utilisent [rclone](https://rclone.org/) pour interagir avec Google Drive. Vous devez d'abord installer rclone :

#### Windows
```powershell
# Avec Chocolatey
choco install rclone

# Ou télécharger et installer manuellement depuis https://rclone.org/downloads/
```

#### Linux
```bash
curl https://rclone.org/install.sh | sudo bash
```

#### macOS
```bash
# Avec Homebrew
brew install rclone
```

### Configuration de rclone pour Google Drive

Après avoir installé rclone, vous devez le configurer pour accéder à votre compte Google Drive :

1. Exécutez la commande suivante :
   ```bash
   rclone config
   ```

2. Suivez les instructions pour créer une nouvelle configuration :
   - Choisissez `n` pour créer une nouvelle configuration
   - Donnez-lui un nom (par exemple `gdrive`)
   - Sélectionnez `drive` pour Google Drive
   - Suivez les instructions pour autoriser rclone à accéder à votre compte Google Drive

3. Vérifiez que la configuration fonctionne :
   ```bash
   rclone lsd gdrive:
   ```

## Utilisation des scripts

### Sauvegarde du fichier .env vers Google Drive

Le script `backup-env-to-gdrive.sh` sauvegarde le fichier `.env` vers Google Drive :

```bash
# Rendre le script exécutable
chmod +x vllm-configs/scripts/backup-env-to-gdrive.sh

# Exécuter le script
./vllm-configs/scripts/backup-env-to-gdrive.sh
```

Ce script :
- Vérifie si rclone est installé et configuré
- Vérifie si le fichier `.env` existe
- Crée une sauvegarde datée du fichier `.env` sur Google Drive
- Crée également un fichier `latest.env` qui pointe vers la dernière sauvegarde
- Nettoie les anciennes sauvegardes (garde les 10 dernières)

Par défaut, les sauvegardes sont stockées dans le répertoire `gdrive:vllm-secrets`. Vous pouvez modifier cette valeur en éditant la variable `GDRIVE_PATH` dans le script.

### Restauration du fichier .env depuis Google Drive

Le script `restore-env-from-gdrive.sh` restaure le fichier `.env` depuis Google Drive :

```bash
# Rendre le script exécutable
chmod +x vllm-configs/scripts/restore-env-from-gdrive.sh

# Restaurer depuis la dernière sauvegarde
./vllm-configs/scripts/restore-env-from-gdrive.sh

# Ou restaurer depuis une sauvegarde spécifique
./vllm-configs/scripts/restore-env-from-gdrive.sh 20250505_123456
```

Ce script :
- Vérifie si rclone est installé et configuré
- Sauvegarde le fichier `.env` actuel (s'il existe) avec un suffixe de date/heure
- Restaure le fichier `.env` depuis la dernière sauvegarde ou depuis une sauvegarde spécifique

## Automatisation des sauvegardes

Vous pouvez automatiser les sauvegardes en ajoutant une tâche cron (Linux/macOS) ou une tâche planifiée (Windows).

### Linux/macOS (cron)

Éditez votre crontab :
```bash
crontab -e
```

Ajoutez une ligne pour exécuter le script quotidiennement à 23h00 :
```
0 23 * * * /chemin/vers/vllm-configs/scripts/backup-env-to-gdrive.sh >> /chemin/vers/backup.log 2>&1
```

### Windows (Tâche planifiée)

1. Ouvrez le Planificateur de tâches
2. Créez une nouvelle tâche de base
3. Configurez-la pour qu'elle s'exécute quotidiennement
4. Définissez l'action pour exécuter le script `backup-env-to-gdrive.sh`

## Sécurité

- Les sauvegardes sur Google Drive sont aussi sécurisées que votre compte Google. Assurez-vous d'utiliser l'authentification à deux facteurs.
- Les fichiers `.env` contiennent des informations sensibles. Ne les partagez pas et ne les rendez pas publics.
- Le fichier `.env` est exclu de git via `.gitignore`, donc il ne sera pas poussé vers GitHub.

## Dépannage

### Erreur "rclone n'est pas installé"

Assurez-vous que rclone est correctement installé et disponible dans votre PATH.

### Erreur "rclone n'est pas configuré pour Google Drive"

Exécutez `rclone config` pour configurer l'accès à Google Drive.

### Erreur lors de la sauvegarde ou de la restauration

Vérifiez que :
- Vous avez une connexion Internet active
- Votre configuration rclone est correcte
- Vous avez les permissions nécessaires sur Google Drive