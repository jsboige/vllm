# Plan de Refactorisation de la Documentation

Basé sur l'analyse comparative avec le `00_MASTER_CONFIGURATION_GUIDE.md`, voici le plan d'action pour consolider la documentation du projet `myia_vllm`. L'objectif est de supprimer l'information obsolète, de fusionner le contenu pertinent et de ne conserver que les documents essentiels et non redondants.

## Légende
- **[SUPPRIMER]** : Fichier obsolète, redondant ou dont le contenu est entièrement couvert par la nouvelle stratégie.
- **[FUSIONNER]** : Contenu pertinent à intégrer dans le `MASTER_CONFIGURATION_GUIDE.md` ou un autre document consolidé.
- **[CONSERVER]** : Document autonome avec une valeur ajoutée claire, non couvert ailleurs.
- **[IGNORER]** : Fichiers non pertinents pour cette refactorisation (ex: listes de commits, plans de restauration, etc.).

---

## `myia_vllm/docs/qwen3/`

- [ ] **[SUPPRIMER]** `DEPLOYMENT-GUIDE.md` (Obsolète, couvert par le master guide)
- [ ] **[SUPPRIMER]** `DEPLOYMENT-RESULTS.md` (Rapport d'étape, obsolète)
- [ ] **[SUPPRIMER]** `DEPLOYMENT-VALIDATION-REPORT.md` (Rapport d'étape, obsolète)
- [ ] **[SUPPRIMER]** `DEPLOYMENT-VERIFICATION.md` (Rapport d'étape, obsolète)
- [ ] **[SUPPRIMER]** `DOCKER-COMPOSE-GUIDE.md` (Obsolète, couvert par le master guide)
- [ ] **[SUPPRIMER]** `ENV-SETUP-GUIDE.md` (Obsolète, couvert par le master guide)
- [ ] **[SUPPRIMER]** `FINAL-ADJUSTMENTS-SUMMARY.md` (Rapport d'étape, obsolète)
- [ ] **[SUPPRIMER]** `guide-deploiement-qwen3.md` (Redondant, couvert par le master guide)
- [ ] **[SUPPRIMER]** `optimisations-qwen3-tool-calling.md` (Obsolète, couvert par le master guide)
- [ ] **[SUPPRIMER]** `PARSER-DOCUMENTATION.md` (Obsolète, la stratégie a changé)
- [ ] **[SUPPRIMER]** `QWEN3-CONFIGURATIONS-DEFINITIVES.md` (Redondant, couvert par le master guide)
- [ ] **[SUPPRIMER]** `QWEN3-CONTAINERS-TEST-REPORT.md` (Rapport de test, obsolète)
- [ ] **[SUPPRIMER]** `QWEN3-CORRECTION-REPORT.md` (Rapport d'étape, obsolète)
- [ ] **[SUPPRIMER]** `QWEN3-DEPLOYMENT-CONFIG.md` (Redondant, couvert par le master guide)
- [ ] **[SUPPRIMER]** `QWEN3-DEPLOYMENT-FINAL-REPORT-COMPLETE.md` (Rapport d'étape, obsolète)
- [ ] **[SUPPRIMER]** `QWEN3-DEPLOYMENT-ISSUES.md` (Obsolète, couvert par le master guide)
- [ ] **[SUPPRIMER]** `QWEN3-FINAL-DEPLOYMENT-REPORT.md` (Rapport d'étape, obsolète)
- [ ] **[SUPPRIMER]** `QWEN3-FINAL-STATUS-REPORT.md` (Rapport d'étape, obsolète)
- [ ] **[SUPPRIMER]** `QWEN3-INTEGRATION-SUMMARY.md` (Rapport d'étape, obsolète)
- [ ] **[SUPPRIMER]** `QWEN3-MAINTENANCE-GUIDE.md` (Obsolète, couvert par le master guide)
- [ ] **[SUPPRIMER]** `QWEN3-PARSER-COMPARISON.md` (Obsolète, la stratégie a changé)
- [ ] **[SUPPRIMER]** `QWEN3-PARSER-INJECTION.md` (Obsolète, la stratégie a changé)
- [ ] **[SUPPRIMER]** `QWEN3-PARSER-PR.md` (Documentation de PR, obsolète)
- [ ] **[SUPPRIMER]** `QWEN3-USER-GUIDE.md` (Redondant, couvert par le master guide)
- [ ] **[SUPPRIMER]** `QWEN3-VALIDATION-REPORT.md` (Rapport de test, obsolète)
- [ ] **[SUPPRIMER]** `rapport-test-qwen3.md` (Rapport de test, obsolète)
- [ ] **[SUPPRIMER]** `TEST-RESULTS.md` (Rapport de test, obsolète)
- [ ] **[SUPPRIMER]** `TESTING-AFTER-SYNC.md` (Documentation de process, obsolète)
- [ ] **[FUSIONNER]** `README.md` dans le `00_MASTER_CONFIGURATION_GUIDE.md`. Le README doit être un pointeur vers le master guide.

## `myia_vllm/docs/archeology/`

- [ ] **[IGNORER]** `COMPARATIVE_ANALYSIS_REPORT.md` (Analyse historique)
- [ ] **[IGNORER]** `CRITICAL_VULNERABILITY_CVE-2025-XXXX.md` (Archivé)
- [ ] **[IGNORER]** `HISTORICAL_ANALYSIS.md` (Analyse historique)
- [ ] **[IGNORER]** `README.md` (Archivé)
- [ ] **[IGNORER]** `RESTORATION_PLAN.md` (Archivé)
- [ ] **[IGNORER]** `REVISED_RESTORATION_PLAN.md` (Archivé)
- [ ] **[SUPPRIMER]** Je propose de supprimer tout le répertoire `archeology` car il ne contient que des informations qui ne sont plus pertinentes.

## `myia_vllm/doc/`

- [ ] **[SUPPRIMER]** `CLEANING_REPORT.md` (Rapport d'étape, obsolète)
- [ ] **[SUPPRIMER]** `CONTEXT-AND-RECOVERY.md` (Rapport d'étape, obsolète)
- [ ] **[SUPPRIMER]** `ETAT_DES_LIEUX.md` (Obsolète, couvert par le master guide)
- [ ] **[SUPPRIMER]** `historical-configs/` (Contient des configurations historiques, obsolètes)
