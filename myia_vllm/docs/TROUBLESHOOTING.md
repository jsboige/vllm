# Guide de Dépannage - Service vLLM Medium

**Dernière mise à jour** : 2025-10-22
**Version** : 1.0

## 📋 Table des Matières
1. Problèmes de Déploiement
2. Problèmes de Configuration
3. Problèmes de Performance
4. Bugs Historiques Résolus (Missions 14a-14k)
5. Scripts de Diagnostic
6. Procédures d'Escalade

---

## 1. Problèmes de Déploiement

### 1.1 Container ne démarre pas

**Symptômes :**
- Container en statut `Exited` immédiatement après lancement
- Logs montrent erreur au démarrage

**Causes possibles :**
1. **Clé API manquante ou invalide**
2. **GPUs non détectés**
3. **Port 8000 déjà utilisé**
4. **Mémoire insuffisante**

**Diagnostic :**
```powershell
# Vérifier logs d'erreur
docker logs myia_vllm-medium-qwen3

# Vérifier GPUs disponibles
nvidia-smi

# Vérifier port 8000
netstat -ano | findstr :8000
```

**Solutions :**

**1. Clé API manquante** (Bug historique #3 - Mission 14e)
```powershell
# Vérifier fichier .env existe
Test-Path myia_vllm\.env

# Vérifier variable définie
cat myia_vllm\.env | Select-String "VLLM_API_KEY_MEDIUM"
```
**Action :** Créer/corriger `.env` avec clé valide (32+ caractères)

**2. GPUs non détectés**
```bash
# Test GPU Docker
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```
**Action :** Installer NVIDIA Container Toolkit si échec

**3. Port occupé**
```powershell
# Identifier processus utilisant port 8000
Get-NetTCPConnection -LocalPort 8000 | Select OwningProcess
```
**Action :** Arrêter processus ou modifier port dans [`medium.yml`](myia_vllm/configs/docker/profiles/medium.yml)

**4. Mémoire insuffisante**
```powershell
# Vérifier RAM disponible
pwsh -c "Get-CimInstance Win32_OperatingSystem | Select FreePhysicalMemory"
```
**Action :** Fermer applications ou réduire `gpu-memory-utilization` à 0.80

---

### 1.2 Health Check échoue

**Symptômes :**
- Container en statut `(starting)` puis `(unhealthy)`
- Timeout après 5-10 minutes

**Causes possibles :**
1. **Modèle trop long à charger** (normal pour 32B params)
2. **Mémoire GPU saturée**
3. **Erreur rope_scaling** (Bug historique #5)

**Diagnostic :**
```powershell
# Suivre logs en temps réel
docker logs -f myia_vllm-medium-qwen3

# Vérifier utilisation VRAM
nvidia-smi -l 5
```

**Solutions :**

**1. Chargement normal (patience requise)**
- **Attendre 5-10 minutes** pour chargement modèle 32B
- Utiliser script [`wait_for_container_healthy.ps1`](myia_vllm/scripts/monitoring/wait_for_container_healthy.ps1) avec timeout 600s

**2. Mémoire GPU saturée**
- Vérifier VRAM utilisée < 90%
- Réduire `gpu-memory-utilization` de 0.85 → 0.80
- Désactiver prefix-caching si activé (consomme VRAM)

**3. Erreur rope_scaling** (Bug #5 - Mission 14i)
```yaml
# INCORRECT (guillemets échappés)
--rope_scaling '{\"rope_type\":\"yarn\",...}'

# CORRECT (guillemets simples)
--rope_scaling '{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":32768}'
```

---

### 1.3 API ne répond pas malgré (healthy)

**Symptômes :**
- Container `(healthy)` confirmé
- `curl http://localhost:8000/health` échoue ou timeout

**Causes possibles :**
1. **Port mapping incorrect**
2. **Firewall Windows bloque port**
3. **Health check interne OK mais API externe inaccessible**

**Diagnostic :**
```powershell
# Vérifier port mapping
docker ps --filter "name=myia_vllm-medium-qwen3" --format "{{.Ports}}"
# Attendu : 0.0.0.0:8000->8000/tcp

# Tester depuis l'intérieur du container
docker exec myia_vllm-medium-qwen3 curl http://localhost:8000/health
```

**Solutions :**

**1. Port mapping manquant**
- Vérifier [`medium.yml`](myia_vllm/configs/docker/profiles/medium.yml) contient :
```yaml
ports:
  - "8000:8000"
```

**2. Firewall bloque**
```powershell
# Autoriser port 8000 (PowerShell Admin)
New-NetFirewallRule -DisplayName "vLLM Medium" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

**3. Erreur configuration API**
- Vérifier logs pour erreurs API : `docker logs myia_vllm-medium-qwen3 | Select-String "error"`

---

## 2. Problèmes de Configuration

### 2.1 Variables d'environnement non chargées

**Symptômes :**
- Container démarre mais erreur "api-key expected"
- Variables `.env` ignorées

**Cause :** Flag `--env-file` manquant (Bug historique #4 - Mission 14g)

**Diagnostic :**
```powershell
# Vérifier commande docker compose utilisée
# DOIT inclure : --env-file myia_vllm\.env
```

**Solution :**
```powershell
# Commande CORRECTE avec --env-file
cd myia_vllm
docker compose -p myia_vllm --env-file .env -f configs/docker/docker-compose.yml -f configs/docker/profiles/medium.yml up -d
```

**Source :** Voir correction appliquée dans [`grid_search_optimization.ps1`](myia_vllm/scripts/grid_search_optimization.ps1) lignes 485, 493, 539

---

### 2.2 Paramètres rope_scaling invalides

**Symptômes :**
- Erreur au démarrage : "argument --rope-scaling: Value ... cannot be converted"

**Cause :** JSON mal formaté avec guillemets échappés (Bug #5 - Mission 14i)

**Solution :**
```yaml
# ❌ INCORRECT
--rope_scaling '{\"rope_type\":\"yarn\",\"factor\":4.0,\"original_max_position_embeddings\":32768}'

# ✅ CORRECT
--rope_scaling '{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":32768}'
```

**Source :** Correction ligne 379 dans [`grid_search_optimization.ps1`](myia_vllm/scripts/grid_search_optimization.ps1)

---

## 3. Problèmes de Performance

### 3.1 TTFT (Time To First Token) élevé

**Symptômes :**
- Premier token > 5 secondes sur requêtes simples
- KV Cache semble non fonctionnel

**Diagnostic :**
```powershell
# Tester accélération KV Cache
pwsh -c ".\myia_vllm\scripts\test_kv_cache_acceleration.ps1"
```

**Causes possibles :**
1. **Configuration non optimale** (prefix-caching activé + chunked-prefill désactivé)
2. **Mémoire GPU saturée** (pas de place pour cache)
3. **Prompt trop long** (> 32K tokens)

**Solutions :**

**1. Utiliser configuration optimale validée**
```yaml
--gpu-memory-utilization 0.85
--enable-chunked-prefill
# PAS de --enable-prefix-caching (contre-intuitif mais validé)
```
**Référence :** [`OPTIMIZATION_GUIDE.md`](myia_vllm/docs/OPTIMIZATION_GUIDE.md) Section 4

**2. Réduire utilisation VRAM**
- Libérer mémoire pour KV Cache
- Réduire `gpu-memory-utilization` si > 90% utilisé

**3. Segmenter prompts longs**
- Limiter prompts initiaux à 16K tokens max
- Utiliser context window incremental

---

### 3.2 Crashes mémoire (OOM)

**Symptômes :**
- Container redémarre aléatoirement
- Logs montrent `CUDA out of memory`

**Causes :**
1. **gpu-memory-utilization trop élevé** (> 0.90)
2. **chunked-prefill désactivé** (pics mémoire)
3. **Multiples requêtes parallèles**

**Solutions :**

**1. Réduire allocation mémoire**
```yaml
# Configuration stable
--gpu-memory-utilization 0.85  # Au lieu de 0.90+
--enable-chunked-prefill       # ESSENTIEL
```

**2. Activer chunked prefill**
- Lisse les pics mémoire
- Permet allocations plus élevées sans crash

**3. Limiter concurrence**
- Réduire `max-num-seqs` si crashes persistent
- Monitorer avec `nvidia-smi -l 1`

---

## 4. Bugs Historiques Résolus (Missions 14a-14k)

**Source détaillée :** [`SYNTHESIS_GRID_SEARCH_MISSIONS_20251021.md`](myia_vllm/docs/SYNTHESIS_GRID_SEARCH_MISSIONS_20251021.md)

### Bug #1 : Nom Container Hardcodé (Mission 14a-14b)

**Symptôme :** `Error: No such container: vllm-medium`

**Cause :** Nom hardcodé au lieu du nom réel `myia_vllm-medium-qwen3`

**Fix :** Fonction `Get-VllmContainerName()` avec détection dynamique via labels Docker

**Fichiers modifiés :**
- [`grid_search_optimization.ps1`](myia_vllm/scripts/grid_search_optimization.ps1) lignes 400-420

**Détails :**
```powershell
# AVANT (ligne 513) - hardcodé
$ContainerName = "vllm-medium"

# APRÈS - détection dynamique
function Get-VllmContainerName {
    $containers = docker ps -a --filter "label=com.docker.compose.project=myia_vllm" `
                               --filter "label=com.docker.compose.service=medium-qwen3" `
                               --format "{{.Names}}"
    return $containers[0]
}
```

---

### Bug #2 : Cleanup Non Garanti (Mission 14d)

**Symptôme :** Container orphelin après grid search interrompu

**Cause :** Absence bloc `finally` pour cleanup

**Fix :** Bloc `try-finally` avec fonction `Invoke-CleanupContainers()`

**Fichiers modifiés :**
- [`grid_search_optimization.ps1`](myia_vllm/scripts/grid_search_optimization.ps1) bloc finally ligne 1500+

**Détails :**
```powershell
try {
    # Exécution grid search
} finally {
    Write-Host "🧹 Cleanup final..."
    Invoke-CleanupContainers
}
```

---

### Bug #3 : Variable API_KEY Supprimée (Mission 14e-14f)

**Symptôme :** `argument --api-key: expected at least one argument`

**Cause :** Mauvais diagnostic → suppression ligne au lieu de corriger chemin .env

**Fix :** Restauration ligne 9 [`medium.yml`](myia_vllm/configs/docker/profiles/medium.yml) + diagnostic réel via logs

**Fichiers modifiés :**
- [`configs/docker/profiles/medium.yml`](myia_vllm/configs/docker/profiles/medium.yml) ligne 9

**Détails :**
```yaml
# CORRECT (restauré)
command:
  - "--api-key"
  - "${VLLM_API_KEY_MEDIUM}"
```

**Leçon :** Toujours analyser les logs RÉELS avant de modifier une configuration

---

### Bug #4 : Chemin .env Non Spécifié (Mission 14g)

**Symptôme :** Variables `.env` non chargées depuis sous-répertoires

**Cause :** Absence flag `--env-file` dans commandes Docker Compose

**Fix :** Ajout `--env-file "$ProjectRoot\.env"` dans 3 commandes

**Fichiers modifiés :**
- [`grid_search_optimization.ps1`](myia_vllm/scripts/grid_search_optimization.ps1) lignes 485, 493, 539

**Détails :**
```powershell
# AVANT
docker compose -p myia_vllm -f docker-compose.yml up -d

# APRÈS
docker compose -p myia_vllm --env-file "$ProjectRoot\.env" -f docker-compose.yml up -d
```

---

### Bug #5 : Paramètre rope_scaling Invalide (Mission 14i)

**Symptôme :** `argument --rope-scaling: Value {...} cannot be converted`

**Cause :** Guillemets JSON échappés `\"` au lieu de simples `"`

**Fix :** Correction format JSON (suppression backslashes)

**Fichiers modifiés :**
- [`grid_search_optimization.ps1`](myia_vllm/scripts/grid_search_optimization.ps1) ligne 379

**Détails :**
```powershell
# AVANT (incorrect - backslashes)
$ropeScaling = '{\"rope_type\":\"yarn\",\"factor\":4.0,\"original_max_position_embeddings\":32768}'

# APRÈS (correct - guillemets simples)
$ropeScaling = '{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":32768}'
```

---

### Bug #6 : Parsing KV Cache Échoue (Mission 14j-14k)

**Symptôme :** 4/4 configurations marquées `parse_error` malgré tests réussis

**Cause :** Patterns regex ne matchent pas format réel logs

**Fix :** Correction patterns regex (lignes 851-856)

**Fichiers modifiés :**
- [`grid_search_optimization.ps1`](myia_vllm/scripts/grid_search_optimization.ps1) lignes 851-856

**Avant :**
```powershell
if ($logContent -match 'TTFT CACHE MISS.*?(\d+\.\d+)ms')
```

**Après :**
```powershell
if ($logContent -match 'Premier message \(MISS\).*?TTFT:\s*(\d+\.\d+)ms')
```

---

## 5. Scripts de Diagnostic

### Scripts de Monitoring

| Script | Usage | Cas d'usage |
|--------|-------|-------------|
| [`wait_for_container_healthy.ps1`](myia_vllm/scripts/monitoring/wait_for_container_healthy.ps1) | Attendre (healthy) | Déploiement automatisé |
| [`monitor_medium.ps1`](myia_vllm/scripts/monitor_medium.ps1) | Logs live | Debugging temps réel |
| [`check_ram_usage.ps1`](myia_vllm/scripts/check_ram_usage.ps1) | RAM/VRAM status | Pré-déploiement |

### Scripts de Test

| Script | Usage | Cas d'usage |
|--------|-------|-------------|
| [`test_kv_cache_acceleration.ps1`](myia_vllm/scripts/test_kv_cache_acceleration.ps1) | Benchmark KV Cache | Validation config |
| [`mission15_validation_tests.ps1`](myia_vllm/scripts/testing/mission15_validation_tests.ps1) | Tests complets | Validation production |
| [`monitor_grid_search_safety.ps1`](myia_vllm/scripts/monitor_grid_search_safety.ps1) | Détection OOM | Grid search |

### Scripts de Maintenance

| Script | Usage | Cas d'usage |
|--------|-------|-------------|
| [`test_cleanup.ps1`](myia_vllm/scripts/test_cleanup.ps1) | Cleanup containers | Après tests |
| À créer : `cleanup_docker.ps1` | Nettoyage complet | Maintenance régulière |

---

## 6. Procédures d'Escalade

### Niveau 1 : Diagnostic Automatisé

1. Exécuter scripts diagnostic
2. Consulter logs container
3. Vérifier GPU status

```powershell
# Diagnostic rapide
docker logs myia_vllm-medium-qwen3 | Select-String "error|warning"
nvidia-smi
docker ps -a
```

### Niveau 2 : Consultation Documentation

1. Lire section pertinente dans ce guide
2. Consulter [`DEPLOYMENT_GUIDE.md`](myia_vllm/docs/DEPLOYMENT_GUIDE.md)
3. Vérifier [`OPTIMIZATION_GUIDE.md`](myia_vllm/docs/OPTIMIZATION_GUIDE.md)

### Niveau 3 : Support Communautaire

1. Rechercher issues similaires dans repo vLLM officiel
2. Consulter Discord vLLM
3. Ouvrir issue avec logs complets

### Logs à Collecter

```powershell
# Logs essentiels pour support
docker logs myia_vllm-medium-qwen3 > logs_container.txt
nvidia-smi > logs_gpu.txt
docker ps -a > logs_containers.txt
cat myia_vllm\configs\docker\profiles\medium.yml > config_current.yml
```

---

## 📚 Documentation Complémentaire

- **Guide Déploiement** : [`DEPLOYMENT_GUIDE.md`](myia_vllm/docs/DEPLOYMENT_GUIDE.md)
- **Guide Optimisation** : [`OPTIMIZATION_GUIDE.md`](myia_vllm/docs/OPTIMIZATION_GUIDE.md)
- **Procédures Maintenance** : [`MAINTENANCE_PROCEDURES.md`](myia_vllm/docs/MAINTENANCE_PROCEDURES.md)
- **Synthèse Bugs Grid Search** : [`SYNTHESIS_GRID_SEARCH_MISSIONS_20251021.md`](myia_vllm/docs/SYNTHESIS_GRID_SEARCH_MISSIONS_20251021.md)

---

**Fin du Guide de Dépannage vLLM Medium**