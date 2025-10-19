# Grid Search Optimization - Documentation Utilisateur

## Vue d'ensemble

Le script `grid_search_optimization.ps1` automatise le test de 12 configurations stratégiques pour optimiser vLLM pour les tâches agentiques multi-tours. Il modifie automatiquement les paramètres du service, redémarre le container Docker, exécute les tests de performance et génère un rapport comparatif complet.

## Prérequis

### Logiciels requis
- **PowerShell 7+** (recommandé pour compatibilité multi-plateforme)
- **Docker Desktop** avec Docker Compose
- **Service vLLM** configuré via `myia_vllm/configs/docker/profiles/medium.yml`

### Fichiers requis
- `myia_vllm/configs/grid_search_configs.json` (créé automatiquement si absent)
- `myia_vllm/configs/docker/profiles/medium.yml` (doit exister)
- `myia_vllm/scripts/test_kv_cache_acceleration.ps1` (test KV cache)

### Espace disque
Minimum **5 GB** d'espace libre pour les logs et résultats.

---

## Syntaxe

```powershell
.\grid_search_optimization.ps1 [-ConfigFile <path>] [-Resume] [-SkipBackup] [-Verbose] [-DryRun]
```

### Paramètres

| Paramètre | Type | Obligatoire | Description |
|-----------|------|-------------|-------------|
| `-ConfigFile` | String | Non | Chemin vers le fichier JSON des configurations<br>**Défaut** : `configs/grid_search_configs.json` |
| `-Resume` | Switch | Non | Reprend un grid search interrompu depuis le dernier état sauvegardé<br>Lit `grid_search_progress.json` |
| `-SkipBackup` | Switch | Non | ⚠️ **DANGEREUX** : Ne crée pas de backup de `medium.yml`<br>**Non recommandé en production** |
| `-Verbose` | Switch | Non | Affiche les logs détaillés en temps réel dans la console |
| `-DryRun` | Switch | Non | Mode simulation : teste la logique sans modifier `medium.yml` ni redémarrer Docker |

---

## Exemples d'utilisation

### 1. Exécution standard (recommandé)

```powershell
cd myia_vllm
.\scripts\grid_search_optimization.ps1
```

**Comportement** :
- Charge les 12 configurations depuis `configs/grid_search_configs.json`
- Crée un backup horodaté de `medium.yml`
- Teste chaque configuration séquentiellement (durée : 3-4 heures)
- Génère un rapport comparatif dans `test_results/`

### 2. Dry-run de validation

```powershell
.\scripts\grid_search_optimization.ps1 -DryRun -Verbose
```

**Comportement** :
- Simule toutes les opérations sans modifications réelles
- Affiche les logs détaillés en temps réel
- Valide la syntaxe et la logique du script
- **Durée** : ~5 secondes

### 3. Reprise après interruption

```powershell
.\scripts\grid_search_optimization.ps1 -Resume
```

**Comportement** :
- Lit `grid_search_progress.json` pour identifier la dernière config complétée
- Reprend depuis la configuration suivante
- **Exemple** : Si interrompu après config 5, reprend à config 6

### 4. Fichier de configuration personnalisé

```powershell
.\scripts\grid_search_optimization.ps1 -ConfigFile "D:\custom_configs.json" -Verbose
```

**Comportement** :
- Charge les configurations depuis le chemin spécifié
- Affiche les logs verbeux
- Utile pour tester des configurations expérimentales

---

## Workflow détaillé

### Phase 1 : Initialisation (< 10 secondes)

1. **Validation environnement** :
   - ✅ Docker daemon disponible
   - ✅ `medium.yml` existant
   - ✅ Fichier configs JSON valide
   - ✅ Espace disque suffisant (≥5GB)
   - ✅ Scripts de test présents

2. **Chargement configurations** :
   - Parse le fichier JSON
   - Valide les 12 configurations
   - Affiche résumé à l'utilisateur

3. **Demande de confirmation** :
   - Affiche durée estimée (3-4 heures)
   - Attend validation utilisateur (appuyez sur Entrée)

### Phase 2 : Boucle de test (6-11 min/config × 12)

Pour chaque configuration (exemple : `prefix_only_095`) :

#### Étape 2.1 : Modification de `medium.yml`

```powershell
# Backup automatique (si première itération)
medium.yml.backup_grid_search_20251017_221543

# Modification des paramètres
--gpu-memory-utilization 0.95
--enable-prefix-caching  # Si prefix_caching: true
--max-num-seqs 64        # Si spécifié
```

#### Étape 2.2 : Redéploiement Docker

```powershell
docker compose -f configs/docker/profiles/medium.yml down
docker compose -f configs/docker/profiles/medium.yml up -d
```

**Timeout** : 10 minutes

#### Étape 2.3 : Vérification Health

```powershell
# Polling toutes les 15 secondes
$status = docker inspect vllm-medium --format '{{.State.Health.Status}}'
```

**Statuts possibles** :
- `healthy` → Continuer aux tests
- `unhealthy` → Capturer logs, skip config
- Timeout (10 min) → Skip config

#### Étape 2.4 : Exécution des tests

**Test 1 : KV Cache Acceleration** (timeout 5 min)
```powershell
.\scripts\test_kv_cache_acceleration.ps1
```

**Métriques collectées** :
- TTFT CACHE MISS (ms)
- TTFT CACHE HIT (ms)
- Cache Acceleration (ratio)
- Gain Percentage (%)

**Test 2 & 3** (optionnels, si scripts existent) :
- `test_performance_ttft.py` (timeout 3 min)
- `test_performance_throughput.py` (timeout 3 min)

#### Étape 2.5 : Sauvegarde des résultats

**Fichier JSON** : `test_results/grid_search_results_{config_name}_{timestamp}.json`

```json
{
  "config_name": "prefix_only_095",
  "timestamp": "2025-10-17T21:30:00Z",
  "config_params": {
    "gpu_memory": 0.95,
    "prefix_caching": true,
    "chunked_prefill": false,
    "max_num_seqs": 64
  },
  "deployment": {
    "status": "success",
    "startup_time_seconds": 45,
    "health_check_attempts": 3
  },
  "tests": {
    "kv_cache_acceleration": {
      "status": "success",
      "ttft_cache_miss_ms": 1850,
      "ttft_cache_hit_ms": 950,
      "cache_acceleration": 1.95,
      "gain_percentage": 48.6
    }
  },
  "errors": []
}
```

### Phase 3 : Rapport final (< 30 secondes)

**Fichier généré** : `test_results/grid_search_comparative_report_{timestamp}.md`

#### Tableau comparatif

```markdown
| Rank | Config Name | GPU Mem | Prefix | Chunked | Max Seqs | TTFT MISS | TTFT HIT | Accel | Gain % | vs Baseline MISS | vs Baseline HIT |
|------|-------------|---------|--------|---------|----------|-----------|----------|-------|--------|------------------|-----------------|
| 1 | prefix_only_095 | 0.95 | ✅ | ❌ | 64 | 1850ms | 950ms | x1.95 | 48.6% | +1.2% | -40.9% |
| 2 | combined_balanced | 0.95 | ✅ | ✅ | 64 | 1920ms | 1100ms | x1.75 | 42.7% | +5.0% | -31.6% |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
```

**Tri** : Par accélération cache décroissante (meilleure en premier)

#### Analyse des résultats

1. **Configuration optimale identifiée**
2. **Trade-offs observés**
3. **Échecs et anomalies**
4. **Recommandation finale pour production**

---

## Gestion des erreurs

### Timeouts

| Situation | Timeout | Action |
|-----------|---------|--------|
| Déploiement Docker | 10 min | Skip config, log erreur, continuer |
| Health check | 10 min | Skip config, capturer logs Docker |
| Test KV cache | 5 min | Marquer test "timeout", continuer |
| Tests additionnels | 3 min | Marquer test "timeout", continuer |

### Crashes de container

**Détection** :
```powershell
docker inspect vllm-medium
# Erreur → Container crashé
```

**Recovery** :
1. Capturer dernières 200 lignes logs → `logs/grid_search_{config_name}_crash.txt`
2. Restaurer backup `medium.yml`
3. Tenter redéploiement baseline
4. Si baseline échoue → **ABORT grid search**, retourner erreur critique

### Interruption manuelle (Ctrl+C)

**État sauvegardé** : `grid_search_progress.json`

```json
{
  "last_completed_config": "prefix_only_092",
  "completed_indices": [0, 1, 2, 3],
  "timestamp": "2025-10-17T22:00:00Z"
}
```

**Reprise** :
```powershell
.\scripts\grid_search_optimization.ps1 -Resume
```

---

## Logs et traçabilité

### Log principal

**Fichier** : `logs/grid_search_{timestamp}.log`

**Format** :
```
[2025-10-17 21:30:00] [INFO] Grid search started with 12 configurations
[2025-10-17 21:30:05] [INFO] Config 1/12: baseline - Starting deployment
[2025-10-17 21:30:15] [SUCCESS] Config 1/12: baseline - Container healthy after 10s
[2025-10-17 21:33:45] [SUCCESS] Config 1/12: baseline - KV cache test completed (TTFT MISS: 1828ms, HIT: 1607ms)
```

**Niveaux** :
- `[INFO]` : Informations générales
- `[SUCCESS]` : Opération réussie
- `[WARNING]` : Avertissement non bloquant
- `[ERROR]` : Erreur récupérable
- `[CRITICAL]` : Erreur fatale nécessitant intervention

### Logs détaillés par config

**Répertoire** : `logs/grid_search/config_{name}/`

**Fichiers** :
- `deployment.log` : Sortie `docker compose up`
- `health_checks.log` : Historique vérifications health
- `kv_cache_test.log` : Sortie complète test KV cache
- `docker_container.log` : Logs Docker (en cas d'échec)

---

## Troubleshooting

### Problème : Script bloqué sur "Vérification du health status..."

**Cause** : Container ne passe pas à `healthy`

**Solution** :
1. Ouvrir un nouveau terminal
2. Vérifier logs container :
   ```powershell
   docker logs vllm-medium --tail 100
   ```
3. Vérifier status :
   ```powershell
   docker inspect vllm-medium --format '{{.State.Health.Status}}'
   ```
4. Si `unhealthy` : Consulter `logs/grid_search/config_{name}/docker_container.log`

### Problème : "Docker daemon not running"

**Cause** : Docker Desktop arrêté

**Solution** :
1. Démarrer Docker Desktop
2. Attendre initialisation complète (~30 secondes)
3. Relancer script

### Problème : "Espace disque insuffisant"

**Cause** : < 5 GB disponible

**Solution** :
1. Nettoyer images Docker :
   ```powershell
   docker system prune -a --volumes
   ```
2. Supprimer anciens logs :
   ```powershell
   Remove-Item -Path "logs/grid_search_*" -Recurse -Force
   ```
3. Relancer script

### Problème : Résultats incohérents (TTFT anormalement élevés)

**Cause** : Charge système élevée pendant tests

**Solution** :
1. Fermer applications gourmandes (navigateurs, IDE)
2. Vérifier utilisation GPU :
   ```powershell
   nvidia-smi
   ```
3. Relancer config spécifique :
   ```powershell
   # Éditer grid_search_progress.json manuellement
   # Supprimer config de "completed_indices"
   .\scripts\grid_search_optimization.ps1 -Resume
   ```

### Problème : "Cannot bind argument to parameter 'Message' because it is an empty string"

**Cause** : Version ancienne du script (avant fix 2025-10-17)

**Solution** :
1. Télécharger dernière version du script
2. Vérifier ligne 112 contient `[AllowEmptyString()]`
3. Relancer script

---

## Estimation de durée

### Par configuration

| Phase | Durée typique |
|-------|---------------|
| Modification `medium.yml` | 5 secondes |
| Déploiement Docker | 30-60 secondes |
| Health check | 30-120 secondes |
| Test KV cache | 3-5 minutes |
| Tests additionnels | 2-3 minutes (si présents) |
| **Total** | **6-11 minutes** |

### Grid search complet

- **12 configurations** : 72-132 minutes (1h12 à 2h12)
- **Marge de sécurité** : Prévoir **3-4 heures** en cas de timeouts/redémarrages

### Mode Dry-run

- **Durée** : ~5 secondes
- Valide uniquement la logique, pas les performances réelles

---

## Fichiers de sortie

### Résultats JSON par config

**Emplacement** : `test_results/grid_search_results_{config_name}_{timestamp}.json`

**Contenu** : Métriques détaillées de chaque test

### Rapport comparatif Markdown

**Emplacement** : `test_results/grid_search_comparative_report_{timestamp}.md`

**Sections** :
1. Tableau récapitulatif (12 configs triées)
2. Configuration optimale identifiée
3. Trade-offs observés
4. Échecs et anomalies
5. Recommandation finale

### Log principal

**Emplacement** : `logs/grid_search_{timestamp}.log`

**Contenu** : Trace complète de l'exécution (tous niveaux de log)

### Backup de medium.yml

**Emplacement** : `configs/docker/profiles/medium.yml.backup_grid_search_{timestamp}`

**Utilité** : Restauration manuelle en cas de problème

---

## Bonnes pratiques

### Avant l'exécution

1. ✅ **Vérifier l'état actuel** :
   ```powershell
   docker ps -a | Select-String "vllm-medium"
   ```
2. ✅ **Effectuer un dry-run** :
   ```powershell
   .\scripts\grid_search_optimization.ps1 -DryRun
   ```
3. ✅ **Libérer la charge système** : Fermer applications gourmandes
4. ✅ **Planifier la durée** : Bloquer 3-4 heures sans interruption

### Pendant l'exécution

1. ⚠️ **Ne pas interrompre manuellement** (sauf si nécessaire)
2. ⚠️ **Ne pas modifier `medium.yml` manuellement**
3. ✅ **Surveiller les logs** : Consulter `logs/grid_search_{timestamp}.log` en temps réel
4. ✅ **Vérifier santé système** :
   ```powershell
   nvidia-smi  # Toutes les 10 minutes
   ```

### Après l'exécution

1. ✅ **Consulter le rapport comparatif** : Identifier configuration optimale
2. ✅ **Valider baseline restaurée** :
   ```powershell
   docker inspect vllm-medium --format '{{.State.Health.Status}}'
   ```
3. ✅ **Archiver les résultats** : Copier `test_results/` vers emplacement sécurisé
4. ✅ **Nettoyer backups intermédiaires** (optionnel) :
   ```powershell
   Remove-Item -Path "configs/docker/profiles/medium.yml.backup_grid_search_*"
   ```

---

## Support et contribution

### Rapport de bugs

**Fichiers à fournir** :
1. `logs/grid_search_{timestamp}.log`
2. `logs/grid_search/config_{name}/docker_container.log` (si crash)
3. Commande exacte utilisée
4. Version PowerShell : `$PSVersionTable.PSVersion`

### Amélioration des configurations

Pour tester des configurations personnalisées :

1. Éditer `configs/grid_search_configs.json`
2. Ajouter nouvelle config :
   ```json
   {
     "name": "custom_experiment",
     "gpu_memory": 0.93,
     "prefix_caching": true,
     "chunked_prefill": true,
     "max_num_seqs": 48,
     "max_num_batched_tokens": 6144
   }
   ```
3. Relancer script (testera 13 configs)

---

## Licence et crédits

Script développé dans le cadre de **MISSION 11 - Optimisation fine vLLM pour tâches agentiques multi-tours**.

**Auteur** : MyIA AI Team  
**Date** : 2025-10-17  
**Version** : 1.0.0