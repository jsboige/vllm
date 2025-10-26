# Architecture Consolidée des Tests de Performance Qwen3

Ce package fournit une architecture consolidée pour tester et optimiser les performances des modèles Qwen3 (MICRO, MINI, MEDIUM).

## Structure du Module de Configuration

Le module de configuration est le composant central de l'architecture et sert de base pour tous les autres modules :

```
qwen3_benchmark/
├── __init__.py                # Initialisation du package principal
└── config/                    # Module de configuration
    ├── __init__.py            # Expose les fonctions principales
    ├── default_config.yaml    # Configuration YAML centralisée
    └── models_config.py       # Configurations spécifiques aux modèles
```

## Fonctionnalités du Module de Configuration

Le module de configuration offre les fonctionnalités suivantes :

1. **Gestion centralisée des paramètres** :
   - Endpoints des modèles (URLs, clés API, etc.)
   - Paramètres de test (itérations, timeouts, etc.)
   - Longueurs de contexte à tester
   - Paramètres d'optimisation (marges de sécurité, etc.)
   - Chemins de sortie pour les rapports et visualisations

2. **Configuration spécifique aux modèles** :
   - Définitions des modèles Qwen3 (MICRO, MINI, MEDIUM)
   - Paramètres spécifiques à chaque modèle
   - Fonctions pour obtenir la configuration d'un modèle spécifique

3. **Génération de configurations optimisées** :
   - Calcul des paramètres optimaux en fonction du contexte maximal
   - Génération de fichiers de configuration YAML
   - Génération de fichiers docker-compose optimisés

## Utilisation du Module de Configuration

### Chargement de la Configuration

```python
from qwen3_benchmark.config import load_config

# Charger la configuration complète
config = load_config()
```

### Accès aux Configurations des Modèles

```python
from qwen3_benchmark.config import get_model_config, get_available_models

# Obtenir la liste des modèles disponibles
models = get_available_models()  # ['micro', 'mini', 'medium']

# Obtenir la configuration complète d'un modèle
model_config = get_model_config('micro')
```

### Accès aux Paramètres Spécifiques

```python
from qwen3_benchmark.config import (
    get_model_endpoint,
    get_model_context_lengths,
    get_optimization_params
)

# Obtenir les informations d'endpoint pour un modèle
endpoint = get_model_endpoint('mini')

# Obtenir les longueurs de contexte à tester pour un modèle
context_lengths = get_model_context_lengths('medium')

# Obtenir les paramètres d'optimisation pour un modèle
optimization = get_optimization_params('micro')
```

### Génération de Configurations Optimisées

```python
from qwen3_benchmark.config import (
    generate_optimized_config,
    create_optimized_config_file,
    generate_docker_compose_file
)

# Générer une configuration optimisée en mémoire
optimized_config = generate_optimized_config('medium', max_context=98304)

# Créer un fichier de configuration YAML optimisé
config_file = create_optimized_config_file('medium', max_context=98304)

# Générer un fichier docker-compose optimisé
docker_file = generate_docker_compose_file('medium', optimized_config)
```

## Extensibilité

Le module de configuration est conçu pour être facilement extensible :

1. Pour ajouter un nouveau modèle, mettez à jour `QWEN3_MODELS` dans `models_config.py`
2. Pour ajouter de nouveaux paramètres, mettez à jour `default_config.yaml`
3. Pour ajouter de nouvelles fonctionnalités, étendez les modules existants

## Prochaines Étapes

Cette implémentation du module de configuration servira de base pour les autres modules de l'architecture consolidée :

1. Module de benchmarking pour exécuter les tests de performance
2. Module d'analyse pour traiter les résultats des tests
3. Module de visualisation pour générer des graphiques et des rapports
4. Module d'optimisation pour générer des configurations optimisées