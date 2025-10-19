# Design du Grid Search pour Optimisation Agentique Multi-Tours
## Mission 11 - Phase 4

**Date de Création** : 2025-10-17  
**Auteur** : Roo Architect (Mode)  
**Statut** : ✅ Design Validé - Prêt pour Implémentation

---

## 📋 Table des Matières

1. [Contexte et Objectifs](#contexte-et-objectifs)
2. [Analyse des Résultats Précédents](#analyse-des-résultats-précédents)
3. [Méthodologie de Sélection](#méthodologie-de-sélection)
4. [Espace de Paramètres](#espace-de-paramètres)
5. [Les 12 Configurations Stratégiques](#les-12-configurations-stratégiques)
6. [Ordre de Test et Priorités](#ordre-de-test-et-priorités)
7. [Métriques de Succès](#métriques-de-succès)
8. [Hypothèses et Prédictions](#hypothèses-et-prédictions)
9. [Procédure d'Exécution](#procédure-dexécution)

---

## 🎯 Contexte et Objectifs

### Problème Initial

Les tests précédents ont révélé une **dégradation catastrophique des performances** lors de l'activation simultanée de `--enable-prefix-caching` et `--enable-chunked-prefill` :

- **Baseline** : TTFT MISS = 1828ms, TTFT HIT = 1607ms
- **Optimisations combinées** : TTFT MISS = 4376ms (+139%), TTFT HIT = 3199ms (+99%)

Bien que l'accélération du cache ait augmenté de +20%, la latence absolue est devenue **inacceptable pour une utilisation en production**.

### Objectifs du Grid Search

1. **Isoler les impacts** : Tester `prefix-caching` et `chunked-prefill` **indépendamment**
2. **Optimiser pour agents multi-tours** : Privilégier les configurations qui minimisent TTFT HIT (tours N+1)
3. **Trouver le sweet spot** : Configuration avec TTFT < baseline +20% et accélération cache > +50%
4. **Valider la robustesse** : Tester différentes valeurs de `gpu_memory_utilization`

### Décision Stratégique : Configuration GPU Actuelle

**Contexte Matériel Découvert** :
- 3x RTX 4090 détectés (au lieu de 2 attendus)
- GPU 0 et 1 : **PCIe 8x** (50% de bande passante théorique vs 16x)
- GPU 2 : PCIe 4x (25% de bande passante)
- Configuration actuelle : `CUDA_VISIBLE_DEVICES_MEDIUM=0,1`

**Décision** : Procéder avec la configuration matérielle actuelle (PCIe 8x). Les recherches web (Reddit, benchmarks DatabaseMart) confirment que PCIe 8x **ne devrait PAS être un goulot d'étranglement** pour vLLM avec 2 GPUs. Approche pragmatique : **optimiser le logiciel d'abord**, investiguer le matériel après si les résultats sont insatisfaisants.

---

## 📊 Analyse des Résultats Précédents

### Configuration Baseline (Référence)

```yaml
# myia_vllm/configs/docker/profiles/medium.yml
command:
  - "--model"
  - "Qwen/Qwen3-32B-AWQ"
  - "--tensor-parallel-size"
  - "2"
  - "--gpu-memory-utilization"
  - "0.95"
  # Prefix caching: DISABLED (par défaut)
  # Chunked prefill: DISABLED (ou défaut V1)
```

**Métriques Baseline** :
- TTFT MISS (premier message) : 1828ms
- TTFT HIT (messages suivants) : 1607ms
- Accélération cache : x1.14 (+12.1%)
- Gain relatif : 12.1%

### Configuration "Optimisée" (Échec Précédent)

```yaml
command:
  - "--model"
  - "Qwen/Qwen3-32B-AWQ"
  - "--tensor-parallel-size"
  - "2"
  - "--gpu-memory-utilization"
  - "0.95"
  - "--enable-prefix-caching"
  - "--enable-chunked-prefill"
  - "--max-num-seqs"
  - "32"
  - "--max-num-batched-tokens"
  - "2048"
```

**Métriques "Optimisées"** :
- TTFT MISS : 4376ms (+139% vs baseline)
- TTFT HIT : 3199ms (+99% vs baseline)
- Accélération cache : x1.37 (+20% vs baseline)
- Gain relatif : 26.9% (+122% vs baseline)

**Analyse** : L'accélération relative du cache a bien augmenté, mais la latence absolue est **2-3x pire** que le baseline. Cette configuration est **inutilisable en production**.

---

## 🔍 Méthodologie de Sélection

### Principe de Design

Au lieu de tester exhaustivement toutes les combinaisons (3×2×2×4×4 = **192 configurations**), nous avons sélectionné **12 configurations stratégiques** basées sur :

1. **Recherches Sémantiques SDDD** :
   - Documentation vLLM sur Optimization & Tuning
   - Automatic Prefix Caching (APC)
   - Chunked Prefill et ses paramètres

2. **Recherches Web SearXNG** :
   - Best practices vLLM pour agents multi-tours
   - Configuration Tensor Parallel pour RTX 4090
   - Benchmarks DatabaseMart et retours Reddit

3. **Hypothèses Scientifiques** :
   - Prefix caching = optimisation idéale pour agents (réutilisation system prompt + historique)
   - Chunked prefill = potentiellement contre-productif (augmente TTFT)
   - Interaction négative entre les deux mécanismes

### Catégories de Tests

1. **Baseline + Prefix Caching Isolé** (4 configs) : Hypothèse principale
2. **Chunked Prefill Isolé** (2 configs) : Compréhension de l'impact négatif
3. **Combinaisons Optimisées** (3 configs) : Si jamais les deux peuvent coexister
4. **Variations Expérimentales** (3 configs) : Exploration des paramètres annexes

---

## 🎛️ Espace de Paramètres

### 1. `gpu_memory_utilization`

**Valeurs testées** : [0.90, 0.92, 0.95]

**Rationale** :
- **0.95** : Valeur actuelle (baseline), maximise la mémoire disponible pour le cache
- **0.92** : Valeur intermédiaire, équilibre cache et stabilité
- **0.90** : Valeur minimale recommandée, réduit les risques d'OOM

**Impact attendu** :
- Réduire la mémoire GPU peut améliorer la **stabilité** en évitant les swaps de cache
- Peut légèrement réduire la taille du cache de préfixes, impactant l'accélération

### 2. `enable_prefix_caching`

**Valeurs testées** : [false, true]

**Rationale** :
- **false** : Comportement par défaut vLLM (pas de réutilisation de cache)
- **true** : Réutilise le KV cache pour les préfixes communs (system prompt, historique)

**Impact attendu** :
- **true** devrait drastiquement réduire TTFT HIT (tours N+1) pour les tâches conversationnelles
- Impact minimal sur TTFT MISS (premier tour)
- Consommation mémoire GPU légèrement accrue

### 3. `enable_chunked_prefill`

**Valeurs testées** : [false, true]

**Rationale** :
- **false** : Traite le prefill en une seule passe (mode traditionnel)
- **true** : Découpe le prefill en chunks pour batching avec decode

**Impact attendu** :
- **true** améliore le throughput (tokens/sec) mais **augmente TTFT**
- Effet probablement **contre-productif** pour agents multi-tours (latence critique)

### 4. `max_num_seqs`

**Valeurs testées** : [null, 32, 64, 128]

**Rationale** :
- **null** : Valeur par défaut vLLM (auto-calculée selon modèle et mémoire)
- **32-128** : Nombre de séquences traitées en parallèle (impact batching et mémoire)

**Impact attendu** :
- Valeurs plus élevées augmentent le throughput mais peuvent impacter TTFT si saturation
- Interaction complexe avec `prefix_caching` (plus de séquences = plus de partage de cache)

### 5. `max_num_batched_tokens`

**Valeurs testées** : [null, 2048, 4096, 8192]

**Rationale** :
- **null** : Valeur par défaut vLLM
- **2048-8192** : Contrôle la taille des chunks pour chunked prefill

**Impact attendu** :
- **Documentation officielle** : Valeurs plus élevées **réduisent TTFT** mais diminuent throughput
- Paramètre critique si chunked prefill est activé

---

## 🧪 Les 12 Configurations Stratégiques

### Configuration 1 : `baseline_reference` (Priorité 1)

**Description** : Baseline actuelle pour référence (déjà testée)

```yaml
gpu_memory: 0.95
prefix_caching: false
chunked_prefill: false
max_num_seqs: null
max_num_batched_tokens: null
```

**Hypothèse** : Configuration de référence (TTFT MISS: 1828ms, HIT: 1607ms)

**Métriques attendues** : Confirmer les valeurs baseline

---

### Configuration 2 : `prefix_only_095` (Priorité 2) ⭐

**Description** : Prefix caching seul avec GPU memory 0.95

```yaml
gpu_memory: 0.95
prefix_caching: true
chunked_prefill: false
max_num_seqs: null
max_num_batched_tokens: null
```

**Hypothèse** : **Optimisation idéale pour multi-tours** - devrait améliorer cache HIT sans impacter MISS

**Métriques attendues** :
- TTFT MISS : ~1800-2000ms (< +10% vs baseline)
- TTFT HIT : ~800-1000ms (-40% à -50% vs baseline) ✅
- Accélération cache : x1.8 à x2.5 (+80% à +150%)

**Pourquoi c'est probablement la configuration gagnante** :
- Conçu explicitement pour tâches conversationnelles
- Réutilise system prompt + historique à chaque tour
- Pas d'impact négatif du chunked prefill

---

### Configuration 3 : `prefix_only_092` (Priorité 3)

**Description** : Prefix caching seul avec GPU memory réduite

```yaml
gpu_memory: 0.92
prefix_caching: true
chunked_prefill: false
max_num_seqs: null
max_num_batched_tokens: null
```

**Hypothèse** : Réduire mémoire GPU peut améliorer stabilité du cache

**Métriques attendues** : Similaires à config 2, légèrement moins de capacité cache

---

### Configuration 4 : `prefix_only_090` (Priorité 4)

**Description** : Prefix caching seul avec GPU memory 0.90

```yaml
gpu_memory: 0.90
prefix_caching: true
chunked_prefill: false
max_num_seqs: null
max_num_batched_tokens: null
```

**Hypothèse** : Mémoire minimale recommandée avec prefix caching

**Métriques attendues** : Cache plus petit mais plus stable (moins d'OOM)

---

### Configuration 5 : `chunked_only_default` (Priorité 5)

**Description** : Chunked prefill seul avec paramètres par défaut

```yaml
gpu_memory: 0.95
prefix_caching: false
chunked_prefill: true
max_num_seqs: null
max_num_batched_tokens: null
```

**Hypothèse** : Test chunked prefill isolé - devrait augmenter TTFT mais améliorer throughput

**Métriques attendues** :
- TTFT MISS : ~2500-3000ms (+30-60% vs baseline) ⚠️
- TTFT HIT : ~2200-2700ms (+35-70% vs baseline)
- Throughput : +20-30% vs baseline ✅

**Objectif** : Quantifier l'impact négatif de chunked prefill sur TTFT

---

### Configuration 6 : `chunked_only_high_tokens` (Priorité 6)

**Description** : Chunked prefill avec `max_num_batched_tokens` élevé

```yaml
gpu_memory: 0.95
prefix_caching: false
chunked_prefill: true
max_num_seqs: null
max_num_batched_tokens: 8192
```

**Hypothèse** : Augmenter tokens par batch devrait réduire TTFT selon doc officielle

**Métriques attendues** : TTFT meilleur que config 5 mais probablement toujours > baseline

---

### Configuration 7 : `combined_optimized_high_tokens` (Priorité 7)

**Description** : Prefix + Chunked avec `max_num_batched_tokens` élevé

```yaml
gpu_memory: 0.92
prefix_caching: true
chunked_prefill: true
max_num_seqs: 64
max_num_batched_tokens: 8192
```

**Hypothèse** : Combinaison optimisée - tokens élevés pour réduire impact chunked sur TTFT

**Métriques attendues** : Meilleur que l'échec précédent (+139%) mais probablement pas mieux que prefix seul

---

### Configuration 8 : `combined_conservative` (Priorité 8)

**Description** : Prefix + Chunked avec paramètres conservateurs

```yaml
gpu_memory: 0.90
prefix_caching: true
chunked_prefill: true
max_num_seqs: 32
max_num_batched_tokens: 4096
```

**Hypothèse** : Approche conservatrice pour éviter over-subscription mémoire

**Métriques attendues** : Plus stable que config 7 mais latence toujours élevée

---

### Configuration 9 : `prefix_high_seqs` (Priorité 9)

**Description** : Prefix caching avec `max_num_seqs` élevé

```yaml
gpu_memory: 0.92
prefix_caching: true
chunked_prefill: false
max_num_seqs: 128
max_num_batched_tokens: null
```

**Hypothèse** : Augmenter parallélisme sans chunked prefill pour améliorer throughput

**Métriques attendues** : TTFT similaire à configs 2-4, throughput légèrement meilleur

---

### Configuration 10 : `chunked_low_memory` (Priorité 10)

**Description** : Chunked prefill avec mémoire GPU réduite

```yaml
gpu_memory: 0.90
prefix_caching: false
chunked_prefill: true
max_num_seqs: 64
max_num_batched_tokens: 4096
```

**Hypothèse** : Tester si mémoire réduite impacte chunked prefill

**Métriques attendues** : TTFT élevé comme config 5, stabilité accrue

---

### Configuration 11 : `combined_balanced` (Priorité 11)

**Description** : Prefix + Chunked avec équilibre tokens/seqs

```yaml
gpu_memory: 0.95
prefix_caching: true
chunked_prefill: true
max_num_seqs: 64
max_num_batched_tokens: 4096
```

**Hypothèse** : Configuration équilibrée entre les deux optimisations

**Métriques attendues** : Compromis entre configs 7 et 8

---

### Configuration 12 : `prefix_only_high_memory_high_seqs` (Priorité 12) ⭐

**Description** : Prefix caching agressif avec mémoire et parallélisme élevés

```yaml
gpu_memory: 0.95
prefix_caching: true
chunked_prefill: false
max_num_seqs: 128
max_num_batched_tokens: null
```

**Hypothèse** : Maximiser les bénéfices du prefix caching seul pour agents multi-tours

**Métriques attendues** : Meilleur throughput que config 2, TTFT similaire

**Configuration alternative gagnante potentielle** : Si throughput est critique

---

## 📐 Ordre de Test et Priorités

### Phase 1 : Baseline + Prefix Caching Isolé (Priorité 1-4)

**Objectif** : Valider l'hypothèse principale (prefix caching = optimisation idéale)

1. **baseline_reference** (config 1) : Confirmer métriques de référence
2. **prefix_only_095** (config 2) : ⭐ Test de l'hypothèse principale
3. **prefix_only_092** (config 3) : Variation mémoire intermédiaire
4. **prefix_only_090** (config 4) : Variation mémoire conservatrice

**Décision intermédiaire** : Si config 2 ou 3 atteint les objectifs (TTFT < +20%, accélération > +50%), on peut **arrêter le grid search** et passer directement à la documentation.

### Phase 2 : Chunked Prefill Isolé (Priorité 5-6)

**Objectif** : Quantifier l'impact négatif de chunked prefill

5. **chunked_only_default** (config 5) : Test avec paramètres par défaut
6. **chunked_only_high_tokens** (config 6) : Test avec paramètre optimisé

**Décision intermédiaire** : Si TTFT > +50% vs baseline, confirmer que chunked prefill est contre-productif pour notre cas d'usage.

### Phase 3 : Combinaisons et Variations (Priorité 7-12)

**Objectif** : Exploration fine si aucune config précédente n'est satisfaisante

7. **combined_optimized_high_tokens** (config 7)
8. **combined_conservative** (config 8)
9. **prefix_high_seqs** (config 9)
10. **chunked_low_memory** (config 10)
11. **combined_balanced** (config 11)
12. **prefix_only_high_memory_high_seqs** (config 12) : ⭐ Alternative

---

## 🎯 Métriques de Succès

Pour chaque configuration, les métriques suivantes seront collectées :

### Métriques Primaires (Performance)

1. **TTFT MISS (ms)** : Time To First Token pour le premier message (cache miss)
   - **Objectif** : < baseline +20% (< 2194ms)
   - **Idéal** : < baseline +10% (< 2011ms)

2. **TTFT HIT (ms)** : Time To First Token pour les messages suivants (cache hit)
   - **Objectif** : < baseline -30% (< 1125ms)
   - **Idéal** : < baseline -50% (< 804ms)

3. **Accélération Cache (ratio)** : TTFT MISS / TTFT HIT
   - **Objectif** : > x1.5 (+50% vs baseline x1.14)
   - **Idéal** : > x2.0 (+75% vs baseline)

4. **Gain Relatif (%)** : (TTFT MISS - TTFT HIT) / TTFT MISS
   - **Objectif** : > 30% (vs baseline 12.1%)
   - **Idéal** : > 50%

5. **Throughput (tokens/sec)** : Pour contexte (non critique pour agents)

### Métriques Secondaires (Stabilité)

6. **Temps démarrage container (sec)** : Délai avant "healthy"
7. **Erreurs OOM** : Nombre d'erreurs Out Of Memory
8. **Crashes** : Nombre de crashes du container pendant les tests
9. **Timeouts** : Nombre de timeouts de requêtes

### Tableau de Synthèse

```markdown
| Config | GPU Mem | Prefix | Chunked | Seqs | Tokens | TTFT MISS | TTFT HIT | Accel | Gain % | Throughput | OOM | Crashes |
|--------|---------|--------|---------|------|--------|-----------|----------|-------|--------|------------|-----|---------|
| baseline | 0.95 | ❌ | ❌ | - | - | 1828ms | 1607ms | x1.14 | 12.1% | [data] | 0 | 0 |
| prefix_only_095 | 0.95 | ✅ | ❌ | - | - | [data] | [data] | [data] | [data] | [data] | [data] | [data] |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
```

---

## 🔮 Hypothèses et Prédictions

### Hypothèse Principale (Haute Confiance)

**`prefix_only_095`** (config 2) ou **`prefix_only_092`** (config 3) sera la **configuration optimale** pour les tâches agentiques multi-tours.

**Justification** :
- Documentation vLLM : Prefix caching conçu explicitement pour conversations
- Pas d'impact négatif du chunked prefill (qui augmente TTFT)
- Réutilisation efficace du system prompt et de l'historique

**Prédictions** :
- TTFT MISS : 1800-2000ms (< +10% vs baseline) ✅
- TTFT HIT : 800-1000ms (-40% à -50% vs baseline) ✅✅✅
- Accélération cache : x1.8 à x2.5 (+80% à +150%) ✅✅
- Gain relatif : 45-55% ✅✅

### Hypothèse Secondaire (Moyenne Confiance)

**Chunked prefill est contre-productif** pour les agents multi-tours (latence critique).

**Justification** :
- Documentation vLLM : Chunked prefill augmente TTFT (compromis throughput vs latence)
- Résultats précédents : +99-139% de latence avec chunked prefill activé
- Cas d'usage agentique : Latence > Throughput

**Prédictions** :
- Config 5 (chunked seul) : TTFT MISS +30-60% vs baseline ⚠️
- Config 6 (chunked + tokens élevés) : TTFT légèrement meilleur mais toujours > baseline
- Configs 7-8 (combinées) : Impossibles à optimiser pour atteindre TTFT < +20%

### Hypothèse Tertiaire (Faible Confiance)

**Réduire `gpu_memory_utilization` peut améliorer la stabilité** sans impacter significativement les performances.

**Justification** :
- Évite les swaps de cache en cas de pics de demande
- Peut réduire légèrement la taille du cache mais améliorer la cohérence

**Prédictions** :
- Configs 3-4 (GPU 0.92-0.90) : TTFT similaire à config 2, moins d'OOM

### Configuration Alternative (Si Throughput Critique)

Si le throughput (tokens/sec) s'avère être un goulot d'étranglement :

**`prefix_only_high_memory_high_seqs`** (config 12) pourrait être préférée :
- TTFT similaire aux configs 2-3
- Throughput supérieur grâce à `max_num_seqs=128`

---

## 🚀 Procédure d'Exécution

### Pré-requis

1. **Environnement** : Docker Compose configuré avec `medium.yml`
2. **Scripts de test** :
   - `myia_vllm/scripts/test_kv_cache_acceleration.ps1` : Tests TTFT et cache
   - `myia_vllm/scripts/test_performance_ttft.py` : Tests TTFT détaillés
   - `myia_vllm/scripts/test_performance_throughput.py` : Tests throughput

3. **Configuration actuelle** : Backup de `medium.yml` avant modifications

### Workflow Automatisé

Le script `grid_search_optimization.ps1` (Phase 5) gérera le workflow complet :

```powershell
# Pour chaque configuration dans le fichier JSON :
ForEach ($config in $configs) {
    # 1. Modifier medium.yml avec les paramètres de la config
    Update-MediumConfig -Config $config

    # 2. Backup de la config actuelle
    Backup-ConfigFile -Name $config.name

    # 3. Redéployer le container
    docker compose -f myia_vllm/configs/docker/profiles/medium.yml down
    docker compose -f myia_vllm/configs/docker/profiles/medium.yml up -d

    # 4. Attendre healthy (timeout 10 min)
    Wait-ContainerHealthy -Timeout 600

    # 5. Exécuter les tests
    & myia_vllm/scripts/test_kv_cache_acceleration.ps1
    python myia_vllm/scripts/test_performance_ttft.py
    python myia_vllm/scripts/test_performance_throughput.py

    # 6. Sauvegarder les résultats
    Save-TestResults -Config $config.name -Output "results_$($config.name).json"

    # 7. Logs et progression
    Write-Progress -Config $config.name -Status "Completed"
}
```

### Gestion des Erreurs

- **Timeout déploiement** : Skip la config après 10 min, passer à la suivante
- **Erreurs OOM** : Logger l'erreur, ajouter flag `oom_error=true` dans les résultats
- **Crashes** : Redéployer une fois, si échec persistant, skip la config
- **Interruption** : Sauvegarder état actuel, permettre reprise depuis la dernière config testée

### Restauration Baseline

En cas d'interruption ou de problème :

```powershell
# Restaurer la configuration baseline
Restore-ConfigFile -Name "baseline_reference"
docker compose -f myia_vllm/configs/docker/profiles/medium.yml down
docker compose -f myia_vllm/configs/docker/profiles/medium.yml up -d
```

### Durée Estimée

- **Déploiement + tests** : ~15-20 min par configuration
- **12 configurations** : ~3-4 heures au total
- **Phases 1-2** (configs 1-6) : ~1.5-2 heures (décision intermédiaire possible)

### Logs et Traçabilité

Tous les logs seront sauvegardés dans :
```
myia_vllm/logs/grid_search_20251017/
├── config_baseline_reference.log
├── config_prefix_only_095.log
├── ...
├── results_baseline_reference.json
├── results_prefix_only_095.json
├── ...
└── grid_search_summary.json
```

---

## 📚 Références

### Recherches Sémantiques SDDD (Phase 1)

1. **Optimisations vLLM existantes** :
   - `KV_CACHE_OPTIMIZATION_20251016.md` : Documentation des tests précédents
   - `optimization_comparison_20251016.md` : Métriques baseline vs optimisé

2. **Architecture actuelle** :
   - `MEDIUM_SERVICE_PARAMETERS.md` : Paramètres du service medium
   - `medium.yml` : Configuration Docker Compose actuelle

3. **Tests de performance** :
   - `test_kv_cache_acceleration.ps1` : Script de test TTFT et cache
   - `run_all_tests.ps1` : Suite de tests complète

### Recherches Web SearXNG (Phase 2)

1. **Best Practices vLLM** :
   - [vLLM Documentation - Optimization & Tuning](https://docs.vllm.ai/en/stable/usage/optimization.html)
   - [Automatic Prefix Caching (APC)](https://docs.vllm.ai/en/stable/usage/automatic_prefix_caching.html)

2. **Configuration Multi-GPU** :
   - [Reddit - Tensor Parallel PCIe Bandwidth](https://www.reddit.com/r/LocalLLaMA/comments/1m8vqnz/tensor_parallel_pcie_bandwidth_requirement/)
   - [DatabaseMart - vLLM 2×RTX 4090 Benchmark](https://www.databasemart.com/blog/vllm-gpu-benchmark-dual-rtx4090)
   - [vLLM Distributed Inference Optimization Guide](https://www.databasemart.com/blog/vllm-distributed-inference-optimization-guide)

3. **Configuration GPU** :
   - [vLLM Discussion #691 - Specify GPU](https://github.com/vllm-project/vllm/discussions/691)
   - [Stack Overflow - Multi-GPU vLLM](https://stackoverflow.com/questions/78990683/how-can-run-vllm-model-on-a-multi-gpu-server)

---

## ✅ Validation du Design

Ce design a été validé selon les critères SDDD :

1. ✅ **Grounding sémantique initial** : 3 recherches effectuées (optimisations, architecture, tests)
2. ✅ **Recherche web SearXNG** : Best practices et configuration multi-GPU validées
3. ✅ **Configuration GPU vérifiée** : PCIe 8x documenté, décision de procéder confirmée
4. ✅ **Sélection intelligente de configurations** : 12 configs stratégiques (vs 192 exhaustives)
5. ✅ **Hypothèses scientifiques** : Prédictions basées sur documentation officielle et retours terrain
6. ✅ **Métriques de succès** : Objectifs clairs (TTFT < +20%, accélération > +50%)

**Prochaine Étape** : Implémentation du script `grid_search_optimization.ps1` (Phase 5 - Délégation CODE)

---

**Statut du Document** : ✅ Prêt pour Implémentation  

---

## ⚠️ Correction Post-Design : Contexte Agentique Max

**Date** : 2025-10-19  
**Type** : Correction Critique  
**Statut** : ✅ Corrigé

### Problème Détecté

Après finalisation du design, une erreur majeure a été identifiée dans les configurations du grid search : **5 configurations sur 12 avaient des valeurs `max_num_batched_tokens` trop basses** (4096 ou 8192) pour supporter les tâches agentiques multi-tours nécessitant un contexte de 100k+ tokens.

### Analyse de l'Erreur

**Configurations Affectées** :
- Config 6 (`chunked_only_high_tokens`) : `max_num_batched_tokens: 8192`
- Config 7 (`combined_optimized_high_tokens`) : `max_num_batched_tokens: 8192`
- Config 8 (`combined_conservative`) : `max_num_batched_tokens: 4096`
- Config 10 (`chunked_low_memory`) : `max_num_batched_tokens: 4096`
- Config 11 (`combined_balanced`) : `max_num_batched_tokens: 4096`

**Contrainte Baseline** :
- Le modèle supporte `--max-model-len 131072` (131K tokens)
- Les tâches agentiques multi-tours nécessitent un contexte de 100k+ tokens
- Les valeurs hardcodées (4K-8K) empêchaient vLLM de tirer parti du contexte complet

**Cause Racine** :
- Design initial privilégiait l'efficacité mémoire sur la capacité de contexte
- Hypothèse erronée que 4K-8K tokens par batch seraient suffisants
- Méconnaissance du comportement par défaut de vLLM avec `max_num_batched_tokens: null`

### Correction Appliquée

**Backup Créé** :
```
grid_search_configs.json.backup_before_context_fix_20251019_195627
```

**Modifications** :
Toutes les 5 configurations affectées ont été mises à jour :

```json
// AVANT (Config 6 exemple)
{
  "name": "chunked_only_high_tokens",
  "max_num_batched_tokens": 8192,
  "description": "... (8192 tokens par batch)"
}

// APRÈS
{
  "name": "chunked_only_high_tokens",
  "max_num_batched_tokens": null,
  "description": "... (par défaut vLLM - 131K pour contexte agentique)"
}
```

**Paramètres Préservés** :
- ✅ `gpu_memory_utilization` : Inchangé
- ✅ `enable_prefix_caching` : Inchangé
- ✅ `enable_chunked_prefill` : Inchangé
- ✅ `max_num_seqs` : Inchangé

### Justification Technique

**Pourquoi `null` est la bonne valeur** :

1. **Avec `enable_chunked_prefill = false`** :
   - vLLM utilise `max_model_len` comme valeur par défaut (131K tokens)
   - Permet le traitement complet du contexte agentique

2. **Avec `enable_chunked_prefill = true`** :
   - vLLM calcule automatiquement la taille optimale des chunks
   - S'adapte dynamiquement à la mémoire GPU disponible
   - Garantit un équilibre entre latence et throughput

3. **Flexibilité maximale** :
   - Pas de limite artificielle sur le contexte
   - Auto-optimisation selon les ressources disponibles
   - Cohérence avec les capacités réelles du modèle (131K)

### Impact sur les Hypothèses

**Hypothèses Initiales (Maintenant Invalides)** :
- ❌ Config 6 : "8192 tokens par batch devrait réduire TTFT"
  - **Réalité** : Limitait artificiellement le contexte à 8K
- ❌ Config 7-8 : "Paramètres optimisés pour combinaison prefix + chunked"
  - **Réalité** : Limitation à 4K-8K empêchait tests valides sur longs contextes

**Nouvelles Hypothèses (Post-Correction)** :
- ✅ Toutes les configs supportent maintenant le contexte complet (131K)
- ✅ Configs avec `chunked_prefill = true` + `null` tokens permettent auto-optimisation
- ✅ Tests agentiques multi-tours (100k+ tokens) maintenant possibles sur toutes les configs
- ✅ Comparaison équitable entre configurations sans limitation artificielle

### Impact sur les Prédictions

**Configs 6-8, 10-11 (Avant Correction)** :
- ⚠️ Risque d'OOM ou troncature pour conversations longues (>4K-8K tokens)
- ⚠️ Throughput suboptimal (batches trop petits)
- ⚠️ Impossible de tester réellement le contexte agentique max

**Configs 6-8, 10-11 (Après Correction)** :
- ✅ Support complet du contexte 131K
- ✅ Auto-optimisation vLLM pour taille de batch
- ✅ Tests agentiques multi-tours valides
- ✅ Meilleure chance de découvrir la configuration optimale

### Nouvelle Hypothèse Émergente

**Config 6 (`chunked_only_high_tokens`) avec `null` pourrait être meilleure** :
- Documentation vLLM : Chunked prefill avec tokens élevés réduit TTFT
- Avec `null`, vLLM choisit automatiquement la taille optimale de chunks
- **Nouvelle prédiction** : Config 6 pourrait rivaliser avec configs prefix-only (2-4)

### Validation Post-Correction

- ✅ JSON syntax validée (Python parser)
- ✅ Toutes les 12 configs supportent 100k+ tokens
- ✅ Backup créé avec succès
- ✅ File encoding : UTF-8
- ✅ Documentation mise à jour (`grid_search_execution_20251018.md`)

### Leçons Apprises

1. **Toujours vérifier la cohérence avec les capacités réelles du modèle**
   - `--max-model-len 131072` était la baseline critique
   - Hardcoder `max_num_batched_tokens` à 4K-8K était incohérent

2. **Comprendre les valeurs par défaut de vLLM avant de les overrider**
   - `null` n'est pas une valeur "vide" mais une directive d'auto-optimisation
   - vLLM a des heuristiques sophistiquées pour ces paramètres

3. **Valider les configurations avec les use cases réels**
   - Tâches agentiques multi-tours = contexte 100k+ obligatoire
   - Toute limitation artificielle fausse les résultats du grid search

### Recommandation pour l'Exécution

**Procéder avec le grid search corrigé** :
- Les 12 configurations sont maintenant cohérentes avec le contexte agentique
- L'hypothèse principale (prefix_only_095) reste valide
- Les configurations chunked (5-11) ont maintenant une chance équitable
- Résultats attendus plus fiables et exploitables

---

**Timestamp Correction** : 2025-10-19T19:59:00Z  
**Status Post-Correction** : ✅ Prêt pour Production Launch #3 (CONFIGURATIONS VALIDÉES)
**Dernière Mise à Jour** : 2025-10-17T21:48:00Z