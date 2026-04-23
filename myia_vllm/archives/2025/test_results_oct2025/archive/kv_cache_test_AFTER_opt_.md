# 🚀 TEST KV CACHE ACCELERATION - QWEN3-32B-AWQ

**Date d'exécution** : 2025-10-16 17:50:57  
**Modèle testé** : Qwen/Qwen3-32B-AWQ  
**Tours de conversation** : 5

---

## 📊 RÉSULTATS GLOBAUX

### 1️⃣ Conversation Continue (KV Cache actif)

| Métrique | Valeur |
|----------|--------|
| **Premier message (CACHE MISS)** | 4375.81ms |
| **Messages suivants (CACHE HIT)** | 3198.87ms |
| **🚀 Accélération** | **x1.37** |
| **Gain de performance** | 26.9% |

### 2️⃣ Messages Indépendants (Pas de cache)

| Métrique | Valeur |
|----------|--------|
| **TTFT moyen** | 2846.84ms |

### 3️⃣ Prefill Cache (Contexte préchargé)

| Métrique | Valeur |
|----------|--------|
| **Premier message (CACHE MISS)** | 3797.72ms |
| **Messages suivants (CACHE HIT)** | 3409.84ms |
| **🚀 Accélération** | **x1.11** |
| **Gain de performance** | 10.2% |

---

## 📈 DÉTAILS DES MESURES

### Conversation Continue

| Tour | Type | TTFT (ms) | Statut |
|------|------|-----------|--------|| 1 | MISS | 4375.81 | ✅ |
| 2 | HIT | 3771.03 | ✅ |
| 3 | HIT | 2898.16 | ✅ |
| 4 | HIT | 3354.94 | ✅ |
| 5 | HIT | 2771.36 | ✅ |

### Messages Indépendants

| Message | TTFT (ms) | Statut |
|---------|-----------|--------|| 1 | 2771.05 | ✅ |
| 2 | 1896.45 | ✅ |
| 3 | 2911.46 | ✅ |
| 4 | 2905.94 | ✅ |
| 5 | 3749.31 | ✅ |

### Prefill Cache

| Tour | Type | TTFT (ms) | Statut |
|------|------|-----------|--------|| 1 | MISS | 3797.72 | ✅ |
| 2 | HIT | 3173.6 | ✅ |
| 3 | HIT | 3646.08 | ✅ |

---

## 🎯 CONCLUSIONS

### Efficacité du KV Cache
❌ **FAIBLE** - Le KV Cache offre seulement une accélération **x1.37**.

### Recommandations
- ⚠️ Vérifier la configuration du KV Cache (--enable-prefix-caching)
- ⚠️ Augmenter --gpu-memory-utilization si possible
- ⚠️ Vérifier que le cache n'est pas éjecté trop rapidement

### Métriques Clés

- **Premier TTFT (cold)** : 4375.81ms
- **TTFT optimisé (warm)** : 3198.87ms
- **Gain absolu** : 1176.94ms
- **Accélération** : x1.37

---

**Fin du rapport**
