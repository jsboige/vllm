#!/bin/bash
# migrate-to-qwen3.sh - Script de migration vers les modèles Qwen3
# 
# Ce script:
# - Arrête les services vLLM actuels
# - Construit la nouvelle image Docker patchée
# - Démarre les nouveaux services avec les modèles Qwen3
# - Vérifie que tout fonctionne correctement
# - Permet de revenir à la configuration précédente en cas de problème

# Définition des couleurs pour les messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Chemin du script et du répertoire de configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/update-config.json"
BACKUP_DIR="${SCRIPT_DIR}/backup-$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${SCRIPT_DIR}/migrate-to-qwen3.log"

# Variables globales
DOCKER_COMPOSE_PROJECT=$(jq -r '.settings.docker_compose_project' "$CONFIG_FILE")
HUGGINGFACE_TOKEN=$(jq -r '.settings.huggingface_token' "$CONFIG_FILE")
# Remplacer la variable d'environnement si présente
if [[ "$HUGGINGFACE_TOKEN" == *"\${HUGGING_FACE_HUB_TOKEN"* ]]; then
    # Extraire la valeur par défaut
    DEFAULT_TOKEN=$(echo "$HUGGINGFACE_TOKEN" | sed -n 's/.*:-\(.*\)}.*/\1/p')
    # Utiliser la variable d'environnement ou la valeur par défaut
    HUGGINGFACE_TOKEN=${HUGGING_FACE_HUB_TOKEN:-$DEFAULT_TOKEN}
fi

# Options
FORCE=false
DRY_RUN=false
SKIP_BACKUP=false
ROLLBACK=false

# Fonction pour afficher l'aide
show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -h, --help                Affiche cette aide"
    echo "  -f, --force               Force la migration même si les modèles ne sont pas disponibles"
    echo "  --dry-run                 Simule les actions sans les exécuter"
    echo "  --skip-backup             Ne pas créer de sauvegarde des fichiers de configuration"
    echo "  --rollback                Restaure la configuration précédente"
    echo ""
}

# Fonction de journalisation
log() {
    local level=$1
    local message=$2
    local color=$NC
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    
    case $level in
        "INFO")
            color=$GREEN
            ;;
        "WARNING")
            color=$YELLOW
            ;;
        "ERROR")
            color=$RED
            ;;
        "DEBUG")
            color=$BLUE
            ;;
    esac
    
    # Affichage dans la console
    echo -e "${color}[${timestamp}] [${level}] ${message}${NC}"
    
    # Journalisation dans le fichier de log
    echo "[${timestamp}] [${level}] ${message}" >> "$LOG_FILE"
}

# Fonction pour vérifier les dépendances
check_dependencies() {
    log "INFO" "Vérification des dépendances..."
    
    # Vérifier si jq est installé
    if ! command -v jq &> /dev/null; then
        log "ERROR" "jq n'est pas installé. Veuillez l'installer avec 'apt-get install jq' ou équivalent."
        exit 1
    fi
    
    # Vérifier si curl est installé
    if ! command -v curl &> /dev/null; then
        log "ERROR" "curl n'est pas installé. Veuillez l'installer avec 'apt-get install curl' ou équivalent."
        exit 1
    fi
    
    # Vérifier si docker est installé
    if ! command -v docker &> /dev/null; then
        log "ERROR" "docker n'est pas installé. Veuillez l'installer avant d'utiliser ce script."
        exit 1
    fi
    
    # Vérifier si docker compose est installé
    if ! docker compose version &> /dev/null; then
        log "ERROR" "docker compose n'est pas installé ou n'est pas accessible."
        exit 1
    fi
    
    log "INFO" "Toutes les dépendances sont installées."
}

# Fonction pour créer une sauvegarde des fichiers de configuration
create_backup() {
    if [ "$SKIP_BACKUP" == true ]; then
        log "INFO" "Sauvegarde ignorée selon les options."
        return 0
    fi

    log "INFO" "Création d'une sauvegarde des fichiers de configuration dans $BACKUP_DIR..."
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Création du répertoire de sauvegarde: $BACKUP_DIR"
    else
        mkdir -p "$BACKUP_DIR"
        mkdir -p "$BACKUP_DIR/docker-compose"
        mkdir -p "$BACKUP_DIR/dockerfiles"
        
        # Copier les fichiers de configuration
        cp "$CONFIG_FILE" "$BACKUP_DIR/"
        cp "${SCRIPT_DIR}/docker-compose/docker-compose-"*.yml "$BACKUP_DIR/docker-compose/"
        cp "${SCRIPT_DIR}/dockerfiles/Dockerfile.patched.speculative" "$BACKUP_DIR/dockerfiles/"
        
        log "INFO" "Sauvegarde créée avec succès."
    fi
}

# Fonction pour vérifier la disponibilité des modèles Qwen3
check_models_availability() {
    log "INFO" "Vérification de la disponibilité des modèles Qwen3..."
    
    local models=("Qwen/Qwen3-4B-AWQ" "Qwen/Qwen3-8B-AWQ" "Qwen/Qwen3-30B-A3B")
    local all_available=true
    
    for model in "${models[@]}"; do
        log "INFO" "Vérification du modèle $model..."
        
        if [ "$DRY_RUN" == true ]; then
            log "INFO" "[DRY RUN] Vérification de la disponibilité du modèle $model"
        else
            # Vérifier si le modèle est disponible sur Hugging Face
            local api_url="https://huggingface.co/api/models/${model}"
            local model_info=$(curl -s -H "Authorization: Bearer $HUGGINGFACE_TOKEN" "$api_url")
            
            if [ $? -ne 0 ] || [ -z "$model_info" ] || [[ "$model_info" == *"error"* ]]; then
                log "ERROR" "Le modèle $model n'est pas disponible sur Hugging Face."
                all_available=false
            else
                log "INFO" "Le modèle $model est disponible."
            fi
        fi
    done
    
    if [ "$all_available" == false ] && [ "$FORCE" == false ]; then
        log "ERROR" "Certains modèles Qwen3 ne sont pas disponibles. Utilisez l'option --force pour forcer la migration."
        return 1
    fi
    
    return 0
}

# Fonction pour arrêter les services vLLM actuels
stop_current_services() {
    log "INFO" "Arrêt des services vLLM actuels..."
    
    local compose_files=(
        "docker-compose/docker-compose-micro.yml"
        "docker-compose/docker-compose-mini.yml"
        "docker-compose/docker-compose-medium.yml"
        "docker-compose/docker-compose-large.yml"
    )
    
    local compose_cmd="docker compose -p $DOCKER_COMPOSE_PROJECT"
    
    # Ajouter les fichiers docker-compose
    for file in "${compose_files[@]}"; do
        compose_cmd+=" -f ${SCRIPT_DIR}/${file}"
    done
    
    # Ajouter la commande d'arrêt
    compose_cmd+=" down"
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Exécution de: $compose_cmd"
    else
        # Exécuter la commande
        eval "$compose_cmd"
        if [ $? -ne 0 ]; then
            log "ERROR" "Échec de l'arrêt des services vLLM."
            return 1
        fi
    fi
    
    log "INFO" "Services vLLM arrêtés avec succès."
    return 0
}

# Fonction pour construire la nouvelle image Docker patchée
build_docker_image() {
    log "INFO" "Construction de la nouvelle image Docker patchée..."
    
    local dockerfile_path="${SCRIPT_DIR}/dockerfiles/Dockerfile.patched.speculative"
    local custom_image="vllm-patched:speculative"
    
    if [ ! -f "$dockerfile_path" ]; then
        log "ERROR" "Dockerfile non trouvé: $dockerfile_path"
        return 1
    fi
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Exécution de: docker build -t $custom_image -f $dockerfile_path $SCRIPT_DIR"
    else
        # Construire l'image personnalisée
        docker build -t "$custom_image" -f "$dockerfile_path" "$SCRIPT_DIR"
        if [ $? -ne 0 ]; then
            log "ERROR" "Échec de la construction de l'image Docker patchée."
            return 1
        fi
    fi
    
    log "INFO" "Image Docker patchée construite avec succès."
    return 0
}

# Fonction pour démarrer les nouveaux services avec les modèles Qwen3
start_qwen3_services() {
    log "INFO" "Démarrage des nouveaux services avec les modèles Qwen3..."
    
    local compose_files=(
        "docker-compose/docker-compose-micro-qwen3.yml"
        "docker-compose/docker-compose-mini-qwen3.yml"
        "docker-compose/docker-compose-medium-qwen3.yml"
    )
    
    local compose_cmd="docker compose -p $DOCKER_COMPOSE_PROJECT"
    
    # Ajouter les fichiers docker-compose
    for file in "${compose_files[@]}"; do
        compose_cmd+=" -f ${SCRIPT_DIR}/${file}"
    done
    
    # Ajouter la commande de démarrage
    compose_cmd+=" up -d"
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Exécution de: $compose_cmd"
    else
        # Exécuter la commande
        eval "$compose_cmd"
        if [ $? -ne 0 ]; then
            log "ERROR" "Échec du démarrage des services Qwen3."
            return 1
        fi
    fi
    
    log "INFO" "Services Qwen3 démarrés avec succès."
    return 0
}

# Fonction pour vérifier que les services fonctionnent correctement
check_services() {
    log "INFO" "Vérification du fonctionnement des services Qwen3..."
    
    local services=(
        "vllm-micro-qwen3:5000"
        "vllm-mini-qwen3:5001"
        "vllm-medium-qwen3:5002"
    )
    
    local all_running=true
    
    # Attendre que les services démarrent
    log "INFO" "Attente du démarrage des services (30 secondes)..."
    if [ "$DRY_RUN" == false ]; then
        sleep 30
    fi
    
    for service_port in "${services[@]}"; do
        local service=$(echo "$service_port" | cut -d':' -f1)
        local port=$(echo "$service_port" | cut -d':' -f2)
        
        log "INFO" "Vérification du service $service sur le port $port..."
        
        if [ "$DRY_RUN" == true ]; then
            log "INFO" "[DRY RUN] Vérification du service $service sur le port $port"
        else
            # Vérifier si le service est en cours d'exécution
            local container_id=$(docker ps -q -f "name=${DOCKER_COMPOSE_PROJECT}_${service}")
            if [ -z "$container_id" ]; then
                log "ERROR" "Le service $service n'est pas en cours d'exécution."
                all_running=false
                continue
            fi
            
            # Vérifier si le service répond
            local response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/v1/models)
            if [ "$response" != "200" ]; then
                log "ERROR" "Le service $service ne répond pas correctement (code HTTP: $response)."
                all_running=false
            else
                log "INFO" "Le service $service fonctionne correctement."
            fi
        fi
    done
    
    if [ "$all_running" == false ]; then
        log "ERROR" "Certains services Qwen3 ne fonctionnent pas correctement."
        return 1
    fi
    
    log "INFO" "Tous les services Qwen3 fonctionnent correctement."
    return 0
}

# Fonction pour restaurer la configuration précédente
rollback() {
    log "INFO" "Restauration de la configuration précédente..."
    
    # Arrêter les services Qwen3
    log "INFO" "Arrêt des services Qwen3..."
    local compose_cmd_down="docker compose -p $DOCKER_COMPOSE_PROJECT"
    for file in docker-compose/docker-compose-*-qwen3.yml; do
        compose_cmd_down+=" -f ${SCRIPT_DIR}/${file}"
    done
    compose_cmd_down+=" down"
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Exécution de: $compose_cmd_down"
    else
        eval "$compose_cmd_down"
    fi
    
    # Trouver le dernier répertoire de sauvegarde
    local latest_backup=$(find "$SCRIPT_DIR" -maxdepth 1 -type d -name "backup-*" | sort -r | head -n 1)
    
    if [ -z "$latest_backup" ]; then
        log "ERROR" "Aucune sauvegarde trouvée pour la restauration."
        return 1
    fi
    
    log "INFO" "Restauration à partir de la sauvegarde: $latest_backup"
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Restauration des fichiers de configuration"
    else
        # Restaurer les fichiers de configuration
        cp "$latest_backup/update-config.json" "$SCRIPT_DIR/"
        cp "$latest_backup/docker-compose/"* "$SCRIPT_DIR/docker-compose/"
        cp "$latest_backup/dockerfiles/"* "$SCRIPT_DIR/dockerfiles/"
        
        # Reconstruire l'image Docker
        docker build -t "vllm-patched:speculative" -f "$SCRIPT_DIR/dockerfiles/Dockerfile.patched.speculative" "$SCRIPT_DIR"
        
        # Redémarrer les services originaux
        local compose_cmd_up="docker compose -p $DOCKER_COMPOSE_PROJECT"
        for file in docker-compose/docker-compose-{micro,mini,medium,large}.yml; do
            if [ -f "${SCRIPT_DIR}/${file}" ]; then
                compose_cmd_up+=" -f ${SCRIPT_DIR}/${file}"
            fi
        done
        compose_cmd_up+=" up -d"
        
        eval "$compose_cmd_up"
    fi
    
    log "INFO" "Configuration précédente restaurée avec succès."
    return 0
}

# Fonction pour mettre à jour le fichier update-config.json
update_config() {
    log "INFO" "Mise à jour du fichier update-config.json..."
    
    local config_file="$CONFIG_FILE"
    local temp_config_file="${SCRIPT_DIR}/update-config.tmp.json"
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Mise à jour du fichier update-config.json"
        return 0
    fi
    
    # Ajouter les nouveaux modèles Qwen3
    jq '.models += [
        {
            "name": "Qwen3-4B-AWQ",
            "huggingface_path": "Qwen/Qwen3-4B-AWQ",
            "service": "vllm-micro-qwen3",
            "port": "5000",
            "last_update": "",
            "last_version": "",
            "last_commit": ""
        },
        {
            "name": "Qwen3-8B-AWQ",
            "huggingface_path": "Qwen/Qwen3-8B-AWQ",
            "service": "vllm-mini-qwen3",
            "port": "5001",
            "last_update": "",
            "last_version": "",
            "last_commit": ""
        },
        {
            "name": "Qwen3-30B-A3B",
            "huggingface_path": "Qwen/Qwen3-30B-A3B",
            "service": "vllm-medium-qwen3",
            "port": "5002",
            "last_update": "",
            "last_version": "",
            "last_commit": ""
        }
    ]' "$config_file" > "$temp_config_file"
    
    # Ajouter les nouveaux fichiers docker-compose
    jq '.settings.docker_compose_files += [
        "docker-compose/docker-compose-micro-qwen3.yml",
        "docker-compose/docker-compose-mini-qwen3.yml",
        "docker-compose/docker-compose-medium-qwen3.yml"
    ]' "$temp_config_file" > "${temp_config_file}.2"
    
    # Mettre à jour la version de Docker
    jq '.docker.last_version = ""' "${temp_config_file}.2" > "$config_file"
    
    # Nettoyer les fichiers temporaires
    rm -f "$temp_config_file" "${temp_config_file}.2"
    
    log "INFO" "Fichier update-config.json mis à jour avec succès."
    return 0
}

# Traitement des arguments en ligne de commande
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-backup)
            SKIP_BACKUP=true
            shift
            ;;
        --rollback)
            ROLLBACK=true
            shift
            ;;
        *)
            echo "Option inconnue: $1"
            show_help
            exit 1
            ;;
    esac
done

# Fonction principale
main() {
    log "INFO" "Démarrage du script de migration vers Qwen3..."
    
    # Vérifier les dépendances
    check_dependencies
    
    # Si l'option de restauration est activée
    if [ "$ROLLBACK" == true ]; then
        rollback
        exit $?
    fi
    
    # Créer une sauvegarde des fichiers de configuration
    create_backup
    
    # Vérifier la disponibilité des modèles Qwen3
    if ! check_models_availability; then
        log "ERROR" "Certains modèles Qwen3 ne sont pas disponibles. Migration annulée."
        exit 1
    fi
    
    # Arrêter les services vLLM actuels
    if ! stop_current_services; then
        log "ERROR" "Échec de l'arrêt des services vLLM. Migration annulée."
        exit 1
    fi
    
    # Construire la nouvelle image Docker patchée
    if ! build_docker_image; then
        log "ERROR" "Échec de la construction de l'image Docker. Migration annulée."
        exit 1
    fi
    
    # Mettre à jour le fichier update-config.json
    if ! update_config; then
        log "ERROR" "Échec de la mise à jour du fichier de configuration. Migration annulée."
        exit 1
    fi
    
    # Démarrer les nouveaux services avec les modèles Qwen3
    if ! start_qwen3_services; then
        log "ERROR" "Échec du démarrage des services Qwen3. Migration annulée."
        log "INFO" "Restauration de la configuration précédente..."
        rollback
        exit 1
    fi
    
    # Vérifier que les services fonctionnent correctement
    if ! check_services; then
        log "WARNING" "Certains services Qwen3 ne fonctionnent pas correctement."
        log "INFO" "Voulez-vous restaurer la configuration précédente? (o/n)"
        read -r response
        if [[ "$response" =~ ^[oO]$ ]]; then
            log "INFO" "Restauration de la configuration précédente..."
            rollback
            exit 1
        fi
    fi
    
    log "INFO" "Migration vers Qwen3 terminée avec succès."
    log "INFO" "Pour revenir à la configuration précédente, exécutez: $0 --rollback"
    return 0
}

# Exécuter la fonction principale
main
exit $?