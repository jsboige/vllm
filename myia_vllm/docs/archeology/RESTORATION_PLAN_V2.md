# PLAN DE RESTAURATION DÉTAILLÉ V2 - Projet myia_vllm

**Date de Création :** 23 septembre 2025  
**Basé sur :** Analyse Archéologique Exhaustive  
**Méthodologie :** SDDD (Semantic Documentation Driven Design)  
**Responsable :** Roo Architect Mode  
**Version :** 2.0 - Plan Final de Consolidation  

---

## Executive Summary

Ce plan de restauration détaillé s'appuie sur l'analyse archéologique exhaustive qui a identifié les **artefacts les plus stables** de la période pré-corruption (fin juillet - début août 2025). Le projet ayant déjà subi une **transformation architecturale majeure** selon la méthodologie SDDD, ce plan V2 se concentre sur la **consolidation finale** et l'élimination des dernières **entropies résiduelles** pour atteindre l'état stable cible.

### Artefacts Stables de Référence

**Configuration Technique Validée (Score Sémantique 0.913) :**
- **Source de Vérité :** `00_MASTER_CONFIGURATION_GUIDE.md` (document maître consolidé)
- **Architecture Docker :** 3 profils modulaires (Micro 1.7B, Mini 8B, Medium 32B)
- **Image Officielle :** `vllm/vllm-openai:v0.9.2`
- **Optimisations vLLM :** FP8, chunked-prefill, prefix-caching, yarn RoPE scaling

### Métriques de Restauration Cibles

| Dimension | État Initial | État Actuel | **Cible V2** | Progression |
|-----------|--------------|-------------|---------------|-------------|
| **Scripts** | 57+ scripts | 8 essentiels + redondances | **8 scripts uniques** | **-86%** |
| **Docker Compose** | Prolifération | 15+ versions | **3 fichiers modulaires** | **-80%** |
| **Documentation** | >150 fichiers | ~10 fichiers | **10 fichiers max** | **-94%** ✅ |
| **Découvrabilité** | Score 0.40 | Score 0.67+ | **Score >0.67** | **+67%** ✅ |

---

## PHASE 1 : DIAGNOSTIC ET VALIDATION DE L'ÉTAT ACTUEL

### 1.1 Audit de Conformité aux Artefacts Stables

#### ✅ Conformités Validées

**Architecture Scripturale Moderne :**
```
myia_vllm/scripts/
├── deploy/deploy-qwen3.ps1       # ✅ Script principal unifié
├── validate/validate-services.ps1 # ✅ Validation consolidée  
├── maintenance/monitor-logs.ps1   # ✅ Monitoring moderne
├── archived/                      # ✅ Archives organisées
└── README.md                      # ✅ Documentation centralisée
```

**Architecture Documentaire SDDD :**
```
myia_vllm/docs/qwen3/
├── 00_MASTER_CONFIGURATION_GUIDE.md  # ✅ Source de vérité (482 lignes)
├── README.md                          # ✅ Pointeur vers maître  
├── SECRETS-README.md                  # ✅ Guide sécurité
├── TEST-README.md                     # ✅ Guide tests
└── [Guides spécialisés]               # ✅ Complémentaires
```

#### ❌ Non-Conformités Critiques Détectées

**1. Entropie Docker Compose Résiduelle :**
- **État Détecté :** 15+ fichiers docker-compose avec versions multiples
- **Impact :** Violation du principe d'architecture modulaire validée
- **Priorité :** CRITIQUE

**Fichiers Non-Conformes Identifiés :**
```
myia_vllm/
├── docker-compose-medium-qwen3-fixed.yml          # ❌ Version redondante
├── docker-compose-medium-qwen3-memory-optimized.yml # ❌ Version redondante  
├── docker-compose-medium-qwen3-optimized.yml      # ❌ Version redondante
├── docker-compose-micro-qwen3-improved.yml        # ❌ Version redondante
├── docker-compose-micro-qwen3-new.yml             # ❌ Version redondante
├── docker-compose-mini-qwen3-optimized.yml        # ❌ Version redondante
└── [8+ autres versions...]                        # ❌ Pattern entropique
```

**2. Scripts Redondants Persistants :**
- **Répertoire powershell/ :** 15+ scripts redondants non-archivés
- **Tests multiples :** python/tests/ contient 7 fichiers de test vs 1 canonique

**3. Artéfacts Obsolètes :**
- **Dockerfile.qwen3 :** Contradiction avec stratégie image officielle
- **Configurations personnalisées :** Désalignement stratégique

### 1.2 Points de Contrôle de Validation Sémantique

#### Test 1 : Découvrabilité Architecture Cible
**Requête :** `"architecture docker modulaire qwen3 avec image officielle vllm"`  
**Score Cible :** ≥0.67  
**Status :** À valider post-restauration

#### Test 2 : Configuration Optimale  
**Requête :** `"déploiement qwen3 medium 32b avec optimisations fp8 et rope scaling"`  
**Score Cible :** ≥0.67  
**Status :** À valider post-restauration

---

## PHASE 2 : CONSOLIDATION DOCKER COMPOSE MODULAIRE

### 2.1 Architecture Cible Selon Artefacts Stables

**Configuration Docker Modulaire Validée :**
```yaml
myia_vllm/
├── docker-compose-qwen3-medium.yml   # 🎯 Qwen2-32B-Instruct-AWQ (2 GPU)
├── docker-compose-qwen3-micro.yml    # 🎯 Qwen2-1.7B-Instruct-fp8 (1 GPU)  
├── docker-compose-qwen3-mini.yml     # 🎯 Qwen1.5-0.5B-Chat (1 GPU)
└── .env                               # 🎯 Configuration centralisée
```

### 2.2 Actions de Consolidation Prioritaires

#### Étape 2.1 : Création des Fichiers Cibles
**Basé sur :** Document maître `00_MASTER_CONFIGURATION_GUIDE.md` lignes 99-248

**Fichier 1 : docker-compose-qwen3-medium.yml**
```yaml
services:
  vllm-medium:
    image: vllm/vllm-openai:v0.9.2
    environment:
      - HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN}
      - VLLM_ATTENTION_BACKEND=FLASHINFER
    ports:
      - "${VLLM_PORT_MEDIUM:-5002}:8000"
    command:
      - "--model=Qwen/Qwen2-32B-Instruct-AWQ"
      - "--quantization=awq_marlin"
      - "--tensor-parallel-size=2"
      - "--kv-cache-dtype=fp8"
      - "--enable-chunked-prefill"
      - "--enable-prefix-caching"
      - "--tool-call-parser=hermes"
      - "--reasoning-parser=qwen3"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['0', '1']
              capabilities: [gpu]
```

**Fichier 2 : docker-compose-qwen3-micro.yml**
```yaml
services:
  vllm-micro:
    image: vllm/vllm-openai:v0.9.2
    environment:
      - CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES_MICRO:-2}
      - HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN}
      - VLLM_ATTENTION_BACKEND=FLASHINFER
    ports:
      - "${VLLM_PORT_MICRO:-5000}:8000"
    command:
      - "--model=Qwen/Qwen2-1.7B-Instruct-fp8"
      - "--quantization=fp8"
      - "--kv-cache-dtype=fp8"
      - "--enable-chunked-prefill"
      - "--enable-prefix-caching"
      - "--tool-call-parser=hermes"
      - "--reasoning-parser=qwen3"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['2']
              capabilities: [gpu]
```

**Fichier 3 : docker-compose-qwen3-mini.yml**
```yaml
services:
  vllm-mini:
    image: vllm/vllm-openai:v0.9.2
    environment:
      - CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES_MINI:-2}
      - HUGGING_FACE_HUB_TOKEN=${HUGGING_FACE_HUB_TOKEN}
    ports:
      - "${VLLM_PORT_MINI:-5001}:8000"
    command:
      - "--model=Qwen/Qwen2-7B-Instruct-AWQ"
      - "--quantization=awq"
      - "--kv-cache-dtype=fp8"
      - "--enable-chunked-prefill"
      - "--enable-prefix-caching"
      - "--tool-call-parser=hermes"
      - "--reasoning-parser=qwen3"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['2']
              capabilities: [gpu]
```

#### Étape 2.2 : Suppression des Versions Redondantes
**Action :** Archivage sécurisé de 15+ fichiers docker-compose obsolètes

**Fichiers à Archiver :**
```bash
# Versions redondantes Medium
docker-compose-medium-qwen3-fixed.yml → archived/
docker-compose-medium-qwen3-memory-optimized.yml → archived/
docker-compose-medium-qwen3-optimized.yml → archived/
docker-compose-medium-qwen3-original-parser.yml → archived/

# Versions redondantes Micro  
docker-compose-micro-qwen3-improved.yml → archived/
docker-compose-micro-qwen3-new.yml → archived/
docker-compose-micro-qwen3-optimized.yml → archived/
docker-compose-micro-qwen3-original-parser.yml → archived/

# Versions redondantes Mini
docker-compose-mini-qwen3-optimized.yml → archived/
docker-compose-mini-qwen3-original-parser.yml → archived/

# Anciennes conventions de nommage
docker-compose-medium.yml → archived/
docker-compose-micro.yml → archived/  
docker-compose-mini.yml → archived/
docker-compose-large.yml → archived/
```

### 2.3 Validation Post-Consolidation

#### Test Fonctionnel
**Commande de Validation :**
```powershell
.\scripts\deploy\deploy-qwen3.ps1 -Profile medium -DryRun -Verbose
```

**Résultats Attendus :**
- ✅ Détection du fichier docker-compose-qwen3-medium.yml  
- ✅ Configuration GPU 0,1 avec tensor-parallel-size=2
- ✅ Image officielle vllm/vllm-openai:v0.9.2
- ✅ Optimisations FP8 + chunked-prefill activées

---

## PHASE 3 : NETTOYAGE FINAL DES SCRIPTS

### 3.1 Analyse de l'Entropie Scripturale Résiduelle

#### Répertoire powershell/ - Non-Conformités
**État Détecté :** 15 scripts redondants non-archivés
```
myia_vllm/scripts/powershell/
├── deploy-qwen3-services.ps1        # ❌ Redondant avec deploy/deploy-qwen3.ps1
├── start-qwen3-services.ps1         # ❌ Redondant avec deploy/deploy-qwen3.ps1  
├── test-qwen3-services.ps1          # ❌ Redondant avec validate/validate-services.ps1
├── setup-qwen3-environment.ps1      # ❌ Doublon avec racine
├── validate-qwen3-configurations.ps1 # ❌ Doublon avec racine
└── [10+ autres redondants...]       # ❌ Entropie critique
```

#### Tests Python - Prolifération
**État Détecté :** 7 fichiers de test vs 1 canonique
```
myia_vllm/scripts/python/tests/
├── test_qwen3_tool_calling.py         # ✅ Canonique à conserver
├── test_qwen3_tool_calling_custom.py  # ❌ Variant redondant
├── test_qwen3_tool_calling_fixed.py   # ❌ Variant redondant  
├── test_qwen3_deployment.py           # ❌ Doublon fonctionnel
└── [3+ autres variants...]           # ❌ Pattern entropique
```

### 3.2 Actions de Nettoyage Final

#### Étape 3.1 : Archivage Répertoire powershell/
**Action :** Déplacement complet vers archived/powershell-deprecated/

```bash
scripts/powershell/ → scripts/archived/powershell-deprecated/
```

**Justification :** Tous les scripts essentiels ont été modernisés dans l'architecture deploy/, validate/, maintenance/

#### Étape 3.2 : Consolidation Tests Python  
**Action :** Conservation du script canonique uniquement

```bash
# Conserver
python/tests/test_qwen3_tool_calling.py ✅

# Archiver
python/tests/test_qwen3_tool_calling_*.py → archived/tests-deprecated/
python/tests/test_qwen3_deployment.py → archived/tests-deprecated/
```

#### Étape 3.3 : Suppression Artéfacts Obsolètes
```bash
# Dockerfile obsolète (contradiction stratégique)
Dockerfile.qwen3 → archived/build-artifacts/

# Scripts racine redondants  
setup-qwen3-environment.ps1 → archived/ (doublon avec scripts/)
validate-qwen3-configurations.ps1 → archived/ (doublon avec scripts/)
```

### 3.3 Architecture Scripturale Finale Cible

**Architecture Validée (8 Scripts Essentiels) :**
```
myia_vllm/scripts/
├── deploy/
│   └── deploy-qwen3.ps1              # 🎯 Script principal unifié
├── validate/  
│   └── validate-services.ps1         # 🎯 Validation consolidée
├── maintenance/
│   └── monitor-logs.ps1              # 🎯 Monitoring moderne
├── python/
│   ├── client.py                     # 🎯 Client API unifié
│   ├── utils.py                      # 🎯 Utilitaires partagés
│   └── tests/
│       └── test_qwen3_tool_calling.py # 🎯 Test canonique unique
├── archived/                         # 📦 Archives organisées
│   ├── legacy-versions/              # Scripts archéologiques
│   ├── build-related/               # Artéfacts build personnalisé
│   ├── powershell-deprecated/       # Scripts powershell redondants
│   └── tests-deprecated/            # Tests variants
└── README.md                        # 📚 Documentation centralisée
```

---

## PHASE 4 : VALIDATION ET TESTS DE RÉGRESSION

### 4.1 Tests de Validation Fonctionnelle

#### Test 1 : Déploiement Modulaire
**Objectif :** Valider le fonctionnement des 3 profils Docker

```powershell
# Test Micro (1.7B)
.\scripts\deploy\deploy-qwen3.ps1 -Profile micro -DryRun
# Attendu: docker-compose -f docker-compose-qwen3-micro.yml up -d

# Test Mini (8B)  
.\scripts\deploy\deploy-qwen3.ps1 -Profile mini -DryRun
# Attendu: docker-compose -f docker-compose-qwen3-mini.yml up -d

# Test Medium (32B)
.\scripts\deploy\deploy-qwen3.ps1 -Profile medium -DryRun  
# Attendu: docker-compose -f docker-compose-qwen3-medium.yml up -d
```

#### Test 2 : Validation Post-Déploiement
**Objectif :** Valider la santé des services

```powershell
.\scripts\validate\validate-services.ps1 -Endpoint http://localhost:5002/health
# Attendu: Service HEALTHY + métriques GPU
```

#### Test 3 : Tests API Tool-Calling
**Objectif :** Valider les parsers hermes + qwen3

```powershell
python .\scripts\python\tests\test_qwen3_tool_calling.py --endpoint medium
# Attendu: Tool-calling fonctionnel + reasoning parser
```

### 4.2 Tests de Validation Sémantique

#### Test Sémantique 1 : Architecture Restaurée
**Requête :** `"architecture docker modulaire qwen3 consolidée avec image officielle"`  
**Score Cible :** ≥0.67  
**Source Attendue :** `00_MASTER_CONFIGURATION_GUIDE.md`

#### Test Sémantique 2 : Scripts Modernes  
**Requête :** `"scripts de déploiement qwen3 consolidés et modernes"`  
**Score Cible :** ≥0.67  
**Source Attendue :** `scripts/README.md`

#### Test Sémantique 3 : Configuration Optimale
**Requête :** `"optimisations vllm fp8 chunked-prefill pour qwen3 medium"`  
**Score Cible :** ≥0.67  
**Source Attendue :** Document maître ou configuration Docker

### 4.3 Métriques de Réussite Finales

#### Critères Quantitatifs
| Métrique | État Initial | Cible V2 | Validation |
|----------|--------------|----------|-----------|
| **Scripts Totaux** | 57+ | 8 uniques | Comptage fichiers |
| **Docker Compose** | 15+ versions | 3 modulaires | Comptage fichiers |  
| **Découvrabilité** | Score 0.40 | Score ≥0.67 | Tests sémantiques |

#### Critères Qualitatifs
- ✅ **Alignement Stratégique :** 100% image officielle vllm/vllm-openai:v0.9.2
- ✅ **Architecture Modulaire :** 3 profils distincts et fonctionnels
- ✅ **Optimisations Natives :** FP8, chunked-prefill, prefix-caching activées  
- ✅ **Parsers Recommandés :** hermes (tool-calling) + qwen3 (reasoning)

---

## PHASE 5 : CONSOLIDATION ET DOCUMENTATION

### 5.1 Mise à Jour Documentation Maître

#### Sections à Actualiser dans 00_MASTER_CONFIGURATION_GUIDE.md

**Section "Configuration Docker" (lignes 95-248) :**
- ✅ Validation des 3 configurations YAML finales
- ✅ Mise à jour des chemins de fichiers consolidés
- ✅ Suppression des références aux versions obsolètes

**Section "Scripts de déploiement" (lignes 325-342) :**
- ✅ Documentation du script principal deploy-qwen3.ps1
- ✅ Suppression des références aux scripts obsolètes
- ✅ Ajout des exemples de commandes consolidées

### 5.2 Validation Finale SDDD

#### Grounding Sémantique Post-Restauration
**Requête de Contrôle Final :** `"projet myia_vllm restauré architecture moderne qwen3"`  
**Score Cible :** ≥0.70  
**Sources Attendues :**
1. `00_MASTER_CONFIGURATION_GUIDE.md` (score ≥0.67)
2. `scripts/README.md` (score ≥0.65)  
3. `RESTORATION_PLAN_V2.md` (ce document, score ≥0.63)

#### Proof of Concept Fonctionnel
**Test d'Intégration Complet :**
```bash
# 1. Déploiement
.\scripts\deploy\deploy-qwen3.ps1 -Profile all

# 2. Validation  
.\scripts\validate\validate-services.ps1

# 3. Test API
python .\scripts\python\tests\test_qwen3_tool_calling.py

# 4. Monitoring
.\scripts\maintenance\monitor-logs.ps1 -Service vllm-medium
```

### 5.3 Documentation des Changements

#### Rapport de Transformation Final
**Fichier :** `myia_vllm/reports/RESTORATION_V2_COMPLETION_REPORT.md`

**Contenu Requis :**
- 📊 Métriques Before/After quantifiées
- 🔄 Liste complète des fichiers supprimés/archivés/créés
- ✅ Résultats des tests de validation fonctionnelle  
- 🎯 Scores de validation sémantique obtenus
- 📈 Preuves de découvrabilité améliorée

---

## PHASE 6 : POINTS DE CONTRÔLE ET VALIDATION UTILISATEUR

### 6.1 Checkpoints Obligatoires

#### Checkpoint 1 : Validation Architecture Docker  
**Moment :** Avant suppression des versions multiples Docker Compose  
**Action :** Présentation des 3 fichiers consolidés pour approbation
**Critère :** Validation fonctionnelle sur au moins 1 profil

#### Checkpoint 2 : Validation Nettoyage Scripts
**Moment :** Avant archivage du répertoire powershell/  
**Action :** Confirmation que tous les scripts essentiels sont préservés
**Critère :** Tests fonctionnels deploy/validate/maintenance réussis

#### Checkpoint 3 : Validation Finale  
**Moment :** Avant marquage de la restauration comme complète
**Action :** Tests de régression complets + validation sémantique
**Critère :** Toutes les métriques cibles atteintes

### 6.2 Rollback et Récupération

#### Plan de Rollback
**Si Problème Critique Détecté :**
1. **Restauration Docker :** Réactivation d'un fichier docker-compose fonctionnel depuis archived/
2. **Restauration Scripts :** Réactivation depuis scripts/archived/ si nécessaire  
3. **Point de Sauvegarde :** État actuel avant restauration V2 documenté

#### Procédures de Récupération
```powershell
# Rollback Docker Compose
cp archived/docker-compose-medium-qwen3.yml ./docker-compose-qwen3-medium.yml

# Rollback Script Critique  
cp scripts/archived/powershell-deprecated/start-qwen3-services.ps1 ./scripts/
```

---

## ANNEXES

### Annexe A : Configurations Docker Complètes

#### Configuration .env Optimisée
```env
# === CONFIGURATION QWEN3 CONSOLIDÉE ===

# Tokens et Authentification
HUGGING_FACE_HUB_TOKEN=YOUR_TOKEN_HERE
VLLM_API_KEY_MICRO=micro_api_key_here  
VLLM_API_KEY_MINI=mini_api_key_here
VLLM_API_KEY_MEDIUM=medium_api_key_here

# Ports Services
VLLM_PORT_MICRO=5000
VLLM_PORT_MINI=5001  
VLLM_PORT_MEDIUM=5002

# Configuration GPU
CUDA_VISIBLE_DEVICES_MICRO=2
CUDA_VISIBLE_DEVICES_MINI=2
CUDA_VISIBLE_DEVICES_MEDIUM=0,1

# Optimisations vLLM
VLLM_ATTENTION_BACKEND=FLASHINFER
GPU_MEMORY_UTILIZATION=0.9
VLLM_ALLOW_LONG_MAX_MODEL_LEN=1

# Modèles (si personnalisation nécessaire)
MODEL_NAME_MICRO=Qwen/Qwen2-1.7B-Instruct-fp8
MODEL_NAME_MINI=Qwen/Qwen2-7B-Instruct-AWQ
MODEL_NAME_MEDIUM=Qwen/Qwen2-32B-Instruct-AWQ
```

### Annexe B : Commandes de Validation

#### Suite de Tests Post-Restauration
```powershell
# === TESTS DE VALIDATION RESTAURATION V2 ===

# 1. Architecture Docker
Write-Host "=== Test Architecture Docker ==="
Get-ChildItem -Name "docker-compose-qwen3-*.yml" | Should -Be 3

# 2. Scripts Consolidés
Write-Host "=== Test Scripts Consolidés ==="  
.\scripts\deploy\deploy-qwen3.ps1 --help
.\scripts\validate\validate-services.ps1 --help
.\scripts\maintenance\monitor-logs.ps1 --help

# 3. Tests Fonctionnels
Write-Host "=== Tests Fonctionnels ==="
.\scripts\deploy\deploy-qwen3.ps1 -Profile micro -DryRun -Verbose
.\scripts\validate\validate-services.ps1 -DryRun

# 4. Test Sémantique (via API ou script)
Write-Host "=== Test Découvrabilité ==="
# Recherche sémantique: "architecture qwen3 restaurée moderne"
# Score attendu: ≥0.67
```

### Annexe C : Métriques de Performance Attendues

#### Benchmarks Post-Restauration
**Temps de Déploiement :**
- Micro (1.7B): ~2-3 minutes (GPU unique)
- Mini (8B): ~3-5 minutes (GPU unique)  
- Medium (32B): ~5-8 minutes (2 GPU, tensor-parallel)

**Métriques API :**
- Latency P50: <1s (textes courts <4K tokens)
- Throughput: 150+ tokens/sec (Medium), 200+ tokens/sec (Micro/Mini)
- Tool-calling success rate: >95%

**Métriques GPU :**
- Memory utilization: ~90% (selon GPU_MEMORY_UTILIZATION)
- Multi-GPU load balancing: Équilibré sur Medium (GPU 0,1)

---

## Conclusion

Ce plan de restauration V2 s'appuie sur les artefacts archéologiques les plus stables identifiés pour finaliser la transformation du projet `myia_vllm` vers un état **moderne, maintenable et performant**. 

### Impact Transformationnel Attendu

**Stabilité :** Architecture Docker modulaire basée sur l'image officielle vLLM  
**Maintenabilité :** Réduction finale à 8 scripts essentiels uniques  
**Performance :** Optimisations natives FP8 + chunked-prefill + parsers recommandés  
**Découvrabilité :** Validation sémantique ≥0.67 sur les requêtes critiques  

### Prochaines Étapes

1. **Validation du plan** par l'équipe projet
2. **Exécution séquentielle** des phases avec checkpoints  
3. **Tests de régression** complets
4. **Documentation finale** de l'état restauré
5. **Archivage** de ce plan comme référence historique

---

**Document créé le 23 septembre 2025**  
**Méthodologie : SDDD + Archéologie Documentaire**  
**Classification : Plan de Restauration Final - Version Définitive V2**