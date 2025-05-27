#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de test pour le module core de l'architecture de tests Qwen3.

Ce script démontre l'utilisation des classes et fonctions du module core
pour effectuer des benchmarks sur les modèles Qwen3.
"""

import os
import sys
import json
from pathlib import Path

# Ajouter le répertoire parent au chemin de recherche Python
sys.path.append(str(Path(__file__).parent.parent))

# Importer les modules nécessaires
from qwen3_benchmark.config import (
    get_available_models,
    get_model_info,
    get_model_endpoint
)
from qwen3_benchmark.core import (
    BenchmarkRunner,
    APIBenchmarkRunner,
    ContextBenchmarkRunner,
    DocumentQABenchmarkRunner,
    ModelClient,
    measure_execution_time,
    monitor_gpu_usage,
    generate_test_text,
    setup_logger,
    count_tokens,
    format_time,
    format_memory
)


def print_section(title):
    """Affiche un titre de section formaté"""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}")


def print_dict(data, indent=2):
    """Affiche un dictionnaire de manière formatée"""
    print(json.dumps(data, indent=indent, ensure_ascii=False))


def test_utils():
    """Teste les fonctions utilitaires"""
    print_section("Test des fonctions utilitaires")
    
    # Tester format_time
    print("Format de temps:")
    times = [0.0005, 0.5, 5, 65, 3665]
    for t in times:
        print(f"  {t} secondes = {format_time(t)}")
    
    # Tester format_memory
    print("\nFormat de mémoire:")
    memory_sizes = [500, 1500, 1500000, 1500000000]
    for size in memory_sizes:
        print(f"  {size} octets = {format_memory(size)}")
    
    # Tester generate_test_text
    print("\nGénération de texte de test:")
    text_length = 100
    text = generate_test_text(text_length)
    print(f"  Texte généré ({len(text)} caractères): {text[:50]}...")
    
    # Tester count_tokens
    print("\nEstimation du nombre de tokens:")
    sample_text = "Ceci est un exemple de texte pour tester l'estimation du nombre de tokens."
    tokens = count_tokens(sample_text)
    print(f"  Texte: '{sample_text}'")
    print(f"  Estimation: {tokens} tokens")
    
    # Tester measure_execution_time
    print("\nMesure du temps d'exécution:")
    def slow_function():
        import time
        time.sleep(0.5)
        return "Résultat de la fonction"
    
    result, execution_time = measure_execution_time(slow_function)
    print(f"  Résultat: {result}")
    print(f"  Temps d'exécution: {format_time(execution_time)}")


def test_model_client():
    """Teste le client API pour les modèles Qwen3"""
    print_section("Test du client API ModelClient")
    
    # Récupérer les modèles disponibles
    models = get_available_models()
    print(f"Modèles disponibles: {', '.join(models)}")
    
    # Utiliser le premier modèle pour le test
    model_name = models[0]
    model_info = get_model_info(model_name)
    endpoint = get_model_endpoint(model_name)
    
    print(f"\nTest avec le modèle {model_name}:")
    print(f"  Nom complet: {model_info['full_name']}")
    print(f"  Endpoint: {endpoint['url']}")
    
    # Créer une instance du client
    client = ModelClient(
        url=endpoint['url'],
        api_key=endpoint['api_key'],
        model=endpoint['model']
    )
    
    # Tester la vérification de santé
    print("\nVérification de la santé de l'API:")
    try:
        status, message = client.check_health()
        print(f"  Statut: {'OK' if status else 'ERROR'}")
        print(f"  Message: {message}")
    except Exception as e:
        print(f"  Erreur: {str(e)}")
    
    # Note: Les tests suivants nécessitent une API fonctionnelle
    # Ils sont commentés pour éviter les erreurs si l'API n'est pas disponible
    
    """
    # Tester l'API de complétion
    print("\nTest de l'API de complétion:")
    try:
        result = client.completions(
            prompt="Qwen3 est un modèle de langage développé par ",
            max_tokens=20
        )
        print(f"  Résultat: {result['choices'][0]['text']}")
    except Exception as e:
        print(f"  Erreur: {str(e)}")
    
    # Tester l'API de chat
    print("\nTest de l'API de chat:")
    try:
        result = client.chat(
            messages=[
                {"role": "system", "content": "Vous êtes un assistant IA utile et concis."},
                {"role": "user", "content": "Expliquez brièvement ce qu'est Qwen3."}
            ],
            max_tokens=50
        )
        print(f"  Résultat: {result['choices'][0]['message']['content']}")
    except Exception as e:
        print(f"  Erreur: {str(e)}")
    """


def test_benchmark_runners():
    """Teste les classes de benchmark"""
    print_section("Test des classes de benchmark")
    
    # Récupérer les modèles disponibles
    models = get_available_models()
    model_name = models[0]
    
    print(f"Test avec le modèle {model_name}")
    
    # Créer une configuration de test simplifiée
    config_override = {
        "test_parameters": {
            "num_iterations": 1,
            "request_timeout": 30,
            "generation": {
                "max_tokens": 10,
                "temperature": 0.7
            }
        }
    }
    
    # Tester APIBenchmarkRunner (sans exécution réelle)
    print("\nTest de APIBenchmarkRunner:")
    try:
        api_runner = APIBenchmarkRunner(model_name, config_override)
        print(f"  Runner initialisé pour le modèle {model_name}")
        print(f"  Nombre d'itérations: {api_runner.config['test_parameters']['num_iterations']}")
    except Exception as e:
        print(f"  Erreur: {str(e)}")
    
    # Tester ContextBenchmarkRunner (sans exécution réelle)
    print("\nTest de ContextBenchmarkRunner:")
    try:
        context_runner = ContextBenchmarkRunner(model_name, config_override)
        print(f"  Runner initialisé pour le modèle {model_name}")
        print(f"  Longueurs de contexte à tester: {context_runner.context_lengths}")
    except Exception as e:
        print(f"  Erreur: {str(e)}")
    
    # Tester DocumentQABenchmarkRunner (sans exécution réelle)
    print("\nTest de DocumentQABenchmarkRunner:")
    try:
        qa_runner = DocumentQABenchmarkRunner(model_name, config_override)
        print(f"  Runner initialisé pour le modèle {model_name}")
        print(f"  Nombre de cas de test: {len(qa_runner._load_test_cases())}")
    except Exception as e:
        print(f"  Erreur: {str(e)}")


def main():
    """Fonction principale de test"""
    print_section("Tests du module core de l'architecture de tests Qwen3")
    
    # Tester les fonctions utilitaires
    test_utils()
    
    # Tester le client API
    test_model_client()
    
    # Tester les classes de benchmark
    test_benchmark_runners()


if __name__ == "__main__":
    main()