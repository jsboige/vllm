#!/bin/bash

# Script de sauvegarde des informations sensibles
# Ce script extrait les informations sensibles des fichiers docker-compose
# et les sauvegarde dans un fichier .env

# Vérifier si le dossier scripts existe
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.env"

echo "Sauvegarde des informations sensibles dans $ENV_FILE"

# Créer le fichier .env s'il n'existe pas
touch "$ENV_FILE"

# Fonction pour extraire une valeur d'un fichier docker-compose
extract_value() {
    local file=$1
    local pattern=$2
    local var_name=$3
    
    # Extraire la valeur en utilisant grep et sed
    local value=$(grep -o "$pattern" "$file" | sed -E "s/$pattern/\1/")
    
    if [ -n "$value" ]; then
        # Vérifier si la variable existe déjà dans le fichier .env
        if grep -q "^$var_name=" "$ENV_FILE"; then
            # Remplacer la valeur existante
            sed -i "s/^$var_name=.*/$var_name=$value/" "$ENV_FILE"
        else
            # Ajouter la nouvelle variable
            echo "$var_name=$value" >> "$ENV_FILE"
        fi
        echo "Variable $var_name sauvegardée"
    fi
}

# Extraire le token Hugging Face
extract_value "$ROOT_DIR/docker-compose/docker-compose-micro-qwen3.yml" "HUGGING_FACE_HUB_TOKEN:-\(.*\)}" "HUGGING_FACE_HUB_TOKEN"

# Extraire les clés API VLLM
extract_value "$ROOT_DIR/docker-compose/docker-compose-micro-qwen3.yml" "VLLM_API_KEY:-\(.*\)}" "VLLM_API_KEY_MICRO"
extract_value "$ROOT_DIR/docker-compose/docker-compose-mini-qwen3.yml" "VLLM_API_KEY:-\(.*\)}" "VLLM_API_KEY_MINI"
extract_value "$ROOT_DIR/docker-compose/docker-compose-medium-qwen3.yml" "VLLM_API_KEY:-\(.*\)}" "VLLM_API_KEY_MEDIUM"
extract_value "$ROOT_DIR/docker-compose/docker-compose-large.yml" "VLLM_API_KEY:-\(.*\)}" "VLLM_API_KEY_LARGE"

# Extraire les ports
extract_value "$ROOT_DIR/docker-compose/docker-compose-micro-qwen3.yml" "VLLM_PORT:-\(.*\)}" "VLLM_PORT_MICRO"
extract_value "$ROOT_DIR/docker-compose/docker-compose-mini-qwen3.yml" "VLLM_PORT:-\(.*\)}" "VLLM_PORT_MINI"
extract_value "$ROOT_DIR/docker-compose/docker-compose-medium-qwen3.yml" "VLLM_PORT:-\(.*\)}" "VLLM_PORT_MEDIUM"
extract_value "$ROOT_DIR/docker-compose/docker-compose-large.yml" "VLLM_PORT:-\(.*\)}" "VLLM_PORT_LARGE"

# Extraire les configurations GPU
extract_value "$ROOT_DIR/docker-compose/docker-compose-micro-qwen3.yml" "CUDA_VISIBLE_DEVICES:-\(.*\)}" "CUDA_VISIBLE_DEVICES_MICRO"
extract_value "$ROOT_DIR/docker-compose/docker-compose-mini-qwen3.yml" "CUDA_VISIBLE_DEVICES:-\(.*\)}" "CUDA_VISIBLE_DEVICES_MINI"
extract_value "$ROOT_DIR/docker-compose/docker-compose-medium-qwen3.yml" "CUDA_VISIBLE_DEVICES:-\(.*\)}" "CUDA_VISIBLE_DEVICES_MEDIUM"
extract_value "$ROOT_DIR/docker-compose/docker-compose-large.yml" "CUDA_VISIBLE_DEVICES:-\(.*\)}" "CUDA_VISIBLE_DEVICES_LARGE"

# Extraire le chemin du cache Hugging Face
HF_CACHE_PATH=$(grep -o "\\\\wsl.localhost\\\\Ubuntu\\\\home\\\\.*\\\\hub" "$ROOT_DIR/docker-compose/docker-compose-micro-qwen3.yml" | head -1)
if [ -n "$HF_CACHE_PATH" ]; then
    if grep -q "^HF_CACHE_PATH=" "$ENV_FILE"; then
        sed -i "s|^HF_CACHE_PATH=.*|HF_CACHE_PATH=$HF_CACHE_PATH|" "$ENV_FILE"
    else
        echo "HF_CACHE_PATH=$HF_CACHE_PATH" >> "$ENV_FILE"
    fi
    echo "Variable HF_CACHE_PATH sauvegardée"
fi

# Extraire les paramètres d'utilisation de la mémoire GPU
extract_value "$ROOT_DIR/docker-compose/docker-compose-micro-qwen3.yml" "GPU_MEMORY_UTILIZATION:-\(.*\)}" "GPU_MEMORY_UTILIZATION_MICRO"
extract_value "$ROOT_DIR/docker-compose/docker-compose-mini-qwen3.yml" "GPU_MEMORY_UTILIZATION:-\(.*\)}" "GPU_MEMORY_UTILIZATION_MINI"
extract_value "$ROOT_DIR/docker-compose/docker-compose-medium-qwen3.yml" "GPU_MEMORY_UTILIZATION:-\(.*\)}" "GPU_MEMORY_UTILIZATION_MEDIUM"
extract_value "$ROOT_DIR/docker-compose/docker-compose-large.yml" "GPU_MEMORY_UTILIZATION:-\(.*\)}" "GPU_MEMORY_UTILIZATION_LARGE"

echo "Sauvegarde terminée"