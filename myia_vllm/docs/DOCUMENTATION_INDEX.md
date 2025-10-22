# Index Documentation Projet myia_vllm

**Dernière mise à jour** : 22/10/2025 - Mission 11 Phase 7

## 📋 Documentation SDDD (Semantic Documentation Driven Design)

### Missions Grid Search Optimization (Octobre 2025)

| ID | Document | Type | Statut | Chemin |
|----|----------|------|--------|--------|
| SDDD-001 | Grid Search Design | Design scientifique | ✅ Final | `docs/optimization/GRID_SEARCH_DESIGN_20251017.md` |
| SDDD-002 | Grid Search Execution Log | Log exécution | 🔄 Actif | `logs/grid_search_execution_20251018.md` |
| SDDD-003 | Grid Search Cleanup Issue | Incident résolu | ✅ Final | `logs/grid_search_cleanup_issue_20251021.md` |
| SDDD-004 | Grid Search Crash Diagnosis | Diagnostic technique | ✅ Final | `logs/grid_search_crash_diagnosis_20251021.md` |
| SDDD-005 | Git Cleanup Report | Maintenance | ✅ Final | `docs/git_cleanup_20251019.md` |

### Documentation Permanente / Guides Principaux

| Catégorie | Document | Lignes | Statut | Chemin |
|-----------|----------|--------|--------|--------|
| **Guides Production** | **DEPLOYMENT_GUIDE** | **382** | ✅ **À jour** | `docs/DEPLOYMENT_GUIDE.md` |
| **Guides Production** | **OPTIMIZATION_GUIDE** | **386** | ✅ **À jour** | `docs/OPTIMIZATION_GUIDE.md` |
| **Guides Production** | **TROUBLESHOOTING** | **495** | ✅ **À jour** | `docs/TROUBLESHOOTING.md` |
| **Guides Production** | **MAINTENANCE_PROCEDURES** | **447** | ✅ **À jour** | `docs/MAINTENANCE_PROCEDURES.md` |
| Architecture | Docker Architecture | - | ✅ À jour | `docs/docker/ARCHITECTURE.md` |
| Architecture | Medium Service Parameters | - | ✅ À jour | `docs/docker/MEDIUM_SERVICE_PARAMETERS.md` |
| Deployment | Deployment Safety | - | ✅ À jour | `docs/deployment/DEPLOYMENT_SAFETY.md` |
| Deployment | Medium Service Guide | - | ✅ À jour | `docs/deployment/MEDIUM_SERVICE.md` |
| Deployment | Deployment Medium | - | ✅ À jour | `docs/deployment/DEPLOYMENT_MEDIUM_20251016.md` |
| Optimization | KV Cache Optimization | - | ✅ À jour | `docs/optimization/KV_CACHE_OPTIMIZATION_20251016.md` |
| Setup | ENV Configuration | - | ✅ À jour | `docs/setup/ENV_CONFIGURATION.md` |
| Testing | Medium Service Test Plan | - | ✅ À jour | `docs/testing/MEDIUM_SERVICE_TEST_PLAN.md` |

### Documentation Transient (Logs de Missions)

| ID | Mission | Document | Archiver | Chemin |
|----|---------|----------|----------|--------|
| LOG-001 | Docker Cleanup | docker_cleanup_20251018.md | ⚠️ Oui | `logs/` |
| LOG-002 | Grid Search Bug Container | grid_search_bugfix_container_name_20251020.md | ⚠️ Oui | `logs/` |

### Archives Missions (Transient)

**Répertoire** : `archives/missions/2025-10-21_missions_11-15/`

| Document | Type | Statut | Taille |
|----------|------|--------|--------|
| README.md | Index archivage | 📦 Archivé | 60 lignes |
| SYNTHESIS_GRID_SEARCH_MISSIONS_20251021.md | Synthèse missions 11-15 | 📦 Archivé | 206 lignes |
| PRODUCTION_VALIDATION_REPORT.md | Rapport validation | 📦 Archivé | 236 lignes |
| git_cleanup_20251019.md | Maintenance Git | 📦 Archivé | 479 lignes |

### Documentation Archéologique

| Catégorie | Document | Statut | Chemin |
|-----------|----------|--------|--------|
| Historical | Historical Analysis | 📚 Archive | `docs/archeology/HISTORICAL_ANALYSIS.md` |
| Restoration | Restoration Plan V2 | 📚 Archive | `docs/archeology/RESTORATION_PLAN_V2.md` |
| Consolidation | Docker Report | 📚 Archive | `docs/archeology/CONSOLIDATION_DOCKER_REPORT.md` |
| Consolidation | Scripts Final | 📚 Archive | `docs/archeology/CONSOLIDATION_SCRIPTS_FINAL.md` |
| Diagnostic | Conformité | 📚 Archive | `docs/archeology/DIAGNOSTIC_CONFORMITE.md` |
| Security | Security Methodology | 📚 Archive | `docs/archeology/SECURITY_METHODOLOGY.md` |
| Security | Recovery Plan | 📚 Archive | `docs/archeology/RECOVERY_SECURITY_PLAN.md` |
| Security | Actions Log | 📚 Archive | `docs/archeology/SECURITY_ACTIONS_LOG.md` |
| Commits | Commits jsboige | 📚 Archive | `docs/archeology/commits_jsboige.md` |

### Documentation Qwen3 (Ancienne)

| Type | Document | Statut | Chemin |
|------|----------|--------|--------|
| Master | Configuration Guide | 📚 Archive | `docs/qwen3/00_MASTER_CONFIGURATION_GUIDE.md` |
| Setup | Various READMEs | 📚 Archive | `docs/qwen3/*.md` |

## 📂 Scripts et Outils

### Scripts Permanents (Production)

| Script | Fonction | Lignes | Statut | Chemin |
|--------|----------|--------|--------|--------|
| grid_search_optimization.ps1 | Grid search automatisé | 1600+ | ✅ Production | `scripts/` |
| monitor_grid_search_safety.ps1 | Monitoring temps réel | 170 | ✅ Production | `scripts/` |
| test_cleanup.ps1 | Test cleanup containers | - | ✅ Production | `scripts/` |
| deploy_medium_monitored.ps1 | Déploiement surveillé | - | ✅ Production | `scripts/` |
| monitor_medium.ps1 | Monitoring service medium | - | ✅ Production | `scripts/` |
| run_all_tests.ps1 | Suite tests complète | - | ✅ Production | `scripts/` |
| test_kv_cache_acceleration.ps1 | Tests KV cache | - | ✅ Production | `scripts/` |
| archive_docker_configs.ps1 | Archivage configs | - | ✅ Production | `scripts/` |

### Scripts Maintenance (Mission 11 Phase 7)

| Script | Fonction | Lignes | Statut | Chemin |
|--------|----------|--------|--------|--------|
| **health_check.ps1** | **Vérification santé services** | **226** | ✅ **Production** | `scripts/maintenance/` |
| **cleanup_docker.ps1** | **Nettoyage automatisé Docker** | **408** | ✅ **Production** | `scripts/maintenance/` |
| **backup_config.ps1** | **Sauvegarde configurations** | **246** | ✅ **Production** | `scripts/maintenance/` |
| monitor-logs.ps1 | Monitoring logs temps réel | 367 | ✅ Production | `scripts/maintenance/` |

### Scripts Transient (Outils ponctuels)

| Script | Fonction | Archiver | Chemin |
|--------|----------|----------|--------|
| archive_obsolete_scripts_20250802.ps1 | Archivage scripts | ⚠️ Oui | `scripts/` |
| reset_doc_state.ps1 | Reset docs | ⚠️ Oui | `scripts/` |
| migrate_documentation.ps1 | Migration docs | ⚠️ Oui | `scripts/` |
| refactor_python_code.ps1 | Refactoring code | ⚠️ Oui | `scripts/` |
| execute_refactoring_safely.ps1 | Exécution refactoring | ⚠️ Oui | `scripts/` |

## 📊 Rapports de Tests et Résultats

### Résultats Grid Search

| Date | Configs | Réussis | Fichier |
|------|---------|---------|---------|
| 2025-10-20 | 12/12 | 0/12 | `test_results/grid_search_comparative_report_20251020_234054.md` |
| 2025-10-21 | 4/4 | 0/4 | `test_results/grid_search_comparative_report_20251021_030821.md` |

### Autres Résultats

| Type | Document | Date | Chemin |
|------|----------|------|--------|
| Comparative Analysis | FINALIZATION_REPORT.md | 2025-10 | `analysis_comparative/` |
| Optimization Comparison | optimization_comparison_20251016.md | 2025-10-16 | `test_results/` |

## 🗂️ Archives

**Répertoire** : `myia_vllm/archives/`

Contient les scripts et configurations obsolètes, notamment:
- Anciens scripts de déploiement Docker Compose
- Configurations Docker redondantes (archivées 2025-10-16)
- Scripts de maintenance ponctuels (à archiver)
- Logs de missions ponctuelles (à créer: `archives/logs_missions_20251021/`)

## 🔧 Configuration

| Fichier | Type | Statut | Chemin |
|---------|------|--------|--------|
| .env | Variables d'environnement | ✅ Actif | `.env` |
| .env.example | Template variables | ✅ À jour | `.env.example` |
| grid_search_configs.json | Configs 12 stratégiques | ✅ Validé | `configs/` |
| grid_search_configs_validation.json | Configs 4 test | ✅ Validé | `configs/` |
| docker-compose.yml | Base Docker Compose | ✅ Actif | `configs/docker/` |
| medium.yml | Profil medium vLLM | ✅ Actif | `configs/docker/profiles/` |

---

## 📝 Conventions de Nommage

### Documents SDDD
- **Format** : `DESCRIPTIF_YYYYMMDD.md` (ex: `GRID_SEARCH_DESIGN_20251017.md`)
- **Numérotation** : SDDD-XXX dans l'index ci-dessus
- **Localisation** : `docs/[catégorie]/` pour permanent, `logs/` pour transient

### Scripts
- **Permanents** : Nom fonctionnel (ex: `grid_search_optimization.ps1`)
- **Transient** : Nom + date (ex: `archive_obsolete_scripts_20250802.ps1`)
- **Backups** : Original + `.backup_[raison]` (ex: `medium.yml.backup_before_api_key_fix`)

### Logs
- **Format** : `[type]_[descriptif]_[timestamp].log`
- **Crash logs** : `grid_search_[config_name]_crash.txt`

---

## 🏷️ Statut des Documents

- ✅ **Final** : Document achevé, pas de modifications prévues
- 🔄 **Actif** : Document mis à jour régulièrement
- ⚠️ **À archiver** : Document obsolète, à déplacer vers `archives/`
- 📝 **Brouillon** : Document en cours de rédaction
- 📚 **Archive** : Document historique conservé pour référence

---

## 🔍 Recherche Sémantique

Pour rechercher efficacement dans la documentation :

1. **Déploiement** : Rechercher "comment déployer service medium production vllm docker compose"
2. **Optimisation** : Rechercher "configuration optimale chunked prefill kv cache accélération"
3. **Maintenance** : Rechercher "scripts maintenance cleanup docker health check automatisé"
4. **Troubleshooting** : Rechercher "résolution erreurs problèmes vllm diagnostics"
5. **Grid Search** : Rechercher "grid search optimization vllm"
6. **Docker** : Rechercher "docker architecture medium service"

---

## 📅 Dernières Mises à Jour

| Date | Mission/Phase | Modifications | Auteur |
|------|---------------|---------------|--------|
| 22/10/2025 | Mission 11 Phase 7 | Ajout 4 guides permanents + 3 scripts maintenance + archivage missions 11-15 | Roo Code |
| 21/10/2025 | Mission 14g | Création index + références grid search | Roo Code |

---

**Date de création** : 21/10/2025
**Auteur** : Roo Code (Mission 14g)
**Dernière mise à jour** : 22/10/2025 (Mission 11 Phase 7 - Sous-tâche 4/4)
**Prochaine révision** : Mission 11 Phase 8