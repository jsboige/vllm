# Guide d'utilisation des services vLLM sous Windows 11

Ce document explique comment gérer les services vLLM sous Windows 11 avec Docker Desktop.

## Prérequis

- Windows 11
- Docker Desktop installé et configuré avec WSL 2
- PowerShell

## Structure des fichiers

- `prepare-update.ps1` : Script de préparation pour la mise à jour des services vLLM
- `start-vllm-services.ps1` : Script pour démarrer les services vLLM
- `test-vllm-services.ps1` : Script pour tester les services vLLM
- `quick-update-qwen3.ps1` : Script généré automatiquement pour mettre à jour rapidement les services vLLM Qwen3

## Démarrer les services vLLM

Pour démarrer les services vLLM, exécutez le script suivant dans PowerShell :

```powershell
.\vllm-configs\start-vllm-services.ps1
```

Options disponibles :
- `-Help` : Affiche l'aide
- `-Verbose` : Mode verbeux (affiche plus de détails)

## Tester les services vLLM

Pour vérifier que les services vLLM fonctionnent correctement, exécutez :

```powershell
.\vllm-configs\test-vllm-services.ps1
```

Options disponibles :
- `-Help` : Affiche l'aide
- `-Verbose` : Mode verbeux (affiche plus de détails)
- `-DetailedTest` : Effectue des tests détaillés des API (génération de texte)

## Préparer une mise à jour des services vLLM

Pour préparer une mise à jour des services vLLM, exécutez :

```powershell
.\vllm-configs\prepare-update.ps1
```

Options disponibles :
- `-Help` : Affiche l'aide
- `-Verbose` : Mode verbeux (affiche plus de détails)
- `-DryRun` : Simule les actions sans les exécuter

Ce script va :
1. Vérifier l'état actuel des services vLLM
2. Créer un répertoire de build temporaire
3. Créer un Dockerfile optimisé
4. Construire l'image Docker
5. Générer un script de mise à jour rapide (`quick-update-qwen3.ps1`)

## Effectuer une mise à jour rapide

Une fois la préparation terminée, vous pouvez effectuer la mise à jour rapide en exécutant :

```powershell
.\vllm-configs\quick-update-qwen3.ps1
```

Ce script va :
1. Arrêter les services vLLM Qwen3
2. Démarrer les services avec la nouvelle image Docker
3. Vérifier que tout fonctionne correctement

## Configuration des services

Les services vLLM sont configurés dans les fichiers docker-compose suivants :
- `docker-compose-micro-qwen3.yml` : Service micro (modèle 1.7B)
- `docker-compose-mini-qwen3.yml` : Service mini (modèle 8B)
- `docker-compose-medium-qwen3.yml` : Service medium (modèle 8B avec 2 GPUs)

Ces fichiers sont déjà adaptés pour Windows 11 avec WSL.

## Résolution des problèmes

Si vous rencontrez des problèmes, vérifiez les fichiers de log générés par les scripts :
- `prepare-update.log`
- `start-vllm-services.log`
- `test-vllm-services.log`
- `quick-update-qwen3.log`

Ces fichiers contiennent des informations détaillées sur les actions effectuées et les erreurs rencontrées.