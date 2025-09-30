# Gestion des configurations sensibles

Ce document explique comment gérer les informations sensibles (tokens, clés API, chemins spécifiques) dans le projet vLLM.

## Problématique

Les fichiers docker-compose contiennent des informations sensibles qui ne devraient pas être partagées publiquement:
- Token Hugging Face
- Clés API VLLM
- Chemins de montage spécifiques
- Configurations GPU spécifiques

## Solution mise en place

Nous avons mis en place un système de gestion des secrets basé sur:
1. Un fichier `.env` (non versionné) contenant toutes les informations sensibles
2. Des scripts pour sauvegarder et restaurer ces informations
3. Des hooks git pour automatiser le processus

## Utilisation

### Installation initiale

1. Cloner le dépôt
2. Exécuter le script d'installation des hooks git:
   ```bash
   bash scripts/install-hooks.sh
   ```
3. Créer le fichier `.env` en copiant `.env.example`:
   ```bash
   cp .env.example .env
   ```
4. Modifier le fichier `.env` avec vos propres valeurs

### Extraction des secrets existants

Si vous avez déjà des fichiers docker-compose avec des informations sensibles, vous pouvez les extraire:

```bash
bash scripts/save-secrets.sh
```

### Restauration des secrets

Pour restaurer les secrets depuis le fichier `.env` vers les fichiers docker-compose:

```bash
bash scripts/restore-secrets.sh
```

### Workflow git

Les hooks git automatisent le processus:
- **pre-commit**: Sauvegarde automatiquement les secrets avant un commit et vérifie qu'aucun secret n'est commité
- **post-checkout**: Propose de restaurer les secrets après un checkout

## Structure des fichiers

```
vllm-configs/
├── .env.example          # Exemple de fichier d'environnement (versionné)
├── .env                  # Fichier d'environnement réel (non versionné)
├── scripts/
│   ├── save-secrets.sh   # Script de sauvegarde des secrets
│   ├── restore-secrets.sh # Script de restauration des secrets
│   ├── install-hooks.sh  # Script d'installation des hooks git
│   └── git-hooks/
│       ├── pre-commit    # Hook exécuté avant un commit
│       └── post-checkout # Hook exécuté après un checkout
└── docker-compose/       # Fichiers docker-compose (sans secrets)
```

## Variables d'environnement

Le fichier `.env` contient les variables suivantes:

| Variable | Description |
|----------|-------------|
| `HUGGING_FACE_HUB_TOKEN` | Token d'accès à Hugging Face |
| `VLLM_API_KEY_MICRO` | Clé API pour le service micro |
| `VLLM_API_KEY_MINI` | Clé API pour le service mini |
| `VLLM_API_KEY_MEDIUM` | Clé API pour le service medium |
| `VLLM_API_KEY_LARGE` | Clé API pour le service large |
| `VLLM_PORT_MICRO` | Port pour le service micro |
| `VLLM_PORT_MINI` | Port pour le service mini |
| `VLLM_PORT_MEDIUM` | Port pour le service medium |
| `VLLM_PORT_LARGE` | Port pour le service large |
| `CUDA_VISIBLE_DEVICES_MICRO` | GPU(s) pour le service micro |
| `CUDA_VISIBLE_DEVICES_MINI` | GPU(s) pour le service mini |
| `CUDA_VISIBLE_DEVICES_MEDIUM` | GPU(s) pour le service medium |
| `CUDA_VISIBLE_DEVICES_LARGE` | GPU(s) pour le service large |
| `HF_CACHE_PATH` | Chemin vers le cache Hugging Face |
| `GPU_MEMORY_UTILIZATION_MICRO` | Utilisation mémoire GPU pour micro |
| `GPU_MEMORY_UTILIZATION_MINI` | Utilisation mémoire GPU pour mini |
| `GPU_MEMORY_UTILIZATION_MEDIUM` | Utilisation mémoire GPU pour medium |
| `GPU_MEMORY_UTILIZATION_LARGE` | Utilisation mémoire GPU pour large |

## Bonnes pratiques

1. Ne jamais commiter le fichier `.env`
2. Toujours utiliser les variables d'environnement dans les fichiers docker-compose
3. Exécuter `restore-secrets.sh` avant de faire des modifications aux fichiers docker-compose
4. Exécuter `save-secrets.sh` après avoir modifié les fichiers docker-compose