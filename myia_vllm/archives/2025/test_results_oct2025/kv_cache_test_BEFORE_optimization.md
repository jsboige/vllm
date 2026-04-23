# 🚀 TEST KV CACHE ACCELERATION - QWEN3-32B-AWQ

**Date d'exécution** : 2025-10-16 17:27:12  
**Modèle testé** : Qwen/Qwen3-32B-AWQ  
**Tours de conversation** : 5

---

## 📊 RÉSULTATS GLOBAUX

### 1️⃣ Conversation Continue (KV Cache actif)

| Métrique | Valeur |
|----------|--------|
| **Premier message (CACHE MISS)** | 1828.33ms |
| **Messages suivants (CACHE HIT)** | 1606.56ms |
| **🚀 Accélération** | **x1.14** |
| **Gain de performance** | 12.1% |

### 2️⃣ Messages Indépendants (Pas de cache)

| Métrique | Valeur |
|----------|--------|
| **TTFT moyen** | 1657.11ms |

### 3️⃣ Prefill Cache (Contexte préchargé)

| Métrique | Valeur |
|----------|--------|
| **Premier message (CACHE MISS)** | 1946ms |
| **Messages suivants (CACHE HIT)** | 1624.71ms |
| **🚀 Accélération** | **x1.2** |
| **Gain de performance** | 16.5% |

---

## 📈 DÉTAILS DES MESURES

### Conversation Continue

| Tour | Type | TTFT (ms) | Statut |
|------|------|-----------|--------|| 1 | MISS | 1828.33 | ✅ |
| 2 | HIT | 1864.23 | ✅ |
| 3 | HIT | 1443.63 | ✅ |
| 4 | HIT | 1488.76 | ✅ |
| 5 | HIT | 1629.62 | ✅ |

### Messages Indépendants

| Message | TTFT (ms) | Statut |
|---------|-----------|--------|| 1 | 1883.96 | ✅ |
| 2 | 1626.57 | ✅ |
| 3 | 1553.08 | ✅ |
| 4 | 1656.82 | ✅ |
| 5 | 1565.11 | ✅ |

### Prefill Cache

| Tour | Type | TTFT (ms) | Statut |
|------|------|-----------|--------|| 1 | MISS | 1946 | ✅ |
| 2 | HIT | 1555.97 | ✅ |
| 3 | HIT | 1693.45 | ✅ |

---

## 🎯 CONCLUSIONS

### Efficacité du KV Cache
❌ **FAIBLE** - Le KV Cache offre seulement une accélération **x1.14**.

### Recommandations
- ⚠️ Vérifier la configuration du KV Cache (--enable-prefix-caching)
- ⚠️ Augmenter --gpu-memory-utilization si possible
- ⚠️ Vérifier que le cache n'est pas éjecté trop rapidement

### Métriques Clés

- **Premier TTFT (cold)** : 1828.33ms
- **TTFT optimisé (warm)** : 1606.56ms
- **Gain absolu** : 221.77ms
- **Accélération** : x1.14

---

**Fin du rapport**
