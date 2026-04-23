# 🚀 TEST KV CACHE ACCELERATION - QWEN3-32B-AWQ

**Date d'exécution** : 2025-10-22 22:14:55  
**Modèle testé** : Qwen/Qwen3-32B-AWQ  
**Tours de conversation** : 5

---

## 📊 RÉSULTATS GLOBAUX

### 1️⃣ Conversation Continue (KV Cache actif)

| Métrique | Valeur |
|----------|--------|
| **Premier message (CACHE MISS)** | 2491.21ms |
| **Messages suivants (CACHE HIT)** | 2278.88ms |
| **🚀 Accélération** | **x1.09** |
| **Gain de performance** | 8.5% |

### 2️⃣ Messages Indépendants (Pas de cache)

| Métrique | Valeur |
|----------|--------|
| **TTFT moyen** | 1930.68ms |

### 3️⃣ Prefill Cache (Contexte préchargé)

| Métrique | Valeur |
|----------|--------|
| **Premier message (CACHE MISS)** | 1489.97ms |
| **Messages suivants (CACHE HIT)** | 2379.35ms |
| **🚀 Accélération** | **x0.63** |
| **Gain de performance** | -59.7% |

---

## 📈 DÉTAILS DES MESURES

### Conversation Continue

| Tour | Type | TTFT (ms) | Statut |
|------|------|-----------|--------|| 1 | MISS | 2491.21 | ✅ |
| 2 | HIT | 2583.3 | ✅ |
| 3 | HIT | 1867.6 | ✅ |
| 4 | HIT | 1968.94 | ✅ |
| 5 | HIT | 2695.68 | ✅ |

### Messages Indépendants

| Message | TTFT (ms) | Statut |
|---------|-----------|--------|| 1 | 2121.1 | ✅ |
| 2 | 1900.45 | ✅ |
| 3 | 2327.87 | ✅ |
| 4 | 1393.27 | ✅ |
| 5 | 1910.73 | ✅ |

### Prefill Cache

| Tour | Type | TTFT (ms) | Statut |
|------|------|-----------|--------|| 1 | MISS | 1489.97 | ✅ |
| 2 | HIT | 2704.77 | ✅ |
| 3 | HIT | 2053.93 | ✅ |

---

## 🎯 CONCLUSIONS

### Efficacité du KV Cache
❌ **FAIBLE** - Le KV Cache offre seulement une accélération **x1.09**.

### Recommandations
- ⚠️ Vérifier la configuration du KV Cache (--enable-prefix-caching)
- ⚠️ Augmenter --gpu-memory-utilization si possible
- ⚠️ Vérifier que le cache n'est pas éjecté trop rapidement

### Métriques Clés

- **Premier TTFT (cold)** : 2491.21ms
- **TTFT optimisé (warm)** : 2278.88ms
- **Gain absolu** : 212.33ms
- **Accélération** : x1.09

---

**Fin du rapport**
