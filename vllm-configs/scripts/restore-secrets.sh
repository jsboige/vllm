#!/bin/bash

# Script de restauration des informations sensibles
# Ce script restaure les informations sensibles depuis le fichier .env
# vers les fichiers docker-compose

# Vérifier si le dossier scripts existe
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"

echo "Restauration des informations sensibles depuis $ENV_FILE"

# Vérifier si le fichier .env existe
if [ ! -f "$ENV_FILE" ]; then
    echo "Erreur: Le fichier $ENV_FILE n'existe pas."
    echo "Veuillez exécuter le script save-secrets.sh pour créer ce fichier."
    exit 1
fi

# Fonction pour remplacer une valeur dans un fichier docker-compose
replace_value() {
    local file=$1
    local pattern=$2
    local var_name=$3
    local suffix=$4
    
    # Lire la valeur depuis le fichier .env
    local value=$(grep "^$var_name=" "$ENV_FILE" | cut -d'=' -f2)
    
    if [ -n "$value" ]; then
        # Remplacer la valeur dans le fichier docker-compose
        sed -i "s/$pattern/$var_name$suffix:-$value}/g" "$file"
        echo "Variable $var_name restaurée dans $file"
    else
        echo "Avertissement: La variable $var_name n'a pas été trouvée dans $ENV_FILE"
    fi
}

# Restaurer le token Hugging Face dans tous les fichiers
for file in "$ROOT_DIR"/docker-compose/docker-compose-*.yml; do
    sed -i "s/HUGGING_FACE_HUB_TOKEN:-[^}]*/HUGGING_FACE_HUB_TOKEN:-\${HUGGING_FACE_HUB_TOKEN}/g" "$file"
done

# Restaurer les clés API VLLM
replace_value "$ROOT_DIR/docker-compose/docker-compose-micro-qwen3.yml" "VLLM_API_KEY:-[^}]*" "VLLM_API_KEY_MICRO" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-micro.yml" "VLLM_API_KEY:-[^}]*" "VLLM_API_KEY_MICRO" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-mini-qwen3.yml" "VLLM_API_KEY:-[^}]*" "VLLM_API_KEY_MINI" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-mini.yml" "VLLM_API_KEY:-[^}]*" "VLLM_API_KEY_MINI" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-medium-qwen3.yml" "VLLM_API_KEY:-[^}]*" "VLLM_API_KEY_MEDIUM" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-medium.yml" "VLLM_API_KEY:-[^}]*" "VLLM_API_KEY_MEDIUM" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-large.yml" "VLLM_API_KEY:-[^}]*" "VLLM_API_KEY_LARGE" ""

# Restaurer les ports
replace_value "$ROOT_DIR/docker-compose/docker-compose-micro-qwen3.yml" "VLLM_PORT:-[^}]*" "VLLM_PORT_MICRO" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-micro.yml" "VLLM_PORT:-[^}]*" "VLLM_PORT_MICRO" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-mini-qwen3.yml" "VLLM_PORT:-[^}]*" "VLLM_PORT_MINI" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-mini.yml" "VLLM_PORT:-[^}]*" "VLLM_PORT_MINI" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-medium-qwen3.yml" "VLLM_PORT:-[^}]*" "VLLM_PORT_MEDIUM" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-medium.yml" "VLLM_PORT:-[^}]*" "VLLM_PORT_MEDIUM" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-large.yml" "VLLM_PORT:-[^}]*" "VLLM_PORT_LARGE" ""

# Restaurer les configurations GPU
replace_value "$ROOT_DIR/docker-compose/docker-compose-micro-qwen3.yml" "CUDA_VISIBLE_DEVICES:-[^}]*" "CUDA_VISIBLE_DEVICES_MICRO" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-micro.yml" "CUDA_VISIBLE_DEVICES:-[^}]*" "CUDA_VISIBLE_DEVICES_MICRO" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-mini-qwen3.yml" "CUDA_VISIBLE_DEVICES:-[^}]*" "CUDA_VISIBLE_DEVICES_MINI" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-mini.yml" "CUDA_VISIBLE_DEVICES:-[^}]*" "CUDA_VISIBLE_DEVICES_MINI" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-medium-qwen3.yml" "CUDA_VISIBLE_DEVICES:-[^}]*" "CUDA_VISIBLE_DEVICES_MEDIUM" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-medium.yml" "CUDA_VISIBLE_DEVICES:-[^}]*" "CUDA_VISIBLE_DEVICES_MEDIUM" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-large.yml" "CUDA_VISIBLE_DEVICES:-[^}]*" "CUDA_VISIBLE_DEVICES_LARGE" ""

# Restaurer les paramètres d'utilisation de la mémoire GPU
replace_value "$ROOT_DIR/docker-compose/docker-compose-micro-qwen3.yml" "GPU_MEMORY_UTILIZATION:-[^}]*" "GPU_MEMORY_UTILIZATION_MICRO" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-micro.yml" "GPU_MEMORY_UTILIZATION:-[^}]*" "GPU_MEMORY_UTILIZATION_MICRO" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-mini-qwen3.yml" "GPU_MEMORY_UTILIZATION:-[^}]*" "GPU_MEMORY_UTILIZATION_MINI" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-mini.yml" "GPU_MEMORY_UTILIZATION:-[^}]*" "GPU_MEMORY_UTILIZATION_MINI" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-medium-qwen3.yml" "GPU_MEMORY_UTILIZATION:-[^}]*" "GPU_MEMORY_UTILIZATION_MEDIUM" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-medium.yml" "GPU_MEMORY_UTILIZATION:-[^}]*" "GPU_MEMORY_UTILIZATION_MEDIUM" ""
replace_value "$ROOT_DIR/docker-compose/docker-compose-large.yml" "GPU_MEMORY_UTILIZATION:-[^}]*" "GPU_MEMORY_UTILIZATION_LARGE" ""

# Restaurer le chemin du cache Hugging Face
HF_CACHE_PATH=$(grep "^HF_CACHE_PATH=" "$ENV_FILE" | cut -d'=' -f2)
if [ -n "$HF_CACHE_PATH" ]; then
    for file in "$ROOT_DIR"/docker-compose/docker-compose-*.yml; do
        sed -i "s|\\\\\\\\wsl.localhost\\\\\\\\Ubuntu\\\\\\\\home\\\\\\\\.*\\\\\\\\hub|$HF_CACHE_PATH|g" "$file"
    done
    echo "Variable HF_CACHE_PATH restaurée dans tous les fichiers docker-compose"
fi

echo "Restauration terminée"