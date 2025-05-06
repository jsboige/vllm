#!/bin/bash

# Script d'installation des hooks git
# Ce script installe les hooks git dans le dossier .git/hooks

# Vérifier si le dossier scripts existe
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
HOOKS_DIR="$SCRIPT_DIR/git-hooks"
GIT_HOOKS_DIR="$ROOT_DIR/.git/hooks"

echo "Installation des hooks git..."

# Vérifier si le dossier .git existe
if [ ! -d "$ROOT_DIR/.git" ]; then
    echo "Erreur: Le dossier $ROOT_DIR/.git n'existe pas."
    echo "Veuillez exécuter ce script depuis la racine du dépôt git."
    exit 1
fi

# Vérifier si le dossier git-hooks existe
if [ ! -d "$HOOKS_DIR" ]; then
    echo "Erreur: Le dossier $HOOKS_DIR n'existe pas."
    exit 1
fi

# Créer le dossier .git/hooks s'il n'existe pas
mkdir -p "$GIT_HOOKS_DIR"

# Copier les hooks
for hook in "$HOOKS_DIR"/*; do
    hook_name=$(basename "$hook")
    cp "$hook" "$GIT_HOOKS_DIR/$hook_name"
    chmod +x "$GIT_HOOKS_DIR/$hook_name"
    echo "Hook $hook_name installé"
done

echo "Installation terminée"