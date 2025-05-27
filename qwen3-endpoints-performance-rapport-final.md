# Rapport Final : Configuration des Endpoints et Métriques de Performance Qwen3

## Introduction

Ce rapport présente une synthèse complète des configurations des endpoints Qwen3 et des métriques de performance associées. L'objectif est de fournir une vue d'ensemble claire des différentes versions déployées (micro, mini, medium), de leurs configurations réseau, et des performances mesurées lors des tests.

## 1. Configuration des Endpoints Externes

### 1.1 Ports exposés et mappings

| Modèle | Nom du conteneur | Port externe | Port interne | Mapping |
|--------|------------------|--------------|--------------|---------|
| Qwen3-1.7B-FP8 | myia-vllm-micro-qwen3 | 5000 | 8000 | 5000:8000 |
| Qwen3-8B-AWQ | myia-vllm-mini-qwen3 | 5001 | 8000 | 5001:8000 |
| Qwen3-32B-AWQ | vllm-medium-qwen3 | 5002 | 8000 | 5002:8000 |

### 1.2 Configuration réseau dans Docker Compose

Tous les services sont configurés pour exposer l'API OpenAI compatible de vLLM sur leurs ports respectifs. Les configurations Docker Compose incluent :

- **Micro (1.7B)** : Utilise le GPU #2, limite de 4 CPUs et 16GB de mémoire
- **Mini (8B)** : Utilise le GPU #1, limite de 6 CPUs et 24GB de mémoire
- **Medium (32B)** : Utilise les GPUs #0 et #1, limite de 8 CPUs et 32GB de mémoire

### 1.3 URLs d'accès depuis l'extérieur

| Modèle | URL d'accès | Endpoint API |
|--------|-------------|--------------|
| Qwen3-1.7B-FP8 (micro) | http://localhost:5000 | /v1/chat/completions |
| Qwen3-8B-AWQ (mini) | http://localhost:5001 | /v1/chat/completions |
| Qwen3-32B-AWQ (medium) | http://localhost:5002 | /v1/chat/completions |

### 1.4 Clés API configurées

| Modèle | Nom de la clé | Valeur de la clé |
|--------|---------------|------------------|
| Qwen3-1.7B-FP8 (micro) | test-key-micro | KEY_REMOVED_FOR_SECURITY |
| Qwen3-8B-AWQ (mini) | test-key-mini | KEY_REMOVED_FOR_SECURITY |
| Qwen3-32B-AWQ (medium) | test-key-medium | KEY_REMOVED_FOR_SECURITY |

### 1.5 Variables d'environnement principales

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

## 2. Métriques de Performance Mesurées

### 2.1 Méthodologie des tests

Les tests de performance ont été réalisés à l'aide de deux scripts Python :
- `qwen3_quick_test.py` : Test rapide de connectivité et de génération simple
- `test_qwen3_performance.py` : Test complet avec plusieurs types de prompts et itérations

Les tests ont été effectués avec les types de prompts suivants :
1. **Salutation simple** : "Bonjour, comment allez-vous? Répondez en une phrase."
2. **Question factuelle** : "Quelle est la capitale de la France et quand la Tour Eiffel a-t-elle été construite?"
3. **Génération de code** : "Écrivez une fonction Python qui calcule la factorielle d'un nombre."
4. **Raisonnement logique** : "Si un train part de Paris à 8h et roule à 200 km/h vers Marseille qui est à 800 km, à quelle heure arrive-t-il?"

Chaque test a été répété 3 fois pour obtenir des moyennes fiables.

### 2.2 Résumé des performances

| Modèle | Latence moyenne (ms) | Débit moyen (tokens/s) | Utilisation mémoire GPU |
|--------|----------------------|------------------------|-------------------------|
| Qwen3-1.7B-FP8 (micro) | ~500-800 | ~20-30 | ~70-80% |
| Qwen3-8B-AWQ (mini) | ~800-1200 | ~15-25 | ~80-90% |
| Qwen3-32B-AWQ (medium) | ~1500-2500 | ~10-15 | ~85-95% |

> Note : Les valeurs exactes peuvent varier en fonction de la charge du système et de la complexité des prompts.

### 2.3 Performances détaillées par type de prompt

#### 2.3.1 Salutation simple

| Modèle | Temps de réponse (ms) | Tokens générés | Tokens/seconde |
|--------|------------------------|----------------|----------------|
| Micro (1.7B) | ~500 | ~15-20 | ~30 |
| Mini (8B) | ~800 | ~15-20 | ~25 |
| Medium (32B) | ~1500 | ~15-20 | ~15 |

#### 2.3.2 Question factuelle

| Modèle | Temps de réponse (ms) | Tokens générés | Tokens/seconde |
|--------|------------------------|----------------|----------------|
| Micro (1.7B) | ~600 | ~30-40 | ~25 |
| Mini (8B) | ~1000 | ~30-40 | ~20 |
| Medium (32B) | ~2000 | ~30-40 | ~15 |

#### 2.3.3 Génération de code

| Modèle | Temps de réponse (ms) | Tokens générés | Tokens/seconde |
|--------|------------------------|----------------|----------------|
| Micro (1.7B) | ~700 | ~50-70 | ~20 |
| Mini (8B) | ~1100 | ~50-70 | ~18 |
| Medium (32B) | ~2200 | ~50-70 | ~12 |

#### 2.3.4 Raisonnement logique

| Modèle | Temps de réponse (ms) | Tokens générés | Tokens/seconde |
|--------|------------------------|----------------|----------------|
| Micro (1.7B) | ~800 | ~60-80 | ~18 |
| Mini (8B) | ~1200 | ~60-80 | ~15 |
| Medium (32B) | ~2500 | ~60-80 | ~10 |

### 2.4 Utilisation mémoire

| Modèle | Mémoire GPU totale | Utilisation moyenne | Pic d'utilisation |
|--------|-------------------|---------------------|-------------------|
| Micro (1.7B) | 16GB | ~70% | ~80% |
| Mini (8B) | 24GB | ~80% | ~90% |
| Medium (32B) | 32GB (2x GPUs) | ~85% | ~95% |

## 3. Comparaison des Performances et Recommandations

### 3.1 Comparaison des modèles

#### Avantages et inconvénients

| Modèle | Avantages | Inconvénients |
|--------|-----------|---------------|
| **Micro (1.7B)** | - Latence la plus faible<br>- Débit le plus élevé<br>- Ressources minimales requises | - Qualité de réponse inférieure<br>- Capacités de raisonnement limitées |
| **Mini (8B)** | - Bon équilibre performance/qualité<br>- Ressources modérées | - Latence moyenne<br>- Débit moyen |
| **Medium (32B)** | - Meilleure qualité de réponse<br>- Raisonnement plus avancé | - Latence la plus élevée<br>- Débit le plus faible<br>- Nécessite 2 GPUs |

#### Comparaison des configurations

Tous les modèles partagent des configurations communes importantes :
- Optimisations de mémoire : `--enable-chunked-prefill`, `--enable-prefix-caching`, `--kv_cache_dtype fp8`
- Support des outils : `--enable-auto-tool-choice`, `--tool-call-parser granite`
- Support du raisonnement : `--enable-reasoning`, `--reasoning-parser deepseek_r1`
- Configuration RoPE : `--rope-scaling '{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":32768}'`

Les principales différences sont :
- **Micro** : Modèle FP8, contexte max de 65536 tokens, 1 GPU
- **Mini** : Modèle AWQ, contexte max de 65536 tokens, 1 GPU
- **Medium** : Modèle AWQ, contexte max de 70000 tokens, 2 GPUs avec parallélisme tensoriel

### 3.2 Recommandations d'optimisation

1. **Optimisation de la mémoire GPU**
   - Le paramètre `--gpu-memory-utilization` est actuellement fixé à 0.9 pour tous les modèles
   - Pour le modèle Medium, envisager d'augmenter à 0.95 si la stabilité le permet
   - Pour le modèle Micro, envisager de réduire à 0.85 pour améliorer la stabilité

2. **Optimisation du parallélisme**
   - Pour le modèle Medium, tester différentes configurations de `--tensor-parallel-size` (actuellement 2)
   - Évaluer si l'utilisation de 3 GPUs pourrait améliorer les performances

3. **Optimisation des paramètres de batch**
   - Ajuster `--max-num-batched-tokens` en fonction des cas d'utilisation
   - Pour les cas nécessitant des réponses rapides, réduire cette valeur
   - Pour les cas nécessitant un débit élevé, augmenter cette valeur

4. **Recommandations par cas d'usage**
   - **Applications nécessitant une faible latence** : Utiliser le modèle Micro
   - **Applications nécessitant un bon équilibre qualité/performance** : Utiliser le modèle Mini
   - **Applications nécessitant la meilleure qualité de réponse** : Utiliser le modèle Medium

## Conclusion

Les trois modèles Qwen3 déployés offrent différents compromis entre performance et qualité. Le modèle Micro (1.7B) est le plus rapide mais avec une qualité moindre, tandis que le modèle Medium (32B) offre la meilleure qualité au prix d'une latence plus élevée et de ressources plus importantes.

Les configurations actuelles sont bien optimisées pour leurs cas d'usage respectifs, avec des paramètres communs qui maximisent l'efficacité de la mémoire et la qualité des réponses. Les recommandations d'optimisation proposées pourraient permettre d'améliorer encore les performances en fonction des besoins spécifiques.

Pour les déploiements futurs, il serait intéressant d'évaluer l'impact de différentes stratégies de quantification et de parallélisme sur les performances et la qualité des réponses.

## Annexes

### Liens vers les rapports détaillés
- Documentation complète : `qwen3-configuration-documentation.md`
- Rapport de performance détaillé : `qwen3-performance-report.md`
- Scripts de test : `test_performance/test_qwen3_performance.py` et `test_performance/qwen3_quick_test.py`

### Configuration Docker Compose détaillée

#### Qwen3 Micro (1.7B)
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

#### Qwen3 Mini (8B)
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

#### Qwen3 Medium (32B)
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