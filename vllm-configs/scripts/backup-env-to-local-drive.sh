#!/bin/bash

# Script de sauvegarde du fichier .env vers un dossier Google Drive local
# Ce script copie le fichier .env vers le dossier Google Drive spécifié

# Vérifier si le dossier scripts existe
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"

# Chemin du dossier Google Drive
GDRIVE_PATH="/mnt/g/Mon Drive/MyIA/IA/LLMs/vllm-secrets"

# Vérifier si le fichier .env existe
if [ ! -f "$ENV_FILE" ]; then
    echo "Le fichier .env n'existe pas. Veuillez exécuter save-secrets.sh d'abord."
    exit 1
fi

# Créer un nom de fichier avec la date et l'heure
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILENAME="env_backup_${TIMESTAMP}.env"

# Vérifier si le répertoire de destination existe, sinon le créer
if [ ! -d "$GDRIVE_PATH" ]; then
    echo "Création du répertoire $GDRIVE_PATH..."
    mkdir -p "$GDRIVE_PATH"
fi

# Copier le fichier .env vers Google Drive
echo "Sauvegarde du fichier .env vers Google Drive local..."
cp "$ENV_FILE" "$GDRIVE_PATH/$BACKUP_FILENAME"

# Vérifier si la sauvegarde a réussi
if [ $? -eq 0 ]; then
    echo "Sauvegarde réussie : $GDRIVE_PATH/$BACKUP_FILENAME"
    
    # Créer un fichier latest.env qui pointe vers la dernière sauvegarde
    echo "Mise à jour du fichier latest.env..."
    cp "$ENV_FILE" "$GDRIVE_PATH/latest.env"
    
    # Lister les sauvegardes disponibles
    echo "Sauvegardes disponibles sur Google Drive :"
    ls -la "$GDRIVE_PATH" | grep "env_backup_"
    
    # Nettoyer les anciennes sauvegardes (garder les 10 dernières)
    echo "Nettoyage des anciennes sauvegardes..."
    BACKUPS=$(ls -t "$GDRIVE_PATH"/env_backup_* 2>/dev/null)
    COUNT=$(echo "$BACKUPS" | wc -l)
    if [ "$COUNT" -gt 10 ]; then
        echo "Suppression des sauvegardes anciennes (conservation des 10 plus récentes)..."
        echo "$BACKUPS" | tail -n +11 | while read -r backup; do
            echo "Suppression de $backup..."
            rm "$backup"
        done
    fi
else
    echo "Erreur lors de la sauvegarde vers Google Drive."
    exit 1
fi

echo "Sauvegarde terminée"