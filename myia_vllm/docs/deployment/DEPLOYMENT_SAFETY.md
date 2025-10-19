# 🛡️ Guide de Sécurité Déploiement - Service Medium vLLM

**Date de création** : 2025-10-16  
**Mission** : SDDD Mission 9 - Audit Critique Pré-Déploiement  
**Statut** : 🚨 LECTURE OBLIGATOIRE AVANT TOUT DÉPLOIEMENT

---

## ⚠️ ALERTE CRITIQUE : CONFUSION ARCHITECTURALE DÉTECTÉE

### 🔍 Problème Identifié

Le projet contient **DEUX architectures Docker parallèles** créant une **confusion dangereuse** :

1. **Architecture Autonome** (racine du projet)
   - `docker-compose-qwen3-medium.yml`
   - `docker-compose-qwen3-micro.yml`
   - `docker-compose-qwen3-mini.yml`

2. **Architecture Modulaire** (configs/)
   - `configs/docker/profiles/medium.yml`
   - Fichier base `configs/docker/docker-compose.yml` : **❌ N'EXISTE PAS**

### 🎯 Configuration Utilisée par le Script de Déploiement

Le script `scripts/deploy_medium_monitored.ps1` (ligne 43) utilise :
```powershell
$composeProfile = "configs\docker\profiles\medium.yml"
```

**⚠️ PROBLÈME** : Ce fichier utilise l'image Docker `latest` (instable) au lieu de `v0.9.2` (stable).

---

## 📊 ANALYSE COMPARATIVE CRITIQUE DES CONFIGURATIONS

### Fichier 1 : `docker-compose-qwen3-medium.yml` (racine)

| Paramètre | Valeur | Évaluation |
|-----------|--------|------------|
| Image Docker | `v0.9.2` | ✅ **Version stable** |
| Context Max | 70000 tokens | ⚠️ **Sous-optimal** (128k possible) |
| Quantization | Non spécifiée | ⚠️ **Manque explicite** |
| Executor Backend | ray (défaut) | ⚠️ **Non optimal pour TP** |
| Healthcheck Start | 30s | ❌ **Trop court** (modèle 32B) |
| Container Name | Non défini | ⚠️ **Monitoring difficile** |
| Swap Space | Non défini | ⚠️ **Risque OOM** |

**Score Global** : 🟡 **5/10** - Stable mais sous-optimal

### Fichier 2 : `configs/docker/profiles/medium.yml` (configs/)

| Paramètre | Valeur | Évaluation |
|-----------|--------|------------|
| Image Docker | `latest` | ❌ **INSTABLE - BLOQUANT** |
| Context Max | 131072 tokens (128k) | ✅ **Optimal** |
| Quantization | `awq_marlin` | ✅ **Explicite et optimal** |
| Executor Backend | `mp` | ✅ **Optimal pour TP** |
| Healthcheck Start | 300s (5min) | ✅ **Réaliste pour 32B** |
| Container Name | `myia-vllm-medium-qwen3` | ✅ **Monitoring facile** |
| Swap Space | 16GB | ✅ **Protection OOM** |

**Score Global** : 🔴 **3/10** - Paramètres optimaux MAIS version instable

---

## 🎯 RECOMMANDATION OFFICIELLE

### ✅ Configuration à Utiliser : AUCUNE DES DEUX EN L'ÉTAT

**Les deux fichiers ont des défauts critiques.** Avant tout déploiement :

### Option A : Corriger `configs/docker/profiles/medium.yml` (RECOMMANDÉ)

**Modification requise** :
```yaml
# AVANT (ligne 3)
image: vllm/vllm-openai:latest

# APRÈS
image: vllm/vllm-openai:v0.9.2
```

**Avantages** :
- ✅ Paramètres optimaux (131k context, awq_marlin, mp backend)
- ✅ Architecture modulaire documentée
- ✅ Utilisé par le script de déploiement officiel

**Inconvénient** :
- ⚠️ Nécessite modification manuelle avant déploiement

### Option B : Utiliser `docker-compose-qwen3-medium.yml` avec améliorations

**Modifications requises** :
1. Augmenter `max-model-len` : 70000 → 131072
2. Ajouter `--quantization awq_marlin`
3. Ajouter `--distributed-executor-backend=mp`
4. Augmenter healthcheck `start_period` : 30s → 300s
5. Ajouter `container_name: myia-vllm-medium-qwen3`

**Avantages** :
- ✅ Version stable v0.9.2
- ✅ Fichier autonome (pas de dépendance)

**Inconvénients** :
- ⚠️ Nombreuses modifications requises
- ⚠️ Nécessite modifier le script de déploiement (ligne 43)

---

## 🚨 CHECKLIST DE SÉCURITÉ PRÉ-DÉPLOIEMENT

### 1️⃣ Validation Configuration Docker

- [ ] **Image Docker** : Vérifier version `v0.9.2` (PAS `latest`)
  ```bash
  grep "image:" configs/docker/profiles/medium.yml
  # Doit afficher: image: vllm/vllm-openai:v0.9.2
  ```

- [ ] **Syntaxe YAML** : Valider avec `docker compose config`
  ```bash
  docker compose -f configs/docker/profiles/medium.yml config
  # Ne doit retourner AUCUNE erreur
  ```

- [ ] **Paramètres critiques** : Vérifier présence
  ```yaml
  --max-model-len 131072        ✅ Requis
  --quantization awq_marlin     ✅ Requis
  --distributed-executor-backend=mp  ✅ Requis
  --tensor-parallel-size 2      ✅ Requis
  ```

### 2️⃣ État Système Pré-Déploiement

- [ ] **Backup état actuel** : Documenter conteneurs running
  ```bash
  docker ps --format "{{.ID}}\t{{.Names}}\t{{.Status}}" > backup_containers_$(date +%Y%m%d_%H%M%S).txt
  docker inspect myia-vllm-medium-qwen3 > backup_config_$(date +%Y%m%d_%H%M%S).json 2>/dev/null || echo "Pas de conteneur existant"
  ```

- [ ] **GPUs disponibles** : Vérifier allocation
  ```bash
  nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv
  # GPU 0,1 doivent être libres ou <50% utilisation
  ```

- [ ] **Espace disque** : Minimum 100GB libre
  ```bash
  df -h ~/ | grep -E "Avail|Available"
  ```

- [ ] **Port 5002 libre** : Vérifier disponibilité
  ```bash
  netstat -tuln | grep 5002 || echo "Port libre"
  ```

### 3️⃣ Configuration Environnement (.env)

- [ ] **Fichier .env existe** : `myia_vllm/.env`
  
- [ ] **Token HuggingFace valide** : Commence par `hf_`
  ```bash
  grep "HUGGING_FACE_HUB_TOKEN=hf_" myia_vllm/.env
  ```

- [ ] **Variables critiques définies** :
  ```bash
  # Vérifier présence (sans afficher valeurs)
  grep -q "CUDA_VISIBLE_DEVICES_MEDIUM" myia_vllm/.env && echo "✅ CUDA_VISIBLE_DEVICES_MEDIUM"
  grep -q "VLLM_PORT_MEDIUM" myia_vllm/.env && echo "✅ VLLM_PORT_MEDIUM"
  grep -q "VLLM_API_KEY_MEDIUM" myia_vllm/.env && echo "✅ VLLM_API_KEY_MEDIUM"
  ```

### 4️⃣ Plan de Rollback Préparé

- [ ] **Identifier configuration actuelle** (si applicable)
  ```bash
  docker inspect myia-vllm-medium-qwen3 --format='{{.Config.Image}}'
  ```

- [ ] **Sauvegarder logs actuels** (si conteneur existe)
  ```bash
  docker logs myia-vllm-medium-qwen3 > logs_backup_$(date +%Y%m%d_%H%M%S).txt 2>&1 || echo "Pas de logs"
  ```

- [ ] **Documenter commande de rollback**
  ```bash
  # Si problème, revenir à l'ancienne version :
  docker compose -f configs/docker/profiles/medium.yml down
  # Puis restaurer backup si nécessaire
  ```

---

## 🛡️ PROCÉDURE DE DÉPLOIEMENT SÉCURISÉ

### Phase 1 : Préparation (10 minutes)

#### 1.1 Corriger la Configuration Docker

**Fichier** : `configs/docker/profiles/medium.yml`

**Modification ligne 3** :
```yaml
# AVANT
image: vllm/vllm-openai:latest

# APRÈS
image: vllm/vllm-openai:v0.9.2
```

**Commande de correction rapide** :
```powershell
# Windows PowerShell
(Get-Content myia_vllm/configs/docker/profiles/medium.yml) -replace 'image: vllm/vllm-openai:latest', 'image: vllm/vllm-openai:v0.9.2' | Set-Content myia_vllm/configs/docker/profiles/medium.yml
```

#### 1.2 Valider la Configuration

```bash
cd myia_vllm
docker compose -f configs/docker/profiles/medium.yml config
```

**Résultat attendu** : Aucune erreur, affichage de la config complète

#### 1.3 Vérifier le Fichier .env

```bash
# Vérifier présence variables critiques (sans afficher valeurs)
cat .env | grep -E "HUGGING_FACE_HUB_TOKEN|CUDA_VISIBLE_DEVICES_MEDIUM|VLLM_PORT_MEDIUM|VLLM_API_KEY_MEDIUM" | wc -l
# Doit retourner: 4
```

### Phase 2 : Déploiement Sécurisé (15-20 minutes)

#### 2.1 Mode Dry-Run (Simulation)

**⚠️ Actuellement NON disponible dans le script**

Alternative manuelle :
```bash
# Vérifier ce qui serait créé sans l'exécuter
docker compose -f configs/docker/profiles/medium.yml config
```

#### 2.2 Backup État Actuel

```bash
# Créer répertoire backups
mkdir -p backups/$(date +%Y%m%d_%H%M%S)
cd backups/$(date +%Y%m%d_%H%M%S)

# Sauvegarder état
docker ps > containers_before.txt
docker logs myia-vllm-medium-qwen3 > logs_before.txt 2>&1 || echo "Pas de logs"
docker inspect myia-vllm-medium-qwen3 > config_before.json 2>&1 || echo "Pas de config"
nvidia-smi > gpu_before.txt

cd ../..
```

#### 2.3 Déploiement avec Monitoring

```powershell
# Option 1 : Utiliser le script officiel (après correction image)
pwsh -c "./scripts/deploy_medium_monitored.ps1"

# Option 2 : Déploiement manuel avec monitoring séparé
docker compose -f configs/docker/profiles/medium.yml up -d --build --force-recreate
pwsh -c "./scripts/monitor_medium.ps1"
```

### Phase 3 : Validation Post-Déploiement (5-10 minutes)

#### 3.1 Vérifier Démarrage Conteneur

```bash
docker ps --filter "name=myia-vllm-medium-qwen3"
# Doit montrer le conteneur en status "Up"
```

#### 3.2 Surveiller Logs de Démarrage

```bash
docker logs -f myia-vllm-medium-qwen3 --tail 100
```

**Indicateurs de succès** :
- ✅ `Uvicorn running on http://0.0.0.0:5002`
- ✅ `Loaded model Qwen/Qwen3-32B-AWQ`
- ✅ `GPU memory utilization: 95%`

**Indicateurs d'échec** :
- ❌ `CUDA out of memory`
- ❌ `Model not found`
- ❌ `Token authentication failed`

#### 3.3 Tests de Santé

```bash
# Test 1 : Health endpoint (sans auth)
curl -f http://localhost:5002/health
# Attendu: {"status":"ok"} ou similar

# Test 2 : Models endpoint (avec auth si configurée)
curl -H "Authorization: Bearer ${VLLM_API_KEY_MEDIUM}" http://localhost:5002/v1/models
# Attendu: Liste des modèles chargés

# Test 3 : GPU Utilization
nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv
# GPU 0,1 doivent montrer utilisation
```

---

## 🔄 PROCÉDURE DE ROLLBACK

### En Cas d'Échec du Déploiement

#### 1. Arrêt du Service Problématique

```bash
docker compose -f configs/docker/profiles/medium.yml down --remove-orphans
```

#### 2. Diagnostic des Logs

```bash
# Sauvegarder logs d'échec
docker logs myia-vllm-medium-qwen3 > logs_failure_$(date +%Y%m%d_%H%M%S).txt 2>&1

# Analyser causes communes
grep -i "error\|failed\|exception" logs_failure_*.txt
```

#### 3. Restauration État Précédent

Si un conteneur fonctionnait avant :

```bash
# Option A : Redémarrer conteneur existant
docker start myia-vllm-medium-qwen3

# Option B : Recréer avec ancienne config
# (si backup de config disponible)
docker run --rm -v $(pwd)/backups/config_before.json:/config.json ...
```

#### 4. Réinitialisation Complète

Si nécessaire revenir à état propre :

```bash
# Arrêter TOUS les conteneurs vLLM
docker ps -a --filter "name=vllm" --format "{{.ID}}" | xargs -r docker rm -f

# Nettoyer volumes orphelins
docker volume prune -f

# Nettoyer images inutilisées
docker image prune -a -f
```

---

## 🚫 ACTIONS INTERDITES SANS VALIDATION UTILISATEUR

### ❌ NE JAMAIS EXÉCUTER SANS CONFIRMATION :

1. **`docker compose down` sur service en production**
   - Risque : Arrêt immédiat du service
   - Alternative : Backup d'abord, puis arrêt planifié

2. **`--force-recreate` sans backup**
   - Risque : Perte config actuelle
   - Alternative : Backup config + logs avant

3. **Modifications directes du .env en production**
   - Risque : Exposition secrets dans historique
   - Alternative : Utiliser `.env.local` non versionné

4. **Pull `latest` en production**
   - Risque : Breaking changes non testés
   - Alternative : Toujours spécifier version (v0.9.2)

5. **Changement `CUDA_VISIBLE_DEVICES` sans test**
   - Risque : Modèle ne charge pas (tensor-parallel-size incompatible)
   - Alternative : Vérifier GPU allocation avant

---

## 📋 TROUBLESHOOTING GUIDE RAPIDE

### Problème 1 : "Image tag 'latest' not stable"

**Cause** : Fichier `configs/docker/profiles/medium.yml` utilise `latest`

**Solution** :
```yaml
# Ligne 3 de configs/docker/profiles/medium.yml
image: vllm/vllm-openai:v0.9.2  # Changer latest → v0.9.2
```

### Problème 2 : "CUDA out of memory"

**Causes possibles** :
- GPU déjà utilisés par autre processus
- `gpu-memory-utilization` trop élevé (>0.95)
- Pas assez de VRAM pour modèle 32B

**Solutions** :
```bash
# 1. Vérifier processus GPU
nvidia-smi

# 2. Libérer GPUs
docker stop $(docker ps -q)  # ATTENTION: Arrête TOUS conteneurs

# 3. Réduire utilisation mémoire dans config
--gpu-memory-utilization 0.90  # Au lieu de 0.95
```

### Problème 3 : "Token authentication failed"

**Cause** : Token HuggingFace manquant ou invalide

**Solution** :
```bash
# 1. Vérifier token dans .env
grep HUGGING_FACE_HUB_TOKEN myia_vllm/.env

# 2. Tester token
curl -H "Authorization: Bearer hf_YOUR_TOKEN" https://huggingface.co/api/whoami-v2

# 3. Regénérer token si besoin sur huggingface.co/settings/tokens
```

### Problème 4 : "Healthcheck failing after deployment"

**Causes possibles** :
- Modèle encore en chargement (normal <5min)
- Port 5002 non accessible
- API Key requise mais non fournie

**Solutions** :
```bash
# 1. Attendre fin chargement
docker logs -f myia-vllm-medium-qwen3 | grep "Uvicorn running"

# 2. Tester port
curl http://localhost:5002/health

# 3. Vérifier auth si configurée
curl -H "Authorization: Bearer ${VLLM_API_KEY_MEDIUM}" http://localhost:5002/health
```

---

## 📚 RÉFÉRENCES

### Documentation Interne

- **Configuration validée** : [`MEDIUM_SERVICE_PARAMETERS.md`](../docker/MEDIUM_SERVICE_PARAMETERS.md)
- **Architecture Docker** : [`ARCHITECTURE.md`](../docker/ARCHITECTURE.md)
- **Guide déploiement** : [`MEDIUM_SERVICE.md`](./MEDIUM_SERVICE.md)
- **Configuration .env** : [`ENV_CONFIGURATION.md`](../setup/ENV_CONFIGURATION.md)

### Scripts Associés

- **Déploiement avec monitoring** : `scripts/deploy_medium_monitored.ps1`
- **Monitoring seul** : `scripts/monitor_medium.ps1`

### Documentation Externe

- **vLLM Official Docs** : https://docs.vllm.ai/
- **Qwen3 Model Card** : https://huggingface.co/Qwen/Qwen3-32B-AWQ
- **Docker Compose Docs** : https://docs.docker.com/compose/

---

## ⚖️ PRINCIPES DE SÉCURITÉ ADOPTÉS

1. **Principe de Version Stable** : Toujours spécifier version explicite (`v0.9.2`), jamais `latest`

2. **Principe de Backup Avant Modification** : Toujours documenter état actuel avant changement

3. **Principe de Validation Progressive** : 
   - Valider syntaxe → Valider config → Backup → Déployer → Monitorer

4. **Principe de Rollback Préparé** : Toujours avoir un plan B avant toute action

5. **Principe de Non-Interférence** : Ne jamais modifier un système en production sans fenêtre de maintenance

---

**Dernière mise à jour** : 2025-10-16  
**Validé par** : SDDD Mission 9 - Audit Critique Pré-Déploiement  
**Prochaine révision** : Après premier déploiement sécurisé réussi

---

## 🔧 Troubleshooting GPU Docker

### Problème : "Failed to infer device type" / "libcuda.so.1: cannot open shared object file"

**Symptômes** :
```
RuntimeError: Failed to infer device type
ImportError: libcuda.so.1: cannot open shared object file: No such file or directory
INFO: No platform detected, vLLM is running on UnspecifiedPlatform
```

**Cause Racine** :
La syntaxe `deploy.resources.reservations.devices` est pour **Docker Swarm**, pas Docker Compose standalone. Le conteneur ne peut pas accéder aux GPUs NVIDIA.

**Solution** :

1. **Vérifier le runtime NVIDIA** :
   ```bash
   docker info | grep -i nvidia
   # Doit afficher: Runtimes: nvidia runc
   
   docker run --rm --runtime=nvidia nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
   # Doit afficher les GPUs disponibles
   ```

2. **Corriger la configuration Docker Compose** :

   ❌ **INCORRECT (syntaxe Swarm)** :
   ```yaml
   deploy:
     resources:
       reservations:
         devices:
           - driver: nvidia
             capabilities: [gpu]
             device_ids: ['${CUDA_VISIBLE_DEVICES}']
   ```

   ✅ **CORRECT (Docker Compose standalone)** :
   ```yaml
   runtime: nvidia
   ipc: host
   shm_size: '16gb'
   environment:
     - NVIDIA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0,1}
     - HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN}
   ```

3. **Tester la configuration** :
   ```bash
   # Test GPU dans conteneur
   docker compose -f medium.yml run --rm vllm-medium-qwen3 nvidia-smi
   
   # Déploiement complet
   pwsh -File scripts/deploy_medium_monitored.ps1
   ```

**Références** :
- vLLM documentation : Recommande `runtime: nvidia` + `ipc: host` + `shm_size`
- Docker Compose vs Docker Swarm : Syntaxes GPU différentes
- Fix appliqué le : 2025-10-16 (Mission Debug GPU)
