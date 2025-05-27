# Configurations historiques Qwen 2.5 QwQ

Ce répertoire contient les configurations historiques de Qwen 2.5 QwQ qui ont été utilisées comme référence pour optimiser les configurations de Qwen3.

## Paramètres ROPE importants

Les paramètres ROPE utilisés dans Qwen 2.5 et adaptés pour Qwen3 :
- `rope_type`: "yarn" (pour une meilleure gestion des contextes longs)
- `factor`: 4.0 (facteur d'échelle pour l'extension du contexte)
- `original_max_position_embeddings`: 32768 (taille maximale du contexte d'origine)

## Répartition GPU

- **MEDIUM (32B)** : GPUs 0,1 (PCIe 4.0) exclusivement, tensor-parallel-size=2
- **MINI (8B)** : GPU 2, tensor-parallel-size=1
- **MICRO (1.7B)** : GPU 2, tensor-parallel-size=1

## Optimisation mémoire

- `gpu-memory-utilization`: 0.99 (au lieu de 0.9999)
- Paramètres KV cache optimisés
- `max-model-len` ajusté selon la mémoire disponible