#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de test pour le module de configuration Qwen3.

Ce script démontre l'utilisation du module de configuration
pour accéder aux paramètres des modèles Qwen3.
"""

import os
import sys
import json
from pathlib import Path

# Ajouter le répertoire parent au chemin de recherche Python
sys.path.append(str(Path(__file__).parent.parent))

# Importer le module de configuration
from qwen3_benchmark.config import (
    load_config,
    get_model_config,
    get_all_models_configs,
    get_available_models,
    get_model_info,
    get_model_endpoint,
    get_model_context_lengths,
    get_optimization_params,
    generate_optimized_config
)


def print_section(title):
    """Affiche un titre de section formaté"""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}")


def print_dict(data, indent=2):
    """Affiche un dictionnaire de manière formatée"""
    print(json.dumps(data, indent=indent, ensure_ascii=False))


def main():
    """Fonction principale de test"""
    print_section("Configuration complète")
    config = load_config()
    print(f"Nombre de sections dans la configuration: {len(config)}")
    print(f"Sections disponibles: {', '.join(config.keys())}")
    
    print_section("Modèles disponibles")
    models = get_available_models()
    print(f"Modèles: {', '.join(models)}")
    
    for model in models:
        print_section(f"Informations sur le modèle {model.upper()}")
        model_info = get_model_info(model)
        print_dict(model_info)
        
        print_section(f"Configuration complète pour {model.upper()}")
        model_config = get_model_config(model)
        print(f"Sections de configuration: {', '.join(model_config.keys())}")
        
        print_section(f"Endpoint pour {model.upper()}")
        endpoint = get_model_endpoint(model)
        print_dict(endpoint)
        
        print_section(f"Longueurs de contexte pour {model.upper()}")
        context_lengths = get_model_context_lengths(model)
        print(context_lengths)
        
        print_section(f"Paramètres d'optimisation pour {model.upper()}")
        optimization = get_optimization_params(model)
        print_dict(optimization)
        
        # Simuler un contexte maximal trouvé par les tests
        max_context = {
            "micro": 32768,
            "mini": 65536,
            "medium": 98304
        }.get(model, 32768)
        
        print_section(f"Configuration optimisée pour {model.upper()} (max_context={max_context})")
        optimized = generate_optimized_config(model, max_context)
        print_dict(optimized)


if __name__ == "__main__":
    main()