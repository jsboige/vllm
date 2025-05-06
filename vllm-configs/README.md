# vllm-configs

Ce dépôt contient les configurations personnalisées pour vLLM (Virtual Large Language Model) utilisées sur une machine équipée de 3 GPUs NVIDIA RTX 4090. Il sert d'archive et de référence pour les configurations Docker permettant de déployer différentes tailles de modèles.

## Objectif

L'objectif de ce dépôt est de sécuriser et centraliser les configurations personnalisées de vLLM, permettant de:
- Conserver un historique des configurations fonctionnelles
- Faciliter le redéploiement rapide des environnements
- Documenter les paramètres optimaux pour différentes tailles de modèles
- Servir de référence pour recréer l'environnement si nécessaire

## Documentation supplémentaire

- [Structure Git](GIT-README.md) - Explique la structure des branches git et les procédures pour contribuer au projet
- [Gestion des secrets](SECRETS-README.md) - Explique comment gérer les informations sensibles (tokens, clés API, etc.)

## Structure du dépôt

```
vllm-configs/
├── docker-compose/         # Fichiers docker-compose pour différentes tailles de modèles
│   ├── docker-compose-micro.yml
│   ├── docker-compose-mini.yml
│   ├── docker-compose-medium.yml
│   ├── docker-compose-medium.old.yml
│   └── docker-compose-large.yml
├── dockerfiles/            # Dockerfiles personnalisés
│   └── Dockerfile.patched.speculative
└── env/                    # Fichiers d'environnement
    └── micro.env
```

## Configurations disponibles

### Micro (3B)

- **Modèle**: Zenabius_Qwen2.5-3B-Instruct-exl2
- **GPU**: 1 GPU (RTX 4090)
- **Utilisation mémoire GPU**: 90%
- **Port**: 5000
- **Caractéristiques**:
  - Modèle léger et rapide
  - Optimisé pour les requêtes simples
  - Support des outils (tool calling)
  - Utilise le format fp8 pour le cache KV

### Mini (7B)

- **Modèle**: Qwen/Qwen2.5-7B-Instruct-AWQ
- **GPU**: 1 GPU (RTX 4090)
- **Utilisation mémoire GPU**: 59.9%
- **Port**: 5001
- **Caractéristiques**:
  - Bon équilibre performance/ressources
  - Support des outils (tool calling)

### Medium (32B)

- **Modèle**: Qwen/QwQ-32B-AWQ
- **GPU**: 2 GPUs (RTX 4090)
- **Utilisation mémoire GPU**: 99.99%
- **Port**: 5002
- **Caractéristiques**:
  - Modèle puissant pour des tâches complexes
  - Support des outils (tool calling)
  - Support du raisonnement (reasoning)
  - Utilise le format fp8 pour le cache KV
  - Extension de contexte (RoPE scaling)
  - Image Docker personnalisée avec support de la génération spéculative

### Large (32B)

- **Modèle**: Qwen/QwQ-32B-AWQ
- **GPU**: 1 GPU (RTX 4090)
- **Utilisation mémoire GPU**: 99.99%
- **Port**: 5003
- **Caractéristiques**:
  - Configuration haute performance sur un seul GPU
  - Support des outils (tool calling)
  - Utilise le format fp8 pour le cache KV

## Utilisation

### Démarrer toutes les configurations

```bash
docker compose -p myia-vllm -f docker-compose/docker-compose-micro.yml -f docker-compose/docker-compose-mini.yml -f docker-compose/docker-compose-medium.yml -f docker-compose/docker-compose-large.yml up -d
```

### Démarrer une configuration spécifique

```bash
# Configuration micro
docker compose -p myia-vllm-micro -f docker-compose/docker-compose-micro.yml --env-file env/micro.env up -d

# Configuration mini
docker compose -p myia-vllm-mini -f docker-compose/docker-compose-mini.yml up -d

# Configuration medium
docker compose -p myia-vllm-medium -f docker-compose/docker-compose-medium.yml up -d

# Configuration large
docker compose -p myia-vllm-large -f docker-compose/docker-compose-large.yml up -d
```

### Arrêter les services

```bash
docker compose -p myia-vllm -f docker-compose/docker-compose-micro.yml -f docker-compose/docker-compose-mini.yml -f docker-compose/docker-compose-medium.yml -f docker-compose/docker-compose-large.yml down
```

## Prérequis et dépendances

- Docker et Docker Compose
- NVIDIA Container Toolkit
- 3 GPUs NVIDIA RTX 4090
- Au moins 24 Go de VRAM par GPU
- Accès à Hugging Face (token configuré dans les fichiers d'environnement)

## Images Docker personnalisées

### vllm-patched:speculative

Cette image est basée sur `vllm/vllm-openai:latest` avec l'ajout de la PR #13849 qui améliore la génération spéculative. Elle est utilisée dans la configuration medium.

Pour construire cette image:

```bash
docker build -t vllm-patched:speculative -f dockerfiles/Dockerfile.patched.speculative .
```

## Notes importantes

- Les configurations utilisent des tokens Hugging Face pour accéder aux modèles. Assurez-vous de mettre à jour ces tokens si nécessaire.
- Les chemins de volumes sont configurés pour WSL (Windows Subsystem for Linux). Adaptez-les à votre environnement si nécessaire.
- Les configurations GPU (device_ids) sont spécifiques à la configuration de la machine. Ajustez-les selon votre configuration matérielle.
- L'image `vllm-patched:speculative` doit être construite localement avant de pouvoir être utilisée.