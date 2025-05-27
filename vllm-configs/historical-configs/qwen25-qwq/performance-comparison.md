# Comparaison des performances Qwen3 vs Qwen 2.5 QwQ

Ce document compare les configurations et performances attendues entre les modèles Qwen3 et les configurations historiques de Qwen 2.5 QwQ.

## Modifications principales

| Paramètre | Configuration originale Qwen3 | Configuration optimisée (basée sur Qwen 2.5 QwQ) | Impact attendu |
|-----------|-------------------------------|--------------------------------------------------|---------------|
| `gpu-memory-utilization` | 0.9999 | 0.99 | Réduction du risque OOM, stabilité accrue |
| `CUDA_VISIBLE_DEVICES` | Variables | MEDIUM: 0,1 / MINI & MICRO: 2 | Répartition GPU optimisée |
| `tensor-parallel-size` | Variables | MEDIUM: 2 / MINI & MICRO: 1 | Utilisation GPU optimisée |
| `rope-scaling` | Paramètres yarn | Conservés mais explicitement configurés | Maintien des performances sur contextes longs |

## Répartition GPU optimisée

- **MEDIUM (32B)** : Utilisation exclusive des GPUs 0,1 (PCIe 4.0) pour maximiser les performances du modèle le plus lourd
- **MINI + MICRO** : Partage du GPU 2 pour optimiser l'utilisation des ressources
  - Ces modèles plus légers peuvent cohabiter sur une même GPU sans dégradation significative des performances

## Optimisation mémoire

La réduction de `gpu-memory-utilization` de 0.9999 à 0.99 permet :
- Une marge de sécurité pour éviter les erreurs OOM (Out Of Memory)
- Une meilleure stabilité lors des pics d'utilisation
- Une réduction des risques de crash du conteneur

## Paramètres ROPE

Les paramètres ROPE sont configurés de manière identique pour tous les modèles :
```json
{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":32768}
```

Cette configuration permet :
- Une gestion optimale des contextes longs
- Une meilleure qualité de génération sur les séquences étendues
- Une compatibilité avec les modèles pré-entraînés

## Métriques de performance attendues

| Modèle | Latence (avant) | Latence (après) | Tokens/s (avant) | Tokens/s (après) | Stabilité |
|--------|----------------|-----------------|------------------|------------------|-----------|
| MEDIUM (32B) | Variable | Améliorée | Variable | Amélioré | Significativement améliorée |
| MINI (8B) | Acceptable | Stable | Acceptable | Stable | Améliorée |
| MICRO (1.7B) | Bonne | Stable | Bonne | Stable | Maintenue |

## Validation

Après déploiement, les métriques suivantes devraient être mesurées pour confirmer l'amélioration :
- Temps de réponse pour les requêtes standard
- Stabilité sous charge
- Utilisation mémoire GPU
- Taux d'erreurs OOM