# Grid Search Comparative Report

**Date de Génération** : 2025-10-18 19:03:54
**Nombre de Configurations Testées** : 12
**Configurations Réussies** : 0

---

## Baseline de Référence

| Métrique | Valeur |
|----------|--------|
| TTFT CACHE MISS | 1828 ms |
| TTFT CACHE HIT | 1607 ms |
| Cache Acceleration | x1.14 |
| Gain Percentage | 12.1% |

---

## Tableau Récapitulatif (Trié par Accélération Cache)

| Rank | Config Name | GPU Mem | Prefix | Chunked | Max Seqs | TTFT MISS | TTFT HIT | Accel | Gain % | vs Baseline MISS | vs Baseline HIT |
|------|-------------|---------|--------|---------|----------|-----------|----------|-------|--------|------------------|-----------------|

---

## Analyse des Résultats

### ⚠️  Échecs et Anomalies

- **baseline_reference** : not_executed
  - Erreurs : Échec déploiement Docker : Échec de docker compose down : yaml: line 2: did not find expected key
- **prefix_only_095** : not_executed
  - Erreurs : Échec déploiement Docker : Échec de docker compose down : yaml: line 2: did not find expected key
- **prefix_only_092** : not_executed
  - Erreurs : Échec déploiement Docker : Échec de docker compose down : yaml: line 2: did not find expected key
- **prefix_only_090** : not_executed
  - Erreurs : Échec déploiement Docker : Échec de docker compose down : yaml: line 2: did not find expected key
- **chunked_only_default** : not_executed
  - Erreurs : Échec déploiement Docker : Échec de docker compose down : yaml: line 2: did not find expected key
- **chunked_only_high_tokens** : not_executed
  - Erreurs : Échec déploiement Docker : Échec de docker compose down : yaml: line 2: did not find expected key
- **combined_optimized_high_tokens** : not_executed
  - Erreurs : Échec déploiement Docker : Échec de docker compose down : yaml: line 2: did not find expected key
- **combined_conservative** : not_executed
  - Erreurs : Échec déploiement Docker : Échec de docker compose down : yaml: line 2: did not find expected key
- **prefix_high_seqs** : not_executed
  - Erreurs : Échec déploiement Docker : Échec de docker compose down : yaml: line 2: did not find expected key
- **chunked_low_memory** : not_executed
  - Erreurs : Échec déploiement Docker : Échec de docker compose down : yaml: line 2: did not find expected key
- **combined_balanced** : not_executed
  - Erreurs : Échec déploiement Docker : Échec de docker compose down : yaml: line 2: did not find expected key
- **prefix_only_high_memory_high_seqs** : not_executed
  - Erreurs : Échec déploiement Docker : Échec de docker compose down : yaml: line 2: did not find expected key

### 💡 Recommandation Finale

**Aucune configuration optimale identifiée** - Tous les tests ont échoué.

---

**Fin du Rapport**