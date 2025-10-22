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