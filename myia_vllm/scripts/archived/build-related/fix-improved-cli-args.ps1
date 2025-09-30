# Script pour corriger le fichier improved_cli_args_patch.py dans le container

# Démarrer un container temporaire
docker run --name temp-qwen3-container -d vllm/vllm-openai:qwen3-final sleep 60

# Créer un script de correction
$script = @"
#!/bin/bash
if [ -f /workspace/improved_cli_args_patch.py ]; then
    # Sauvegarder le fichier original
    cp /workspace/improved_cli_args_patch.py /workspace/improved_cli_args_patch.py.bak
    
    # Remplacer l'importation problématique
    sed -i 's/import vllm.entrypoints.openai.tool_parsers.qwen3_tool_parser/# import vllm.entrypoints.openai.tool_parsers.qwen3_tool_parser/g' /workspace/improved_cli_args_patch.py
    
    echo "Le fichier improved_cli_args_patch.py a été corrigé"
else
    echo "Le fichier improved_cli_args_patch.py n'existe pas"
fi
"@

# Écrire le script dans un fichier temporaire
$script | Out-File -Encoding ASCII -FilePath "fix-script.sh"

# Copier le script dans le container
docker cp fix-script.sh temp-qwen3-container:/workspace/

# Exécuter le script dans le container
docker exec temp-qwen3-container bash -c "chmod +x /workspace/fix-script.sh && /workspace/fix-script.sh"

# Copier le fichier corrigé depuis le container
docker cp temp-qwen3-container:/workspace/improved_cli_args_patch.py improved_cli_args_patch.py

# Arrêter et supprimer le container temporaire
docker stop temp-qwen3-container
docker rm temp-qwen3-container

# Supprimer le fichier temporaire
Remove-Item -Path "fix-script.sh"

Write-Host "Le fichier improved_cli_args_patch.py a été extrait et corrigé"