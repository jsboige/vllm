#!/bin/bash
# update-vllm.sh - Script de mise à jour automatisée pour vLLM et ses modèles
# 
# Ce script:
# - Met à jour l'image Docker vLLM officielle
# - Reconstruit l'image personnalisée avec le patch pour le décodage spéculatif
# - Vérifie les nouvelles versions des modèles Qwen sur Hugging Face
# - Propose à l'utilisateur de mettre à jour les modèles si de nouvelles versions sont disponibles
# - Redémarre les services Docker après les mises à jour

# Définition des couleurs pour les messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Chemin du script et du répertoire de configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/update-config.json"
TEMP_CONFIG_FILE="${SCRIPT_DIR}/update-config.tmp.json"
LOG_FILE=""

# Variables globales
AUTO_UPDATE_DOCKER=false
AUTO_UPDATE_MODELS=false
HUGGINGFACE_TOKEN=""
DOCKER_COMPOSE_FILES=()
DOCKER_COMPOSE_PROJECT=""
FORCE_UPDATE=false
VERBOSE=false
DRY_RUN=false

# Fonction pour afficher l'aide
show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -h, --help                Affiche cette aide"
    echo "  -f, --force               Force la mise à jour même si aucune nouvelle version n'est détectée"
    echo "  -d, --docker-only         Met à jour uniquement les images Docker"
    echo "  -m, --models-only         Met à jour uniquement les modèles"
    echo "  -a, --auto                Effectue les mises à jour automatiquement sans demander de confirmation"
    echo "  -v, --verbose             Mode verbeux (affiche plus de détails)"
    echo "  --dry-run                 Simule les actions sans les exécuter"
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
    if [ -n "$LOG_FILE" ]; then
        echo "[${timestamp}] [${level}] ${message}" >> "$LOG_FILE"
    fi
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
    }
    
    log "INFO" "Toutes les dépendances sont installées."
}

# Fonction pour charger la configuration
load_config() {
    log "INFO" "Chargement de la configuration depuis $CONFIG_FILE..."
    
    if [ ! -f "$CONFIG_FILE" ]; then
        log "ERROR" "Fichier de configuration non trouvé: $CONFIG_FILE"
        exit 1
    fi
    
    # Charger les paramètres de configuration
    LOG_FILE=$(jq -r '.settings.log_file' "$CONFIG_FILE")
    if [[ "$LOG_FILE" != "null" && "$LOG_FILE" != "" ]]; then
        LOG_FILE="${SCRIPT_DIR}/${LOG_FILE}"
        # Créer le fichier de log s'il n'existe pas
        touch "$LOG_FILE" 2>/dev/null || {
            log "WARNING" "Impossible de créer le fichier de log: $LOG_FILE. Les logs seront uniquement affichés dans la console."
            LOG_FILE=""
        }
    fi
    
    # Charger les autres paramètres
    if [ "$AUTO_UPDATE_DOCKER" == false ]; then
        AUTO_UPDATE_DOCKER=$(jq -r '.settings.auto_update_docker' "$CONFIG_FILE")
    fi
    
    if [ "$AUTO_UPDATE_MODELS" == false ]; then
        AUTO_UPDATE_MODELS=$(jq -r '.settings.auto_update_models' "$CONFIG_FILE")
    fi
    
    HUGGINGFACE_TOKEN=$(jq -r '.settings.huggingface_token' "$CONFIG_FILE")
    # Remplacer la variable d'environnement si présente
    if [[ "$HUGGINGFACE_TOKEN" == *"\${HUGGING_FACE_HUB_TOKEN"* ]]; then
        # Extraire la valeur par défaut
        DEFAULT_TOKEN=$(echo "$HUGGINGFACE_TOKEN" | sed -n 's/.*:-\(.*\)}.*/\1/p')
        # Utiliser la variable d'environnement ou la valeur par défaut
        HUGGINGFACE_TOKEN=${HUGGING_FACE_HUB_TOKEN:-$DEFAULT_TOKEN}
    fi
    
    # Charger les fichiers docker-compose
    DOCKER_COMPOSE_FILES=()
    while IFS= read -r file; do
        DOCKER_COMPOSE_FILES+=("$file")
    done < <(jq -r '.settings.docker_compose_files[]' "$CONFIG_FILE")
    
    DOCKER_COMPOSE_PROJECT=$(jq -r '.settings.docker_compose_project' "$CONFIG_FILE")
    
    log "INFO" "Configuration chargée avec succès."
    if [ "$VERBOSE" == true ]; then
        log "DEBUG" "Paramètres chargés:"
        log "DEBUG" "  - LOG_FILE: $LOG_FILE"
        log "DEBUG" "  - AUTO_UPDATE_DOCKER: $AUTO_UPDATE_DOCKER"
        log "DEBUG" "  - AUTO_UPDATE_MODELS: $AUTO_UPDATE_MODELS"
        log "DEBUG" "  - DOCKER_COMPOSE_PROJECT: $DOCKER_COMPOSE_PROJECT"
        log "DEBUG" "  - Nombre de fichiers docker-compose: ${#DOCKER_COMPOSE_FILES[@]}"
    fi
}

# Fonction pour mettre à jour la configuration
update_config() {
    local key=$1
    local value=$2
    local model_name=$3
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Mise à jour de la configuration: $key = $value pour $model_name"
        return 0
    fi
    
    # Créer une copie temporaire du fichier de configuration
    cp "$CONFIG_FILE" "$TEMP_CONFIG_FILE"
    
    if [ -n "$model_name" ]; then
        # Mise à jour pour un modèle spécifique
        jq --arg name "$model_name" --arg key "$key" --arg value "$value" '
            .models |= map(
                if .name == $name then
                    . + {($key): $value}
                else
                    .
                end
            )
        ' "$CONFIG_FILE" > "$TEMP_CONFIG_FILE"
    else
        # Mise à jour pour Docker
        jq --arg key "$key" --arg value "$value" '.docker[$key] = $value' "$CONFIG_FILE" > "$TEMP_CONFIG_FILE"
    fi
    
    # Vérifier que le fichier temporaire a été créé correctement
    if [ ! -s "$TEMP_CONFIG_FILE" ]; then
        log "ERROR" "Erreur lors de la mise à jour de la configuration."
        return 1
    fi
    
    # Remplacer le fichier original par le fichier temporaire
    mv "$TEMP_CONFIG_FILE" "$CONFIG_FILE"
    log "INFO" "Configuration mise à jour: $key = $value pour ${model_name:-docker}"
    return 0
}

# Fonction pour vérifier les mises à jour de l'image Docker officielle
check_docker_updates() {
    log "INFO" "Vérification des mises à jour pour l'image Docker officielle..."
    
    local official_image=$(jq -r '.docker.official_image' "$CONFIG_FILE")
    local last_update=$(jq -r '.docker.last_update' "$CONFIG_FILE")
    local last_version=$(jq -r '.docker.last_version' "$CONFIG_FILE")
    
    # Extraire le nom et le tag de l'image
    local image_name=$(echo "$official_image" | cut -d':' -f1)
    local image_tag=$(echo "$official_image" | cut -d':' -f2)
    if [ "$image_tag" == "$official_image" ]; then
        image_tag="latest"
    fi
    
    log "INFO" "Vérification de l'image $image_name:$image_tag..."
    
    # Récupérer les informations sur l'image depuis Docker Hub
    local image_info
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Récupération des informations sur l'image depuis Docker Hub"
        image_info='{"results":[{"last_updated":"2025-01-01T00:00:00.000000Z","digest":"sha256:1234567890abcdef"}]}'
    else
        image_info=$(curl -s "https://hub.docker.com/v2/repositories/${image_name}/tags/${image_tag}/")
        if [ $? -ne 0 ]; then
            log "ERROR" "Impossible de récupérer les informations sur l'image depuis Docker Hub."
            return 1
        fi
    fi
    
    # Extraire la date de dernière mise à jour et le digest
    local current_update=$(echo "$image_info" | jq -r '.last_updated')
    local current_digest=$(echo "$image_info" | jq -r '.digest')
    
    if [ "$current_update" == "null" ] || [ "$current_digest" == "null" ]; then
        log "ERROR" "Impossible de récupérer les informations sur l'image depuis Docker Hub."
        return 1
    fi
    
    log "INFO" "Image actuelle: dernière mise à jour le $current_update, digest: $current_digest"
    
    # Comparer avec la dernière version connue
    if [ "$last_version" != "$current_digest" ] || [ "$FORCE_UPDATE" == true ]; then
        log "INFO" "Une nouvelle version de l'image Docker officielle est disponible."
        return 0  # Mise à jour disponible
    else
        log "INFO" "L'image Docker officielle est à jour."
        return 1  # Pas de mise à jour disponible
    fi
}

# Fonction pour mettre à jour l'image Docker officielle
update_docker_image() {
    log "INFO" "Mise à jour de l'image Docker officielle..."
    
    local official_image=$(jq -r '.docker.official_image' "$CONFIG_FILE")
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Exécution de: docker pull $official_image"
    else
        # Tirer la dernière version de l'image
        docker pull "$official_image"
        if [ $? -ne 0 ]; then
            log "ERROR" "Échec de la mise à jour de l'image Docker officielle."
            return 1
        fi
    fi
    
    log "INFO" "Image Docker officielle mise à jour avec succès."
    
    # Récupérer les informations sur l'image
    local image_name=$(echo "$official_image" | cut -d':' -f1)
    local image_tag=$(echo "$official_image" | cut -d':' -f2)
    if [ "$image_tag" == "$official_image" ]; then
        image_tag="latest"
    fi
    
    local image_info
    if [ "$DRY_RUN" == true ]; then
        image_info='{"results":[{"last_updated":"2025-01-01T00:00:00.000000Z","digest":"sha256:1234567890abcdef"}]}'
    else
        image_info=$(curl -s "https://hub.docker.com/v2/repositories/${image_name}/tags/${image_tag}/")
    fi
    
    local current_update=$(echo "$image_info" | jq -r '.last_updated')
    local current_digest=$(echo "$image_info" | jq -r '.digest')
    
    # Mettre à jour la configuration
    update_config "last_update" "$current_update"
    update_config "last_version" "$current_digest"
    
    return 0
}

# Fonction pour reconstruire l'image personnalisée
rebuild_custom_image() {
    log "INFO" "Reconstruction de l'image Docker personnalisée..."
    
    local custom_image=$(jq -r '.docker.custom_image' "$CONFIG_FILE")
    local dockerfile_path=$(jq -r '.docker.dockerfile_path' "$CONFIG_FILE")
    local full_dockerfile_path="${SCRIPT_DIR}/${dockerfile_path}"
    
    if [ ! -f "$full_dockerfile_path" ]; then
        log "ERROR" "Dockerfile non trouvé: $full_dockerfile_path"
        return 1
    fi
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Exécution de: docker build -t $custom_image -f $full_dockerfile_path $SCRIPT_DIR"
    else
        # Construire l'image personnalisée
        docker build -t "$custom_image" -f "$full_dockerfile_path" "$SCRIPT_DIR"
        if [ $? -ne 0 ]; then
            log "ERROR" "Échec de la reconstruction de l'image Docker personnalisée."
            return 1
        fi
    fi
    
    log "INFO" "Image Docker personnalisée reconstruite avec succès."
    return 0
}

# Fonction pour vérifier les mises à jour des modèles sur Hugging Face
check_model_updates() {
    local model_name=$1
    local huggingface_path=$2
    local last_commit=$3
    
    log "INFO" "Vérification des mises à jour pour le modèle $model_name ($huggingface_path)..."
    
    # Construire l'URL de l'API Hugging Face
    local api_url="https://huggingface.co/api/models/${huggingface_path}"
    
    # Récupérer les informations sur le modèle
    local model_info
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Récupération des informations sur le modèle depuis Hugging Face"
        model_info='{"sha":"1234567890abcdef","lastModified":"2025-01-01T00:00:00.000Z"}'
    else
        model_info=$(curl -s -H "Authorization: Bearer $HUGGINGFACE_TOKEN" "$api_url")
        if [ $? -ne 0 ] || [ -z "$model_info" ]; then
            log "ERROR" "Impossible de récupérer les informations sur le modèle depuis Hugging Face."
            return 1
        fi
    fi
    
    # Extraire le dernier commit et la date de dernière modification
    local current_commit=$(echo "$model_info" | jq -r '.sha')
    local last_modified=$(echo "$model_info" | jq -r '.lastModified')
    
    if [ "$current_commit" == "null" ] || [ "$last_modified" == "null" ]; then
        log "ERROR" "Impossible de récupérer les informations sur le modèle depuis Hugging Face."
        return 1
    fi
    
    log "INFO" "Modèle actuel: dernière modification le $last_modified, commit: $current_commit"
    
    # Comparer avec le dernier commit connu
    if [ "$last_commit" != "$current_commit" ] || [ "$FORCE_UPDATE" == true ]; then
        log "INFO" "Une nouvelle version du modèle $model_name est disponible."
        echo "$current_commit"  # Retourner le nouveau commit
        return 0  # Mise à jour disponible
    else
        log "INFO" "Le modèle $model_name est à jour."
        return 1  # Pas de mise à jour disponible
    fi
}

# Fonction pour redémarrer un service Docker
restart_service() {
    local service=$1
    
    log "INFO" "Redémarrage du service $service..."
    
    # Construire la commande docker-compose
    local compose_cmd="docker compose -p $DOCKER_COMPOSE_PROJECT"
    
    # Ajouter les fichiers docker-compose
    for file in "${DOCKER_COMPOSE_FILES[@]}"; do
        compose_cmd+=" -f ${SCRIPT_DIR}/${file}"
    done
    
    # Ajouter la commande de redémarrage
    compose_cmd+=" restart $service"
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Exécution de: $compose_cmd"
    else
        # Exécuter la commande
        eval "$compose_cmd"
        if [ $? -ne 0 ]; then
            log "ERROR" "Échec du redémarrage du service $service."
            return 1
        fi
    fi
    
    log "INFO" "Service $service redémarré avec succès."
    return 0
}

# Fonction pour redémarrer tous les services Docker
restart_all_services() {
    log "INFO" "Redémarrage de tous les services Docker..."
    
    # Construire la commande docker-compose
    local compose_cmd="docker compose -p $DOCKER_COMPOSE_PROJECT"
    
    # Ajouter les fichiers docker-compose
    for file in "${DOCKER_COMPOSE_FILES[@]}"; do
        compose_cmd+=" -f ${SCRIPT_DIR}/${file}"
    done
    
    # Ajouter la commande de redémarrage
    compose_cmd+=" restart"
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Exécution de: $compose_cmd"
    else
        # Exécuter la commande
        eval "$compose_cmd"
        if [ $? -ne 0 ]; then
            log "ERROR" "Échec du redémarrage des services."
            return 1
        fi
    fi
    
    log "INFO" "Tous les services redémarrés avec succès."
    return 0
}

# Fonction pour mettre à jour les images Docker
update_docker_images() {
    log "INFO" "Mise à jour des images Docker..."
    
    # Vérifier les mises à jour de l'image Docker officielle
    if check_docker_updates; then
        if [ "$AUTO_UPDATE_DOCKER" == true ] || [ "$FORCE_UPDATE" == true ]; then
            log "INFO" "Mise à jour automatique de l'image Docker officielle..."
            if ! update_docker_image; then
                log "ERROR" "Échec de la mise à jour de l'image Docker officielle."
                return 1
            fi
        else
            # Demander confirmation à l'utilisateur
            read -p "Voulez-vous mettre à jour l'image Docker officielle? (o/n): " confirm
            if [[ "$confirm" =~ ^[oO]$ ]]; then
                if ! update_docker_image; then
                    log "ERROR" "Échec de la mise à jour de l'image Docker officielle."
                    return 1
                fi
            else
                log "INFO" "Mise à jour de l'image Docker officielle annulée par l'utilisateur."
            fi
        fi
        
        # Reconstruire l'image personnalisée
        log "INFO" "L'image officielle a été mise à jour, reconstruction de l'image personnalisée..."
        if ! rebuild_custom_image; then
            log "ERROR" "Échec de la reconstruction de l'image Docker personnalisée."
            return 1
        fi
        
        # Demander si l'utilisateur souhaite redémarrer les services
        if [ "$AUTO_UPDATE_DOCKER" == true ] || [ "$FORCE_UPDATE" == true ]; then
            log "INFO" "Redémarrage automatique des services Docker..."
            if ! restart_all_services; then
                log "ERROR" "Échec du redémarrage des services Docker."
                return 1
            fi
        else
            read -p "Voulez-vous redémarrer les services Docker maintenant? (o/n): " confirm
            if [[ "$confirm" =~ ^[oO]$ ]]; then
                if ! restart_all_services; then
                    log "ERROR" "Échec du redémarrage des services Docker."
                    return 1
                fi
            else
                log "INFO" "Redémarrage des services Docker annulé par l'utilisateur."
            fi
        fi
    else
        log "INFO" "Aucune mise à jour disponible pour les images Docker."
    fi
    
    return 0
}

# Fonction pour mettre à jour les modèles
update_models() {
    log "INFO" "Vérification des mises à jour pour les modèles..."
    
    local models_updated=false
    
    # Parcourir tous les modèles
    while IFS= read -r model_json; do
        local model_name=$(echo "$model_json" | jq -r '.name')
        local huggingface_path=$(echo "$model_json" | jq -r '.huggingface_path')
        local service=$(echo "$model_json" | jq -r '.service')
        local last_commit=$(echo "$model_json" | jq -r '.last_commit')
        
        # Vérifier les mises à jour pour ce modèle
        local new_commit
        new_commit=$(check_model_updates "$model_name" "$huggingface_path" "$last_commit")
        local update_available=$?
        
        if [ $update_available -eq 0 ]; then
            if [ "$AUTO_UPDATE_MODELS" == true ] || [ "$FORCE_UPDATE" == true ]; then
                log "INFO" "Mise à jour automatique du modèle $model_name..."
                
                # Mettre à jour la configuration
                local current_date=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")
                update_config "last_update" "$current_date" "$model_name"
                update_config "last_commit" "$new_commit" "$model_name"
                
                # Redémarrer le service
                if ! restart_service "$service"; then
                    log "ERROR" "Échec du redémarrage du service $service."
                    continue
                fi
                
                models_updated=true
            else
                # Demander confirmation à l'utilisateur
                read -p "Voulez-vous mettre à jour le modèle $model_name? (o/n): " confirm
                if [[ "$confirm" =~ ^[oO]$ ]]; then
                    # Mettre à jour la configuration
                    local current_date=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")
                    update_config "last_update" "$current_date" "$model_name"
                    update_config "last_commit" "$new_commit" "$model_name"
                    
                    # Redémarrer le service
                    if ! restart_service "$service"; then
                        log "ERROR" "Échec du redémarrage du service $service."
                        continue
                    fi
                    
                    models_updated=true
                else
                    log "INFO" "Mise à jour du modèle $model_name annulée par l'utilisateur."
                fi
            fi
        fi
    done < <(jq -c '.models[]' "$CONFIG_FILE")
    
    if [ "$models_updated" == false ]; then
        log "INFO" "Aucune mise à jour disponible pour les modèles."
    fi
    
    return 0
}

# Fonction principale
main() {
    log "INFO" "Démarrage du script de mise à jour vLLM..."
    
    # Vérifier les dépendances
    check_dependencies
    
    # Charger la configuration
    load_config
    
    # Mettre à jour les images Docker si demandé
    if [ "$MODELS_ONLY" != true ]; then
        update_docker_images
    fi
    
    # Mettre à jour les modèles si demandé
    if [ "$DOCKER_ONLY" != true ]; then
        update_models
    fi
    
    log "INFO" "Script de mise à jour vLLM terminé avec succès."
    return 0
}

# Traitement des arguments en ligne de commande
DOCKER_ONLY=false
MODELS_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -f|--force)
            FORCE_UPDATE=true
            shift
            ;;
        -d|--docker-only)
            DOCKER_ONLY=true
            shift
            ;;
        -m|--models-only)
            MODELS_ONLY=true
            shift
            ;;
        -a|--auto)
            AUTO_UPDATE_DOCKER=true
            AUTO_UPDATE_MODELS=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            echo "Option inconnue: $1"
            show_help
            exit 1
            ;;
    esac
done

# Exécuter la fonction principale
main
exit $?