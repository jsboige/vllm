# Guide de soumission de Pull Requests au dépôt vLLM original

Ce guide explique comment soumettre des Pull Requests (PR) au dépôt original de vLLM à partir de notre fork.

## Prérequis

1. Avoir un compte GitHub
2. Avoir un fork du dépôt vLLM
3. Avoir configuré le dépôt original comme remote "upstream"

## Étapes pour soumettre une PR

### 1. Synchroniser votre fork avec le dépôt original

Avant de créer une PR, assurez-vous que votre fork est à jour avec le dépôt original:

```bash
# Ajouter le dépôt original comme remote (si ce n'est pas déjà fait)
git remote add upstream https://github.com/vllm-project/vllm.git

# Récupérer les dernières modifications du dépôt original
git fetch upstream

# Créer une branche pour la synchronisation
git checkout -b sync-upstream

# Fusionner les modifications du dépôt original
git merge upstream/main

# Résoudre les éventuels conflits
# ...

# Valider les modifications
git commit -m "Merge upstream/main into sync-upstream"

# Pousser les modifications vers votre fork
git push origin sync-upstream
```

### 2. Créer une branche spécifique pour la PR

Créez une branche spécifique pour la fonctionnalité ou le correctif que vous souhaitez soumettre:

```bash
# Créer une branche à partir de la branche synchronisée
git checkout -b pr-feature-name sync-upstream

# Développer la fonctionnalité ou le correctif
# ...

# Valider les modifications
git commit -m "Description des modifications"

# Pousser la branche vers votre fork
git push origin pr-feature-name
```

### 3. Soumettre la PR

1. Allez sur la page GitHub du dépôt original: https://github.com/vllm-project/vllm
2. Cliquez sur "Pull requests" puis sur "New pull request"
3. Cliquez sur "compare across forks"
4. Sélectionnez votre fork comme "head repository" et la branche spécifique comme "compare"
5. Vérifiez les modifications et cliquez sur "Create pull request"
6. Remplissez le formulaire de PR avec:
   - Un titre clair et concis
   - Une description détaillée des modifications
   - Des références aux issues concernées (le cas échéant)
   - Des captures d'écran ou des exemples (si pertinent)
7. Cliquez sur "Create pull request"

## Bonnes pratiques pour les PR

### Contenu de la PR

- **Gardez la PR focalisée**: Une PR doit se concentrer sur une seule fonctionnalité ou un seul correctif.
- **Taille raisonnable**: Évitez les PR trop volumineuses qui sont difficiles à réviser.
- **Tests**: Incluez des tests pour les nouvelles fonctionnalités ou les correctifs.
- **Documentation**: Mettez à jour la documentation si nécessaire.

### Messages de commit

- Utilisez des messages de commit clairs et descriptifs.
- Commencez par un verbe à l'impératif (Add, Fix, Update, etc.).
- Limitez la première ligne à 72 caractères.
- Ajoutez des détails dans le corps du message si nécessaire.

### Processus de révision

- Soyez réactif aux commentaires des réviseurs.
- N'hésitez pas à demander des clarifications si nécessaire.
- Mettez à jour votre PR en fonction des commentaires.

## Exemple de PR pour le parser Qwen3 amélioré

Voici un exemple de description de PR pour notre parser Qwen3 amélioré:

```
Title: Improve Qwen3 reasoning parser to preserve content before <think> tag

Description:
This PR improves the Qwen3 reasoning parser to better handle content that appears before the <think> tag. The current implementation discards any content that appears before the <think> tag, which can lead to loss of important information.

Changes:
- Add a new `Qwen3ImprovedReasoningParser` class that extends the original parser
- Preserve content before the <think> tag in both streaming and non-streaming modes
- Add comprehensive tests to verify the behavior
- Add documentation explaining the improvements

The improved parser is registered as "qwen3_improved" and can be used by specifying `--reasoning-parser qwen3_improved` when launching the API server.

Test results:
- All tests pass
- Manual testing confirms that content before the <think> tag is preserved

This PR does not modify the original parser, so existing behavior is preserved for backward compatibility.
```

## Suivi de la PR

Après avoir soumis votre PR:

1. Surveillez les commentaires et les demandes de modifications.
2. Répondez rapidement aux commentaires.
3. Mettez à jour votre PR si nécessaire.
4. Une fois la PR approuvée et fusionnée, vous pouvez supprimer la branche locale:

```bash
git branch -d pr-feature-name
```

## Résolution des problèmes courants

### Conflits de fusion

Si des conflits de fusion apparaissent:

```bash
# Mettre à jour votre branche avec les dernières modifications du dépôt original
git fetch upstream
git merge upstream/main

# Résoudre les conflits
# ...

# Valider les modifications
git commit -m "Resolve merge conflicts"

# Pousser les modifications
git push origin pr-feature-name
```

### Tests qui échouent

Si les tests CI échouent:

1. Consultez les logs d'erreur dans l'interface GitHub.
2. Corrigez les problèmes localement.
3. Validez et poussez les corrections.