# Plan de Rationalisation des Scripts myia_vllm

**Date :** 21 septembre 2025  
**Auteur :** Roo Code  
**Mission :** Rationalisation et consolidation des scripts selon la stratégie d'image Docker officielle

---

## Synthèse du Grounding SDDD

### Découvertes Critiques

1. **Changement Stratégique Majeur :** Passage à l'image officielle `vllm/vllm-openai:v0.9.2`
   - **Impact :** Rend obsolètes tous les scripts de construction d'images personnalisées
   - **Source :** `myia_vllm/docs/qwen3/00_MASTER_CONFIGURATION_GUIDE.md`

2. **Prolifération de Scripts Critique :**
   - **57 scripts total** identifiés dans `myia_vllm/scripts/`
   - **Redondances massives :** Multiples versions (-fixed, -improved, -final, -v2, -v3)
   - **Scripts dupliqués** entre répertoires `scripts/` et `scripts/powershell/`

3. **Configuration Centralisée :**
   - Fichier `.env` fonctionnel avec 3 modèles (Micro, Mini, Medium)
   - Variables d'environnement standardisées
   - Configuration GPU claire (0,1 pour Medium, 2 pour Mini/Micro)

---

## Analyse Fonctionnelle par Catégorie

### 🚀 **Catégorie : Déploiement**

#### Scripts à Conserver et Moderniser
- **CONSERVER+MODERNISER** : [`start-qwen3-services.ps1`](myia_vllm/scripts/start-qwen3-services.ps1:1) → Refactoriser pour image officielle
- **CONSERVER+MODERNISER** : [`setup-qwen3-environment.ps1`](myia_vllm/scripts/setup-qwen3-environment.ps1:1) → Moderniser variables .env

#### Scripts à Fusionner
- **FUSIONNER** : `deploy-all-containers.ps1` + `deploy-all.ps1` + `deploy-qwen3-containers.ps1` → `deploy-qwen3.ps1`
- **FUSIONNER** : `deploy-optimized-qwen3.ps1` + `deploy-optimized-qwen3-fixed.ps1` → Intégrer dans le script principal

#### Scripts Obsolètes (Image Personnalisée)
- **ARCHIVER** : `extract-qwen3-parser.ps1` (obsolète avec image officielle)
- **ARCHIVER** : `fix-hardcoded-paths.ps1` (lié aux builds personnalisés)
- **ARCHIVER** : `fix-improved-cli-args.ps1` (obsolète)

### 🧪 **Catégorie : Validation et Test**

#### Scripts à Conserver et Moderniser
- **CONSERVER+MODERNISER** : [`test-qwen3-services.ps1`](myia_vllm/scripts/test-qwen3-services.ps1:1) → Moderniser endpoints
- **CONSERVER+MODERNISER** : `scripts/python/tests/test_qwen3_tool_calling.py` → Version canonique

#### Scripts à Fusionner 
- **FUSIONNER** : 6 scripts de validation redondants :
  - `validate-optimized-qwen3.ps1`
  - `validate-optimized-qwen3-fixed.ps1` 
  - `validate-optimized-qwen3-improved.ps1`
  - `validate-optimized-qwen3-final.ps1`
  - `validate-optimized-qwen3-final-v2.ps1`
  - `validate-optimized-qwen3-final-v3.ps1`
  → **`validate-services.ps1`**

#### Scripts à Supprimer (Redondances)
- **SUPPRIMER** : 4 versions redondantes de `test_qwen3_tool_calling` (garder 1 version)
- **SUPPRIMER** : `run-validation.ps1`, `run-validation-improved.ps1`, `run-validation-final.ps1` (3 doublons)

### 🔧 **Catégorie : Maintenance**

#### Scripts à Conserver et Moderniser
- **CONSERVER+MODERNISER** : [`update-qwen3-services.ps1`](myia_vllm/scripts/update-qwen3-services.ps1:1) → Simplifier pour image officielle
- **CONSERVER+MODERNISER** : `check-qwen3-logs.ps1` → Maintenir pour debugging

#### Scripts à Archiver (Fonctionnalités Obsolètes)
- **ARCHIVER** : `prepare-update.ps1` (trop complexe pour image officielle)
- **ARCHIVER** : `sync-upstream.ps1` (plus nécessaire)
- **ARCHIVER** : `backup-env-to-gdrive.ps1` (fonctionnalité spécialisée)

---

## Architecture Cible des Scripts

```
myia_vllm/scripts/
├── deploy/
│   ├── deploy-qwen3.ps1              # Script principal de déploiement unifié
│   └── setup-environment.ps1         # Configuration environnement (.env)
├── validate/
│   ├── validate-services.ps1         # Validation post-déploiement consolidée
│   └── test-endpoints.ps1             # Tests fonctionnels des API
├── maintenance/
│   ├── update-services.ps1           # Mise à jour simple (changement tag image)
│   ├── monitor-logs.ps1               # Monitoring logs (ex check-qwen3-logs.ps1)
│   └── backup-configs.ps1             # Sauvegarde configurations
├── python/
│   ├── client.py                      # Client API unifié
│   ├── test_qwen3_complete.py         # Suite de tests consolidée
│   └── utils.py                       # Utilitaires communs
├── archived/
│   ├── build-related/                 # Scripts de construction obsolètes
│   ├── legacy-versions/               # Anciennes versions multiples
│   └── specialized-tools/             # Outils spécialisés (backup, sync, etc.)
└── README.md                          # Documentation d'utilisation
```

---

## Plan d'Exécution Détaillé

### Phase 1 : Scripts à Supprimer Immédiatement (14 scripts)

**Versions Multiples Redondantes :**
```powershell
# Supprimer (garder la dernière version fonctionnelle)
- deploy-optimized-qwen3-fixed.ps1
- validate-optimized-qwen3.ps1
- validate-optimized-qwen3-fixed.ps1  
- validate-optimized-qwen3-improved.ps1
- validate-optimized-qwen3-final-v2.ps1
- validate-optimized-qwen3-final-v3.ps1
- run-validation.ps1
- run-validation-improved.ps1
- test-vllm-services.ps1 (doublon avec test-qwen3-services.ps1)
- start-vllm-services.ps1 (doublon avec start-qwen3-services.ps1)

# Python - garder seulement 1 version de tool_calling
- test_qwen3_tool_calling_custom.py
- test_qwen3_tool_calling_fixed.py  
- test_qwen3_tool_calling.py (garder celui-ci comme référence)
```

### Phase 2 : Scripts à Archiver (12 scripts)

**Fonctionnalités Obsolètes avec Image Officielle :**
```powershell
# Scripts liés aux images personnalisées
- extract-qwen3-parser.ps1
- fix-hardcoded-paths.ps1
- fix-improved-cli-args.ps1
- prepare-secure-push.ps1
- remove-hardcoded-api-keys.ps1
- update-gitignore.ps1

# Scripts de maintenance spécialisés
- backup-env-to-gdrive.ps1
- consolidate-qwen3-branches.ps1
- git-reorganization.ps1
- prepare-update.ps1
- sync-upstream.ps1
- final-commits.ps1
```

### Phase 3 : Scripts à Moderniser et Consolider (8 scripts finaux)

**Scripts de Déploiement :**
1. **`deploy-qwen3.ps1`** (fusion de deploy-all*, deploy-optimized*)
2. **`setup-environment.ps1`** (basé sur setup-qwen3-environment.ps1)

**Scripts de Validation :**
3. **`validate-services.ps1`** (consolidation des 6 versions validate-*)
4. **`test-endpoints.ps1`** (basé sur test-qwen3-services.ps1)

**Scripts de Maintenance :**
5. **`update-services.ps1`** (simplification d'update-qwen3-services.ps1)
6. **`monitor-logs.ps1`** (basé sur check-qwen3-logs.ps1)

**Scripts Python :**
7. **`test_qwen3_complete.py`** (consolidation des tests)
8. **`client.py`** (client unifié)

---

## Validation du Plan

### Critères de Réussite
- [x] **Réduction drastique** : De 57 scripts → 8 scripts finaux + archives
- [x] **Élimination des redondances** : Suppression des versions multiples
- [x] **Alignement stratégique** : Scripts compatibles image officielle
- [x] **Architecture claire** : Organisation fonctionnelle (deploy/, validate/, maintenance/)
- [x] **Conservation des fonctionnalités essentielles** : Déploiement, validation, maintenance

### Points de Contrôle Obligatoires
- [ ] **Validation utilisateur** avant suppression définitive
- [ ] **Test fonctionnel** du script principal de déploiement
- [ ] **Vérification** que tous les scripts essentiels restent accessibles
- [ ] **Documentation** des changements pour la traçabilité

---

**⚠️ Attention :** Ce plan nécessite validation avant exécution. Les 26 scripts marqués pour suppression/archivage seront préservés temporairement pour validation.