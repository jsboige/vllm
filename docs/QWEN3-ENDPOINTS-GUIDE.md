# Guide d'utilisation des endpoints Qwen3 optimisés

Ce guide explique comment utiliser les endpoints Qwen3 déployés avec les configurations optimisées.

## Endpoints disponibles

| Modèle | Taille | URL | Clé API |
|--------|--------|-----|---------|
| MEDIUM | 32B | `http://localhost:5002/v1` | `test-key-medium` |
| MINI | 8B | `http://localhost:5001/v1` | `test-key-mini` |
| MICRO | 1.7B | `http://localhost:5000/v1` | `test-key-micro` |

## Noms des modèles

Pour utiliser les modèles, vous devez spécifier le nom correct du modèle dans vos requêtes :

| Modèle | Nom à utiliser dans les requêtes |
|--------|----------------------------------|
| MEDIUM | `Qwen/Qwen3-32B-AWQ` |
| MINI | `Qwen/Qwen3-8B-AWQ` |
| MICRO | `Qwen/Qwen3-1.7B-FP8` |

## Exemples d'utilisation

### Lister les modèles disponibles

```bash
# Pour le modèle MEDIUM
curl -H "Authorization: Bearer test-key-medium" http://localhost:5002/v1/models

# Pour le modèle MINI
curl -H "Authorization: Bearer test-key-mini" http://localhost:5001/v1/models

# Pour le modèle MICRO
curl -H "Authorization: Bearer test-key-micro" http://localhost:5000/v1/models
```

### Génération de texte (chat)

```bash
# Pour le modèle MEDIUM
curl -X POST http://localhost:5002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-key-medium" \
  -d '{
    "model": "Qwen/Qwen3-32B-AWQ",
    "messages": [
      {"role": "user", "content": "Explique-moi brièvement ce qu'est l'intelligence artificielle."}
    ],
    "max_tokens": 100
  }'

# Pour le modèle MINI
curl -X POST http://localhost:5001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-key-mini" \
  -d '{
    "model": "Qwen/Qwen3-8B-AWQ",
    "messages": [
      {"role": "user", "content": "Explique-moi brièvement ce qu'est l'intelligence artificielle."}
    ],
    "max_tokens": 100
  }'

# Pour le modèle MICRO
curl -X POST http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-key-micro" \
  -d '{
    "model": "Qwen/Qwen3-1.7B-FP8",
    "messages": [
      {"role": "user", "content": "Explique-moi brièvement ce qu'est l'intelligence artificielle."}
    ],
    "max_tokens": 100
  }'
```

### Exemple avec Python

```python
import requests
import json

# Configuration pour le modèle MEDIUM
url = "http://localhost:5002/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer test-key-medium"
}
data = {
    "model": "Qwen/Qwen3-32B-AWQ",
    "messages": [
        {"role": "user", "content": "Explique-moi brièvement ce qu'est l'intelligence artificielle."}
    ],
    "max_tokens": 100
}

# Envoi de la requête
response = requests.post(url, headers=headers, data=json.dumps(data))
print(response.json())
```

## Paramètres de génération

Vous pouvez personnaliser la génération de texte en ajoutant ces paramètres à vos requêtes :

| Paramètre | Description | Valeur par défaut |
|-----------|-------------|-------------------|
| `temperature` | Contrôle la créativité (0.0 = déterministe, 1.0 = créatif) | 0.6 |
| `top_p` | Échantillonnage nucleus (0.0 - 1.0) | 0.95 |
| `top_k` | Limite le nombre de tokens considérés | 20 |
| `max_tokens` | Nombre maximum de tokens à générer | - |
| `stream` | Retourne les tokens au fur et à mesure de leur génération | false |

Exemple avec paramètres personnalisés :

```bash
curl -X POST http://localhost:5002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-key-medium" \
  -d '{
    "model": "Qwen/Qwen3-32B-AWQ",
    "messages": [
      {"role": "user", "content": "Écris un poème sur l'intelligence artificielle."}
    ],
    "max_tokens": 200,
    "temperature": 0.8,
    "top_p": 0.9,
    "top_k": 40
  }'
```

## Bonnes pratiques

1. **Choix du modèle** :
   - MEDIUM (32B) : Pour les tâches complexes nécessitant une haute qualité
   - MINI (8B) : Pour un bon équilibre entre qualité et performance
   - MICRO (1.7B) : Pour les tâches simples nécessitant une réponse rapide

2. **Optimisation des requêtes** :
   - Limitez `max_tokens` au strict nécessaire
   - Utilisez des prompts clairs et concis
   - Évitez les requêtes trop fréquentes sur le même endpoint

3. **Gestion des erreurs** :
   - Implémentez des mécanismes de retry avec backoff exponentiel
   - Surveillez les codes d'erreur HTTP et adaptez votre comportement

## Limitations connues

- Les requêtes de génération longue peuvent échouer avec l'erreur "There was an error parsing the body"
- Le partage du GPU 2 entre les modèles MINI et MICRO peut entraîner des ralentissements lors d'une utilisation simultanée intensive

## Support

Pour toute question ou problème concernant l'utilisation des endpoints Qwen3, veuillez contacter l'équipe d'administration système.