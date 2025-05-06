#!/bin/bash

# Script de restauration du fichier .env depuis Google Drive
# Ce script utilise rclone pour restaurer le fichier .env depuis Google Drive

# Vérifier si rclone est installé
if ! command -v rclone &> /dev/null; then
    echo "rclone n'est pas installé. Veuillez l'installer d'abord."
    echo "Instructions d'installation : https://rclone.org/install/"
    exit 1
fi

# Vérifier si rclone est configuré pour Google Drive
if ! rclone listremotes | grep -q "gdrive:"; then
    echo "rclone n'est pas configuré pour Google Drive."
    echo "Veuillez exécuter 'rclone config' pour configurer Google Drive."
    exit 1
fi

# Vérifier si le dossier scripts existe
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"

# Chemin de destination sur Google Drive (à modifier selon vos besoins)
GDRIVE_PATH="gdrive:vllm-secrets"

# Fonction pour lister les sauvegardes disponibles
list_backups() {
    echo "Sauvegardes disponibles sur Google Drive :"
    rclone lsf "$GDRIVE_PATH" | grep "env_backup_" | sort -r
}

# Vérifier si un argument a été fourni
if [ -z "$1" ]; then
    # Aucun argument fourni, utiliser la dernière sauvegarde
    echo "Aucune sauvegarde spécifique demandée, utilisation de la dernière sauvegarde..."
    
    # Vérifier si le fichier latest.env existe
    if ! rclone lsf "$GDRIVE_PATH/latest.env" &> /dev/null; then
        echo "Erreur : Aucune sauvegarde récente trouvée."
        list_backups
        exit 1
    fi
    
    # Sauvegarder le fichier .env actuel si existant
    if [ -f "$ENV_FILE" ]; then
        BACKUP_TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
        echo "Sauvegarde du fichier .env actuel vers ${ENV_FILE}.${BACKUP_TIMESTAMP}.bak..."
        cp "$ENV_FILE" "${ENV_FILE}.${BACKUP_TIMESTAMP}.bak"
    fi
    
    # Restaurer depuis la dernière sauvegarde
    echo "Restauration depuis la dernière sauvegarde..."
    rclone copy "$GDRIVE_PATH/latest.env" "$ENV_FILE"
    
    if [ $? -eq 0 ]; then
        echo "Restauration réussie depuis la dernière sauvegarde."
    else
        echo "Erreur lors de la restauration depuis la dernière sauvegarde."
        exit 1
    fi
else
    # Un argument a été fourni, vérifier s'il s'agit d'une sauvegarde valide
    BACKUP_FILE="$1"
    
    # Si l'argument ne commence pas par "env_backup_", ajouter le préfixe
    if [[ ! "$BACKUP_FILE" == env_backup_* ]]; then
        BACKUP_FILE="env_backup_${BACKUP_FILE}"
    fi
    
    # Si l'argument ne se termine pas par ".env", ajouter l'extension
    if [[ ! "$BACKUP_FILE" == *.env ]]; then
        BACKUP_FILE="${BACKUP_FILE}.env"
    fi
    
    # Vérifier si la sauvegarde existe
    if ! rclone lsf "$GDRIVE_PATH/$BACKUP_FILE" &> /dev/null; then
        echo "Erreur : La sauvegarde $BACKUP_FILE n'existe pas."
        list_backups
        exit 1
    fi
    
    # Sauvegarder le fichier .env actuel si existant
    if [ -f "$ENV_FILE" ]; then
        BACKUP_TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
        echo "Sauvegarde du fichier .env actuel vers ${ENV_FILE}.${BACKUP_TIMESTAMP}.bak..."
        cp "$ENV_FILE" "${ENV_FILE}.${BACKUP_TIMESTAMP}.bak"
    fi
    
    # Restaurer depuis la sauvegarde spécifiée
    echo "Restauration depuis la sauvegarde $BACKUP_FILE..."
    rclone copy "$GDRIVE_PATH/$BACKUP_FILE" "$ENV_FILE"
    
    if [ $? -eq 0 ]; then
        echo "Restauration réussie depuis $BACKUP_FILE."
    else
        echo "Erreur lors de la restauration depuis $BACKUP_FILE."
        exit 1
    fi
fi

echo "Restauration terminée"