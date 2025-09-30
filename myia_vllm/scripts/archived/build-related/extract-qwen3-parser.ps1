# Script pour extraire le parser d'outils Qwen3 du container

# Créer le répertoire pour stocker le parser
$parsersDir = "qwen3/parsers"
if (-not (Test-Path $parsersDir)) {
    New-Item -ItemType Directory -Path $parsersDir -Force
}

# Démarrer un container temporaire
docker run --name temp-qwen3-container -d vllm/vllm-openai:qwen3-final sleep 60

# Extraire le fichier qwen3_tool_parser.py
docker cp temp-qwen3-container:/workspace/vllm/entrypoints/openai/tool_parsers/qwen3_tool_parser.py qwen3/parsers/

# Arrêter et supprimer le container temporaire
docker stop temp-qwen3-container
docker rm temp-qwen3-container

Write-Host "Le fichier qwen3_tool_parser.py a été extrait avec succès dans $parsersDir"