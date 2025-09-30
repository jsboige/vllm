# Documentation des Configurations Qwen3

Ce document présente une analyse complète des configurations Qwen3 dans le projet vLLM, incluant les endpoints configurés, les clés API utilisées, les métriques de performance disponibles et les scripts de test existants.

## Changement de Stratégie : Passage à l'Image Officielle vLLM

L'approche initiale consistait à construire une image Docker personnalisée (`vllm/vllm-openai:qwen3-refactored`) à partir d'une version modifiée du `Dockerfile` de vLLM. Cette démarche, bien que partie d'une intention de maîtriser l'environnement, s'est avérée complexe, lente et source d'erreurs (notamment des `Segmentation Fault` lors de la compilation).

Suite à l'analyse de la documentation officielle (vLLM v0.9.2), il a été confirmé que **la construction manuelle n'est plus nécessaire**. Les versions récentes de vLLM (>=0.8.5) supportent nativement les modèles Qwen3, y compris les optimisations spécifiques comme le `rope-scaling` et les parsers dédiés.

**La nouvelle stratégie consiste donc à utiliser l'image Docker officielle `vllm/vllm-openai:v0.9.2`.**

Les avantages sont multiples :
- **Simplicité :** Plus besoin de maintenir un `Dockerfile` personnalisé.
- **Stabilité :** Utilisation d'une image testée et validée par la communauté et les mainteneurs de vLLM.
- **Performance :** Bénéfice des dernières optimisations (comme FP8 Marlin sur Ampere) directement intégrées.
- **Maintenance Réduite :** Les mises à jour se feront simplement en changeant le tag de l'image.

Ce changement stratégique a conduit à l'annulation des modifications sur `setup.py` et `docker/Dockerfile`, et à la mise à jour des fichiers `docker-compose-*.yml` pour utiliser `image: vllm/vllm-openai:v0.9.2` au lieu d'une section `build`.

---
## Table des matières

- [Documentation des Configurations Qwen3](#documentation-des-configurations-qwen3)
  - [Changement de Stratégie : Passage à l'Image Officielle vLLM](#changement-de-stratégie--passage-à-limage-officielle-vllm)
  - [Table des matières](#table-des-matières)
  - [Synthèse des Recommandations (Basée sur la Documentation Officielle)](#synthèse-des-recommandations-basée-sur-la-documentation-officielle)
  - [Structure du projet](#structure-du-projet)
  - [Endpoints configurés](#endpoints-configurés)
  - [Configuration Docker](#configuration-docker)
    - [Qwen3 Micro (1.7B)](#qwen3-micro-17b)
    - [Qwen3 Mini (8B)](#qwen3-mini-8b)
    - [Qwen3 Medium (32B)](#qwen3-medium-32b)
  - [Variables d'environnement](#variables-denvironnement)
  - [Métriques de performance](#métriques-de-performance)
  - [Scripts de déploiement et de test](#scripts-de-déploiement-et-de-test)
    - [Scripts de déploiement](#scripts-de-déploiement)
    - [Scripts de test](#scripts-de-test)
  - [Parsers d'outils](#parsers-doutils)
  - [Caractéristiques des modèles](#caractéristiques-des-modèles)
    - [Configurations communes](#configurations-communes)
    - [Différences entre les modèles](#différences-entre-les-modèles)
  - [Scripts d'intégration et de maintenance](#scripts-dintégration-et-de-maintenance)
    - [Scripts de déploiement](#scripts-de-déploiement-1)
    - [Scripts de maintenance](#scripts-de-maintenance)
    - [Scripts de test](#scripts-de-test-1)
  - [Recommandations Officielles Détaillées](#recommandations-officielles-détaillées)
    - [Gestion du Contexte Long (RoPE Scaling)](#gestion-du-contexte-long-rope-scaling)
    - [Gestion de la Mémoire GPU (`gpu-memory-utilization`)](#gestion-de-la-mémoire-gpu-gpu-memory-utilization)
    - [Déploiement des Modèles Quantifiés (FP8 et AWQ)](#déploiement-des-modèles-quantifiés-fp8-et-awq)

## Synthèse des Recommandations (Basée sur la Documentation Officielle)

Cette section met en évidence les divergences critiques entre la configuration actuelle et les recommandations officielles de Qwen/vLLM. L'alignement sur ces bonnes pratiques est essentiel pour la stabilité et la performance, en particulier pour le modèle `medium`.

| Paramètre | Valeur Actuelle (Prod) | Recommandation Officielle | Justification et Impact |
| :--- | :--- | :--- | :--- |
| `--reasoning-parser` | `deepseek_r1` | `qwen3` | **Stabilité :** Le parser `qwen3` (disponible depuis vLLM 0.9.0) est le parser natif. Il résout les conflits avec `enable_thinking=False` et est mieux maintenu. |
| `--tool-call-parser` | `granite` | `hermes` | **Fiabilité :** Le parser `hermes` est celui qui est explicitement recommandé et testé par l'équipe Qwen pour le *function calling*. |
| `--rope-scaling` | Appliqué systématiquement (`factor:4.0`) | Appliquer **uniquement si nécessaire** et avec un `factor` adapté (ex: 2.0 pour 65k tokens). | **Performance critique :** L'activation systématique dégrade les performances sur les textes courts (<32k tokens). C'est une cause probable de latence. |
| `--gpu-memory-utilization` | `0.9` (avec intention de monter) | **Baisser** en cas d'erreur OOM (Out Of Memory). | **Correction Mémoire critique :** vLLM utilise des "CUDA Graphs" qui allouent de la mémoire non suivie par ce paramètre. Augmenter la valeur peut paradoxalement aggraver les OOMs. |

---

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
- `tests/performance/`: Scripts de test de performance
  - `qwen3_quick_test.py`: Script de test rapide pour les endpoints Qwen3

## Endpoints configurés

Trois endpoints Qwen3 sont configurés:

| Nom | URL | Port | Modèle | Clé API |
|-----|-----|------|--------|---------|
| micro | http://localhost:5000 | 5000 | Qwen/Qwen3-1.7B-FP8 | `${VLLM_API_KEY:-${VLLM_API_KEY_MICRO}}` (ex: `YOUR_API_KEY_MICRO`) |
| mini | http://localhost:5001 | 5001 | Qwen/Qwen3-8B-AWQ | `${VLLM_API_KEY:-${VLLM_API_KEY_MINI}}` (ex: `YOUR_API_KEY_MINI`) |
| medium | http://localhost:5002 | 5002 | Qwen/Qwen3-32B-AWQ | `${VLLM_API_KEY:-${VLLM_API_KEY_MEDIUM}}` (ex: `YOUR_API_KEY_MEDIUM`) |

## Configuration Docker

Les configurations suivantes utilisent l'image officielle `vllm/vllm-openai:v0.9.2` et sont alignées avec les fichiers `docker-compose-*.yml` du projet.

### Qwen3 Micro (1.7B)

```yaml
services:
  vllm-micro:
    env_file:
      - ../../../.env
    image: vllm/vllm-openai:v0.9.2
    restart: unless-stopped
    environment:
      - CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES_MICRO}
      - HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN}
      - VLLM_ATTENTION_BACKEND=FLASHINFER
      - VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
    ports:
      - "${VLLM_PORT_MICRO}:8000"
    volumes:
      - ~/.cache/huggingface:/root/.cache/huggingface
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health"]
      interval: 1m
      timeout: ${VLLM_HEALTHCHECK_TIMEOUT_MICRO:-60s}
      retries: 5
      start_period: 5m
    command:
      - "--model=Qwen/Qwen2-1.5B-Instruct-AWQ"
      - "--quantization"
      - "awq"
      - "--dtype"
      - "float16"
      - "--gpu-memory-utilization"
      - "${GPU_MEMORY_UTILIZATION_MICRO}"
      - "--max-model-len"
      - "${VLLM_MICRO_MAX_MODEL_LEN:-128000}"
      - "--kv-cache-dtype"
      - "fp8"
      - "--port"
      - "8000"
      - "--api-key"
      - "${VLLM_API_KEY_MICRO}"
      - "--served-model-name"
      - "qwen3-1.7b-awq"
      - "--chat-template"
      - "/chat-templates/qwen.jinja"
      - "--enable-reasoning"
      - "--reasoning-parser"
      - "qwen3"
      - "--enable-auto-tool-choice"
      - "--tool-call-parser"
      - "hermes"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['2']
              capabilities: [gpu]
```

### Qwen3 Mini (8B)

```yaml
services:
  vllm-mini:
    env_file:
      - ../../../.env
    image: vllm/vllm-openai:v0.9.2
    restart: unless-stopped
    environment:
      - CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES_MINI}
      - HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN}
    ports:
      - "${VLLM_PORT_MINI}:8000"
    volumes:
      - ~/.cache/huggingface:/root/.cache/huggingface
    command:
      - "--model=Qwen/Qwen2-7B-Instruct-AWQ"
      - "--quantization"
      - "awq"
      - "--gpu-memory-utilization"
      - "${GPU_MEMORY_UTILIZATION_MINI}"
      - "--max-model-len"
      - "${VLLM_MINI_MAX_MODEL_LEN:-128000}"
      - "--kv-cache-dtype"
      - "fp8"
      - "--rope_scaling"
      - '{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":32768}'
      - "--enable-reasoning"
      - "--reasoning-parser"
      - "qwen3"
      - "--port"
      - "8000"
      - "--api-key"
      - "${VLLM_API_KEY_MINI}"
      - "--served-model-name"
      - "qwen3-8b-awq"
      - "--chat-template"
      - "/chat-templates/qwen.jinja"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['2']
              capabilities: [gpu]
```

### Qwen3 Medium (32B)

```yaml
services:
  vllm-medium:
    env_file:
      - ../../../.env
    image: vllm/vllm-openai:v0.9.2
    shm_size: 4g
    restart: unless-stopped
    environment:
      - HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN}
      - VLLM_ALLOW_LONG_MAX_MODEL_LEN=1
      - NCCL_DEBUG=INFO
      - VLLM_ATTENTION_BACKEND=FLASHINFER
    ports:
      - "${VLLM_PORT_MEDIUM}:8000"
    volumes:
      - ~/.cache/huggingface:/root/.cache/huggingface
    command:
      - "--host=0.0.0.0"
      - "--port=8092"
      - "--model=${MODEL_NAME_MEDIUM}"
      - "--chat-template=/app/chat-templates/qwen.jinja"
      - "--max-model-len=${VLLM_MEDIUM_MAX_MODEL_LEN:-75000}"
      - "--quantization=awq_marlin"
      - "--tensor-parallel-size=2"
      - "--kv-cache-dtype=fp8"
      - "--rope-scaling={\"rope_type\":\"yarn\",\"factor\":4.0,\"original_max_position_embeddings\":32768}"
      - "--enable-reasoning"
      - "--reasoning-parser"
      - "qwen3"
      - "--enable-auto-tool-choice"
      - "--tool-call-parser"
      - "hermes"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['0', '1']
              capabilities: [gpu]
```

## Variables d'environnement

Les variables d'environnement suivantes sont utilisées pour configurer les services:

```
# Clés API pour les différents services (utilisées avec des valeurs par défaut dans Docker Compose)
VLLM_API_KEY_MICRO=YOUR_API_KEY_MICRO
VLLM_API_KEY_MINI=YOUR_API_KEY_MINI
VLLM_API_KEY_MEDIUM=YOUR_API_KEY_MEDIUM

# Ports pour les différents services (utilisés avec des valeurs par défaut dans Docker Compose)
VLLM_PORT_MICRO=5000
VLLM_PORT_MINI=5001
VLLM_PORT_MEDIUM=5002

# Configuration des GPUs (utilisées avec des valeurs par défaut dans Docker Compose)
CUDA_VISIBLE_DEVICES_MICRO=2
CUDA_VISIBLE_DEVICES_MINI=2 # Correction: Était '1' dans la doc, mais '2' dans docker-compose-mini-qwen3.yml
CUDA_VISIBLE_DEVICES_MEDIUM=0,1

# Paramètres d'utilisation de la mémoire GPU (utilisés avec des valeurs par défaut dans Docker Compose)
GPU_MEMORY_UTILIZATION_MICRO=0.9
GPU_MEMORY_UTILIZATION_MINI=0.9
GPU_MEMORY_UTILIZATION_MEDIUM=0.9

# Token Hugging Face (requis pour accéder aux modèles)
HUGGING_FACE_HUB_TOKEN=YOUR_HUGGING_FACE_TOKEN_HERE

# Fuseau horaire (utilisé avec une valeur par défaut vide dans Docker Compose)
TZ=

# Pourcentage d'utilisation du GPU (utilisé avec une valeur par défaut dans Docker Compose)
GPU_PERCENTAGE=0.9999

# Backend d'attention VLLM (utilisé avec une valeur par défaut dans Docker Compose)
VLLM_ATTENTION_BACKEND=FLASHINFER

# Type de données (utilisé avec une valeur par défaut dans Docker Compose)
DATATYPE=float16

# Nom du modèle (utilisé avec une valeur par défaut dans Docker Compose pour Medium)
MODEL_NAME=Qwen/Qwen3-32B-AWQ

# Nombre de GPUs pour le parallélisme tensoriel (utilisé avec une valeur par défaut dans Docker Compose)
NUM_GPUS=1 # Ou 2 pour le modèle Medium

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
  - `--tool-call-parser hermes` (Recommandation officielle)

- **Support du raisonnement**:
  - `--enable-reasoning`
  - `--reasoning-parser qwen3` (Recommandation officielle)

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
| GPU(s) utilisé(s) | '2' | '2' | '0','1' |

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

## Recommandations Officielles Détaillées

Cette section approfondit les bonnes pratiques de configuration basées sur la documentation officielle de vLLM et Qwen.

### Gestion du Contexte Long (RoPE Scaling)

**Problématique :** L'activation systématique de RoPE Scaling avec un facteur élevé (`"factor":4.0`) pour tous les modèles a un impact négatif sur les performances.

**Recommandation Officielle :**
- **N'activez `rope-scaling` que si vous traitez des contextes longs dépassant la capacité native du modèle (32 768 tokens).**
- L'utilisation de `rope_scaling` (`"rope_type":"yarn"`) est qualifiée de "statique" dans vLLM. Cela signifie que le facteur d'échelle est constant et peut **dégrader significativement les performances sur des textes courts**.
- **Adaptez le `factor` à votre besoin réel.** Par exemple, pour une longueur de contexte cible de 65 536 tokens, un `factor` de `2.0` est plus approprié et performant qu'un `factor` de `4.0`.

**Action :** Le paramètre a été conservé dans les `docker-compose` pour mémoire, mais un commentaire d'avertissement a été ajouté. Il doit être retiré pour les usages courants et activé avec discernement pour les cas spécifiques de contexte long.

### Gestion de la Mémoire GPU (`gpu-memory-utilization`)

**Problématique :** L'intuition commune est d'augmenter la valeur de `--gpu-memory-utilization` pour allouer plus de mémoire au modèle. Cela peut être contre-productif.

**Recommandation Officielle :**
- Par défaut, vLLM utilise des **CUDA Graphs**, qui peuvent allouer de la mémoire GPU d'une manière qui n'est pas directement contrôlée ou comptabilisée par le paramètre `gpu-memory-utilization`.
- En cas d'erreur **Out-Of-Memory (OOM)**, il est souvent recommandé de **BAISSER** la valeur de `gpu-memory-utilization` (par ex. à `0.85` ou `0.8`) pour laisser plus de marge à ces allocations cachées.
- Si le problème persiste, les alternatives sont de désactiver les graphs avec `--enforce-eager` (ce qui peut ralentir l'inférence) ou de réduire `--max-model-len`.

**Action :** Ne pas augmenter `GPU_MEMORY_UTILIZATION_MEDIUM` à `0.95`. En cas de problème de mémoire, la première étape devrait être de le réduire.

### Déploiement des Modèles Quantifiés (FP8 et AWQ)

**Contexte :** Le projet utilise des modèles FP8 et AWQ, mais la documentation manquait de détails techniques critiques.

**Informations de la Documentation Officielle :**
- **Prérequis pour FP8 :** Les modèles FP8 de Qwen3 sont "block-wise quantized".
  - Ils fonctionnent nativement en `w8a8` sur des GPUs avec une capacité de calcul **supérieure à 8.9** (Ada Lovelace, Hopper).
  - Depuis `vLLM v0.9.0`, ils sont également supportés sur les cartes **Ampere** (compute capability 8.0-8.9) grâce à FP8 Marlin, qui opère en `w8a16`.
- **Erreur courante avec FP8 :** Si vous rencontrez une erreur `ValueError: The output_size of gate's and up's weight ... is not divisible by weight quantization block_n ...`, cela indique que la taille du parallélisme tensoriel n'est pas compatible avec les poids du modèle. La solution est de **réduire le `tensor-parallel-size`**.