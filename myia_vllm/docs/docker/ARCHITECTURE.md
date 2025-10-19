# Architecture Docker - Service vLLM

**Date de création**: 2025-10-16  
**Auteur**: SDDD Mission 9 - Redéploiement Service Medium  
**Statut**: ✅ Active

---

## Table des Matières

1. [Vue d'Ensemble](#vue-densemble)
2. [Structure Actuelle](#structure-actuelle)
3. [Fichiers Actifs](#fichiers-actifs)
4. [Fichiers Archivés](#fichiers-archivés)
5. [Convention de Nommage](#convention-de-nommage)
6. [Historique et Rationnelle](#historique-et-rationnelle)

---

## Vue d'Ensemble

L'architecture Docker de myia_vllm utilise une **approche modulaire par profils** pour gérer différentes configurations de services vLLM optimisées selon les besoins de ressources et les modèles déployés.

### Principes Architecturaux

- **Séparation par profils** : Chaque service (micro, mini, medium, large) a son propre fichier de profil
- **Composition Docker Compose** : Utilisation de la fonctionnalité de composition multi-fichiers
- **Variables d'environnement** : Configuration centralisée via `.env`
- **Isolation des configurations** : Pas de configurations redondantes dans l'arborescence active

---

## Structure Actuelle

```
myia_vllm/
├── configs/
│   └── docker/
│       ├── docker-compose.yml          # ⚠️ Fichier de base (à vérifier)
│       └── profiles/
│           └── medium.yml              # ✅ ACTIF - Service Medium
│
├── archived/
│   └── docker_configs_20251016/        # 📦 Archives (15 fichiers)
│
├── scripts/
│   └── archive_docker_configs.ps1     # Script d'archivage
│
└── docs/
    └── docker/
        └── ARCHITECTURE.md             # 📄 Ce document
```

### Répertoires Clés

- **`configs/docker/`** : Configurations Docker actives uniquement
- **`configs/docker/profiles/`** : Profils de services spécifiques
- **`archived/docker_configs_20251016/`** : Configurations obsolètes archivées
- **`scripts/`** : Scripts d'automatisation (déploiement, monitoring, archivage)

---

## Fichiers Actifs

### 1. `configs/docker/profiles/medium.yml`

**Statut** : ✅ ACTIF  
**Rôle** : Configuration du service medium (Qwen3-32B-AWQ)  
**Dernière révision** : 2025-10-16

#### Caractéristiques Principales

```yaml
Service: myia-vllm-medium-qwen3
Modèle: Qwen/Qwen3-32B-AWQ
GPUs: 2 (CUDA_VISIBLE_DEVICES=0,1)
Context Max: 131072 tokens (128k) ✅ OPTIMAL
Memory Util: 0.95
Tensor Parallel: 2
Quantization: awq_marlin
KV Cache: fp8
Port: 8002
```

#### Paramètres Critiques

| Paramètre | Valeur | Justification |
|-----------|--------|---------------|
| `--max-model-len` | 131072 | Taille maximale supportée par Qwen3-32B (128k tokens) |
| `--tensor-parallel-size` | 2 | Requis pour AWQ sur 2 GPUs |
| `--gpu-memory-utilization` | 0.95 | Optimal pour production (balance performance/stabilité) |
| `--quantization` | awq_marlin | Activation-aware Weight Quantization optimisée |
| `--kv_cache_dtype` | fp8 | 8-bit float pour optimisation mémoire cache |

#### Commande de Déploiement

```bash
docker compose \
  -f myia_vllm/configs/docker/docker-compose.yml \
  -f myia_vllm/configs/docker/profiles/medium.yml \
  up -d --build --force-recreate
```

### 2. `configs/docker/docker-compose.yml` (À Vérifier)

**Statut** : ⚠️ À AUDITER  
**Rôle** : Potentiellement fichier de base pour composition  
**Action requise** : Vérifier son contenu et sa nécessité

---

## Fichiers Archivés

### Archive du 2025-10-16

**Localisation** : `myia_vllm/archived/docker_configs_20251016/`  
**Nombre de fichiers** : 15  
**Raison de l'archivage** : Prolifération de configurations redondantes et obsolètes

#### Liste des Fichiers Archivés

| Fichier | Raison de l'archivage | Notes |
|---------|----------------------|-------|
| `docker-compose-large.yml` | Obsolète - Service large non utilisé | Potentiellement réactivable si besoin futur |
| `docker-compose-medium-qwen3-fixed.yml` | Redondant - Version "fixed" d'un bug résolu | Remplacé par `profiles/medium.yml` |
| `docker-compose-medium-qwen3-memory-optimized.yml` | Redondant - Tests d'optimisation mémoire | Optimisations intégrées dans profil actuel |
| `docker-compose-medium-qwen3-original-parser.yml` | Obsolète - Test de parser original | Parser optimisé maintenant standard |
| `docker-compose-medium-qwen3.yml` | Redondant - Version standalone | Remplacé par approche par profils |
| `docker-compose-medium.old.yml` | Obsolète - Ancienne version | Backup historique |
| `docker-compose-medium.yml` | Redondant - Version standalone | Remplacé par `profiles/medium.yml` |
| `docker-compose-micro-qwen3-improved.yml` | Obsolète - Tests d'amélioration | Service micro non prioritaire |
| `docker-compose-micro-qwen3-new.yml` | Redondant - Version "new" | Confusion de nommage |
| `docker-compose-micro-qwen3-original-parser.yml` | Obsolète - Test de parser | Parser optimisé maintenant standard |
| `docker-compose-micro-qwen3.yml` | Redondant - Version standalone | Service micro non prioritaire |
| `docker-compose-micro.yml` | Obsolète - Ancienne version | Service micro non prioritaire |
| `docker-compose-mini-qwen3-original-parser.yml` | Obsolète - Test de parser | Parser optimisé maintenant standard |
| `docker-compose-mini-qwen3.yml` | Redondant - Version standalone | Service mini non prioritaire |
| `docker-compose-mini.yml` | Obsolète - Ancienne version | Service mini non prioritaire |

### Stratégie de Rétention

- **Durée de conservation** : 6 mois minimum
- **Révision** : Avril 2026
- **Suppression définitive** : Uniquement après validation qu'aucun élément n'est nécessaire

---

## Convention de Nommage

### Approche Actuelle (Recommandée)

**Pattern** : `profiles/{service_size}.yml`

**Exemples** :
- `profiles/micro.yml` - Service micro (modèles <7B)
- `profiles/mini.yml` - Service mini (modèles 7B-14B)
- `profiles/medium.yml` - Service medium (modèles 14B-34B)
- `profiles/large.yml` - Service large (modèles 34B+)

**Avantages** :
- ✅ Clarté immédiate du rôle
- ✅ Évite la redondance de "docker-compose" dans le nom
- ✅ Facilite la composition multi-profils
- ✅ Scalabilité pour ajouter de nouveaux profils

### Approche Obsolète (À Éviter)

**Pattern** : `docker-compose-{size}-{model}-{variant}.yml`

**Problèmes identifiés** :
- ❌ Noms très longs et redondants
- ❌ Prolifération de variants (fixed, improved, new, original-parser, etc.)
- ❌ Confusion sur le fichier actif vs obsolète
- ❌ Difficulté de maintenance

**Exemples à ne pas reproduire** :
- `docker-compose-medium-qwen3-memory-optimized.yml` (trop spécifique)
- `docker-compose-micro-qwen3-improved.yml` (variant ambigu)

### Convention pour Archives

**Pattern** : `docker_configs_YYYYMMDD/`

**Raison** :
- Date ISO claire et triable
- Facilite la recherche historique
- Permet plusieurs archives dans l'année si nécessaire

---

## Historique et Rationnelle

### Contexte Historique

Entre 2024 et début 2025, le projet a connu une **prolifération de configurations Docker** due à :

1. **Tests itératifs d'optimisation** : Mémoire, parsers, quantization
2. **Manque de convention de nommage** : Ajout de suffixes (fixed, improved, new)
3. **Conservation excessive** : Fichiers de test conservés à côté des configs de production
4. **Absence de stratégie d'archivage** : Accumulation dans le même répertoire

### Problèmes Identifiés

- **Confusion** : Difficulté d'identifier la configuration active
- **Risque d'erreur** : Déploiement accidentel d'une config obsolète
- **Maintenance complexe** : Modifications à dupliquer dans plusieurs fichiers
- **Documentation difficile** : Trop de fichiers à documenter

### Solution Adoptée (Mission 9 - 2025-10-16)

1. **Archivage systématique** : 15 fichiers déplacés vers archives datées
2. **Structure par profils** : Un seul fichier actif par taille de service
3. **Documentation centralisée** : Ce document ARCHITECTURE.md
4. **Script d'archivage** : Automatisation pour futures maintenances

### Métriques de Simplification

| Métrique | Avant | Après | Amélioration |
|----------|-------|-------|--------------|
| Fichiers dans `configs/docker/` | 16 | 1 (+ répertoire profiles/) | -94% |
| Fichiers actifs de config | Ambigu (3-5?) | 1 clair | ✅ Clarté |
| Convention de nommage | Aucune | Établie | ✅ Maintenance |
| Documentation architecture | Absente | Ce document | ✅ Traçabilité |

---

## Commandes de Référence

### Déploiement du Service Medium

```bash
# Avec monitoring intégré (recommandé)
pwsh -c "./myia_vllm/scripts/deploy_medium_monitored.ps1"

# Manuel (sans monitoring)
docker compose \
  -f myia_vllm/configs/docker/docker-compose.yml \
  -f myia_vllm/configs/docker/profiles/medium.yml \
  up -d --build --force-recreate
```

### Vérification de Santé

```bash
# Status du conteneur
docker ps --filter "name=myia-vllm-medium-qwen3"

# Logs en temps réel
docker logs -f myia-vllm-medium-qwen3

# Endpoint de santé
curl http://localhost:8002/health
```

### Arrêt Propre

```bash
docker compose \
  -f myia_vllm/configs/docker/docker-compose.yml \
  -f myia_vllm/configs/docker/profiles/medium.yml \
  down --remove-orphans
```

---

## Prochaines Étapes

### Actions Recommandées

1. **Créer profils manquants** : `micro.yml`, `mini.yml`, `large.yml` selon besoins
2. **Auditer docker-compose.yml** : Vérifier si fichier de base nécessaire
3. **Documenter stratégie multi-services** : Déploiement simultané de plusieurs profils
4. **Créer template de profil** : Faciliter ajout de nouveaux services

### Évolutions Futures

- **Kubernetes** : Migration vers K8s pour production à grande échelle
- **Helm Charts** : Packaging réutilisable des configurations
- **CI/CD intégré** : Automatisation du déploiement via pipelines
- **Monitoring Prometheus** : Métriques détaillées de performance

---

## Références

- **Mission Source** : MISSION 9 - Redéploiement Service Medium
- **Méthodologie** : SDDD (Semantic-Documentation-Driven-Design)
- **Date d'archivage** : 2025-10-16
- **Script d'archivage** : `myia_vllm/scripts/archive_docker_configs.ps1`
- **Documentation .env** : `myia_vllm/docs/setup/ENV_CONFIGURATION.md`

---

**Dernière mise à jour** : 2025-10-16  
**Prochaine révision** : Avril 2026 (révision archives) ou lors d'ajout de nouveau profil