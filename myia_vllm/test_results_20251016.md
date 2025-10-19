# 📊 RAPPORT DE TESTS - SERVICE MEDIUM QWEN3-32B-AWQ

**Date d'exécution** : 2025-10-16 17:25:06  
**Durée totale** : 478.15s  
**Modèle testé** : Qwen/Qwen3-32B-AWQ  
**URL de base** : http://localhost:5002

---

## 📈 RÉSULTATS GLOBAUX

| Métrique | Valeur |
|----------|--------|
| **Tests exécutés** | 14 |
| **Tests réussis** | 14 ✅ |
| **Tests échoués** | 0 ❌ |
| **Tests partiels** | 0 ⚠️ |
| **Taux de réussite** | **100%** |

---

## 📋 TABLEAU RÉCAPITULATIF DES TESTS

| # | Test | Statut | Durée | Détails |
|---|------|--------|-------|---------|| 1 | Test 1: Health Check | ✅ PASS | 0.12s | OK |
| 2 | Test 2: Liste Modèles | ✅ PASS | 0.11s | OK |
| 3 | Test 3: Chat Completion Simple | ✅ PASS | 14.83s | OK |
| 4 | Test 4: Chain-of-Thought Simple | ✅ PASS | 12.95s | OK |
| 5 | Test 5: Raisonnement Complexe (Trains) | ✅ PASS | 15.44s | OK |
| 6 | Test 6: Tool Calling Basique | ✅ PASS | 6.35s | OK |
| 7 | Test 7: TTFT (Time To First Token) | ✅ PASS | 1.03s | Moyenne TTFT: 1.03259242s sur 5 essais |
| 8 | Test 8: Throughput | ✅ PASS | 15.47s | OK |
| 9 | Test 9: Charge Concurrente (10 requêtes) | ✅ PASS | N/A | 10/10 requêtes réussies |
| 10 | Test 10: Contexte 8k tokens | ✅ PASS | 70.69s | OK |
| 11 | Test 11: Contexte 32k tokens | ✅ PASS | 107.9s | OK |
| 12 | Test 12: Contexte 64k tokens | ✅ PASS | 216.26s | OK |
| 13 | Test 13: Requêtes Invalides | ✅ PASS | N/A | Erreurs gérées correctement (2/2) |
| 14 | Test 14: Streaming | ✅ PASS | 4s | OK |

---

## 📊 DÉTAILS DES TESTS

### Test 1: Health Check

- **Statut** : ✅ PASS
- **Durée** : 0.1234623s
### Test 2: Liste Modèles

- **Statut** : ✅ PASS
- **Durée** : 0.1080733s- **Réponse** :
```
{"object":"list","data":[{"id":"Qwen/Qwen3-32B-AWQ","object":"model","created":1760627828,"owned_by":"vllm","root":"Qwen/Qwen3-32B-AWQ","parent":null,"max_model_len":131072,"permission":[{"id":"modelperm-870316454b194a149c5da6186b2445db","object":"model_permission","created":1760627828,"allow_create_engine":false,"allow_sampling":true,"allow_logprobs":true,"allow_search_indices":false,"allow_view":true,"allow_fine_tuning":false,"organization":"*","group":null,"is_blocking":false}]}]}
```

### Test 3: Chat Completion Simple

- **Statut** : ✅ PASS
- **Durée** : 14.829677s
### Test 4: Chain-of-Thought Simple

- **Statut** : ✅ PASS
- **Durée** : 12.9549839s
### Test 5: Raisonnement Complexe (Trains)

- **Statut** : ✅ PASS
- **Durée** : 15.4420966s
### Test 6: Tool Calling Basique

- **Statut** : ✅ PASS
- **Durée** : 6.3489406s
### Test 7: TTFT (Time To First Token)

- **Statut** : ✅ PASS
- **Durée** : 1.03259242s- **Réponse** :
```
Moyenne TTFT: 1.03259242s sur 5 essais
```

### Test 8: Throughput

- **Statut** : ✅ PASS
- **Durée** : 15.4711327s
### Test 9: Charge Concurrente (10 requêtes)

- **Statut** : ✅ PASS
- **Durée** : s- **Réponse** :
```
10/10 requêtes réussies
```

### Test 10: Contexte 8k tokens

- **Statut** : ✅ PASS
- **Durée** : 70.6886387s
### Test 11: Contexte 32k tokens

- **Statut** : ✅ PASS
- **Durée** : 107.8981965s
### Test 12: Contexte 64k tokens

- **Statut** : ✅ PASS
- **Durée** : 216.2623486s
### Test 13: Requêtes Invalides

- **Statut** : ✅ PASS
- **Durée** : s- **Réponse** :
```
Erreurs gérées correctement (2/2)
```

### Test 14: Streaming

- **Statut** : ✅ PASS
- **Durée** : 4.0017507s
---

## 🎯 RECOMMANDATIONS PRODUCTION

### ✅ Points Forts
- Taux de réussite élevé : 100%
- Service stable et opérationnel

### ⚠️ Points d'Attention

### 🚀 Recommandations
- ✅ **PRÊT POUR PRODUCTION** - Le service passe tous les tests critiques

---

## 📝 NOTES

- Tests exécutés automatiquement via PowerShell
- Tous les tests ont un timeout de 60-240s selon complexité
- Container testé : myia_vllm-medium-qwen3
- Port : 5002

**Fin du rapport**
