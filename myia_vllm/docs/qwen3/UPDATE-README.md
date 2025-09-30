# Système de mise à jour automatisée pour vLLM

Ce système permet de mettre à jour automatiquement les images Docker de vLLM et les modèles hébergés sur Hugging Face. Il est conçu pour fonctionner sur Windows avec WSL (Windows Subsystem for Linux).

## Composants

Le système de mise à jour comprend les fichiers suivants:

- `update-vllm.sh`: Script principal qui effectue les mises à jour
- `update-config.json`: Fichier de configuration qui liste les modèles à surveiller et stocke les informations sur les versions
- `vllm-updater.service`: Fichier de service systemd pour exécuter le script à intervalles réguliers (pour WSL)
- `vllm-updater.cron`: Fichier de configuration cron pour exécuter le script à intervalles réguliers (pour WSL)
- `setup-scheduled-task.bat`: Script batch Windows pour configurer une tâche planifiée

## Prérequis

- Docker et Docker Compose
- WSL (Windows Subsystem for Linux)
- jq (installé dans WSL)
- curl (installé dans WSL)
- Un token Hugging Face valide

## Installation

### 1. Configuration

Avant d'utiliser le système de mise à jour, vous devez configurer le fichier `update-config.json`:

1. Ouvrez le fichier `update-config.json` dans un éditeur de texte
2. Vérifiez et mettez à jour les chemins des images Docker et des fichiers docker-compose
3. Vérifiez et mettez à jour les informations sur les modèles
4. Configurez les paramètres dans la section `settings`:
   - `check_interval_days`: Intervalle de vérification des mises à jour (en jours)
   - `auto_update_docker`: Mettre à `true` pour mettre à jour automatiquement les images Docker
   - `auto_update_models`: Mettre à `true` pour mettre à jour automatiquement les modèles
   - `notification_email`: Adresse email pour les notifications (non implémenté)
   - `log_file`: Chemin du fichier de log
   - `huggingface_token`: Token Hugging Face (peut être défini via la variable d'environnement `HUGGING_FACE_HUB_TOKEN`)
   - `docker_compose_files`: Liste des fichiers docker-compose à utiliser
   - `docker_compose_project`: Nom du projet Docker Compose

### 2. Rendre le script exécutable

Dans WSL, exécutez la commande suivante:

```bash
chmod +x /chemin/vers/vllm-configs/update-vllm.sh
```

### 3. Configuration de l'exécution automatique

Vous avez trois options pour exécuter le script automatiquement:

#### Option 1: Tâche planifiée Windows

1. Ouvrez le fichier `setup-scheduled-task.bat` dans un éditeur de texte
2. Mettez à jour le chemin du script WSL si nécessaire
3. Exécutez le script en double-cliquant dessus ou via l'invite de commandes
4. Confirmez la création de la tâche planifiée

#### Option 2: Service systemd (dans WSL)

1. Ouvrez le fichier `vllm-updater.service` dans un éditeur de texte
2. Mettez à jour les chemins et les informations d'utilisateur
3. Copiez le fichier dans le répertoire des services systemd:
   ```bash
   sudo cp /chemin/vers/vllm-configs/vllm-updater.service /etc/systemd/system/
   ```
4. Activez et démarrez le service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable vllm-updater.service
   sudo systemctl start vllm-updater.service
   ```

#### Option 3: Tâche cron (dans WSL)

1. Ouvrez le fichier `vllm-updater.cron` dans un éditeur de texte
2. Mettez à jour les chemins si nécessaire
3. Ajoutez la tâche à votre crontab:
   ```bash
   crontab -e
   ```
4. Copiez le contenu du fichier `vllm-updater.cron` dans votre crontab et sauvegardez

## Utilisation manuelle

Vous pouvez également exécuter le script manuellement:

```bash
# Exécution standard (interactive)
/chemin/vers/vllm-configs/update-vllm.sh

# Mise à jour automatique (sans confirmation)
/chemin/vers/vllm-configs/update-vllm.sh --auto

# Mise à jour uniquement des images Docker
/chemin/vers/vllm-configs/update-vllm.sh --docker-only

# Mise à jour uniquement des modèles
/chemin/vers/vllm-configs/update-vllm.sh --models-only

# Forcer la mise à jour même si aucune nouvelle version n'est détectée
/chemin/vers/vllm-configs/update-vllm.sh --force

# Mode verbeux (affiche plus de détails)
/chemin/vers/vllm-configs/update-vllm.sh --verbose

# Simulation (n'effectue aucune action réelle)
/chemin/vers/vllm-configs/update-vllm.sh --dry-run

# Afficher l'aide
/chemin/vers/vllm-configs/update-vllm.sh --help
```

## Fonctionnement

Le script effectue les opérations suivantes:

1. Vérification des mises à jour de l'image Docker officielle
2. Mise à jour de l'image Docker officielle si une nouvelle version est disponible
3. Reconstruction de l'image personnalisée avec le patch pour le décodage spéculatif
4. Vérification des nouvelles versions des modèles sur Hugging Face
5. Mise à jour des modèles si de nouvelles versions sont disponibles
6. Redémarrage des services Docker après les mises à jour

Toutes les actions sont journalisées dans le fichier de log spécifié dans la configuration.

## Dépannage

### Problèmes courants

1. **Le script ne s'exécute pas**:
   - Vérifiez que le script est exécutable (`chmod +x update-vllm.sh`)
   - Vérifiez que les dépendances sont installées (jq, curl)

2. **Erreur lors de la mise à jour de l'image Docker**:
   - Vérifiez que Docker est en cours d'exécution
   - Vérifiez que vous avez les permissions nécessaires pour exécuter Docker

3. **Erreur lors de la vérification des modèles Hugging Face**:
   - Vérifiez que votre token Hugging Face est valide
   - Vérifiez votre connexion Internet

4. **Les services ne redémarrent pas correctement**:
   - Vérifiez que les fichiers docker-compose sont correctement configurés
   - Vérifiez que vous avez les permissions nécessaires pour exécuter Docker Compose

### Logs

Consultez le fichier de log spécifié dans la configuration pour plus d'informations sur les erreurs.

## Personnalisation

Vous pouvez personnaliser le comportement du script en modifiant le fichier `update-config.json`. Par exemple:

- Ajouter de nouveaux modèles à surveiller
- Modifier les intervalles de vérification
- Activer ou désactiver les mises à jour automatiques
- Configurer les notifications par email (nécessite une implémentation supplémentaire)

## Sécurité

Le script utilise un token Hugging Face pour accéder aux modèles. Assurez-vous de protéger ce token et de ne pas le partager.

## Limitations

- Le script ne gère pas actuellement les notifications par email (à implémenter si nécessaire)
- Le script suppose que les services Docker sont configurés pour redémarrer automatiquement
- Le script ne gère pas les rollbacks automatiques en cas d'échec de la mise à jour (à implémenter si nécessaire)