# Configuration des Variables d'Environnement vLLM

## 🔐 Principes de Sécurité

### Pourquoi .env ne doit JAMAIS être commité

Le fichier `.env` contient des **secrets sensibles** qui, s'ils sont exposés publiquement, peuvent compromettre votre infrastructure:

1. **Token Hugging Face** (`HUGGING_FACE_HUB_TOKEN`)
   - Accès complet à votre compte Hugging Face
   - Téléchargement illimité de modèles (coûts potentiels)
   - Accès aux modèles privés et données personnelles

2. **Clés API vLLM** (`VLLM_API_KEY_*`)
   - Accès non autorisé à vos services d'inférence
   - Utilisation abusive de vos ressources GPU (très coûteuses)
   - Déni de service potentiel

3. **URLs d'infrastructure** (`VLLM_URL_*`)
   - Exposition de l'architecture réseau
   - Facilite les attaques ciblées

### Historique de Compromissions

⚠️ **LEÇON IMPORTANTE**: Ce projet a subi plusieurs fuites de secrets:
- **Mai-Juillet 2025**: Token HuggingFace compromis lors d'attaque APT
- **Historique Git**: Multiples commits avec tokens réels exposés
- **Clés API**: Clés compromises retrouvées dans l'historique

**Action corrective**: Tous les secrets historiques ont été révoqués et remplacés.

---

## 📋 Configuration Initiale

### Étape 1: Copier le Template

```bash
# Depuis la racine du projet
cp myia_vllm/.env.example myia_vllm/.env
```

### Étape 2: Éditer le Fichier .env

```bash
# Utiliser votre éditeur préféré
code myia_vllm/.env
# ou
nano myia_vllm/.env
```

### Étape 3: Remplacer les Placeholders

#### 🔑 Token Hugging Face (OBLIGATOIRE)

1. Créer un compte sur [Hugging Face](https://huggingface.co/)
2. Aller dans [Settings > Access Tokens](https://huggingface.co/settings/tokens)
3. Créer un nouveau token avec les permissions:
   - ✅ Read access to contents of all public repositories
   - ✅ Read access to contents of all repos you can access
4. Copier le token (format: `hf_` + 37 caractères)

```env
HUGGING_FACE_HUB_TOKEN=hf_VotreTokenRéelDe37Caractères
```

#### 🔐 Clés API vLLM (OBLIGATOIRE)

Générer des clés aléatoires sécurisées (32 caractères minimum):

```powershell
# Génération PowerShell (recommandé)
pwsh -c "[guid]::NewGuid().ToString('N').ToUpper()"

# Génération Python (alternative)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Génération OpenSSL (alternative)
openssl rand -hex 16
```

Exemple de configuration sécurisée:

```env
VLLM_API_KEY_MICRO=A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6
VLLM_API_KEY_MINI=Q7R8S9T0U1V2W3X4Y5Z6A7B8C9D0E1F2
VLLM_API_KEY_MEDIUM=G3H4I5J6K7L8M9N0O1P2Q3R4S5T6U7V8
```

#### 🌐 URLs Externes (OPTIONNEL)

Si vos services sont exposés publiquement via reverse proxy/load balancer:

```env
VLLM_URL_MICRO=https://api.micro.votre-domaine.com/
VLLM_URL_MINI=https://api.mini.votre-domaine.com/
VLLM_URL_MEDIUM=https://api.medium.votre-domaine.com/
```

**Note**: Laisser les valeurs par défaut si utilisation locale uniquement.

---

## 📊 Variables d'Environnement Détaillées

### Authentification

| Variable | Type | Obligatoire | Description |
|----------|------|-------------|-------------|
| `HUGGING_FACE_HUB_TOKEN` | string | ✅ Oui | Token d'accès Hugging Face Hub |
| `VLLM_API_KEY_MICRO` | string | ✅ Oui | Clé API service micro |
| `VLLM_API_KEY_MINI` | string | ✅ Oui | Clé API service mini |
| `VLLM_API_KEY_MEDIUM` | string | ✅ Oui | Clé API service medium |

### Configuration Réseau

| Variable | Type | Défaut | Description |
|----------|------|--------|-------------|
| `VLLM_PORT_MICRO` | integer | 5000 | Port d'écoute service micro |
| `VLLM_PORT_MINI` | integer | 5001 | Port d'écoute service mini |
| `VLLM_PORT_MEDIUM` | integer | 5002 | Port d'écoute service medium |
| `VLLM_URL_MICRO` | string | - | URL publique service micro (optionnel) |
| `VLLM_URL_MINI` | string | - | URL publique service mini (optionnel) |
| `VLLM_URL_MEDIUM` | string | - | URL publique service medium (optionnel) |

### Configuration GPU

| Variable | Type | Défaut | Description |
|----------|------|--------|-------------|
| `CUDA_VISIBLE_DEVICES_MICRO` | string | "2" | GPU(s) pour service micro |
| `CUDA_VISIBLE_DEVICES_MINI` | string | "2" | GPU(s) pour service mini |
| `CUDA_VISIBLE_DEVICES_MEDIUM` | string | "0,1" | GPU(s) pour service medium |
| `GPU_MEMORY_UTILIZATION_MICRO` | float | 0.90 | % mémoire GPU utilisé (micro) |
| `GPU_MEMORY_UTILIZATION_MINI` | float | 0.90 | % mémoire GPU utilisé (mini) |
| `GPU_MEMORY_UTILIZATION_MEDIUM` | float | 0.95 | % mémoire GPU utilisé (medium) |

**Notes GPU**:
- Format: numéros séparés par virgules (ex: `"0,1"` pour 2 GPUs)
- Vérifier disponibilité: `nvidia-smi`
- Service medium nécessite 2 GPUs (tensor parallelism)
- `GPU_MEMORY_UTILIZATION`: 0.90-0.95 recommandé pour production

### Modèles

| Variable | Type | Défaut | Description |
|----------|------|--------|-------------|
| `VLLM_MODEL_MICRO` | string | Orion-zhen/Qwen3-1.7B-AWQ | Modèle service micro |
| `VLLM_MODEL_MINI` | string | Qwen/Qwen3-8B-AWQ | Modèle service mini |
| `VLLM_MODEL_MEDIUM` | string | Qwen/Qwen3-32B-AWQ | Modèle service medium |

**Notes Modèles**:
- Format: `organisation/nom-modèle` (Hugging Face Hub)
- Suffixe `-AWQ`: quantization pour performance
- Téléchargement automatique au premier démarrage

### Paramètres Système

| Variable | Type | Défaut | Description |
|----------|------|--------|-------------|
| `OMP_NUM_THREADS` | integer | 1 | Threads OpenMP (1 recommandé) |
| `TZ` | string | Europe/Paris | Fuseau horaire |
| `HF_CACHE_PATH` | string | ~/.cache/huggingface | Cache Hugging Face (optionnel) |

### Paramètres Avancés (Optionnels)

| Variable | Type | Défaut | Description |
|----------|------|--------|-------------|
| `DTYPE_MICRO` | string | half | Type de données (half/float16/bfloat16) |
| `DTYPE_MINI` | string | half | Type de données mini |
| `DTYPE_MEDIUM` | string | half | Type de données medium |
| `MAX_MODEL_LEN_MICRO` | integer | 32768 | Contexte max micro (tokens) |
| `MAX_MODEL_LEN_MINI` | integer | 65536 | Contexte max mini (tokens) |
| `MAX_MODEL_LEN_MEDIUM` | integer | 131072 | Contexte max medium (tokens) |
| `VLLM_ATTENTION_BACKEND` | string | FLASHINFER | Backend attention (FLASHINFER/FLASH_ATTN) |
| `VLLM_ALLOW_LONG_MAX_MODEL_LEN` | integer | 1 | Autoriser contextes > config modèle |

---

## ✅ Vérification de la Configuration

### Checklist Pré-Déploiement

```bash
# 1. Vérifier que .env existe
test -f myia_vllm/.env && echo "✅ .env existe" || echo "❌ .env manquant"

# 2. Vérifier que .env n'est PAS dans Git
git ls-files myia_vllm/.env | grep -q "." && echo "❌ .env est tracké par Git!" || echo "✅ .env non tracké"

# 3. Vérifier .gitignore
grep -q "^\.env$" .gitignore && echo "✅ .env dans .gitignore" || echo "❌ .env manquant dans .gitignore"

# 4. Vérifier GPUs disponibles
nvidia-smi --query-gpu=index,name,memory.total --format=csv

# 5. Tester connectivité Hugging Face
huggingface-cli whoami
```

### Script de Validation

```bash
# myia_vllm/scripts/validate_env.sh
#!/bin/bash

echo "=== Validation Configuration .env ==="

# Vérifier présence du fichier
if [ ! -f "myia_vllm/.env" ]; then
    echo "❌ Fichier .env manquant"
    echo "   Créer avec: cp myia_vllm/.env.example myia_vllm/.env"
    exit 1
fi

# Vérifier variables obligatoires
required_vars=(
    "HUGGING_FACE_HUB_TOKEN"
    "VLLM_API_KEY_MICRO"
    "VLLM_API_KEY_MINI"
    "VLLM_API_KEY_MEDIUM"
)

source myia_vllm/.env

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Variable manquante: $var"
        exit 1
    fi
    echo "✅ $var configuré"
done

# Vérifier format token HuggingFace
if [[ ! $HUGGING_FACE_HUB_TOKEN =~ ^hf_[A-Za-z0-9]{37}$ ]]; then
    echo "⚠️  Format token HuggingFace invalide (attendu: hf_ + 37 caractères)"
fi

echo "✅ Configuration valide"
```

---

## 🔒 Bonnes Pratiques de Sécurité

### 1. Rotation des Secrets

**Fréquence recommandée**:
- Tokens HuggingFace: tous les 6 mois
- Clés API vLLM: tous les 3 mois
- Immédiatement après tout incident de sécurité

**Procédure**:
1. Générer nouveau secret
2. Mettre à jour `.env`
3. Redémarrer services
4. Révoquer ancien secret
5. Tester fonctionnement

### 2. Gestion des Accès

- **Principe du moindre privilège**: créer des tokens avec permissions minimales
- **Séparation des environnements**: `.env` différents pour dev/staging/prod
- **Audit régulier**: vérifier qui a accès aux secrets

### 3. Sauvegardes Sécurisées

```bash
# ❌ NE JAMAIS faire ceci:
git add myia_vllm/.env
cp .env .env.backup  # dans le même repo
tar czf backup.tar.gz .env  # puis commit de l'archive

# ✅ Méthodes sécurisées:
# Option 1: Gestionnaire de mots de passe (1Password, Bitwarden, etc.)
# Option 2: Azure Key Vault, AWS Secrets Manager, HashiCorp Vault
# Option 3: Stockage chiffré externe au dépôt Git
```

### 4. Détection de Fuites

```bash
# Vérifier historique Git pour fuites accidentelles
git log --all --full-history --source --patch -- '*/.env' '*/.env.*' | grep -i "token\|key\|secret"

# Scanner avec git-secrets (recommandé)
git secrets --scan --scan-history

# Scanner avec truffleHog (détection de secrets)
trufflehog git file://. --only-verified
```

---

## 🚨 Procédure en Cas de Fuite

### Si Token/Clé Exposé dans Git

1. **Révocation immédiate**:
   ```bash
   # HuggingFace: https://huggingface.co/settings/tokens
   # → Supprimer le token compromis
   
   # vLLM APIs: Régénérer toutes les clés
   pwsh -c "[guid]::NewGuid().ToString('N').ToUpper()"
   ```

2. **Nettoyage historique Git** (⚠️ opération destructive):
   ```bash
   # Utiliser BFG Repo-Cleaner (recommandé)
   java -jar bfg.jar --delete-files .env
   git reflog expire --expire=now --all
   git gc --prune=now --aggressive
   
   # Ou git-filter-repo (alternative)
   git filter-repo --invert-paths --path myia_vllm/.env
   ```

3. **Force push** (si repo privé et équipe coordonnée):
   ```bash
   git push --force --all
   git push --force --tags
   ```

4. **Communication équipe**:
   - Alerter tous les collaborateurs
   - Demander de supprimer leurs clones locaux
   - Re-cloner après nettoyage

5. **Monitoring post-incident**:
   - Surveiller utilisation anormale des ressources
   - Vérifier logs d'accès HuggingFace
   - Auditer accès aux services vLLM

---

## 📚 Ressources Complémentaires

- [Hugging Face Security](https://huggingface.co/docs/hub/security)
- [Git Secrets Best Practices](https://github.com/awslabs/git-secrets)
- [OWASP Secrets Management](https://owasp.org/www-community/vulnerabilities/Use_of_hard-coded_password)
- [12-Factor App: Config](https://12factor.net/config)

---

## 📝 Changelog

| Version | Date | Changements |
|---------|------|-------------|
| 1.0.0 | 2025-10-16 | Documentation initiale |

---

**Dernière mise à jour**: 2025-10-16  
**Auteur**: Système de déploiement vLLM  
**Statut**: ✅ Production