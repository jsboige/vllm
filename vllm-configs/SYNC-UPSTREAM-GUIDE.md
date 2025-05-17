# Guide de synchronisation avec le dépôt vLLM original

Ce guide explique comment synchroniser notre fork avec le dépôt original de vLLM pour rester à jour avec les dernières modifications.

## Configuration initiale

Si vous n'avez pas encore configuré le dépôt original comme remote "upstream", faites-le avec la commande suivante:

```bash
git remote add upstream https://github.com/vllm-project/vllm.git
```

Vous pouvez vérifier que le remote a bien été ajouté avec:

```bash
git remote -v
```

Vous devriez voir quelque chose comme:

```
origin    https://github.com/votre-username/vllm.git (fetch)
origin    https://github.com/votre-username/vllm.git (push)
upstream  https://github.com/vllm-project/vllm.git (fetch)
upstream  https://github.com/vllm-project/vllm.git (push)
```

## Procédure de synchronisation

### 1. Récupérer les dernières modifications du dépôt original

```bash
git fetch upstream
```

### 2. Créer une branche pour la synchronisation

Il est recommandé de créer une branche dédiée pour la synchronisation afin de ne pas perturber votre branche principale:

```bash
git checkout -b sync-upstream
```

### 3. Fusionner les modifications du dépôt original

```bash
git merge upstream/main
```

### 4. Résoudre les éventuels conflits

Si des conflits apparaissent, vous devrez les résoudre manuellement:

1. Ouvrez les fichiers en conflit et résolvez les conflits
2. Utilisez `git add <fichier>` pour marquer les fichiers comme résolus
3. Validez les modifications avec `git commit -m "Résolution des conflits de fusion"`

### 5. Tester les modifications

Assurez-vous que tout fonctionne correctement après la fusion:

```bash
# Exécuter les tests
python -m pytest tests/

# Vérifier que l'application démarre correctement
python -m vllm.entrypoints.openai.api_server --model <votre-modèle>
```

### 6. Pousser les modifications vers votre fork

```bash
git push origin sync-upstream
```

### 7. Mettre à jour votre branche principale

Une fois que vous avez vérifié que tout fonctionne correctement, vous pouvez mettre à jour votre branche principale:

```bash
git checkout main
git merge sync-upstream
git push origin main
```

## Synchronisation des branches de fonctionnalités

Si vous avez des branches de fonctionnalités en cours de développement, vous devrez également les mettre à jour avec les dernières modifications du dépôt original:

```bash
git checkout feature-branch
git merge sync-upstream
# Résoudre les éventuels conflits
git push origin feature-branch
```

## Automatisation de la synchronisation

Vous pouvez créer un script pour automatiser la synchronisation:

```bash
#!/bin/bash

# Récupérer les dernières modifications du dépôt original
git fetch upstream

# Créer une branche pour la synchronisation
git checkout -b sync-upstream-$(date +%Y%m%d)

# Fusionner les modifications du dépôt original
git merge upstream/main

# Pousser les modifications vers votre fork
git push origin sync-upstream-$(date +%Y%m%d)

echo "Synchronisation terminée. Vérifiez les éventuels conflits et testez les modifications."
echo "Une fois que tout fonctionne correctement, vous pouvez mettre à jour votre branche principale:"
echo "git checkout main"
echo "git merge sync-upstream-$(date +%Y%m%d)"
echo "git push origin main"
```

## Gestion des modifications personnalisées

Si vous avez des modifications personnalisées qui ne sont pas destinées à être soumises au dépôt original, vous pouvez les maintenir dans des branches séparées ou utiliser des stratégies de fusion plus avancées:

### Option 1: Branches séparées

Maintenez vos modifications personnalisées dans des branches séparées et fusionnez régulièrement les modifications du dépôt original dans ces branches.

### Option 2: Rebasing

Utilisez `git rebase` pour appliquer vos modifications personnalisées par-dessus les modifications du dépôt original:

```bash
git checkout custom-feature
git rebase upstream/main
# Résoudre les éventuels conflits
git push origin custom-feature --force
```

**Note**: Le rebasing réécrit l'historique des commits, donc utilisez cette option avec précaution, surtout si vous travaillez en équipe.

## Bonnes pratiques

1. **Synchronisez régulièrement**: Synchronisez votre fork régulièrement pour éviter d'accumuler trop de différences.
2. **Testez après la synchronisation**: Assurez-vous que tout fonctionne correctement après la synchronisation.
3. **Documentez les modifications**: Documentez les modifications que vous apportez pour faciliter les futures synchronisations.
4. **Utilisez des branches**: Utilisez des branches pour isoler les différentes fonctionnalités et faciliter la gestion des conflits.
5. **Communiquez**: Si vous travaillez en équipe, communiquez les synchronisations pour éviter les surprises.

## Résolution des problèmes courants

### Conflits de fusion impossibles à résoudre

Si vous rencontrez des conflits de fusion impossibles à résoudre, vous pouvez essayer de:

1. Annuler la fusion: `git merge --abort`
2. Créer une nouvelle branche à partir du dépôt original: `git checkout -b new-branch upstream/main`
3. Appliquer vos modifications manuellement sur cette nouvelle branche

### Erreurs de push

Si vous rencontrez des erreurs lors du push, assurez-vous que:

1. Vous avez les droits d'écriture sur le dépôt
2. Vous n'essayez pas de pousser sur le dépôt original au lieu de votre fork
3. Votre branche locale est à jour avec la branche distante: `git pull origin <branche>` avant de pousser