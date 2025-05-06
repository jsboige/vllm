#!/bin/bash

# Script d'initialisation de la structure git
# Ce script met en place la structure des branches git selon le plan de réorganisation

echo "Initialisation de la structure git..."

# Vérifier si le dossier .git existe
if [ ! -d ".git" ]; then
    echo "Erreur: Le dossier .git n'existe pas."
    echo "Veuillez exécuter ce script depuis la racine du dépôt git."
    exit 1
fi

# Vérifier la branche actuelle
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Branche actuelle: $CURRENT_BRANCH"

# Sauvegarder les modifications non commitées si nécessaire
if ! git diff-index --quiet HEAD --; then
    echo "Des modifications non commitées ont été détectées."
    echo "Sauvegarde des modifications..."
    git stash save "Modifications avant réorganisation des branches"
    STASHED=1
else
    STASHED=0
fi

# S'assurer que la branche main existe
if ! git show-ref --verify --quiet refs/heads/main; then
    # Si main n'existe pas mais master existe, renommer master en main
    if git show-ref --verify --quiet refs/heads/master; then
        echo "Renommage de la branche master en main..."
        git branch -m master main
    else
        echo "Création de la branche main..."
        git checkout -b main
    fi
fi

# S'assurer que nous sommes sur la branche main
git checkout main

# Créer la branche develop si elle n'existe pas
if ! git show-ref --verify --quiet refs/heads/develop; then
    echo "Création de la branche develop..."
    git checkout -b develop
    git push -u origin develop
else
    echo "La branche develop existe déjà."
    git checkout develop
    git pull
fi

# Créer une branche feature pour les modifications en cours
FEATURE_BRANCH="feature/secure-configs"
if ! git show-ref --verify --quiet refs/heads/$FEATURE_BRANCH; then
    echo "Création de la branche $FEATURE_BRANCH..."
    git checkout -b $FEATURE_BRANCH
    git push -u origin $FEATURE_BRANCH
else
    echo "La branche $FEATURE_BRANCH existe déjà."
    git checkout $FEATURE_BRANCH
    git pull
fi

# Restaurer les modifications sauvegardées si nécessaire
if [ $STASHED -eq 1 ]; then
    echo "Restauration des modifications sauvegardées..."
    git stash pop
fi

echo "Structure git initialisée avec succès."
echo ""
echo "Branches créées:"
echo "- main (branche principale stable)"
echo "- develop (branche de développement)"
echo "- $FEATURE_BRANCH (branche de fonctionnalité pour la sécurisation des configurations)"
echo ""
echo "Vous êtes maintenant sur la branche $FEATURE_BRANCH."
echo "Vous pouvez commiter vos modifications et créer une pull request vers develop."
echo ""
echo "Commandes pour commiter vos modifications:"
echo "git add ."
echo "git commit -m \"Sécurisation des configurations et réorganisation des branches\""
echo "git push"
echo ""
echo "Ensuite, créez une pull request de $FEATURE_BRANCH vers develop dans l'interface web de votre dépôt git."