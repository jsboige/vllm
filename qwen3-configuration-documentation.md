# Documentation des Configurations Qwen3

Ce document présente une analyse complète des configurations Qwen3 dans le projet vLLM, incluant les endpoints configurés, les clés API utilisées, les métriques de performance disponibles et les scripts de test existants.

## Table des matières

1. [Structure du projet](#structure-du-projet)
2. [Endpoints configurés](#endpoints-configurés)
3. [Configuration Docker](#configuration-docker)
4. [Variables d'environnement](#variables-denvironnement)
5. [Métriques de performance](#métriques-de-performance)
6. [Scripts de déploiement et de test](#scripts-de-déploiement-et-de-test)
7. [Parsers d'outils](#parsers-doutils)
8. [Scripts d'intégration et de maintenance](#scripts-dintégration-et-de-maintenance)

## Structure du projet

Le projet est organisé comme suit:

- `qwen3/`: Répertoire principal pour les fichiers spécifiques à Qwen3
  - `parsers/`: Parsers pour les appels d'outils (vide ou non existant)
  - `scripts/`: Scripts PowerShell pour le déploiement et la maintenance
    - `deploy-qwen3-32b-awq.ps1`: Script pour déployer le modèle Qwen3-32B-AWQ
    - `finalize-qwen3-integration.ps1`: Script pour finaliser l'intégration de Qwen3
    - `find_parser_references.ps1`: Script pour trouver les références au parser Qwen3
    - `fix_qwen3_parser.ps1`: Script pour corriger le parser Qwen3
    - `quick-update-qwen3.ps1`: Script pour mettre à jour rapidement Qwen3
- `vllm-configs/`: Configurations pour le déploiement
  - `docker-compose/`: Fichiers docker-compose pour les différentes versions de Qwen3
    - `build/tool_parsers/`: Parsers d'outils personnalisés
      - `qwen3_tool_parser.py`: Parser d'outils personnalisé pour Qwen3
  - `scripts/`: Scripts PowerShell pour le déploiement et la maintenance
- `test_performance/`: Scripts de test de performance
  - `qwen3_quick_test.py`: Script de test rapide pour les endpoints Qwen3

## Endpoints configurés

Trois endpoints Qwen3 sont configurés:

| Nom | URL | Port | Modèle | Clé API |
|-----|-----|------|--------|---------|
| micro | http://localhost:5000 | 5000 | Qwen/Qwen3-1.7B-FP8 | test-key-micro / KEY_REMOVED_FOR_SECURITY |
| mini | http://localhost:5001 | 5001 | Qwen/Qwen3-8B-AWQ | test-key-mini / KEY_REMOVED_FOR_SECURITY |
| medium | http://localhost:5002 | 5002 | Qwen/Qwen3-32B-AWQ | test-key-medium / KEY_REMOVED_FOR_SECURITY |

## Configuration Docker

### Qwen3 Micro (1.7B)

```yaml
services:
  vllm-micro-qwen3:
    image: vllm/vllm-openai:qwen3-fixed
    container_name: myia-vllm-micro-qwen3
    command:
      --model Qwen/Qwen3-1.7B-FP8
      --tensor-parallel-size 1
      --gpu-memory-utilization 0.9
      --enable-chunked-prefill
      --max-model-len 65536
      --max-num-batched-tokens 65536
      --enable-prefix-caching
      --dtype float16
      --enable-auto-tool-choice
      --tool-call-parser granite
      --kv_cache_dtype fp8
      --enable-reasoning
      --reasoning-parser deepseek_r1
      --rope-scaling '{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":32768}'
    ports:
      - "5000:8000"
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
              device_ids: ['2']
        limits:
          cpus: '4.0'
          memory: 16G
```

### Qwen3 Mini (8B)

```yaml
services:
  vllm-mini-qwen3:
    image: vllm/vllm-openai:qwen3-fixed
    container_name: myia-vllm-mini-qwen3
    command:
      --model Qwen/Qwen3-8B-AWQ
      --tensor-parallel-size 1
      --gpu-memory-utilization 0.9
      --enable-chunked-prefill
      --max-model-len 65536
      --max-num-batched-tokens 65536
      --enable-prefix-caching
      --dtype float16
      --enable-auto-tool-choice
      --tool-call-parser granite
      --kv_cache_dtype fp8
      --enable-reasoning
      --reasoning-parser deepseek_r1
      --rope-scaling '{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":32768}'
    ports:
      - "5001:8000"
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
              device_ids: ['1']
        limits:
          cpus: '6.0'
          memory: 24G
```

### Qwen3 Medium (32B)

```yaml
services:
  vllm-medium-qwen3:
    image: vllm/vllm-openai:qwen3-fixed
    command:
      --model Qwen/Qwen3-32B-AWQ
      --tensor-parallel-size 2
      --gpu-memory-utilization 0.9
      --enable-chunked-prefill
      --max-model-len 70000
      --max-num-batched-tokens 70000
      --enable-prefix-caching
      --enable-auto-tool-choice
      --tool-call-parser granite
      --dtype float16
      --rope-scaling '{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":32768}'
      --enable-reasoning
      --reasoning-parser deepseek_r1
      --kv_cache_dtype fp8
    ports:
      - "5002:8000"
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
              device_ids: ['0','1']
        limits:
          cpus: '8.0'
          memory: 32G
```

## Variables d'environnement

Les variables d'environnement suivantes sont utilisées pour configurer les services:

```
# Clés API pour les différents services
VLLM_API_KEY_MICRO=test-key-micro / KEY_REMOVED_FOR_SECURITY
VLLM_API_KEY_MINI=test-key-mini / KEY_REMOVED_FOR_SECURITY
VLLM_API_KEY_MEDIUM=test-key-medium / KEY_REMOVED_FOR_SECURITY

# Ports pour les différents services
VLLM_PORT_MICRO=5000
VLLM_PORT_MINI=5001
VLLM_PORT_MEDIUM=5002

# Configuration des GPUs
CUDA_VISIBLE_DEVICES_MICRO=2
CUDA_VISIBLE_DEVICES_MINI=1
CUDA_VISIBLE_DEVICES_MEDIUM=0,1

# Paramètres d'utilisation de la mémoire GPU
GPU_MEMORY_UTILIZATION_MICRO=0.9
GPU_MEMORY_UTILIZATION_MINI=0.9
GPU_MEMORY_UTILIZATION_MEDIUM=0.9

# Token Hugging Face (requis pour accéder aux modèles)
HUGGING_FACE_HUB_TOKEN=YOUR_HUGGING_FACE_TOKEN_HERE

# Permettre des longueurs de contexte plus grandes que celles définies dans les modèles
VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
```

## Métriques de performance

Le script `qwen3_quick_test.py` mesure les métriques de performance suivantes:

1. **Connectivité**:
   - Vérification de la disponibilité de l'API
   - Statut HTTP de la réponse

2. **Génération de texte**:
   - Temps de réponse (en ms)
   - Nombre de tokens (prompt, completion, total)
   - Débit en tokens par seconde

Exemple de requête de test:
```python
chat_data = {
    "model": config["model"],
    "messages": [
        {"role": "user", "content": "Bonjour, comment allez-vous? Répondez en une phrase."}
    ],
    "max_tokens": 50,
    "temperature": 0.7
}
```

## Scripts de déploiement et de test

### Scripts de déploiement

- `start-qwen3-services.ps1`: Script principal pour démarrer les services Qwen3
  - Définit les variables d'environnement
  - Vérifie l'état des services Docker
  - Démarre les services avec docker-compose
  - Vérifie la santé des services après le démarrage
  - Teste l'appel d'outils (si demandé)

### Scripts de test

- `qwen3_quick_test.py`: Script de test rapide pour les endpoints Qwen3
  - Teste la connectivité aux endpoints
  - Teste la génération de texte
  - Mesure les métriques de performance
  - Sauvegarde les résultats dans un fichier JSON

## Parsers d'outils

Le projet utilise deux parsers d'outils:

1. **Parser Granite**: Utilisé dans la configuration docker-compose (`--tool-call-parser granite`)

2. **Parser Qwen3 personnalisé**: Implémenté dans `vllm-configs/docker-compose/build/tool_parsers/qwen3_tool_parser.py`
   - Enregistré sous le nom "qwen3" dans le gestionnaire de parsers d'outils
   - Gère deux formats d'appels d'outils:
     - Format `<tool_call>...</tool_call>`
     - Format `<function_call>...</function_call>`
   - Extrait les appels d'outils à partir de la sortie du modèle
   - Prend en charge le streaming des appels d'outils

## Caractéristiques des modèles

### Configurations communes

Tous les modèles Qwen3 partagent les configurations suivantes:

- **Optimisations de mémoire**:
  - `--enable-chunked-prefill`
  - `--enable-prefix-caching`
  - `--kv_cache_dtype fp8`

- **Support des outils**:
  - `--enable-auto-tool-choice`
  - `--tool-call-parser granite`

- **Support du raisonnement**:
  - `--enable-reasoning`
  - `--reasoning-parser deepseek_r1`

- **Configuration RoPE**:
  - `--rope-scaling '{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":32768}'`

### Différences entre les modèles

| Caractéristique | Micro (1.7B) | Mini (8B) | Medium (32B) |
|-----------------|--------------|-----------|--------------|
| Taille du modèle | 1.7B | 8B | 32B |
| Quantification | FP8 | AWQ | AWQ |
| Parallélisme tensoriel | 1 GPU | 1 GPU | 2 GPUs |
| Longueur maximale | 65536 | 65536 | 70000 |
| CPUs alloués | 4.0 | 6.0 | 8.0 |
| Mémoire allouée | 16G | 24G | 32G |
| GPU(s) utilisé(s) | '2' | '1' | '0','1' |

## Scripts d'intégration et de maintenance

### Scripts de déploiement

1. **start-qwen3-services.ps1**
   - Script principal pour démarrer les services Qwen3
   - Définit les variables d'environnement
   - Vérifie l'état des services Docker
   - Démarre les services avec docker-compose
   - Vérifie la santé des services après le démarrage
   - Teste l'appel d'outils (si demandé)

2. **deploy-qwen3-32b-awq.ps1**
   - Script spécifique pour déployer le modèle Qwen3-32B-AWQ
   - Définit les variables d'environnement nécessaires
   - Vérifie si Docker et les GPUs NVIDIA sont disponibles
   - Déploie le conteneur à l'aide d'un fichier docker-compose spécifique

### Scripts de maintenance

1. **quick-update-qwen3.ps1**
   - Script pour mettre à jour rapidement les services Qwen3
   - Arrête les services existants
   - Démarre les services avec la nouvelle image Docker
   - Vérifie que tout fonctionne correctement

2. **finalize-qwen3-integration.ps1**
   - Script pour finaliser l'intégration du tool calling avec Qwen3 dans vLLM
   - Crée un répertoire de build temporaire
   - Copie les fichiers nécessaires (parsers d'outils et de raisonnement)
   - Crée un Dockerfile optimisé
   - Construit l'image Docker
   - Redémarre les services avec la nouvelle image
   - Teste le tool calling
   - Met à jour la documentation

3. **fix_qwen3_parser.ps1**
   - Script pour corriger l'option du parser d'outils Qwen3
   - Remplace `--parser qwen3` par `--tool-call-parser qwen3` dans les fichiers de configuration

4. **find_parser_references.ps1**
   - Script pour rechercher toutes les références à `--parser qwen3` ou similaires dans le projet
   - Aide à identifier les fichiers qui pourraient nécessiter des corrections

### Scripts de test

1. **qwen3_quick_test.py**
   - Script de test rapide pour les endpoints Qwen3
   - Teste la connectivité aux endpoints
   - Teste la génération de texte
   - Mesure les métriques de performance

2. **test_qwen3_tool_calling_fixed.py** (mentionné dans les scripts mais non trouvé)
   - Script pour tester le tool calling avec Qwen3
   - Teste à la fois le mode normal et le mode streaming