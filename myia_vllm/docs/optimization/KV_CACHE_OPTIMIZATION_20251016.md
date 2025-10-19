# Optimisations KV Cache - 16 Octobre 2025

## Changements Appliqués

### 1. Activation Prefix Caching
**Paramètre** : `--enable-prefix-caching`  
**Objectif** : Accélérer les conversations multi-tours en réutilisant les prefixes communs  
**Gain attendu** : x2-3 sur TTFT pour messages suivants dans une conversation  
**Documentation** : Ce paramètre permet de réutiliser les tokens de contexte communs entre plusieurs requêtes, évitant ainsi de recalculer les KV cache pour les parties de prompt identiques.

### 2. Activation Chunked Prefill  
**Paramètre** : `--enable-chunked-prefill`  
**Objectif** : Meilleur pipeline prefill/decode  
**Gain attendu** : Réduction latence, meilleur throughput  
**Documentation** : Le chunked prefill découpe le traitement du prompt en chunks plus petits, permettant un meilleur entrelacement avec les opérations de decode et une latence réduite.

### 3. Correction Syntaxe KV Cache
**Avant** : `--kv_cache_dtype fp8` (underscore)  
**Après** : `--kv-cache-dtype fp8` (tiret)  
**Objectif** : Conformité avec la syntaxe standard vLLM  
**Impact** : Assure que le paramètre est correctement reconnu par vLLM

### 4. Correction Tool Call Parser
**Avant** : `--tool-call-parser hermes`  
**Après** : `--tool-call-parser qwen3`  
**Objectif** : Utiliser le parser natif pour Qwen3  
**Impact** : Meilleure compatibilité et performances avec le modèle Qwen3-32B

### 5. GPU Memory Utilization
**Configuration actuelle** : `--gpu-memory-utilization 0.95` (95%)  
**Statut** : ✅ Déjà optimal  
**Mémoire KV Cache** : ~12.58 GiB par GPU (25.16 GiB total)

---

## Configuration Détaillée

### Fichier Modifié
`myia_vllm/configs/docker/profiles/medium.yml`

### Diff des Changements
```diff
- --kv_cache_dtype fp8
- --tool-call-parser hermes
+ --kv-cache-dtype fp8
+ --enable-prefix-caching
+ --enable-chunked-prefill
+ --tool-call-parser qwen3
```

---

## Métriques Avant Optimisation

### Tests KV Cache (17:27:12 - 16/10/2025)

| Test | Métrique | Valeur |
|------|----------|--------|
| **Conversation Continue** | Premier message (CACHE MISS) | 1828.33ms |
| | Messages suivants (CACHE HIT) | 1606.56ms |
| | 🚀 Accélération | **x1.14** |
| | Gain de performance | 12.1% |
| **Prefill Cache** | Premier message (CACHE MISS) | 1946ms |
| | Messages suivants (CACHE HIT) | 1624.71ms |
| | 🚀 Accélération | **x1.20** |
| | Gain de performance | 16.5% |
| **Messages Indépendants** | TTFT moyen | 1657.11ms |

### Analyse
❌ **Performance FAIBLE** - L'accélération du cache était seulement x1.14, bien en-dessous de l'attendu (x2-3).

**Causes probables** :
- Prefix caching non activé
- Syntaxe KV cache incorrecte (underscore vs tiret)
- Parser non optimal (hermes vs qwen3)

---

## Métriques Cibles Après Optimisation

| Métrique | Avant | Cible | Amélioration Visée |
|----------|-------|-------|-------------------|
| TTFT premier message | 1828ms | <1500ms | -18% |
| TTFT messages suivants | 1606ms | <800ms | -50% |
| Accélération cache conversation | x1.14 | **x2.0+** | +75% |
| Accélération cache prefill | x1.20 | **x2.5+** | +108% |

---

## Procédure de Validation

### Étapes
1. ✅ Backup configuration actuelle
2. ✅ Application des optimisations
3. ⏳ Redéploiement avec monitoring
4. ⏳ Exécution des tests de validation
5. ⏳ Analyse comparative
6. ⏳ Rapport final

### Tests à Exécuter
- `test_kv_cache_acceleration.ps1` - Tests KV cache complets
- `test_performance_ttft.py` - TTFT (5 essais)
- `test_performance_throughput.py` - Throughput
- `test_performance_concurrent.py` - Charge concurrente

---

## Notes Techniques

### Prefix Caching
Le prefix caching est particulièrement efficace pour :
- Conversations multi-tours avec contexte commun
- Prompts système répétés
- Instructions de base identiques

### Chunked Prefill
Le chunked prefill améliore :
- La latence perçue (premier token arrive plus vite)
- Le throughput global
- La gestion de la mémoire

### Risques
- **Mémoire** : Prefix caching nécessite plus de mémoire KV cache
- **Compatibilité** : Vérifier logs pour confirmer activation
- **Stabilité** : Monitorer le service après déploiement

---

## Références

- [vLLM Prefix Caching Documentation](https://docs.vllm.ai/en/latest/performance/caching.html)
- [vLLM Chunked Prefill](https://docs.vllm.ai/en/latest/performance/chunked_prefill.html)
- Configuration backup : `medium.yml.backup_before_optimization`
- Tests backup : `kv_cache_test_BEFORE_optimization.md`

---

**Statut** : 🚧 En cours de validation  
**Auteur** : Roo Code  
**Date** : 16 octobre 2025