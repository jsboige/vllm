#!/bin/bash
# prepare-update.sh - Script de préparation pour la mise à jour des services vLLM
# 
# Ce script:
# - Vérifie l'état actuel des services vLLM
# - Crée un répertoire de build temporaire pour la nouvelle image Docker
# - Configure un mécanisme pour construire la nouvelle image sans arrêter les services existants

# Définition des couleurs pour les messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Chemin du script et du répertoire de configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="${PARENT_DIR}/update-config.json"
BUILD_DIR="${PARENT_DIR}/docker-compose/build-temp"
LOG_FILE="${PARENT_DIR}/prepare-update.log"

# Variables globales
DOCKER_COMPOSE_PROJECT=""
HUGGINGFACE_TOKEN=""
VERBOSE=false
DRY_RUN=false

# Fonction pour afficher l'aide
show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -h, --help                Affiche cette aide"
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

# Fonction pour charger la configuration
load_config() {
    log "INFO" "Chargement de la configuration depuis $CONFIG_FILE..."
    
    if [ ! -f "$CONFIG_FILE" ]; then
        log "ERROR" "Fichier de configuration non trouvé: $CONFIG_FILE"
        exit 1
    fi
    
    # Charger les paramètres de configuration
    DOCKER_COMPOSE_PROJECT=$(jq -r '.settings.docker_compose_project' "$CONFIG_FILE")
    
    HUGGINGFACE_TOKEN=$(jq -r '.settings.huggingface_token' "$CONFIG_FILE")
    # Remplacer la variable d'environnement si présente
    if [[ "$HUGGINGFACE_TOKEN" == *"\${HUGGING_FACE_HUB_TOKEN"* ]]; then
        # Extraire la valeur par défaut
        DEFAULT_TOKEN=$(echo "$HUGGINGFACE_TOKEN" | sed -n 's/.*:-\(.*\)}.*/\1/p')
        # Utiliser la variable d'environnement ou la valeur par défaut
        HUGGINGFACE_TOKEN=${HUGGING_FACE_HUB_TOKEN:-$DEFAULT_TOKEN}
    fi
    
    log "INFO" "Configuration chargée avec succès."
    if [ "$VERBOSE" == true ]; then
        log "DEBUG" "Paramètres chargés:"
        log "DEBUG" "  - DOCKER_COMPOSE_PROJECT: $DOCKER_COMPOSE_PROJECT"
    fi
}

# Fonction pour vérifier l'état des services vLLM
check_services_status() {
    log "INFO" "Vérification de l'état des services vLLM..."
    
    local services=(
        "vllm-micro:5000"
        "vllm-mini:5001"
        "vllm-medium:5002"
        "vllm-micro-qwen3:5000"
        "vllm-mini-qwen3:5001"
        "vllm-medium-qwen3:5002"
    )
    
    local running_services=()
    local stopped_services=()
    
    for service_port in "${services[@]}"; do
        local service=$(echo "$service_port" | cut -d':' -f1)
        local port=$(echo "$service_port" | cut -d':' -f2)
        
        if [ "$DRY_RUN" == true ]; then
            log "INFO" "[DRY RUN] Vérification du service $service sur le port $port"
            running_services+=("$service")
        else
            # Vérifier si le service est en cours d'exécution
            local container_id=$(docker ps -q -f "name=${DOCKER_COMPOSE_PROJECT}_${service}")
            if [ -z "$container_id" ]; then
                stopped_services+=("$service")
                log "INFO" "Le service $service n'est pas en cours d'exécution."
            else
                running_services+=("$service")
                log "INFO" "Le service $service est en cours d'exécution (container ID: $container_id)."
                
                # Vérifier l'utilisation des ressources
                local cpu_usage=$(docker stats --no-stream --format "{{.CPUPerc}}" "$container_id")
                local mem_usage=$(docker stats --no-stream --format "{{.MemUsage}}" "$container_id")
                log "INFO" "  - Utilisation CPU: $cpu_usage"
                log "INFO" "  - Utilisation mémoire: $mem_usage"
            fi
        fi
    done
    
    log "INFO" "Services en cours d'exécution: ${#running_services[@]}"
    log "INFO" "Services arrêtés: ${#stopped_services[@]}"
    
    # Retourner le nombre de services en cours d'exécution
    echo "${#running_services[@]}"
}

# Fonction pour créer un répertoire de build temporaire
create_build_directory() {
    log "INFO" "Création du répertoire de build temporaire..."
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Création du répertoire: $BUILD_DIR"
    else
        # Supprimer le répertoire s'il existe déjà
        if [ -d "$BUILD_DIR" ]; then
            log "INFO" "Suppression du répertoire de build existant..."
            rm -rf "$BUILD_DIR"
        fi
        
        # Créer le répertoire
        mkdir -p "$BUILD_DIR"
        mkdir -p "$BUILD_DIR/tool_parsers"
        mkdir -p "$BUILD_DIR/reasoning"
        
        # Copier les fichiers nécessaires
        cp "${PARENT_DIR}/docker-compose/build/tool_parsers/qwen3_tool_parser.py" "$BUILD_DIR/tool_parsers/"
        cp "${PARENT_DIR}/docker-compose/build/tool_parsers/__init__.py" "$BUILD_DIR/tool_parsers/"
        
        # Copier le fichier du parser de raisonnement Qwen3 corrigé (PR #17506)
        cp "${SCRIPT_DIR}/../vllm/reasoning/qwen3_reasoning_parser.py" "$BUILD_DIR/reasoning/"
        
        log "INFO" "Répertoire de build créé avec succès: $BUILD_DIR"
    fi
}

# Fonction pour créer un Dockerfile temporaire optimisé
create_optimized_dockerfile() {
    log "INFO" "Création d'un Dockerfile temporaire optimisé..."
    
    local dockerfile_path="${BUILD_DIR}/Dockerfile.qwen3.optimized"
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Création du Dockerfile: $dockerfile_path"
    else
        cat > "$dockerfile_path" << EOF
FROM vllm/vllm-openai:latest

# Optimisation des couches Docker
# Copier tous les fichiers en une seule couche pour réduire la taille de l'image
COPY tool_parsers/qwen3_tool_parser.py /vllm/vllm/entrypoints/openai/tool_parsers/
COPY tool_parsers/__init__.py /vllm/vllm/entrypoints/openai/tool_parsers/
COPY reasoning/qwen3_reasoning_parser.py /vllm/vllm/reasoning/

# Définir le répertoire de travail
WORKDIR /vllm

# Optimisation pour le démarrage rapide
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONOPTIMIZE=1
EOF
        
        log "INFO" "Dockerfile optimisé créé avec succès: $dockerfile_path"
    fi
}

# Fonction pour construire l'image Docker en parallèle
build_docker_image_parallel() {
    log "INFO" "Construction de l'image Docker en parallèle..."
    
    local image_name="vllm-qwen3:latest"
    local dockerfile_path="${BUILD_DIR}/Dockerfile.qwen3.optimized"
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Construction de l'image Docker: $image_name"
    else
        # Construire l'image en arrière-plan
        log "INFO" "Démarrage de la construction de l'image Docker en arrière-plan..."
        docker build -t "$image_name" -f "$dockerfile_path" "$BUILD_DIR" > "${BUILD_DIR}/docker-build.log" 2>&1 &
        local build_pid=$!
        
        log "INFO" "Construction de l'image Docker en cours (PID: $build_pid)..."
        log "INFO" "Vous pouvez suivre la progression avec: tail -f ${BUILD_DIR}/docker-build.log"
        
        # Attendre que la construction soit terminée
        wait $build_pid
        local build_status=$?
        
        if [ $build_status -eq 0 ]; then
            log "INFO" "Image Docker construite avec succès: $image_name"
        else
            log "ERROR" "Échec de la construction de l'image Docker. Consultez le journal pour plus de détails: ${BUILD_DIR}/docker-build.log"
            exit 1
        fi
    fi
}

# Fonction pour créer un script de mise à jour rapide
create_quick_update_script() {
    log "INFO" "Création d'un script de mise à jour rapide..."
    
    local script_path="${PARENT_DIR}/quick-update-qwen3.sh"
    
    if [ "$DRY_RUN" == true ]; then
        log "INFO" "[DRY RUN] Création du script: $script_path"
    else
        cat > "$script_path" << 'EOF'
#!/bin/bash
# quick-update-qwen3.sh - Script de mise à jour rapide des services vLLM Qwen3
# 
# Ce script:
# - Arrête les services vLLM Qwen3 existants
# - Démarre les services avec la nouvelle image Docker
# - Vérifie que tout fonctionne correctement

# Définition des couleurs pour les messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Chemin du script et du répertoire de configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/update-config.json"
LOG_FILE="${SCRIPT_DIR}/quick-update-qwen3.log"

# Variables globales
DOCKER_COMPOSE_PROJECT=$(jq -r '.settings.docker_compose_project' "$CONFIG_FILE")
START_TIME=$(date +%s)

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

# Fonction pour arrêter les services vLLM Qwen3
stop_qwen3_services() {
    log "INFO" "Arrêt des services vLLM Qwen3..."
    
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
    
    # Ajouter la commande d'arrêt
    compose_cmd+=" down"
    
    # Exécuter la commande
    eval "$compose_cmd"
    if [ $? -ne 0 ]; then
        log "ERROR" "Échec de l'arrêt des services vLLM Qwen3."
        return 1
    fi
    
    log "INFO" "Services vLLM Qwen3 arrêtés avec succès."
    return 0
}

# Fonction pour démarrer les services vLLM Qwen3
start_qwen3_services() {
    log "INFO" "Démarrage des services vLLM Qwen3..."
    
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
    
    # Exécuter la commande
    eval "$compose_cmd"
    if [ $? -ne 0 ]; then
        log "ERROR" "Échec du démarrage des services vLLM Qwen3."
        return 1
    fi
    
    log "INFO" "Services vLLM Qwen3 démarrés avec succès."
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
    local max_retries=10
    local retry_interval=5
    
    for service_port in "${services[@]}"; do
        local service=$(echo "$service_port" | cut -d':' -f1)
        local port=$(echo "$service_port" | cut -d':' -f2)
        
        log "INFO" "Vérification du service $service sur le port $port..."
        
        local retries=0
        local service_running=false
        
        while [ $retries -lt $max_retries ] && [ "$service_running" == false ]; do
            # Vérifier si le service est en cours d'exécution
            local container_id=$(docker ps -q -f "name=${DOCKER_COMPOSE_PROJECT}_${service}")
            if [ -z "$container_id" ]; then
                log "WARNING" "Le service $service n'est pas en cours d'exécution. Tentative $((retries+1))/$max_retries..."
                retries=$((retries+1))
                sleep $retry_interval
                continue
            fi
            
            # Vérifier si le service répond
            local response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/v1/models)
            if [ "$response" != "200" ]; then
                log "WARNING" "Le service $service ne répond pas correctement (code HTTP: $response). Tentative $((retries+1))/$max_retries..."
                retries=$((retries+1))
                sleep $retry_interval
            else
                log "INFO" "Le service $service fonctionne correctement."
                service_running=true
            fi
        done
        
        if [ "$service_running" == false ]; then
            log "ERROR" "Le service $service ne fonctionne pas correctement après $max_retries tentatives."
            all_running=false
        fi
    done
    
    if [ "$all_running" == false ]; then
        log "ERROR" "Certains services Qwen3 ne fonctionnent pas correctement."
        return 1
    fi
    
    log "INFO" "Tous les services Qwen3 fonctionnent correctement."
    return 0
}

# Fonction principale
main() {
    log "INFO" "Démarrage de la mise à jour rapide des services vLLM Qwen3..."
    
    # Arrêter les services vLLM Qwen3
    if ! stop_qwen3_services; then
        log "ERROR" "Échec de l'arrêt des services vLLM Qwen3. Mise à jour annulée."
        exit 1
    fi
    
    # Démarrer les services vLLM Qwen3
    if ! start_qwen3_services; then
        log "ERROR" "Échec du démarrage des services vLLM Qwen3. Mise à jour annulée."
        exit 1
    fi
    
    # Vérifier que les services fonctionnent correctement
    if ! check_services; then
        log "ERROR" "Certains services vLLM Qwen3 ne fonctionnent pas correctement."
        exit 1
    fi
    
    # Calculer le temps d'indisponibilité
    local end_time=$(date +%s)
    local downtime=$((end_time - START_TIME))
    local minutes=$((downtime / 60))
    local seconds=$((downtime % 60))
    
    log "INFO" "Mise à jour rapide des services vLLM Qwen3 terminée avec succès."
    log "INFO" "Temps d'indisponibilité total: ${minutes}m ${seconds}s"
    return 0
}

# Exécuter la fonction principale
main
exit $?
EOF
        
        # Rendre le script exécutable
        chmod +x "$script_path"
        
        log "INFO" "Script de mise à jour rapide créé avec succès: $script_path"
    fi
}

# Fonction principale
main() {
    log "INFO" "Démarrage du script de préparation pour la mise à jour des services vLLM..."
    
    # Vérifier les dépendances
    check_dependencies
    
    # Charger la configuration
    load_config
    
    # Vérifier l'état des services vLLM
    local running_services=$(check_services_status)
    log "INFO" "Nombre de services en cours d'exécution: $running_services"
    
    # Créer un répertoire de build temporaire
    create_build_directory
    
    # Créer un Dockerfile temporaire optimisé
    create_optimized_dockerfile
    
    # Construire l'image Docker en parallèle
    build_docker_image_parallel
    
    # Créer un script de mise à jour rapide
    create_quick_update_script
    
    log "INFO" "Préparation pour la mise à jour des services vLLM terminée avec succès."
    log "INFO" "Pour effectuer la mise à jour rapide, exécutez: ${PARENT_DIR}/quick-update-qwen3.sh"
    return 0
}

# Traitement des arguments en ligne de commande
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
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