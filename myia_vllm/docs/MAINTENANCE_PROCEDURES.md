# Procédures de Maintenance - Service vLLM Medium

**Dernière mise à jour** : 2025-10-22
**Version** : 1.0

## 📋 Table des Matières
1. Monitoring Régulier
2. Nettoyage Docker
3. Backup Configuration
4. Mise à Jour Modèle
5. Rotation Logs
6. Calendrier Maintenance

---

## 1. Monitoring Régulier

### 1.1 Monitoring Quotidien

**Fréquence :** Chaque jour ouvré

**Vérifications :**
```powershell
# 1. Statut container (doit être "healthy")
docker ps --filter "name=myia_vllm-medium-qwen3" --format "{{.Status}}"

# 2. Utilisation GPU (doit être < 90%)
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv

# 3. Uptime
docker inspect myia_vllm-medium-qwen3 --format='{{.State.StartedAt}}'
```

**Script automatisé :** À créer [`scripts/maintenance/health_check.ps1`](myia_vllm/scripts/maintenance/health_check.ps1)

**Durée estimée :** 2 minutes

---

### 1.2 Monitoring Hebdomadaire

**Fréquence :** Chaque lundi

**Vérifications :**
```powershell
# 1. Logs d'erreur (semaine écoulée)
docker logs --since 168h myia_vllm-medium-qwen3 | Select-String -Pattern "error|warning|fatal"

# 2. Performance KV Cache
pwsh -c ".\myia_vllm\scripts\test_kv_cache_acceleration.ps1"

# 3. Espace disque
Get-PSDrive -Name C | Select-Object Used,Free
```

**Objectifs :**
- Logs erreur < 10/semaine
- Accélération KV Cache ≥ x3.0
- Espace disque libre > 20GB

**Durée estimée :** 5 minutes

---

## 2. Nettoyage Docker

### 2.1 Nettoyage Hebdomadaire

**Fréquence :** Chaque vendredi

**Script :** À créer [`scripts/maintenance/cleanup_docker.ps1`](myia_vllm/scripts/maintenance/cleanup_docker.ps1)

**Actions :**
```powershell
# 1. Supprimer containers arrêtés
docker container prune -f

# 2. Supprimer images inutilisées
docker image prune -a --filter "until=168h" -f

# 3. Supprimer volumes orphelins
docker volume prune -f

# 4. Afficher espace récupéré
docker system df
```

**⚠️ ATTENTION** : NE PAS supprimer volumes nommés (contiennent modèles)

**Durée estimée :** 10 minutes

---

### 2.2 Nettoyage Mensuel Complet

**Fréquence :** Premier jour du mois

**Actions supplémentaires :**
```powershell
# 1. Arrêter tous containers vLLM
cd myia_vllm
docker compose -p myia_vllm --env-file .env -f configs/docker/docker-compose.yml down

# 2. Nettoyage agressif
docker system prune -a -f

# 3. Redéployer
pwsh -c ".\scripts\deploy_medium_monitored.ps1"
```

**Durée estimée :** 30 minutes

---

## 3. Backup Configuration

### 3.1 Backup Automatique

**Fréquence :** Avant chaque modification de [`medium.yml`](myia_vllm/configs/docker/profiles/medium.yml)

**Script :** À créer [`scripts/maintenance/backup_config.ps1`](myia_vllm/scripts/maintenance/backup_config.ps1)

**Actions :**
```powershell
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$source = "configs/docker/profiles/medium.yml"
$destination = "configs/docker/profiles/backups/medium_$timestamp.yml"

# Créer répertoire backups
New-Item -ItemType Directory -Force -Path "configs/docker/profiles/backups"

# Copier fichier
Copy-Item -Path $source -Destination $destination

Write-Host "✓ Backup créé: $destination"
```

**Durée estimée :** 1 minute

---

### 3.2 Backup Manuel Complet

**Fréquence :** Avant migrations majeures (ex: Qwen3-VL)

**Fichiers à sauvegarder :**
```powershell
# Créer archive complète
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = "backups/full_backup_$timestamp"

New-Item -ItemType Directory -Force -Path $backupDir

# Copier fichiers critiques
Copy-Item ".env" -Destination "$backupDir/.env"
Copy-Item "configs/docker/profiles/medium.yml" -Destination "$backupDir/medium.yml"
Copy-Item "docs/" -Destination "$backupDir/docs/" -Recurse
Copy-Item "scripts/" -Destination "$backupDir/scripts/" -Recurse

Write-Host "✓ Backup complet créé: $backupDir"
```

**Durée estimée :** 5 minutes

---

## 4. Mise à Jour Modèle

### 4.1 Vérification Nouvelles Versions

**Fréquence :** Mensuelle

**Actions :**
```powershell
# 1. Vérifier versions disponibles
# Visiter https://huggingface.co/Qwen/Qwen3-32B-AWQ

# 2. Lire changelog
# Identifier améliorations pertinentes

# 3. Décider si mise à jour nécessaire
# Peser bénéfices vs risques
```

**Critères de décision :**
- Corrections de bugs critiques
- Améliorations performance significatives (>10%)
- Nouvelles fonctionnalités requises

**Durée estimée :** 15 minutes

---

### 4.2 Procédure Mise à Jour

**Prérequis :** Backup complet effectué

**Étapes :**
```powershell
# 1. Arrêter service
cd myia_vllm
docker compose -p myia_vllm --env-file .env -f configs/docker/docker-compose.yml down

# 2. Supprimer ancien modèle (si espace limité)
docker volume rm myia_vllm_models

# 3. Modifier version dans Dockerfile ou docker-compose.yml
# Mettre à jour tag version

# 4. Reconstruire image
docker compose -p myia_vllm --env-file .env -f configs/docker/docker-compose.yml build --no-cache

# 5. Redéployer
pwsh -c ".\scripts\deploy_medium_monitored.ps1"

# 6. Valider
pwsh -c ".\scripts\testing\mission15_validation_tests.ps1"
```

**Durée estimée :** 2-3 heures (téléchargement modèle)

---

## 5. Rotation Logs

### 5.1 Rotation Hebdomadaire

**Fréquence :** Chaque dimanche

**Actions :**
```powershell
$timestamp = Get-Date -Format "yyyyMMdd"
$logDir = "logs/archived"

# Créer répertoire archives
New-Item -ItemType Directory -Force -Path $logDir

# Exporter logs container
docker logs myia_vllm-medium-qwen3 > "$logDir/container_logs_$timestamp.txt"

# Archiver logs > 30 jours
Get-ChildItem "$logDir" -Filter "*.txt" | Where-Object {
    $_.LastWriteTime -lt (Get-Date).AddDays(-30)
} | Compress-Archive -DestinationPath "$logDir/archive_old_logs.zip" -Update
```

**Durée estimée :** 5 minutes

---

### 5.2 Nettoyage Logs Anciens

**Fréquence :** Trimestrielle

**Actions :**
```powershell
# Supprimer logs > 90 jours
Get-ChildItem "logs/archived" -Filter "*.txt" | Where-Object {
    $_.LastWriteTime -lt (Get-Date).AddDays(-90)
} | Remove-Item -Force

# Supprimer archives > 180 jours
Get-ChildItem "logs/archived" -Filter "*.zip" | Where-Object {
    $_.LastWriteTime -lt (Get-Date).AddDays(-180)
} | Remove-Item -Force
```

**Durée estimée :** 10 minutes

---

## 6. Calendrier Maintenance

### Vue d'Ensemble

| Fréquence | Tâche | Script | Durée estimée |
|-----------|-------|--------|---------------|
| **Quotidien** | Monitoring health | `health_check.ps1` | 2 min |
| **Hebdomadaire** | Monitoring performance | [`test_kv_cache_acceleration.ps1`](myia_vllm/scripts/test_kv_cache_acceleration.ps1) | 5 min |
| **Hebdomadaire** | Nettoyage Docker | `cleanup_docker.ps1` | 10 min |
| **Hebdomadaire** | Rotation logs | Script manuel | 5 min |
| **Mensuel** | Nettoyage complet | Script manuel | 30 min |
| **Mensuel** | Vérification mises à jour | Vérification manuelle | 15 min |
| **Trimestriel** | Nettoyage logs anciens | Script manuel | 10 min |
| **Avant modifications** | Backup config | `backup_config.ps1` | 1 min |

### Checklist Hebdomadaire

**Lundi :**
- [ ] Monitoring health quotidien
- [ ] Monitoring performance hebdomadaire (test KV Cache)
- [ ] Analyser logs erreur semaine écoulée

**Mardi-Jeudi :**
- [ ] Monitoring health quotidien

**Vendredi :**
- [ ] Monitoring health quotidien
- [ ] Nettoyage Docker hebdomadaire
- [ ] Vérifier espace disque

**Dimanche :**
- [ ] Rotation logs hebdomadaire
- [ ] Archiver logs > 30 jours

### Checklist Mensuelle

**Premier jour du mois :**
- [ ] Nettoyage Docker complet
- [ ] Vérifier nouvelles versions modèle
- [ ] Tester performance globale
- [ ] Réviser documentation mise à jour

**Actions :**
```powershell
# Nettoyage complet mensuel
cd myia_vllm
docker compose -p myia_vllm --env-file .env -f configs/docker/docker-compose.yml down
docker system prune -a -f
pwsh -c ".\scripts\deploy_medium_monitored.ps1"

# Validation
pwsh -c ".\scripts\testing\mission15_validation_tests.ps1"
```

### Checklist Trimestrielle

**Premier jour du trimestre :**
- [ ] Nettoyage logs anciens (> 90 jours)
- [ ] Audit complet configuration
- [ ] Mise à jour documentation
- [ ] Révision scripts maintenance

---

## 📚 Scripts de Référence

### Scripts Existants

- [`deploy_medium_monitored.ps1`](myia_vllm/scripts/deploy_medium_monitored.ps1) - Déploiement automatisé
- [`monitor_medium.ps1`](myia_vllm/scripts/monitor_medium.ps1) - Monitoring live
- [`test_kv_cache_acceleration.ps1`](myia_vllm/scripts/test_kv_cache_acceleration.ps1) - Benchmark KV Cache
- [`mission15_validation_tests.ps1`](myia_vllm/scripts/testing/mission15_validation_tests.ps1) - Tests validation

### Scripts à Créer (Sous-tâche 3/4)

Les scripts suivants seront créés dans la sous-tâche 3/4 :

- [`scripts/maintenance/health_check.ps1`](myia_vllm/scripts/maintenance/health_check.ps1) - Health check automatisé
- [`scripts/maintenance/cleanup_docker.ps1`](myia_vllm/scripts/maintenance/cleanup_docker.ps1) - Nettoyage Docker
- [`scripts/maintenance/backup_config.ps1`](myia_vllm/scripts/maintenance/backup_config.ps1) - Backup configuration

**Priorité :** Ces scripts amélioreront significativement l'automatisation de la maintenance.

---

## 📊 Tableau de Bord Maintenance

### Indicateurs Clés de Performance (KPI)

| Métrique | Objectif | Seuil Alerte |
|----------|----------|--------------|
| Uptime mensuel | > 99% | < 95% |
| Logs erreur/semaine | < 10 | > 20 |
| Accélération KV Cache | ≥ x3.0 | < x2.5 |
| Espace disque libre | > 20GB | < 10GB |
| VRAM utilisée | < 90% | > 95% |
| TTFT moyen (avec cache) | < 1000ms | > 1500ms |

### Actions si Seuil Alerte Atteint

**Uptime < 95% :**
1. Analyser logs crashes
2. Vérifier stabilité GPU
3. Réduire `gpu-memory-utilization`

**Logs erreur > 20/semaine :**
1. Catégoriser erreurs
2. Identifier patterns récurrents
3. Consulter [`TROUBLESHOOTING.md`](myia_vllm/docs/TROUBLESHOOTING.md)

**Accélération KV Cache < x2.5 :**
1. Tester avec script benchmark
2. Vérifier configuration optimale appliquée
3. Consulter [`OPTIMIZATION_GUIDE.md`](myia_vllm/docs/OPTIMIZATION_GUIDE.md)

**Espace disque < 10GB :**
1. Nettoyer logs anciens immédiatement
2. Supprimer images Docker inutilisées
3. Archiver test results

**VRAM > 95% :**
1. Réduire `gpu-memory-utilization` de 0.05
2. Limiter `max-num-seqs`
3. Monitorer après ajustement

**TTFT > 1500ms :**
1. Benchmark KV Cache
2. Vérifier GPU utilization
3. Redémarrer service si nécessaire

---

## 🔧 Outils et Commandes Utiles

### Monitoring Rapide

```powershell
# Status complet en une commande
docker ps --filter "name=myia_vllm-medium-qwen3" --format "{{.Status}}" ; `
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader ; `
docker logs --tail 50 myia_vllm-medium-qwen3 | Select-String "error"
```

### Restart Rapide

```powershell
# Redémarrage propre
cd myia_vllm
docker compose -p myia_vllm --env-file .env -f configs/docker/docker-compose.yml restart medium-qwen3

# Attendre healthy
pwsh -c ".\scripts\monitoring\wait_for_container_healthy.ps1 -Timeout 600"
```

### Diagnostic Approfondi

```powershell
# Collecter toutes les infos pertinentes
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
docker logs myia_vllm-medium-qwen3 > "logs/diagnostic_$timestamp.txt"
nvidia-smi >> "logs/diagnostic_$timestamp.txt"
docker ps -a >> "logs/diagnostic_$timestamp.txt"
```

---

## 📚 Documentation Complémentaire

- **Guide Déploiement** : [`DEPLOYMENT_GUIDE.md`](myia_vllm/docs/DEPLOYMENT_GUIDE.md)
- **Guide Optimisation** : [`OPTIMIZATION_GUIDE.md`](myia_vllm/docs/OPTIMIZATION_GUIDE.md)
- **Guide Dépannage** : [`TROUBLESHOOTING.md`](myia_vllm/docs/TROUBLESHOOTING.md)
- **Index Documentation** : [`DOCUMENTATION_INDEX.md`](myia_vllm/docs/DOCUMENTATION_INDEX.md)

---

**Fin des Procédures de Maintenance vLLM Medium**