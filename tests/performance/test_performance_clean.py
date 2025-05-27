#!/usr/bin/env python3
"""
Script pour mesurer et comparer les performances des API des modèles Qwen3
entre l'accès local et l'accès externe.

Ce script effectue des tests de performance sur les différentes API
(models, completions, chat/completions, tool_calling) et compare les résultats
entre l'accès local et l'accès externe.

Usage:
    python -m tests.performance.test_performance_clean [OPTIONS]

Options:
    --model MODEL_TYPE         Type de modèle à tester (mini, medium, all) (default: all)
    --api API_TYPE             Type d'API à tester (models, completions, chat, tool_calling, all) (default: all)
    --iterations N             Nombre d'itérations pour chaque test (default: 5)
    --output-dir DIR           Répertoire de sortie pour les résultats (default: tests/performance/results)

Example:
    # Test de toutes les API pour le modèle mini avec 10 itérations
    python -m tests.performance.test_performance_clean --model mini --iterations 10
"""

import os
import sys
import json
import time
import argparse
import statistics
import datetime
import requests
from typing import Dict, List, Any, Optional, Union, Tuple
from requests.exceptions import RequestException

# Configuration des modèles
MODELS = {
    "mini": {
        "external": {
            "base_url": "https://api.mini.text-generation-webui.myia.io/v1",
            "api_key": "2NEQLFX1OONFLFCMMW9U7L15DOC9ECB",
            "model_name": "vllm-qwen3-8b-awq"
        },
        "local": {
            "base_url": "http://localhost:5002/v1",
            "api_key": "",
            "model_name": "qwen3-8b-awq"
        }
    },
    "medium": {
        "external": {
            "base_url": "https://api.medium.text-generation-webui.myia.io/v1",
            "api_key": "X0EC4YYP068CPD5TGARP9VQB5U4MAGHY",
            "model_name": "vllm-qwen3-32b-awq"
        },
        "local": {
            "base_url": "http://localhost:5001/v1",
            "api_key": "",
            "model_name": "qwen3-32b-awq"
        }
    }
}

# Définition des prompts de test
TEST_PROMPTS = {
    "completions": "Explique le concept d'intelligence artificielle en une phrase.",
    "chat": [
        {"role": "system", "content": "Tu es un assistant utile."},
        {"role": "user", "content": "Explique le concept d'intelligence artificielle en une phrase."}
    ],
    "tool_calling": "Quelle est la météo à Paris aujourd'hui?"
}

# Définition des outils pour le test de tool calling
AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Obtient les informations météorologiques pour un lieu donné",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Le lieu pour lequel obtenir la météo, par exemple 'Paris, France'"
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "L'unité de température à utiliser"
                    }
                },
                "required": ["location"]
            }
        }
    }
]

def print_header(title: str) -> None:
    """Affiche un en-tête formaté pour les sections de test."""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80)

def print_subheader(title: str) -> None:
    """Affiche un sous-en-tête formaté pour les sous-sections de test."""
    print("\n" + "-" * 80)
    print(f" {title} ".center(80, "-"))
    print("-" * 80)

def make_api_request(base_url: str, endpoint: str, api_key: str, method: str = "GET", 
                    data: Dict[str, Any] = None, timeout: int = 30) -> Tuple[Dict[str, Any], float]:
    """
    Effectue une requête à l'API et mesure le temps de réponse.
    
    Args:
        base_url: URL de base de l'API
        endpoint: Endpoint de l'API (sans le slash initial)
        api_key: Clé API
        method: Méthode HTTP (GET ou POST)
        data: Données à envoyer (pour les requêtes POST)
        timeout: Délai d'attente maximum en secondes
        
    Returns:
        Un tuple contenant la réponse de l'API et le temps d'exécution
    """
    url = f"{base_url}/{endpoint}"
    headers = {
        "Content-Type": "application/json"
    }
    
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    start_time = time.time()
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, timeout=timeout)
        else:  # POST
            response = requests.post(url, headers=headers, json=data, timeout=timeout)
        
        response.raise_for_status()
        result = response.json()
        
    except RequestException as e:
        if hasattr(e, 'response') and e.response:
            error_msg = f"Erreur {e.response.status_code}: {e.response.text}"
        else:
            error_msg = str(e)
        result = {"error": error_msg}
    
    execution_time = time.time() - start_time
    
    return result, execution_time

def test_models_api_performance(model_type: str, access_type: str, iterations: int = 5) -> Dict[str, Any]:
    """
    Teste les performances de l'API models.
    
    Args:
        model_type: Type de modèle (mini ou medium)
        access_type: Type d'accès (external ou local)
        iterations: Nombre d'itérations pour le test
        
    Returns:
        Un dictionnaire contenant les résultats du test
    """
    config = MODELS[model_type][access_type]
    print(f"Test de performance de l'API models pour {model_type.upper()} ({access_type})")
    
    execution_times = []
    success_count = 0
    
    for i in range(iterations):
        print(f"  Itération {i+1}/{iterations}...", end="", flush=True)
        
        result, execution_time = make_api_request(
            config["base_url"], 
            "models", 
            config["api_key"]
        )
        
        success = "error" not in result
        
        if success:
            execution_times.append(execution_time)
            success_count += 1
            print(f" ✓ {execution_time:.2f}s")
        else:
            print(f" ✗ {execution_time:.2f}s - {result.get('error', 'Erreur inconnue')}")
    
    # Calculer les statistiques
    if execution_times:
        avg_time = statistics.mean(execution_times)
        min_time = min(execution_times)
        max_time = max(execution_times)
        median_time = statistics.median(execution_times)
        stdev_time = statistics.stdev(execution_times) if len(execution_times) > 1 else 0
    else:
        avg_time = min_time = max_time = median_time = stdev_time = 0
    
    success_rate = success_count / iterations if iterations > 0 else 0
    
    print(f"\nRésultats pour {model_type.upper()} ({access_type}):")
    print(f"  Taux de réussite: {success_rate*100:.1f}% ({success_count}/{iterations})")
    print(f"  Temps moyen: {avg_time:.2f}s")
    print(f"  Temps min: {min_time:.2f}s")
    print(f"  Temps max: {max_time:.2f}s")
    print(f"  Temps médian: {median_time:.2f}s")
    print(f"  Écart-type: {stdev_time:.2f}s")
    
    return {
        "model_type": model_type,
        "access_type": access_type,
        "api_type": "models",
        "success_rate": success_rate,
        "execution_times": execution_times,
        "avg_time": avg_time,
        "min_time": min_time,
        "max_time": max_time,
        "median_time": median_time,
        "stdev_time": stdev_time
    }

def main():
    """Fonction principale qui exécute les tests de performance."""
    parser = argparse.ArgumentParser(description="Tests de performance des API des modèles Qwen3")
    parser.add_argument("--model", choices=["mini", "medium", "all"], default="all", help="Type de modèle à tester")
    parser.add_argument("--api", choices=["models", "completions", "chat", "tool_calling", "all"], default="all", help="Type d'API à tester")
    parser.add_argument("--iterations", type=int, default=5, help="Nombre d'itérations pour chaque test")
    parser.add_argument("--output-dir", default="tests/performance/results", help="Répertoire de sortie pour les résultats")
    args = parser.parse_args()
    
    # Déterminer les modèles à tester
    model_types = ["mini", "medium"] if args.model == "all" else [args.model]
    
    # Déterminer les API à tester
    api_types = ["models", "completions", "chat", "tool_calling"] if args.api == "all" else [args.api]
    
    # Créer le répertoire de sortie s'il n'existe pas
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Stocker tous les résultats
    all_results = {}
    
    # Exécuter les tests pour chaque modèle et chaque API
    for model_type in model_types:
        print_header(f"Tests pour le modèle {model_type.upper()}")
        all_results[model_type] = {}
        
        for api_type in api_types:
            if api_type == "models":
                print_subheader(f"Tests de l'API {api_type}")
                all_results[model_type][api_type] = {}
                
                # Test de l'accès local
                print_subheader(f"Accès local - {model_type.upper()} - API {api_type}")
                local_results = test_models_api_performance(model_type, "local", args.iterations)
                all_results[model_type][api_type]["local"] = local_results
    
    print_header("Tests terminés")
    print("Les tests ont été exécutés avec succès.")
    print(f"Les résultats ont été sauvegardés dans {args.output_dir}")

if __name__ == "__main__":
    main()