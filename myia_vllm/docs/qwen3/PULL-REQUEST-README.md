# Pull Request : Système de gestion des configurations sensibles

## Description

Cette pull request met en place un système complet de gestion des configurations sensibles pour le projet vLLM. Ce système permet de sécuriser les informations sensibles (tokens, clés API, chemins spécifiques) tout en facilitant le développement et le déploiement du projet.

## Changements effectués

### 1. Structure de gestion des secrets

- Mise en place d'un système basé sur un fichier `.env` (non versionné) contenant toutes les informations sensibles
- Ajout d'un fichier `.env.example` comme modèle pour la création du fichier `.env`
- Ajout d'un fichier `.gitignore` pour éviter de commiter les fichiers sensibles

### 2. Scripts de gestion des secrets

- `save-secrets.sh` : Script pour extraire les secrets des fichiers docker-compose vers le fichier `.env`
- `restore-secrets.sh` : Script pour injecter les secrets du fichier `.env` dans les fichiers docker-compose
- `secure-docker-compose.sh` : Script pour sécuriser les fichiers docker-compose en remplaçant les valeurs sensibles par des variables d'environnement

### 3. Hooks git

- `pre-commit` : Hook exécuté avant un commit pour sauvegarder automatiquement les secrets et vérifier qu'aucun secret n'est commité
- `post-checkout` : Hook exécuté après un checkout pour proposer de restaurer les secrets

### 4. Documentation

- `SECRETS-README.md` : Documentation complète sur la gestion des secrets
- `GIT-README.md` : Documentation sur la structure git du projet et les procédures pour contribuer
- Autres fichiers README pour documenter les différentes fonctionnalités

### 5. Fichiers docker-compose sécurisés

- Ajout de fichiers docker-compose utilisant des variables d'environnement pour les informations sensibles
- Organisation des fichiers docker-compose dans un dossier dédié

### 6. Scripts de sauvegarde et restauration

- Scripts pour sauvegarder et restaurer les configurations vers/depuis Google Drive
- Scripts pour sauvegarder et restaurer les configurations vers/depuis un disque local
- Configuration de tâches planifiées pour automatiser les sauvegardes

## Avantages

1. **Sécurité renforcée** : Les informations sensibles ne sont plus versionnées dans git
2. **Facilité de développement** : Les développeurs peuvent facilement configurer leur environnement local
3. **Automatisation** : Les hooks git automatisent la gestion des secrets
4. **Documentation complète** : Tous les aspects du système sont documentés
5. **Préparation pour les contributions** : La structure git mise en place facilite les contributions au projet original

## Tests effectués

- Vérification que les scripts de sauvegarde et restauration fonctionnent correctement
- Vérification que les hooks git fonctionnent comme prévu
- Vérification que les fichiers docker-compose peuvent être utilisés avec les variables d'environnement

## Prochaines étapes

- Intégration continue pour vérifier automatiquement qu'aucun secret n'est commité
- Amélioration des scripts pour supporter plus de types de configurations sensibles
- Extension du système pour gérer les secrets dans d'autres parties du projet