# Guide de sécurisation pour les commits et push de Qwen3

Ce document décrit les bonnes pratiques pour sécuriser les commits et push du projet Qwen3, en veillant à ne pas exposer de tokens, clés API ou autres informations sensibles.

## Principes généraux

1. **Ne jamais committer de secrets** - Tokens, clés API, mots de passe, etc.
2. **Utiliser des variables d'environnement** - Toujours référencer les secrets via des variables d'environnement
3. **Fournir des fichiers .example** - Créer des fichiers `.env.example` avec la structure mais sans les valeurs réelles
4. **Configurer correctement .gitignore** - S'assurer que les fichiers sensibles sont exclus

## Fichiers sensibles à ne pas committer

- `.env`
- `huggingface.env`
- Tout fichier contenant des tokens ou clés API
- Fichiers de logs
- Caches et données temporaires

## Utilisation des variables d'environnement

Dans les fichiers docker-compose et scripts, utilisez toujours des variables d'environnement pour les informations sensibles:

```yaml
environment:
  - HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN}
  - VLLM_API_KEY=${VLLM_API_KEY_MEDIUM}
```

## Chemins de fichiers

Évitez les chemins hardcodés spécifiques à votre environnement. Utilisez des chemins relatifs ou des variables d'environnement:

```yaml
volumes:
  - ${HF_CACHE_PATH}:/root/.cache/huggingface/hub
```

Dans les scripts PowerShell, utilisez `$PSScriptRoot` pour les chemins relatifs:

```powershell
$logDir = Join-Path -Path $PSScriptRoot -ChildPath "logs"
```

## Vérification avant commit

Avant de committer, exécutez cette commande pour vérifier qu'aucun secret n'est exposé:

```powershell
# Rechercher des tokens potentiels
git diff --cached | grep -E "token|key|secret|password"

# Vérifier les fichiers sensibles
git status | grep -E "\.env|huggingface\.env"
```

## Procédure de commit sécurisé

1. Mettez à jour le fichier `.gitignore` pour exclure les fichiers sensibles
2. Créez ou mettez à jour les fichiers `.env.example` avec la structure mais sans les valeurs réelles
3. Vérifiez qu'aucun fichier sensible n'est inclus dans le commit avec `git status`
4. Committez et poussez les modifications

## Restauration des secrets en production

Pour déployer en production:

1. Copiez les fichiers `.env.example` vers `.env` et `huggingface.env`
2. Remplissez les valeurs réelles des secrets
3. Configurez les variables d'environnement nécessaires

## En cas d'exposition accidentelle de secrets

Si des secrets sont accidentellement exposés:

1. Considérez les secrets comme compromis
2. Régénérez immédiatement de nouveaux tokens/clés
3. Utilisez `git filter-branch` ou BFG Repo-Cleaner pour supprimer les secrets de l'historique
4. Forcez le push avec `git push --force`

## Outils recommandés

- **git-secrets**: Outil pour prévenir les commits de secrets
- **pre-commit hooks**: Pour automatiser les vérifications avant commit
- **GitGuardian**: Service de détection de secrets dans le code

En suivant ces bonnes pratiques, nous pouvons maintenir la sécurité de notre code et de nos déploiements.