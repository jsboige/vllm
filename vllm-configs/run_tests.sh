#!/bin/bash
# Script pour exécuter les tests des services vLLM

# Définition des couleurs pour les messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Fonction pour afficher l'aide
show_help() {
    echo -e "${BLUE}Usage: $0 [options]${NC}"
    echo ""
    echo "Options:"
    echo "  -h, --help                Affiche cette aide"
    echo "  -a, --all                 Exécute tous les tests"
    echo "  -c, --connection          Teste la connexion aux services"
    echo "  -g, --generation          Teste la génération de texte"
    echo "  -t, --tools               Teste l'utilisation d'outils"
    echo "  -r, --reasoning           Teste le raisonnement"
    echo "  -b, --benchmark           Effectue un benchmark de performance"
    echo "  -p, --parallel            Teste le traitement parallèle"
    echo "  --repeats N               Nombre de répétitions pour le benchmark (défaut: 3)"
    echo "  --parallel-requests N     Nombre de requêtes parallèles (défaut: 5)"
    echo ""
    echo "Exemples:"
    echo "  $0 --all                  Exécute tous les tests"
    echo "  $0 -c -g                  Teste la connexion et la génération de texte"
    echo "  $0 -b --repeats 5         Effectue un benchmark avec 5 répétitions"
    echo ""
}

# Vérifier si Python est installé
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 n'est pas installé. Veuillez l'installer avant d'utiliser ce script.${NC}"
    exit 1
fi

# Vérifier si le script Python existe
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/test_vllm_services.py"

if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo -e "${RED}Le script Python n'existe pas: $PYTHON_SCRIPT${NC}"
    exit 1
fi

# Vérifier si les dépendances Python sont installées
echo -e "${BLUE}Vérification des dépendances Python...${NC}"
python3 -c "import requests, dotenv, aiohttp, openai" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Installation des dépendances Python...${NC}"
    pip install requests python-dotenv aiohttp openai
    if [ $? -ne 0 ]; then
        echo -e "${RED}Échec de l'installation des dépendances. Veuillez les installer manuellement:${NC}"
        echo "pip install requests python-dotenv aiohttp openai"
        exit 1
    fi
fi

# Vérifier si le fichier .env existe
if [ ! -f "${SCRIPT_DIR}/../.env" ]; then
    echo -e "${YELLOW}Le fichier .env n'existe pas. Création d'un fichier .env par défaut...${NC}"
    cat > "${SCRIPT_DIR}/../.env" << EOF
# Configuration des endpoints pour les tests vLLM
OPENAI_ENDPOINT_NAME_2="Local Model - Micro"
OPENAI_API_KEY_2=32885271D7845A3839F1AE0274676D87
OPENAI_BASE_URL_2="https://api.micro.text-generation-webui.myia.io/v1"
OPENAI_CHAT_MODEL_ID_2="Qwen/Qwen3-4B-AWQ"

OPENAI_ENDPOINT_NAME_3="Local Model - Mini"
OPENAI_API_KEY_3=0EO6JAQITAL2Q0LW0ZUVA55W3YNCX4W9
OPENAI_BASE_URL_3="https://api.mini.text-generation-webui.myia.io/v1"
OPENAI_CHAT_MODEL_ID_3="Qwen/Qwen3-8B-AWQ"

OPENAI_ENDPOINT_NAME_4="Local Model - Medium"
OPENAI_API_KEY_4=X0EC4YYP068CPD5TGARP9VQB5U4MAGHY
OPENAI_BASE_URL_4="https://api.medium.text-generation-webui.myia.io/v1"
OPENAI_CHAT_MODEL_ID_4="Qwen/Qwen3-30B-A3B"
EOF
    echo -e "${GREEN}Fichier .env créé avec succès.${NC}"
fi

# Traitement des arguments
PYTHON_ARGS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -a|--all)
            PYTHON_ARGS="$PYTHON_ARGS --all"
            shift
            ;;
        -c|--connection)
            PYTHON_ARGS="$PYTHON_ARGS --connection"
            shift
            ;;
        -g|--generation)
            PYTHON_ARGS="$PYTHON_ARGS --generation"
            shift
            ;;
        -t|--tools)
            PYTHON_ARGS="$PYTHON_ARGS --tools"
            shift
            ;;
        -r|--reasoning)
            PYTHON_ARGS="$PYTHON_ARGS --reasoning"
            shift
            ;;
        -b|--benchmark)
            PYTHON_ARGS="$PYTHON_ARGS --benchmark"
            shift
            ;;
        -p|--parallel)
            PYTHON_ARGS="$PYTHON_ARGS --parallel"
            shift
            ;;
        --repeats)
            PYTHON_ARGS="$PYTHON_ARGS --repeats $2"
            shift 2
            ;;
        --parallel-requests)
            PYTHON_ARGS="$PYTHON_ARGS --parallel-requests $2"
            shift 2
            ;;
        *)
            echo -e "${RED}Option inconnue: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Si aucun argument n'est spécifié, exécuter tous les tests
if [ -z "$PYTHON_ARGS" ]; then
    PYTHON_ARGS="--all"
fi

# Exécuter le script Python
echo -e "${GREEN}Exécution des tests...${NC}"
echo -e "${BLUE}Commande: python3 $PYTHON_SCRIPT $PYTHON_ARGS${NC}"
echo ""

python3 "$PYTHON_SCRIPT" $PYTHON_ARGS

# Vérifier le code de retour
if [ $? -eq 0 ]; then
    echo -e "${GREEN}Tests terminés avec succès.${NC}"
else
    echo -e "${RED}Les tests ont échoué.${NC}"
    exit 1
fi