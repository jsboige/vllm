#!/bin/bash

# Script pour sécuriser les fichiers docker-compose
# Ce script remplace les valeurs sensibles par des variables d'environnement

# Vérifier si le dossier scripts existe
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_COMPOSE_DIR="$ROOT_DIR/docker-compose"
ENV_FILE="$ROOT_DIR/.env"

echo "Sécurisation des fichiers docker-compose..."

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
    
    # Remplacer la valeur dans le fichier docker-compose
    sed -i "s/$pattern/$var_name$suffix/g" "$file"
    echo "Variable $var_name remplacée dans $file"
}

# Sécuriser le token Hugging Face
for file in "$DOCKER_COMPOSE_DIR"/docker-compose-*.yml; do
    # Remplacer le token Hugging Face par une variable d'environnement
    sed -i "s/HUGGING_FACE_HUB_TOKEN:-[^}]*/HUGGING_FACE_HUB_TOKEN:-\${HUGGING_FACE_HUB_TOKEN}/g" "$file"
    echo "Token Hugging Face sécurisé dans $file"
done

# Sécuriser les clés API VLLM
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-micro-qwen3.yml" "VLLM_API_KEY:-[^}]*" "VLLM_API_KEY" ":-\${VLLM_API_KEY_MICRO}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-micro.yml" "VLLM_API_KEY:-[^}]*" "VLLM_API_KEY" ":-\${VLLM_API_KEY_MICRO}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-mini-qwen3.yml" "VLLM_API_KEY:-[^}]*" "VLLM_API_KEY" ":-\${VLLM_API_KEY_MINI}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-mini.yml" "VLLM_API_KEY:-[^}]*" "VLLM_API_KEY" ":-\${VLLM_API_KEY_MINI}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-medium-qwen3.yml" "VLLM_API_KEY:-[^}]*" "VLLM_API_KEY" ":-\${VLLM_API_KEY_MEDIUM}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-medium.yml" "VLLM_API_KEY:-[^}]*" "VLLM_API_KEY" ":-\${VLLM_API_KEY_MEDIUM}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-large.yml" "VLLM_API_KEY:-[^}]*" "VLLM_API_KEY" ":-\${VLLM_API_KEY_LARGE}"

# Sécuriser les ports
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-micro-qwen3.yml" "VLLM_PORT:-[^}]*" "VLLM_PORT" ":-\${VLLM_PORT_MICRO}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-micro.yml" "VLLM_PORT:-[^}]*" "VLLM_PORT" ":-\${VLLM_PORT_MICRO}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-mini-qwen3.yml" "VLLM_PORT:-[^}]*" "VLLM_PORT" ":-\${VLLM_PORT_MINI}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-mini.yml" "VLLM_PORT:-[^}]*" "VLLM_PORT" ":-\${VLLM_PORT_MINI}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-medium-qwen3.yml" "VLLM_PORT:-[^}]*" "VLLM_PORT" ":-\${VLLM_PORT_MEDIUM}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-medium.yml" "VLLM_PORT:-[^}]*" "VLLM_PORT" ":-\${VLLM_PORT_MEDIUM}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-large.yml" "VLLM_PORT:-[^}]*" "VLLM_PORT" ":-\${VLLM_PORT_LARGE}"

# Sécuriser les configurations GPU
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-micro-qwen3.yml" "CUDA_VISIBLE_DEVICES:-[^}]*" "CUDA_VISIBLE_DEVICES" ":-\${CUDA_VISIBLE_DEVICES_MICRO}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-micro.yml" "CUDA_VISIBLE_DEVICES:-[^}]*" "CUDA_VISIBLE_DEVICES" ":-\${CUDA_VISIBLE_DEVICES_MICRO}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-mini-qwen3.yml" "CUDA_VISIBLE_DEVICES:-[^}]*" "CUDA_VISIBLE_DEVICES" ":-\${CUDA_VISIBLE_DEVICES_MINI}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-mini.yml" "CUDA_VISIBLE_DEVICES:-[^}]*" "CUDA_VISIBLE_DEVICES" ":-\${CUDA_VISIBLE_DEVICES_MINI}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-medium-qwen3.yml" "CUDA_VISIBLE_DEVICES:-[^}]*" "CUDA_VISIBLE_DEVICES" ":-\${CUDA_VISIBLE_DEVICES_MEDIUM}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-medium.yml" "CUDA_VISIBLE_DEVICES:-[^}]*" "CUDA_VISIBLE_DEVICES" ":-\${CUDA_VISIBLE_DEVICES_MEDIUM}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-large.yml" "CUDA_VISIBLE_DEVICES:-[^}]*" "CUDA_VISIBLE_DEVICES" ":-\${CUDA_VISIBLE_DEVICES_LARGE}"

# Sécuriser les paramètres d'utilisation de la mémoire GPU
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-micro-qwen3.yml" "GPU_MEMORY_UTILIZATION:-[^}]*" "GPU_MEMORY_UTILIZATION" ":-\${GPU_MEMORY_UTILIZATION_MICRO}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-micro.yml" "GPU_MEMORY_UTILIZATION:-[^}]*" "GPU_MEMORY_UTILIZATION" ":-\${GPU_MEMORY_UTILIZATION_MICRO}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-mini-qwen3.yml" "GPU_MEMORY_UTILIZATION:-[^}]*" "GPU_MEMORY_UTILIZATION" ":-\${GPU_MEMORY_UTILIZATION_MINI}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-mini.yml" "GPU_MEMORY_UTILIZATION:-[^}]*" "GPU_MEMORY_UTILIZATION" ":-\${GPU_MEMORY_UTILIZATION_MINI}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-medium-qwen3.yml" "GPU_MEMORY_UTILIZATION:-[^}]*" "GPU_MEMORY_UTILIZATION" ":-\${GPU_MEMORY_UTILIZATION_MEDIUM}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-medium.yml" "GPU_MEMORY_UTILIZATION:-[^}]*" "GPU_MEMORY_UTILIZATION" ":-\${GPU_MEMORY_UTILIZATION_MEDIUM}"
replace_value "$DOCKER_COMPOSE_DIR/docker-compose-large.yml" "GPU_MEMORY_UTILIZATION:-[^}]*" "GPU_MEMORY_UTILIZATION" ":-\${GPU_MEMORY_UTILIZATION_LARGE}"

# Sécuriser le chemin du cache Hugging Face
HF_CACHE_PATH=$(grep "^HF_CACHE_PATH=" "$ENV_FILE" | cut -d'=' -f2)
if [ -n "$HF_CACHE_PATH" ]; then
    for file in "$DOCKER_COMPOSE_DIR"/docker-compose-*.yml; do
        sed -i "s|\\\\\\\\wsl.localhost\\\\\\\\Ubuntu\\\\\\\\home\\\\\\\\.*\\\\\\\\hub|$HF_CACHE_PATH|g" "$file"
        # Ajouter une variable d'environnement pour le chemin du cache
        sed -i "s|$HF_CACHE_PATH|\\${HF_CACHE_PATH}|g" "$file"
    done
    echo "Chemin du cache Hugging Face sécurisé dans tous les fichiers docker-compose"
fi

echo "Sécurisation terminée"