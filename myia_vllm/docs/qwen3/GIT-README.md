# Structure Git du projet vLLM

Ce document explique la structure des branches git du projet vLLM et les procédures pour contribuer au projet.

## Structure des branches

```
main                  # Branche principale stable
├── develop           # Branche de développement
│   ├── feature/xxx   # Branches de fonctionnalités
│   └── bugfix/xxx    # Branches de correction de bugs
└── release/x.y.z     # Branches de release
```

### Branches principales

- **main**: Branche principale contenant le code stable et déployé en production. Cette branche est protégée et ne peut être modifiée que par des pull requests validées.
- **develop**: Branche de développement contenant les dernières fonctionnalités validées mais pas encore déployées en production.

### Branches temporaires

- **feature/xxx**: Branches de développement de nouvelles fonctionnalités. Ces branches sont créées à partir de `develop` et fusionnées dans `develop` une fois la fonctionnalité terminée.
- **bugfix/xxx**: Branches de correction de bugs. Ces branches sont créées à partir de `develop` et fusionnées dans `develop` une fois le bug corrigé.
- **hotfix/xxx**: Branches de correction de bugs critiques en production. Ces branches sont créées à partir de `main` et fusionnées dans `main` ET `develop` une fois le bug corrigé.
- **release/x.y.z**: Branches de préparation de release. Ces branches sont créées à partir de `develop` et fusionnées dans `main` ET `develop` une fois la release validée.

## Workflow de développement

### Développement d'une nouvelle fonctionnalité

1. Créer une branche `feature/xxx` à partir de `develop`:
   ```bash
   git checkout develop
   git pull
   git checkout -b feature/xxx
   ```

2. Développer la fonctionnalité et commiter les changements:
   ```bash
   git add .
   git commit -m "Description de la fonctionnalité"
   ```

3. Pousser la branche sur le dépôt distant:
   ```bash
   git push -u origin feature/xxx
   ```

4. Créer une pull request vers `develop`

5. Une fois la pull request validée et fusionnée, supprimer la branche:
   ```bash
   git checkout develop
   git pull
   git branch -d feature/xxx
   ```

### Correction d'un bug

1. Créer une branche `bugfix/xxx` à partir de `develop`:
   ```bash
   git checkout develop
   git pull
   git checkout -b bugfix/xxx
   ```

2. Corriger le bug et commiter les changements:
   ```bash
   git add .
   git commit -m "Description de la correction"
   ```

3. Pousser la branche sur le dépôt distant:
   ```bash
   git push -u origin bugfix/xxx
   ```

4. Créer une pull request vers `develop`

5. Une fois la pull request validée et fusionnée, supprimer la branche:
   ```bash
   git checkout develop
   git pull
   git branch -d bugfix/xxx
   ```

### Correction d'un bug critique en production

1. Créer une branche `hotfix/xxx` à partir de `main`:
   ```bash
   git checkout main
   git pull
   git checkout -b hotfix/xxx
   ```

2. Corriger le bug et commiter les changements:
   ```bash
   git add .
   git commit -m "Description de la correction"
   ```

3. Pousser la branche sur le dépôt distant:
   ```bash
   git push -u origin hotfix/xxx
   ```

4. Créer une pull request vers `main`

5. Une fois la pull request validée et fusionnée, fusionner également dans `develop`:
   ```bash
   git checkout develop
   git pull
   git merge main
   git push
   ```

6. Supprimer la branche:
   ```bash
   git branch -d hotfix/xxx
   ```

### Préparation d'une release

1. Créer une branche `release/x.y.z` à partir de `develop`:
   ```bash
   git checkout develop
   git pull
   git checkout -b release/x.y.z
   ```

2. Effectuer les derniers ajustements et commiter les changements:
   ```bash
   git add .
   git commit -m "Préparation de la release x.y.z"
   ```

3. Pousser la branche sur le dépôt distant:
   ```bash
   git push -u origin release/x.y.z
   ```

4. Créer une pull request vers `main`

5. Une fois la pull request validée et fusionnée, fusionner également dans `develop`:
   ```bash
   git checkout develop
   git pull
   git merge main
   git push
   ```

6. Supprimer la branche:
   ```bash
   git branch -d release/x.y.z
   ```

## Gestion des tags

Chaque release est taguée avec son numéro de version:

```bash
git checkout main
git pull
git tag -a vx.y.z -m "Release x.y.z"
git push origin vx.y.z
```

## Commandes pour la réorganisation initiale des branches

Pour mettre en place cette structure à partir d'un dépôt existant:

```bash
# Créer la branche develop à partir de main
git checkout main
git pull
git checkout -b develop
git push -u origin develop

# Protéger les branches main et develop
# (À faire dans l'interface web de GitHub/GitLab/etc.)

# Créer une branche feature pour les modifications en cours
git checkout develop
git checkout -b feature/nom-de-la-fonctionnalite
git push -u origin feature/nom-de-la-fonctionnalite
```

## Gestion des informations sensibles

Voir le fichier [SECRETS-README.md](SECRETS-README.md) pour la gestion des informations sensibles.