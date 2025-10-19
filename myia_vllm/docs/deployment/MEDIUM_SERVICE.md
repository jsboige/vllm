# Guide de Déploiement - Service Medium (Qwen3-32B-AWQ)

**Date de création**: 2025-10-16  
**Mission**: SDDD Mission 9 - Redéploiement Service Medium  
**Statut**: ✅ PRÊT POUR DÉPLOIEMENT

---

## Table des Matières

1. [Vue d'Ensemble](#vue-densemble)
2. [Prérequis](#prérequis)
3. [Validation de la Configuration](#validation-de-la-configuration)
4. [Procédure de Déploiement](#procédure-de-déploiement)
5. [Monitoring et Surveillance](#monitoring-et-surveillance)
6. [Validation Post-Déploiement](#validation-post-déploiement)
7. [Troubleshooting](#troubleshooting)

---

## Vue d'Ensemble

### Objectif

Déployer le service vLLM Medium configuré pour le modèle **Qwen3-32B-AWQ** avec les paramètres optimaux validés lors de la Mission 9 SDDD.

### Caractéristiques du Service

| Paramètre | Valeur | Notes |
|-----------|--------|-------|
| **Modèle** | Qwen/Qwen3-32B-AWQ | Quantization AWQ Marlin |
| **GPUs** | 2 (CUDA 0,1) | Tensor Parallel Size 2 |
| **Context Max** | 131072 tokens (128k) | ROPE scaling YARN 4.0 |
| **Memory Util** | 0.95 (95%) | Optimal pour production |
| **Port** | 5002 | Configurable via .env |
| **Container** | myia-vllm-medium-qwen3 | Docker Compose |
| **Image** | vllm/vllm-openai:latest | Image officielle |

### Temps de Déploiement Estimé

- **Démarrage conteneur** : 30-60 secondes
- **Chargement modèle** : 3-5 minutes
- **Health check** : Jusqu'à 5 minutes (start_period)
- **TOTAL** : ~6-10 minutes

---

## Prérequis

### 1. Matériel Requis

```yaml
GPUs: 2x NVIDIA (CUDA compatible)
VRAM: Minimum 24GB par GPU (recommandé: 40GB+)
RAM: Minimum 64GB système
Disque: 100GB+ espace libre (modèle + cache)
```

### 2. Logiciels Requis

```bash
# Vérifier Docker
docker --version
# Minimum: Docker 20.10+

# Vérifier Docker Compose
docker compose version
# Minimum: Docker Compose 2.0+

# Vérifier NVIDIA Container Toolkit
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

### 3. Configuration Environnement

**Fichier `.env` requis** : `myia_vllm/.env`

Variables critiques à vérifier :
```bash
# HuggingFace Token (CRITIQUE)
HUGGING_FACE_HUB_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# API Key
VLLM_API_KEY_MEDIUM=your-secure-api-key-here

# GPUs
CUDA_VISIBLE_DEVICES_MEDIUM=0,1

# Port
VLLM_PORT_MEDIUM=5002

# Optimisations
GPU_MEMORY_UTILIZATION_MEDIUM=0.95
```

**📚 Documentation** : Voir [`ENV_CONFIGURATION.md`](../setup/ENV_CONFIGURATION.md) pour guide complet

### 4. Validation Pré-Déploiement

```powershell
# Vérifier que le fichier .env existe et contient le token
Test-Path "myia_vllm/.env"

# Vérifier que le profil medium existe
Test-Path "myia_vllm/configs/docker/profiles/medium.yml"

# Vérifier disponibilité GPUs
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv
```

---

## Validation de la Configuration

### Configuration Validée ✅

La configuration actuelle dans `configs/docker/profiles/medium.yml` a été validée comme **100% optimale** :

- ✅ **14/14 paramètres** conformes aux meilleures pratiques
- ✅ **Score 100%** selon checklist vLLM
- ✅ **Score 100%** selon recommandations Qwen3
- ✅ **Context 128k** maximisé
- ✅ **GPU memory 95%** optimisé

**📚 Rapport détaillé** : [`MEDIUM_SERVICE_PARAMETERS.md`](../docker/MEDIUM_SERVICE_PARAMETERS.md)

### Paramètres Critiques Confirmés

```yaml
--model Qwen/Qwen3-32B-AWQ
--max-model-len 131072                    # ✅ 128k tokens
--tensor-parallel-size 2                  # ✅ 2 GPUs requis
--gpu-memory-utilization 0.95             # ✅ 95% optimal
--quantization awq_marlin                 # ✅ Meilleure perf
--kv_cache_dtype fp8                      # ✅ Économie mémoire
--enable-auto-tool-choice                 # ✅ Tool calling
--tool-call-parser hermes                 # ✅ Compatible
--reasoning-parser qwen3                  # ✅ Natif Qwen3
--distributed-executor-backend=mp         # ✅ Multiprocessing
--rope_scaling '{"rope_type":"yarn","factor":4.0,...}'  # ✅ Extension contexte
```

---

## Procédure de Déploiement

### Méthode 1 : Déploiement avec Monitoring Intégré (RECOMMANDÉ)

```powershell
# Script complet avec monitoring automatique
pwsh -c "./myia_vllm/scripts/deploy_medium_monitored.ps1"
```

**Avantages** :
- ✅ Monitoring automatique toutes les 10s
- ✅ Détection erreurs en temps réel
- ✅ Timeout 10 minutes configurable
- ✅ Logs détaillés sauvegardés

### Méthode 2 : Déploiement Manuel

#### Étape 1 : Arrêt du service existant (si applicable)

```bash
docker compose \
  -f myia_vllm/configs/docker/docker-compose.yml \
  -f myia_vllm/configs/docker/profiles/medium.yml \
  down --remove-orphans
```

#### Étape 2 : Vérification de l'environnement

```bash
# Vérifier que les GPUs sont libres
nvidia-smi

# Vérifier l'espace disque
df -h | grep vllm

# Vérifier que le port 5002 est libre
netstat -tuln | grep 5002
```

#### Étape 3 : Déploiement

```bash
docker compose \
  -f myia_vllm/configs/docker/docker-compose.yml \
  -f myia_vllm/configs/docker/profiles/medium.yml \
  up -d --build --force-recreate
```

**Options expliquées** :
- `-d` : Mode détaché (background)
- `--build` : Rebuild si changements Dockerfile
- `--force-recreate` : Recréer conteneurs existants

#### Étape 4 : Vérification immédiate

```bash
# Vérifier que le conteneur démarre
docker ps -a | grep myia-vllm-medium-qwen3

# Suivre les logs en temps réel
docker logs -f myia-vllm-medium-qwen3
```

---

## Monitoring et Surveillance

### Script de Monitoring Automatique

**Localisation** : `myia_vllm/scripts/monitor_medium.ps1`

```powershell
# Monitoring avec intervalles personnalisés
pwsh -c "./myia_vllm/scripts/monitor_medium.ps1 -IntervalSeconds 10 -TimeoutMinutes 10"
```

**Fonctionnalités** :
- ✅ Surveillance status conteneur toutes les 10s
- ✅ Extraction derniers logs (20 lignes)
- ✅ Détection erreurs critiques (ERROR, FATAL, OOM)
- ✅ Confirmation état healthy
- ✅ Timeout configurable (défaut 10 min)

### Surveillance Manuelle

#### Vérifier le Status

```bash
# Status conteneur
docker ps --filter "name=myia-vllm-medium-qwen3"

# Status détaillé
docker inspect myia-vllm-medium-qwen3 | grep -A 10 Health
```

#### Logs en Temps Réel

```bash
# Logs complets
docker logs -f myia-vllm-medium-qwen3

# Filtrer erreurs
docker logs myia-vllm-medium-qwen3 2>&1 | grep -i error

# Dernières 50 lignes
docker logs myia-vllm-medium-qwen3 --tail 50
```

#### Métriques GPU

```bash
# Utilisation GPU en temps réel
watch -n 2 nvidia-smi

# GPU du conteneur spécifique
docker exec myia-vllm-medium-qwen3 nvidia-smi
```

### Logs Critiques à Surveiller

**Phase 1 : Démarrage (0-60s)**
```
✅ "Starting vLLM engine"
✅ "Initializing Qwen/Qwen3-32B-AWQ"
⚠️ Erreurs potentielles : "CUDA out of memory", "Failed to load model"
```

**Phase 2 : Chargement Modèle (60-300s)**
```
✅ "Loading model weights"
✅ "Loading safetensors checkpoint"
✅ "Model loaded successfully"
⚠️ Erreurs potentielles : "Connection timeout", "Download failed"
```

**Phase 3 : Initialisation Engine (300-360s)**
```
✅ "Initializing KV cache"
✅ "Starting scheduler"
✅ "Server is ready"
✅ "Application startup complete"
⚠️ Erreurs potentielles : "Failed to initialize", "Scheduler error"
```

**Phase 4 : Healthy (360s+)**
```
✅ Health check: "status: (healthy)"
✅ "Uvicorn running on http://0.0.0.0:8000"
```

---

## Validation Post-Déploiement

### 1. Test Health Endpoint

```bash
# Test endpoint /health
curl -f http://localhost:5002/health

# Réponse attendue
# HTTP 200 OK
# {"status": "ok"}
```

### 2. Test Models Endpoint

```bash
# Lister modèles disponibles
curl http://localhost:5002/v1/models

# Réponse attendue
# {
#   "object": "list",
#   "data": [{
#     "id": "Qwen/Qwen3-32B-AWQ",
#     "object": "model",
#     ...
#   }]
# }
```

### 3. Test Génération Simple

```bash
curl -X POST http://localhost:5002/v1/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${VLLM_API_KEY_MEDIUM}" \
  -d '{
    "model": "Qwen/Qwen3-32B-AWQ",
    "prompt": "Hello, how are you?",
    "max_tokens": 50
  }'
```

### 4. Test Tool Calling

```python
# Utiliser le script de test existant
python myia_vllm/tests/scripts/tests/test_qwen3_tool_calling.py \
  --endpoint http://localhost:5002/v1/chat/completions \
  --api-key ${VLLM_API_KEY_MEDIUM}
```

**📚 Script complet** : [`test_qwen3_tool_calling.py`](../../tests/scripts/tests/test_qwen3_tool_calling.py)

### 5. Test Reasoning

```python
# Utiliser le script de test existant
python myia_vllm/tests/scripts/tests/test_reasoning.py \
  --endpoint http://localhost:5002/v1/chat/completions \
  --api-key ${VLLM_API_KEY_MEDIUM}
```

**📚 Script complet** : [`test_reasoning.py`](../../tests/scripts/tests/test_reasoning.py)

### Checklist de Validation

- [ ] ✅ Conteneur status: `Up` et `(healthy)`
- [ ] ✅ Endpoint `/health` répond HTTP 200
- [ ] ✅ Endpoint `/v1/models` liste Qwen3-32B-AWQ
- [ ] ✅ GPUs utilisés : CUDA 0 et 1 (via nvidia-smi)
- [ ] ✅ Memory utilization : ~95% sur les 2 GPUs
- [ ] ✅ Test génération simple fonctionne
- [ ] ✅ Test tool calling réussit
- [ ] ✅ Test reasoning réussit
- [ ] ✅ Aucune erreur CUDA dans les logs
- [ ] ✅ Aucun OOM event dans les logs

---

## Troubleshooting

### Problème 1 : Conteneur ne démarre pas

**Symptômes** :
```bash
docker ps -a  # Status: Exited (1)
```

**Diagnostic** :
```bash
# Vérifier les logs d'erreur
docker logs myia-vllm-medium-qwen3 2>&1 | tail -50
```

**Solutions courantes** :

1. **Token HuggingFace manquant/invalide**
   ```bash
   # Vérifier dans .env
   grep HUGGING_FACE_HUB_TOKEN myia_vllm/.env
   
   # Tester le token
   curl -H "Authorization: Bearer ${HUGGING_FACE_HUB_TOKEN}" \
     https://huggingface.co/api/whoami
   ```

2. **GPUs non disponibles**
   ```bash

### Problème 3 : GPUs Non Détectés ("Failed to infer device type")

**Symptômes** :
```bash
docker logs myia-vllm-medium-qwen3
# RuntimeError: Failed to infer device type
# ImportError: libcuda.so.1: cannot open shared object file
# INFO: No platform detected, vLLM is running on UnspecifiedPlatform
```

**Diagnostic** :

1. **Vérifier runtime NVIDIA dans Docker** :
   ```bash
   docker info | grep -i nvidia
   # Doit afficher: Runtimes: nvidia runc
   ```

2. **Tester GPU dans conteneur basique** :
   ```bash
   docker run --rm --runtime=nvidia nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
   # Doit lister les 3x RTX 4090
   ```

3. **Vérifier configuration Docker Compose** :
   ```bash
   # La syntaxe deploy.resources.reservations est pour Docker SWARM
   # Elle ne fonctionne PAS avec Docker Compose standalone
   ```

**Solution** :

Utiliser la syntaxe Docker Compose correcte dans [`medium.yml`](../../configs/docker/profiles/medium.yml) :

```yaml
services:
  vllm-medium-qwen3:
    runtime: nvidia              # ✅ Runtime NVIDIA explicite
    ipc: host                     # ✅ IPC pour communication inter-GPU
    shm_size: '16gb'             # ✅ Mémoire partagée pour vLLM
    environment:
      - NVIDIA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES_MEDIUM:-0,1}
      - HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN}
```

**Validation du Fix** :
```powershell
# Déploiement avec script officiel
pwsh -File scripts/deploy_medium_monitored.ps1

# Le monitoring doit afficher :
# ✅ Automatically detected platform cuda
# ✅ GPU KV cache size: 195,312 tokens
# ✅ Available KV cache memory: 11.92 GiB
# ✅ Status: healthy
```

**Références** :
- Docker Compose GPU : [`runtime: nvidia`](https://docs.docker.com/compose/gpu-support/)
- vLLM Best Practices : `ipc: host` + `shm_size` requis
- Fix appliqué : 2025-10-16

   # Vérifier NVIDIA runtime
   docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
   
   # Vérifier CUDA_VISIBLE_DEVICES
   echo $CUDA_VISIBLE_DEVICES_MEDIUM
   ```

3. **Port déjà utilisé**
   ```bash
   # Vérifier port 5002
   netstat -tuln | grep 5002
   
   # Changer le port dans .env si nécessaire
   VLLM_PORT_MEDIUM=5003
   ```

### Problème 2 : CUDA Out of Memory (OOM)

**Symptômes** :
```
RuntimeError: CUDA out of memory
```

**Solutions** :

1. **Vérifier mémoire GPU disponible**
   ```bash
   nvidia-smi --query-gpu=memory.free,memory.total --format=csv
   ```

2. **Réduire gpu-memory-utilization (temporaire)**
   ```yaml
   # Dans .env
   GPU_MEMORY_UTILIZATION_MEDIUM=0.90  # Passer de 0.95 à 0.90
   ```

3. **Vérifier qu'aucun autre processus n'utilise les GPUs**
   ```bash
   nvidia-smi | grep -A 3 Processes
   
   # Libérer si nécessaire
   kill -9 <PID>
   ```

### Problème 3 : Modèle ne se charge pas

**Symptômes** :
```
Failed to load model weights
Connection timeout
```

**Solutions** :

1. **Vérifier cache HuggingFace**
   ```bash
   # Localisation cache (selon OS)
   # Linux/WSL: ~/.cache/huggingface/hub
   # Windows: %USERPROFILE%\.cache\huggingface\hub
   
   # Vérifier si modèle téléchargé
   ls -lh ~/.cache/huggingface/hub/ | grep Qwen3-32B-AWQ
   ```

2. **Forcer re-téléchargement**
   ```bash
   # Supprimer cache modèle
   rm -rf ~/.cache/huggingface/hub/models--Qwen--Qwen3-32B-AWQ
   
   # Redémarrer conteneur
   docker compose ... up -d --force-recreate
   ```

3. **Vérifier connexion HuggingFace**
   ```bash
   # Test connexion
   curl -I https://huggingface.co/Qwen/Qwen3-32B-AWQ
   ```

### Problème 4 : Health Check ne passe jamais

**Symptômes** :
```bash
docker ps  # Status: (unhealthy)
```

**Solutions** :

1. **Vérifier que le modèle charge**
   ```bash
   # Suivre logs en temps réel
   docker logs -f myia-vllm-medium-qwen3
   
   # Chercher "Model loaded successfully"
   ```

2. **Augmenter start_period si chargement lent**
   ```yaml
   # Dans profiles/medium.yml
   healthcheck:
     start_period: 600s  # 10 min au lieu de 5 min
   ```

3. **Tester manuellement le endpoint**
   ```bash
   # Depuis l'hôte
   curl -f http://localhost:5002/health
   
   # Depuis le conteneur
   docker exec myia-vllm-medium-qwen3 curl -f http://localhost:8000/health
   ```

### Problème 5 : Performance dégradée

**Symptômes** :
- Latence élevée (>5s pour première token)
- Throughput faible (<50 tokens/sec)

**Solutions** :

1. **Vérifier utilisation GPU**
   ```bash
   watch -n 1 nvidia-smi
   # GPU-Util devrait être ~90-100% pendant inférence
   ```

2. **Vérifier contexte utilisé**
   ```bash
   # Dans les logs, chercher
   docker logs myia-vllm-medium-qwen3 | grep "context_len"
   ```

3. **Vérifier paramètres quantization**
   ```bash
   # Confirmer awq_marlin actif
   docker logs myia-vllm-medium-qwen3 | grep quantization
   # Devrait voir: "Using quantization: awq_marlin"
   ```

---

## Commandes de Référence Rapide

### Déploiement
```bash
# Avec monitoring
pwsh -c "./myia_vllm/scripts/deploy_medium_monitored.ps1"

# Manuel
docker compose -f myia_vllm/configs/docker/docker-compose.yml \
  -f myia_vllm/configs/docker/profiles/medium.yml up -d --force-recreate
```

### Monitoring
```bash
# Logs temps réel
docker logs -f myia-vllm-medium-qwen3

# Status
docker ps --filter "name=myia-vllm-medium-qwen3"

# GPU
nvidia-smi
```

### Tests
```bash
# Health
curl -f http://localhost:5002/health

# Models
curl http://localhost:5002/v1/models

# Tool calling
python myia_vllm/tests/scripts/tests/test_qwen3_tool_calling.py
```

### Arrêt
```bash
# Arrêt propre
docker compose -f myia_vllm/configs/docker/docker-compose.yml \
  -f myia_vllm/configs/docker/profiles/medium.yml down --remove-orphans

# Force stop
docker stop myia-vllm-medium-qwen3
docker rm myia-vllm-medium-qwen3
```

---

## Prochaines Étapes

Après déploiement réussi :

1. **Benchmarking** : Utiliser `qwen3_benchmark/` pour tests de charge
2. **Monitoring Production** : Intégrer Prometheus/Grafana si nécessaire
3. **Optimisation** : Ajuster paramètres selon métriques réelles
4. **Documentation** : Mettre à jour ce guide avec retours terrain

---

## Références

### Documentation Interne

- **Configuration validée** : [`MEDIUM_SERVICE_PARAMETERS.md`](../docker/MEDIUM_SERVICE_PARAMETERS.md)
- **Architecture Docker** : [`ARCHITECTURE.md`](../docker/ARCHITECTURE.md)
- **Configuration .env** : [`ENV_CONFIGURATION.md`](../setup/ENV_CONFIGURATION.md)

### Scripts

- **Monitoring** : `myia_vllm/scripts/monitor_medium.ps1`
- **Déploiement** : `myia_vllm/scripts/deploy_medium_monitored.ps1`
- **Tests** : `myia_vllm/tests/scripts/tests/test_qwen3_tool_calling.py`

### Documentation Externe

- **vLLM Official** : https://docs.vllm.ai/
- **Qwen3 Model Card** : https://huggingface.co/Qwen/Qwen3-32B-AWQ
- **Docker Compose** : https://docs.docker.com/compose/

---

**Dernière mise à jour** : 2025-10-16  
**Mission** : SDDD Mission 9 - Redéploiement Service Medium  
**Prochaine révision** : Après premier déploiement production