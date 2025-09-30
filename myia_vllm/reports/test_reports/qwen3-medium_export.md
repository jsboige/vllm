# Rapport de benchmark - QWEN3-MEDIUM

## Informations générales

- **Modèle**: QWEN3-MEDIUM
- **Date du benchmark**: 2025-05-27T17:14:51.143838
- **Version**: 0.1.0
- **Environnement**: Test Environment

## Résumé des performances

### Métriques LLM

| Métrique | Valeur |
|----------|--------|
| tokens_per_second | 150.75 |
| latency_p50 | 0.8 |
| latency_p90 | 1.2 |
| latency_p99 | 1.5 |
| throughput | 1000 |
| accuracy | 0.95 |
| recommended_batch_size | 16 |
| recommended_context_length | 8192 |
| overall_performance_score | 8.5 |

### Métriques de ressources

| Métrique | Valeur |
|----------|--------|
| gpu_utilization_avg | 75.5 |
| gpu_memory_used_avg | 8192 |
| cpu_utilization_avg | 45.0 |
| recommended_memory | 16384 |

## Détails des tests

### Résultats par API

#### API completions

| Métrique | Valeur |
|----------|--------|
| Nombre de tests | 2 |
| Temps d'exécution moyen | 11.25 s |
| Tokens générés moyen | 1100.0 |

| Tokens par seconde moyen | 97.78 |

#### API chat

| Métrique | Valeur |
|----------|--------|
| Nombre de tests | 2 |
| Temps d'exécution moyen | 16.95 s |
| Tokens générés moyen | 1650.0 |

| Tokens par seconde moyen | 97.35 |


### Impact de la longueur de contexte

| Longueur de contexte | Temps d'exécution moyen | Tokens générés moyen | Tokens par seconde moyen |
|----------------------|-------------------------|----------------------|--------------------------|
| 4096 | 21.25 s | 2100.0 | 98.82 |
| 8192 | 31.75 s | 3100.0 | 97.64 |

## Visualisations

### Temps d'exécution

![Temps d'exécution](resources/qwen3-medium_execution_time.png)

### Débit (tokens par seconde)

![Débit](resources/qwen3-medium_throughput.png)

### Impact de la longueur de contexte

![Impact de la longueur de contexte](resources/qwen3-medium_context_impact.png)

## Recommandations

- **Taille de batch recommandée**: 16

- **Longueur de contexte recommandée**: 8192

- **Mémoire recommandée**: 16384 MB

## Conclusion

Ce rapport présente les résultats des benchmarks pour le modèle QWEN3-MEDIUM. Les tests ont été effectués pour évaluer les performances du modèle dans différentes configurations et avec différentes longueurs de contexte.

Le score global de performance est de 8.5/10.

---

*Rapport généré automatiquement par qwen3_benchmark*