# Scripts myia_vllm - Guide et Cartographie

## 📂 Scripts de Production (Permanents)

### Grid Search et Optimisation

#### grid_search_optimization.ps1
**Fonction** : Grid search automatisé pour identification configuration optimale vLLM  
**Usage** : `.\grid_search_optimization.ps1 -ConfigFile "configs/grid_search_configs.json"`  
**Dépendances** : Docker Compose, PowerShell 7+, `.env` configuré  
**Documentation** : [GRID_SEARCH_DESIGN_20251017.md](../docs/optimization/GRID_SEARCH_DESIGN_20251017.md)

**Paramètres** :
- `-ConfigFile` : Chemin vers fichier JSON de configurations
- `-Resume` : Reprendre depuis dernière config testée (optionnel)
- `-DryRun` : Mode simulation sans modifications réelles
- `-Verbose` : Affichage logs détaillés

**Corrections récentes** :
- 2025-10-21 : Ajout `--env-file` pour chargement variables (Mission 14g)
- 2025-10-21 : Ajout bloc `finally` pour cleanup garanti (Mission 14d)
- 2025-10-20 : Ajout fonction `Get-VllmContainerName()` (Mission 14b)

#### monitor_grid_search_safety.ps1
**Fonction** : Monitoring temps réel grid search avec détection crashs  
**Usage** : `.\monitor_grid_search_safety.ps1 -IntervalSeconds 60`  
**État** : Production (Mission 14a)

#### test_cleanup.ps1
**Fonction** : Test validation cleanup containers Docker  
**Usage** : `.\test_cleanup.ps1`  
**État** : Production (Mission 14d)

### Déploiement et Monitoring

#### deploy_medium_monitored.ps1
**Fonction** : Déploiement service medium avec monitoring health  
**État** : Production  
**Documentation** : [DEPLOYMENT_MEDIUM_20251016.md](../docs/deployment/DEPLOYMENT_MEDIUM_20251016.md)

#### monitor_medium.ps1
**Fonction** : Monitoring continu service medium  
**État** : Production

### Tests Performance

#### test_kv_cache_acceleration.ps1
**Fonction** : Tests accélération KV cache (TTFT MISS/HIT)  
**État** : Production  
**Documentation** : [KV_CACHE_OPTIMIZATION_20251016.md](../docs/optimization/KV_CACHE_OPTIMIZATION_20251016.md)

#### run_all_tests.ps1
**Fonction** : Suite complète tests service medium  
**État** : Production

### Maintenance

#### archive_docker_configs.ps1
**Fonction** : Archivage configurations Docker obsolètes  
**Usage** : `.\archive_docker_configs.ps1`  
**État** : Production
---

## 🛠️ Scripts Maintenance

### health_check.ps1
**Fonction** : Monitoring quotidien automatisé du service vLLM medium  
**Localisation** : `scripts/maintenance/health_check.ps1`  
**Usage** : `.\scripts\maintenance\health_check.ps1`  
**Fréquence recommandée** : Quotidienne (chaque jour ouvré)

**Vérifications automatiques** :
- Statut container Docker (healthy/unhealthy)
- Utilisation GPU NVIDIA (seuil configurable, défaut 90%)
- Uptime du service
- Génération rapport horodaté dans `logs/health_checks/`

**Paramètres** :
- `-GpuThreshold` : Seuil d'alerte GPU en % (défaut: 90)
- `-Silent` : Mode silencieux sans sortie console
- `-OutputDir` : Répertoire rapports (défaut: logs/health_checks)

**Exemple** :
```powershell
# Health check standard
.\scripts\maintenance\health_check.ps1

# Health check avec seuil GPU 85% en mode silencieux
.\scripts\maintenance\health_check.ps1 -GpuThreshold 85 -Silent
```

**Exit codes** :
- `0` : Toutes vérifications réussies
- `1` : Une ou plusieurs vérifications échouées

**Documentation** : [MAINTENANCE_PROCEDURES.md](../docs/MAINTENANCE_PROCEDURES.md) Section 1.1

---

### cleanup_docker.ps1
**Fonction** : Nettoyage hebdomadaire des ressources Docker orphelines  
**Localisation** : `scripts/maintenance/cleanup_docker.ps1`  
**Usage** : `.\scripts\maintenance\cleanup_docker.ps1`  
**Fréquence recommandée** : Hebdomadaire (chaque vendredi)

**Actions de nettoyage** :
- Containers arrêtés (docker container prune)
- Images inutilisées > 7 jours (docker image prune)
- Volumes orphelins - ⚠️ **PROTÈGE** volumes nommés (myia_vllm_models)
- Build cache Docker
- Calcul et rapport de l'espace récupéré

**Paramètres** :
- `-Force` : Mode automatique sans confirmation utilisateur
- `-DryRun` : Simulation sans suppression réelle
- `-ImageAgeHours` : Âge minimum images à supprimer (défaut: 168h = 7j)
- `-SkipContainers` : Ignorer nettoyage containers
- `-SkipImages` : Ignorer nettoyage images
- `-SkipVolumes` : Ignorer nettoyage volumes

**Exemple** :
```powershell
# Nettoyage interactif (recommandé)
.\scripts\maintenance\cleanup_docker.ps1

# Nettoyage automatique sans confirmation
.\scripts\maintenance\cleanup_docker.ps1 -Force

# Simulation pour voir ce qui serait supprimé
.\scripts\maintenance\cleanup_docker.ps1 -DryRun

# Nettoyage sans volumes, images > 14 jours
.\scripts\maintenance\cleanup_docker.ps1 -SkipVolumes -ImageAgeHours 336
```

**Sécurité** : 
- Demande confirmation avant chaque type de suppression (sauf mode -Force)
- Protection automatique des volumes nommés critiques
- Logs détaillés dans `logs/maintenance/cleanup_docker_*.txt`

**Documentation** : [MAINTENANCE_PROCEDURES.md](../docs/MAINTENANCE_PROCEDURES.md) Section 2

---

### backup_config.ps1
**Fonction** : Backup automatisé configuration vLLM medium avant modifications  
**Localisation** : `scripts/maintenance/backup_config.ps1`  
**Usage** : `.\scripts\maintenance\backup_config.ps1`  
**Fréquence recommandée** : Avant chaque modification de medium.yml

**Fichiers sauvegardés** :
- `medium.yml` (principal, toujours inclus)
- `.env` (optionnel avec -IncludeEnv)
- `docker-compose.yml` (optionnel avec -IncludeCompose)

**Paramètres** :
- `-IncludeEnv` : Inclure le fichier .env dans le backup
- `-IncludeCompose` : Inclure docker-compose.yml dans le backup
- `-Comment` : Ajouter un commentaire descriptif au nom du backup
- `-BackupDir` : Répertoire destination (défaut: configs/docker/profiles/backups)

**Exemple** :
```powershell
# Backup simple de medium.yml
.\scripts\maintenance\backup_config.ps1

# Backup complet avec .env et docker-compose
.\scripts\maintenance\backup_config.ps1 -IncludeEnv -IncludeCompose

# Backup avec commentaire descriptif
.\scripts\maintenance\backup_config.ps1 -Comment "before_gpu_tuning"
```

**Format horodatage** : `medium_yyyyMMdd_HHmmss.yml` (ex: medium_20251022_143055.yml)

**Workflow recommandé** :
```powershell
# 1. Créer backup
.\scripts\maintenance\backup_config.ps1 -Comment "before_optimization"

# 2. Modifier medium.yml
# ...édition manuelle...

# 3. Tester nouvelle config
.\scripts\deploy_medium_monitored.ps1
```

**Documentation** : [MAINTENANCE_PROCEDURES.md](../docs/MAINTENANCE_PROCEDURES.md) Section 3.1


---

## 🗂️ Scripts Transient (Archivés ou À Archiver)

### Scripts de Maintenance Ponctuelle

| Script | Fonction | Date | Action |
|--------|----------|------|--------|
| archive_obsolete_scripts_20250802.ps1 | Archivage configs Docker obsolètes | 2025-08-02 | ⚠️ À archiver |
| reset_doc_state.ps1 | Reset état documentation | 2025-08 | ⚠️ À archiver |
| migrate_documentation.ps1 | Migration docs | 2025-08 | ⚠️ À archiver |
| refactor_python_code.ps1 | Refactoring code Python | 2025-08 | ⚠️ À archiver |
| execute_refactoring_safely.ps1 | Exécution refactoring sécurisée | 2025-08 | ⚠️ À archiver |

**Recommandation** : Déplacer vers `archives/scripts_maintenance_20250802/`

---

## 📖 Documentation README Associée

- **Grid Search** : [README_grid_search.md](README_grid_search.md)
- **General** : [Index Documentation](../docs/DOCUMENTATION_INDEX.md)

---

## 🔧 Configuration et Dépendances

**Prérequis** :
- PowerShell 7+
- Docker Desktop (avec Compose V2)
- Fichier `.env` configuré (voir [ENV_CONFIGURATION.md](../docs/setup/ENV_CONFIGURATION.md))
- GPUs NVIDIA avec CUDA (pour scripts vLLM)

**Fichiers de configuration** :
- `.env` : Variables d'environnement (API keys, CUDA devices)
- `configs/grid_search_configs.json` : Configurations grid search (12 stratégiques)
- `configs/grid_search_configs_validation.json` : Configurations test (4 validation)

---

## 📊 Métriques et Résultats

Les résultats des tests sont sauvegardés dans :
- `test_results/` : Rapports comparatifs, résultats JSON individuels
- `logs/` : Logs d'exécution, logs de crash

---

## 🔄 Workflow Typique Grid Search

1. **Préparation** :
   ```powershell
   # Vérifier l'état Docker
   docker ps -a
   
   # Vérifier le .env
   cat .env | Select-String "HUGGING_FACE_HUB_TOKEN"
   ```

2. **Exécution** :
   ```powershell
   # Grid search complet (12 configs, 3-4h)
   .\scripts\grid_search_optimization.ps1
   
   # OU Grid search validation (4 configs, 30-60min)
   .\scripts\grid_search_optimization.ps1 -ConfigFile "configs/grid_search_configs_validation.json"
   ```

3. **Monitoring** (terminal séparé) :
   ```powershell
   .\scripts\monitor_grid_search_safety.ps1
   ```

4. **Analyse résultats** :
   ```powershell
   # Consulter le rapport comparatif généré
   cat test_results/grid_search_comparative_report_*.md
   ```

---

## 🐛 Dépannage

### Erreur: "No such container"
**Cause** : Nom container incorrect ou container non démarré  
**Solution** : Le script utilise maintenant `Get-VllmContainerName()` pour détection dynamique

### Erreur: "argument --api-key: expected at least one argument"
**Cause** : Variables .env non chargées  
**Solution** : Corrigé dans Mission 14g avec ajout `--env-file` (lignes 485, 493, 539)

### Container orphelin après grid search
**Cause** : Absence de cleanup final  
**Solution** : Corrigé dans Mission 14d avec bloc `finally` (ligne 1425)

### Grid search s'interrompt
**Cause** : Crash config ou timeout  
**Solution** : Utiliser `-Resume` pour reprendre depuis dernier état

---

## 📝 Conventions

### Backups
- Format : `{script}.backup_{raison}`
- Exemple : `grid_search_optimization.ps1.backup_before_envfile_fix`
- Archivage : `archives/logs_missions_YYYYMMDD/`

### Logs
- Format : `grid_search_{timestamp}.log`
- Crash logs : `grid_search_{config_name}_crash.txt`
- Localisation : `logs/`

---

## 🚀 Évolutions Futures

### Fonctionnalités Planifiées
- Support multi-GPU pour grid search parallèle
- Interface web monitoring temps réel
- Génération automatique rapports PDF
- Intégration CI/CD pour validation configs

### Améliorations Scripts
- Ajout paramètre `-MaxParallel` pour grid search concurrent
- Support profils custom (micro, mini, large)
- Export résultats vers base de données
- Notifications Slack/Discord fin grid search

---

**Dernière mise à jour** : 21/10/2025 (Mission 14g)  
**Mainteneur** : Roo Code Mode  
**Version** : 1.0.0