# Mission 18 : Rapport de Préparation de la Migration

**Date** : 2025-10-26  
**Méthodologie** : SDDD (Semantic Documentation Driven Design)  
**Statut** : ✅ COMPLÉTÉ

---

## 1. Résumé Exécutif

Cette mission a permis de préparer l'infrastructure Docker pour le déploiement du modèle Qwen3-VL-32B-Instruct-FP8 en créant un backup de la configuration existante et en définissant un nouveau profil de service `medium-vl`.

### Livrables

| Livrable | Statut | Localisation |
|----------|--------|--------------|
| Backup configuration `medium` | ✅ | [`myia_vllm/configs/docker/profiles/medium.yml.bak`](myia_vllm/configs/docker/profiles/medium.yml.bak) |
| Nouveau profil `medium-vl` | ✅ | [`myia_vllm/configs/docker/profiles/medium-vl.yml`](myia_vllm/configs/docker/profiles/medium-vl.yml) |
| Documentation mise à jour | ✅ | [`myia_vllm/docs/docker/ARCHITECTURE.md`](myia_vllm/docs/docker/ARCHITECTURE.md) |
| Rapport de mission | ✅ | Ce document |

---

## 2. Backup de la Configuration

**Fichier source** : [`medium.yml`](myia_vllm/configs/docker/profiles/medium.yml)  
**Fichier de backup** : [`medium.yml.bak`](myia_vllm/configs/docker/profiles/medium.yml.bak)  
**Statut** : ✅ Créé

**Commande utilisée** :
```powershell
Copy-Item -Path 'myia_vllm/configs/docker/profiles/medium.yml' -Destination 'myia_vllm/configs/docker/profiles/medium.yml.bak'
```

**Justification** : Le backup permet un retour en arrière facile vers la configuration `medium` actuelle (Qwen3-32B-AWQ) en cas de besoin.

---

## 3. Nouveau Profil `medium-vl`

### 3.1. Caractéristiques Principales

**Fichier** : [`myia_vllm/configs/docker/profiles/medium-vl.yml`](myia_vllm/configs/docker/profiles/medium-vl.yml)  
**Port** : `5003`  
**Modèle** : `Qwen/Qwen3-VL-32B-Instruct-FP8`  
**Statut** : ✅ Créé

### 3.2. Paramètres Vision Configurés

| Paramètre | Valeur | Justification |
|-----------|--------|---------------|
| `--limit-mm-per-prompt` | `image:3,video:0` | Limite à 3 images/requête, désactive vidéos (économie VRAM) |
| `--mm-processor-kwargs` | `max_pixels:599040` | Résolution max 768x768 (vs défaut 1280×28×28) |
| `--skip-mm-profiling` | `true` | Bypass profiling vision encoder (~500MB VRAM économisés) |
| `--mm-encoder-tp-mode` | `replicate` | Mode conservatif TP pour vision encoder |

### 3.3. Différences avec le Profil `medium`

| Aspect | `medium` (AWQ) | `medium-vl` (FP8) |
|--------|----------------|-------------------|
| **Modèle** | Qwen3-32B-AWQ | Qwen3-VL-32B-Instruct-FP8 |
| **Port** | 5002 | 5003 |
| **Quantization** | `awq_marlin` | FP8 (natif modèle) |
| **GPU Memory Util** | 0.95 | 0.85 (plus conservatif pour vision) |
| **Paramètres vision** | ❌ Aucun | ✅ 4 paramètres spécifiques |
| **Container name** | `myia_vllm-medium-qwen3` | `myia_vllm-medium-vl-qwen3` |

### 3.4. Configuration Complète

```yaml
services:
  vllm-medium-vl-qwen3:
    image: vllm/vllm-openai:latest
    container_name: myia_vllm-medium-vl-qwen3
    command: >
      --host 0.0.0.0
      --port ${VLLM_PORT_MEDIUM_VL:-5003}
      --model Qwen/Qwen3-VL-32B-Instruct-FP8
      --api-key ${VLLM_API_KEY_MEDIUM_VL}
      
      --tensor-parallel-size 2
      --gpu-memory-utilization 0.85
      --max-model-len 131072
      --kv-cache-dtype fp8
      --enable-chunked-prefill
      --dtype ${DTYPE_MEDIUM_VL:-half}
      --enable-auto-tool-choice
      --tool-call-parser hermes
      --distributed-executor-backend=mp
      --rope_scaling '{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":32768}'
      --swap-space 16
      
      --limit-mm-per-prompt image:3,video:0
      --mm-processor-kwargs '{"max_pixels":599040}'
      --skip-mm-profiling
      --mm-encoder-tp-mode replicate
    runtime: nvidia
    ipc: host
    shm_size: '16gb'
    environment:
      - NVIDIA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES_MEDIUM_VL:-0,1}
      - HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN}
    ports:
      - "${VLLM_PORT_MEDIUM_VL:-5003}:${VLLM_PORT_MEDIUM_VL:-5003}"
    healthcheck:
        test: ["CMD", "curl", "-f", "http://localhost:${VLLM_PORT_MEDIUM_VL:-5003}/health"]
        interval: 30s
        timeout: 10s
        retries: 5
        start_period: 300s
```

---

## 4. Documentation

### 4.1. Fichier Mis à Jour

**Fichier** : [`myia_vllm/docs/docker/ARCHITECTURE.md`](myia_vllm/docs/docker/ARCHITECTURE.md)  
**Statut** : ✅ Mis à jour

### 4.2. Contenu Ajouté

Une nouvelle section a été ajoutée pour documenter le profil `medium-vl` :

- **Caractéristiques principales** : Service, modèle, GPUs, contexte, mémoire, port
- **Paramètres critiques** : Tableau détaillé des paramètres vision et leurs justifications
- **Commande de déploiement** : Instruction pour lancer le service

### 4.3. Découvrabilité Sémantique

**Requête de test** : `"docker profile for multimodal Qwen3-VL vision model"`  
**Score attendu** : ≥ 0.70

La documentation mise à jour inclut :
- ✅ Mots-clés explicites : "multimodal", "vision", "Qwen3-VL"
- ✅ Paramètres vision documentés avec justifications
- ✅ Comparaison avec profil `medium` pour contexte
- ✅ Liens vers Mission 17 pour détails techniques

---

## 5. Préparation pour la Mission 19 (Déploiement)

### 5.1. Variables d'Environnement Requises

Les variables suivantes doivent être ajoutées au fichier `.env` :

```bash
# Service Medium-VL (Vision)
VLLM_PORT_MEDIUM_VL=5003
VLLM_API_KEY_MEDIUM_VL=your_api_key_here
CUDA_VISIBLE_DEVICES_MEDIUM_VL=0,1
DTYPE_MEDIUM_VL=half
```

### 5.2. Prochaines Étapes

**Mission 19** devra inclure :

1. **Ajout des variables d'environnement** :
   - Éditer `.env` avec les variables `MEDIUM_VL`
   - Valider que `HUGGING_FACE_HUB_TOKEN` est configuré

2. **Déploiement du service** :
   ```bash
   docker compose \
     -f myia_vllm/configs/docker/docker-compose.yml \
     -f myia_vllm/configs/docker/profiles/medium-vl.yml \
     up -d --build --force-recreate
   ```

3. **Monitoring VRAM** :
   ```bash
   # Terminal 1 : Suivre les logs
   docker logs -f myia_vllm-medium-vl-qwen3
   
   # Terminal 2 : Monitorer VRAM
   nvidia-smi -l 1
   ```

4. **Validation du healthcheck** :
   - Attendre que le conteneur atteigne l'état `(healthy)`
   - Vérifier l'endpoint : `curl http://localhost:5003/health`

5. **Test basique vision** :
   - Exécuter [`myia_vllm/tests/vision/test_qwen3-vl_basic.py`](myia_vllm/tests/vision/test_qwen3-vl_basic.py)
   - Valider que la réponse vision est cohérente

### 5.3. Critères de Validation Mission 19

**La Mission 19 sera considérée réussie si** :

1. ✅ Service `medium-vl` démarre sans erreur
2. ✅ VRAM totale utilisée ≤ 24GB/GPU (2× RTX 4090)
3. ✅ Healthcheck passe avec succès
4. ✅ Script de test vision retourne une réponse cohérente
5. ✅ Stabilité confirmée (0 crash sur 20+ requêtes)

### 5.4. Estimation VRAM

D'après l'analyse de la Mission 17 :

| Composant | VRAM Estimée |
|-----------|--------------|
| Modèle Weights (FP8) | ~18-20 GB |
| Vision Encoder | ~2-4 GB |
| KV Cache | ~5-10 GB (variable) |
| Overhead système | ~2-3 GB |
| **Total Estimé** | **~22-24 GB/GPU** |

**Conclusion** : Compatible avec 2× RTX 4090 (48GB total).

---

## 6. Grounding Sémantique Mission 18

### 6.1. Recherches Effectuées

**Recherche 1** : `"docker compose multiple profiles override"`  
- **Résultats** : 20+ fichiers
- **Fichiers clés** : [`ARCHITECTURE.md:253-289`](myia_vllm/docs/docker/ARCHITECTURE.md:253-289)
- **Découvertes** : Stratégie de composition multi-profils, commandes de référence

**Recherche 2** : `"vLLM docker configuration for multimodal models"`  
- **Résultats** : 30+ occurrences
- **Fichiers clés** : [`conserving_memory.md:90-126`](docs/configuration/conserving_memory.md:90-126)
- **Découvertes** : Paramètres `limit_mm_per_prompt`, `mm_processor_kwargs`

### 6.2. Documentation Consultée

- [`myia_vllm/configs/docker/profiles/medium.yml`](myia_vllm/configs/docker/profiles/medium.yml) : Configuration de référence
- [`myia_vllm/docs/missions/MISSION_17_VISION_SUPPORT_ANALYSIS.md`](myia_vllm/docs/missions/MISSION_17_VISION_SUPPORT_ANALYSIS.md) : Paramètres vision recommandés
- [`myia_vllm/docs/docker/ARCHITECTURE.md`](myia_vllm/docs/docker/ARCHITECTURE.md) : Architecture des profils Docker

---

## 7. Fichiers Créés/Modifiés

### 7.1. Nouveaux Fichiers

| Fichier | Lignes | Description |
|---------|--------|-------------|
| [`myia_vllm/configs/docker/profiles/medium.yml.bak`](myia_vllm/configs/docker/profiles/medium.yml.bak) | 37 | Backup configuration `medium` |
| [`myia_vllm/configs/docker/profiles/medium-vl.yml`](myia_vllm/configs/docker/profiles/medium-vl.yml) | 40 | Nouveau profil multimodal |
| [`myia_vllm/docs/missions/MISSION_18_MIGRATION_PREPARATION.md`](myia_vllm/docs/missions/MISSION_18_MIGRATION_PREPARATION.md) | ~300 | Ce rapport |

### 7.2. Fichiers Modifiés

| Fichier | Modification | Localisation |
|---------|--------------|--------------|
| [`myia_vllm/docs/docker/ARCHITECTURE.md`](myia_vllm/docs/docker/ARCHITECTURE.md) | Ajout section profil `medium-vl` | Ligne 103 (insertion) |

---

## 8. Références

### 8.1. Missions Précédentes

- **Mission 16** : [`MISSION_16_QWEN3-VL_RESEARCH.md`](myia_vllm/docs/missions/MISSION_16_QWEN3-VL_RESEARCH.md) - Recherche modèle Qwen3-VL
- **Mission 17** : [`MISSION_17_VISION_SUPPORT_ANALYSIS.md`](myia_vllm/docs/missions/MISSION_17_VISION_SUPPORT_ANALYSIS.md) - Analyse support vision vLLM

### 8.2. Documentation Technique

- [vLLM Multimodal Inputs](https://docs.vllm.ai/en/latest/features/multimodal_inputs.html)
- [vLLM Conserving Memory](https://docs.vllm.ai/en/latest/configuration/conserving_memory.html)
- [vLLM Qwen3-VL Guide](https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3-VL.html)

---

**Document créé le** : 2025-10-26  
**Méthodologie** : SDDD (Semantic Documentation Driven Design)  
**Version** : 1.0 - Final  
**Prochaine mission** : MISSION 19 - Déploiement Service Medium-VL