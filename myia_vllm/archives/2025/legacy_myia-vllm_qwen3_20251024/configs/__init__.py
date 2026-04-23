#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module d'initialisation pour la configuration des tests de performance Qwen3.

Ce module expose les fonctions principales pour accéder et manipuler
les configurations des tests de performance pour les modèles Qwen3.
"""

from typing import Dict, Any, List, Optional, Union
import os
import yaml
from pathlib import Path

# Importer les fonctions du module models_config
from .models_config import (
    get_model_config,
    get_all_models_configs,
    get_model_endpoint,
    get_model_context_lengths,
    get_optimization_params,
    update_model_config,
    generate_optimized_config,
    QWEN3_MODELS
)


def get_config_path() -> Path:
    """
    Retourne le chemin vers le fichier de configuration par défaut.
    
    Returns:
        Path: Chemin vers le fichier de configuration
    """
    return Path(__file__).parent / "default_config.yaml"


def load_config() -> Dict[str, Any]:
    """
    Charge la configuration complète depuis le fichier YAML.
    
    Returns:
        Dict[str, Any]: Configuration complète
    """
    config_path = get_config_path()
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Erreur lors du chargement de la configuration: {e}")
        return {}


def save_config(config: Dict[str, Any]) -> bool:
    """
    Sauvegarde la configuration dans le fichier YAML.
    
    Args:
        config (Dict[str, Any]): Configuration à sauvegarder
        
    Returns:
        bool: True si la sauvegarde a réussi, False sinon
    """
    config_path = get_config_path()
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        return True
    except Exception as e:
        print(f"Erreur lors de la sauvegarde de la configuration: {e}")
        return False


def get_test_parameters() -> Dict[str, Any]:
    """
    Récupère les paramètres de test généraux.
    
    Returns:
        Dict[str, Any]: Paramètres de test
    """
    config = load_config()
    return config.get("test_parameters", {})


def get_output_paths() -> Dict[str, str]:
    """
    Récupère les chemins de sortie pour les résultats et rapports.
    
    Returns:
        Dict[str, str]: Chemins de sortie
    """
    config = load_config()
    return config.get("output_paths", {})


def get_docker_compose_template(model_name: str) -> str:
    """
    Récupère le chemin vers le template docker-compose pour un modèle spécifique.
    
    Args:
        model_name (str): Nom du modèle ('micro', 'mini', 'medium')
        
    Returns:
        str: Chemin vers le template docker-compose
    """
    config = load_config()
    templates = config.get("docker_compose_templates", {})
    return templates.get(model_name, "")


def get_available_models() -> List[str]:
    """
    Récupère la liste des modèles disponibles.
    
    Returns:
        List[str]: Liste des noms de modèles disponibles
    """
    return list(QWEN3_MODELS.keys())


def get_model_info(model_name: str) -> Dict[str, str]:
    """
    Récupère les informations de base sur un modèle spécifique.
    
    Args:
        model_name (str): Nom du modèle ('micro', 'mini', 'medium')
        
    Returns:
        Dict[str, str]: Informations sur le modèle
    """
    if model_name not in QWEN3_MODELS:
        raise ValueError(f"Modèle inconnu: {model_name}. Les modèles disponibles sont: {', '.join(QWEN3_MODELS.keys())}")
    
    return QWEN3_MODELS[model_name]


def create_optimized_config_file(model_name: str, max_context: int, 
                                safety_margin: float = None, 
                                output_dir: str = None) -> str:
    """
    Crée un fichier de configuration YAML optimisé pour un modèle spécifique.
    
    Args:
        model_name (str): Nom du modèle ('micro', 'mini', 'medium')
        max_context (int): Contexte maximal stable déterminé par les tests
        safety_margin (float, optional): Marge de sécurité à appliquer (0.0-1.0)
        output_dir (str, optional): Répertoire de sortie pour le fichier de configuration
        
    Returns:
        str: Chemin vers le fichier de configuration créé
    """
    # Générer la configuration optimisée
    optimized_config = generate_optimized_config(model_name, max_context, safety_margin)
    
    # Déterminer le répertoire de sortie
    if output_dir is None:
        config = load_config()
        output_dir = config.get("output_paths", {}).get("optimized_configs_dir", "optimized_configs")
    
    # Créer le répertoire s'il n'existe pas
    os.makedirs(output_dir, exist_ok=True)
    
    # Définir le chemin du fichier de sortie
    output_file = os.path.join(output_dir, f"qwen3_{model_name}_optimized_config.yaml")
    
    # Ajouter des métadonnées supplémentaires
    from datetime import datetime
    config_with_metadata = {
        "model": model_name,
        "max_context": max_context,
        "recommended_context": optimized_config["recommended_context"],
        "parameters": optimized_config["config"],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "notes": "Configuration optimisée générée automatiquement"
    }
    
    # Sauvegarder la configuration dans un fichier YAML
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            yaml.dump(config_with_metadata, f, default_flow_style=False, sort_keys=False)
        return output_file
    except Exception as e:
        print(f"Erreur lors de la création du fichier de configuration optimisée: {e}")
        return ""


def generate_docker_compose_file(model_name: str, optimized_config: Dict[str, Any], 
                               output_dir: str = None) -> str:
    """
    Génère un fichier docker-compose optimisé à partir d'un template et des recommandations.
    
    Args:
        model_name (str): Nom du modèle ('micro', 'mini', 'medium')
        optimized_config (Dict[str, Any]): Configuration optimisée
        output_dir (str, optional): Répertoire de sortie pour le fichier docker-compose
        
    Returns:
        str: Chemin vers le fichier docker-compose créé
    """
    import re
    
    # Récupérer le chemin du template
    template_path = get_docker_compose_template(model_name)
    if not template_path or not os.path.exists(template_path):
        print(f"Template docker-compose introuvable pour {model_name}: {template_path}")
        return ""
    
    # Déterminer le répertoire de sortie
    if output_dir is None:
        config = load_config()
        output_dir = config.get("output_paths", {}).get("optimized_configs_dir", "optimized_configs")
    
    # Créer le répertoire s'il n'existe pas
    os.makedirs(output_dir, exist_ok=True)
    
    # Définir le chemin du fichier de sortie
    output_file = os.path.join(output_dir, f"docker-compose-{model_name}-qwen3-optimized-max-context.yml")
    
    try:
        # Lire le template
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remplacer les paramètres
        config = optimized_config["config"]
        
        # Remplacer max-model-len
        content = re.sub(
            r'--max-model-len \d+',
            f'--max-model-len {config["max_model_len"]}',
            content
        )
        
        # Remplacer max-num-batched-tokens
        content = re.sub(
            r'--max-num-batched-tokens \d+',
            f'--max-num-batched-tokens {config["max_num_batched_tokens"]}',
            content
        )
        
        # Remplacer gpu-memory-utilization
        content = re.sub(
            r'--gpu-memory-utilization \${GPU_MEMORY_UTILIZATION:-[\d\.]+}',
            f'--gpu-memory-utilization ${{GPU_MEMORY_UTILIZATION:-{config["gpu_memory_utilization"]}}}',
            content
        )
        
        # Remplacer rope-scaling
        import json
        rope_config = json.dumps(config["rope_scaling"]).replace('"', '\\"')
        content = re.sub(
            r'--rope-scaling \'.*?\'',
            f'--rope-scaling \'{rope_config}\'',
            content
        )
        
        # Écrire le fichier optimisé
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return output_file
    except Exception as e:
        print(f"Erreur lors de la génération du fichier docker-compose: {e}")
        return ""


# Exposer les fonctions et constantes principales
__all__ = [
    'load_config',
    'save_config',
    'get_model_config',
    'get_all_models_configs',
    'get_model_endpoint',
    'get_model_context_lengths',
    'get_optimization_params',
    'update_model_config',
    'get_test_parameters',
    'get_output_paths',
    'get_docker_compose_template',
    'get_available_models',
    'get_model_info',
    'create_optimized_config_file',
    'generate_docker_compose_file',
    'generate_optimized_config',
    'QWEN3_MODELS'
]