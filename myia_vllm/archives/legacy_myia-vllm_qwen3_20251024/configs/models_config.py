#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de configuration des modèles Qwen3.

Ce module définit les configurations spécifiques aux différents modèles Qwen3
(MICRO, MINI, MEDIUM) et fournit des fonctions pour obtenir ces configurations.
"""

from typing import Dict, Any, List, Optional, Union
import os
import yaml
from pathlib import Path


# Définitions des modèles Qwen3
QWEN3_MODELS = {
    "micro": {
        "name": "Qwen3 MICRO",
        "full_name": "Qwen/Qwen3-1.7B-FP8",
        "size": "1.7B",
        "quantization": "FP8",
        "description": "Version la plus légère de Qwen3, optimisée pour les déploiements à ressources limitées",
        "typical_gpu_vram": "4-6 GB",
        "recommended_gpu": "NVIDIA RTX 3060 ou supérieur",
    },
    "mini": {
        "name": "Qwen3 MINI",
        "full_name": "Qwen/Qwen3-8B-AWQ",
        "size": "8B",
        "quantization": "AWQ",
        "description": "Version intermédiaire de Qwen3, bon équilibre entre performances et ressources requises",
        "typical_gpu_vram": "8-12 GB",
        "recommended_gpu": "NVIDIA RTX 3080 ou supérieur",
    },
    "medium": {
        "name": "Qwen3 MEDIUM",
        "full_name": "Qwen/Qwen3-32B-AWQ",
        "size": "32B",
        "quantization": "AWQ",
        "description": "Version la plus puissante de Qwen3, pour les tâches complexes nécessitant de hautes performances",
        "typical_gpu_vram": "24-32 GB",
        "recommended_gpu": "NVIDIA RTX 4090 ou A100",
    }
}


def load_default_config() -> Dict[str, Any]:
    """
    Charge la configuration par défaut depuis le fichier YAML.
    
    Returns:
        Dict[str, Any]: Configuration par défaut
    """
    config_path = Path(__file__).parent / "default_config.yaml"
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Erreur lors du chargement de la configuration par défaut: {e}")
        return {}


def get_model_config(model_name: str) -> Dict[str, Any]:
    """
    Récupère la configuration complète pour un modèle spécifique.
    
    Args:
        model_name (str): Nom du modèle ('micro', 'mini', 'medium')
        
    Returns:
        Dict[str, Any]: Configuration complète du modèle
    
    Raises:
        ValueError: Si le modèle spécifié n'existe pas
    """
    if model_name not in QWEN3_MODELS:
        raise ValueError(f"Modèle inconnu: {model_name}. Les modèles disponibles sont: {', '.join(QWEN3_MODELS.keys())}")
    
    # Charger la configuration par défaut
    default_config = load_default_config()
    
    # Récupérer les informations spécifiques au modèle
    model_info = QWEN3_MODELS[model_name]
    
    # Récupérer les paramètres d'endpoint pour ce modèle
    endpoint_config = default_config.get("endpoints", {}).get(model_name, {})
    
    # Récupérer les longueurs de contexte spécifiques au modèle ou utiliser les valeurs par défaut
    context_lengths = default_config.get("context_lengths", {}).get(
        model_name, 
        default_config.get("context_lengths", {}).get("default", [])
    )
    
    # Construire la configuration complète du modèle
    config = {
        "model_info": model_info,
        "endpoint": endpoint_config,
        "context_lengths": context_lengths,
        "optimization": default_config.get("optimization", {}),
        "test_parameters": default_config.get("test_parameters", {})
    }
    
    return config


def get_all_models_configs() -> Dict[str, Dict[str, Any]]:
    """
    Récupère les configurations pour tous les modèles disponibles.
    
    Returns:
        Dict[str, Dict[str, Any]]: Dictionnaire des configurations de tous les modèles
    """
    return {model: get_model_config(model) for model in QWEN3_MODELS.keys()}


def get_model_endpoint(model_name: str) -> Dict[str, str]:
    """
    Récupère uniquement les informations d'endpoint pour un modèle spécifique.
    
    Args:
        model_name (str): Nom du modèle ('micro', 'mini', 'medium')
        
    Returns:
        Dict[str, str]: Configuration de l'endpoint du modèle
    """
    config = get_model_config(model_name)
    return config.get("endpoint", {})


def get_model_context_lengths(model_name: str) -> List[int]:
    """
    Récupère les longueurs de contexte à tester pour un modèle spécifique.
    
    Args:
        model_name (str): Nom du modèle ('micro', 'mini', 'medium')
        
    Returns:
        List[int]: Liste des longueurs de contexte à tester
    """
    config = get_model_config(model_name)
    return config.get("context_lengths", [])


def get_optimization_params(model_name: str) -> Dict[str, Any]:
    """
    Récupère les paramètres d'optimisation pour un modèle spécifique.
    
    Args:
        model_name (str): Nom du modèle ('micro', 'mini', 'medium')
        
    Returns:
        Dict[str, Any]: Paramètres d'optimisation
    """
    config = get_model_config(model_name)
    return config.get("optimization", {})


def update_model_config(model_name: str, updates: Dict[str, Any]) -> None:
    """
    Met à jour la configuration d'un modèle spécifique dans le fichier YAML.
    
    Args:
        model_name (str): Nom du modèle ('micro', 'mini', 'medium')
        updates (Dict[str, Any]): Mises à jour à appliquer
        
    Note:
        Cette fonction modifie directement le fichier de configuration.
    """
    config_path = Path(__file__).parent / "default_config.yaml"
    
    try:
        # Charger la configuration actuelle
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # Mettre à jour les sections appropriées
        if "endpoint" in updates and model_name in config.get("endpoints", {}):
            config["endpoints"][model_name].update(updates["endpoint"])
        
        if "context_lengths" in updates and "context_lengths" in config:
            config["context_lengths"][model_name] = updates["context_lengths"]
        
        if "optimization" in updates and "optimization" in config:
            # Mise à jour récursive des paramètres d'optimisation
            for key, value in updates["optimization"].items():
                if isinstance(value, dict) and key in config["optimization"] and isinstance(config["optimization"][key], dict):
                    config["optimization"][key].update(value)
                else:
                    config["optimization"][key] = value
        
        # Sauvegarder la configuration mise à jour
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            
    except Exception as e:
        print(f"Erreur lors de la mise à jour de la configuration: {e}")


def generate_optimized_config(model_name: str, max_context: int, safety_margin: float = None) -> Dict[str, Any]:
    """
    Génère une configuration optimisée pour un modèle spécifique en fonction du contexte maximal.
    
    Args:
        model_name (str): Nom du modèle ('micro', 'mini', 'medium')
        max_context (int): Contexte maximal stable déterminé par les tests
        safety_margin (float, optional): Marge de sécurité à appliquer (0.0-1.0)
        
    Returns:
        Dict[str, Any]: Configuration optimisée
    """
    # Charger la configuration par défaut
    config = get_model_config(model_name)
    
    # Utiliser la marge de sécurité spécifiée ou celle par défaut
    if safety_margin is None:
        safety_margin = config.get("optimization", {}).get("safety_margin", 0.9)
    
    # Calculer le contexte recommandé avec la marge de sécurité
    recommended_context = int(max_context * safety_margin)
    
    # Déterminer les paramètres RoPE optimaux
    rope_scaling = config.get("optimization", {}).get("rope_scaling", {}).copy()
    
    # Si le contexte recommandé est supérieur à 65536, augmenter le facteur
    if recommended_context > 65536:
        rope_scaling["factor"] = 8.0
    
    # Générer la configuration optimisée
    optimized_config = {
        "model": model_name,
        "max_context": max_context,
        "recommended_context": recommended_context,
        "config": {
            "max_model_len": recommended_context,
            "max_num_batched_tokens": recommended_context,
            "gpu_memory_utilization": config.get("optimization", {}).get("advanced", {}).get("gpu_memory_utilization", 0.95),
            "rope_scaling": rope_scaling,
            "kv_cache_dtype": config.get("optimization", {}).get("advanced", {}).get("kv_cache_dtype", "fp8"),
            "enable_chunked_prefill": config.get("optimization", {}).get("advanced", {}).get("enable_chunked_prefill", True),
            "enable_prefix_caching": config.get("optimization", {}).get("advanced", {}).get("enable_prefix_caching", True)
        }
    }
    
    return optimized_config


if __name__ == "__main__":
    # Test simple pour vérifier que le module fonctionne correctement
    print("Configurations des modèles Qwen3:")
    for model in QWEN3_MODELS.keys():
        config = get_model_config(model)
        print(f"\n{model.upper()}:")
        print(f"  Nom complet: {config['model_info']['full_name']}")
        print(f"  Taille: {config['model_info']['size']}")
        print(f"  Endpoint: {config['endpoint']['url']}")
        print(f"  Longueurs de contexte à tester: {config['context_lengths']}")