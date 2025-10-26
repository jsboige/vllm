#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de test pour démontrer l'utilisation des benchmarks Qwen3.

Ce script montre comment utiliser les différentes classes de benchmark
pour évaluer les performances des modèles Qwen3.
"""

import os
import sys
import json
import argparse
from typing import Dict, Any, List, Optional

from qwen3_benchmark.config import (
    load_config,
    get_available_models,
    get_model_endpoint,
    get_output_paths
)
from qwen3_benchmark.benchmarks import (
    APIComparisonBenchmark,
    ContextLengthBenchmark,
    DocumentQABenchmark
)


def run_api_comparison_benchmark(model_name: str, external_endpoint: Dict[str, str]) -> Dict[str, Any]:
    """
    Exécute un benchmark de comparaison d'API pour le modèle spécifié.
    
    Args:
        model_name (str): Nom du modèle à tester ('micro', 'mini', 'medium')
        external_endpoint (Dict[str, str]): Configuration de l'endpoint externe
        
    Returns:
        Dict[str, Any]: Résultats du benchmark
    """
    print(f"\n=== Exécution du benchmark de comparaison d'API pour {model_name} ===")
    
    # Initialiser le benchmark
    benchmark = APIComparisonBenchmark(model_name, external_endpoint)
    
    # Exécuter le benchmark
    results = benchmark.execute()
    
    # Sauvegarder les résultats
    output_path = benchmark.save_results()
    print(f"Résultats sauvegardés dans {output_path}")
    
    # Générer un rapport
    report_path = benchmark.generate_report()
    print(f"Rapport généré dans {report_path}")
    
    return results


def run_context_length_benchmark(model_name: str) -> Dict[str, Any]:
    """
    Exécute un benchmark de longueur de contexte pour le modèle spécifié.
    
    Args:
        model_name (str): Nom du modèle à tester ('micro', 'mini', 'medium')
        
    Returns:
        Dict[str, Any]: Résultats du benchmark
    """
    print(f"\n=== Exécution du benchmark de longueur de contexte pour {model_name} ===")
    
    # Initialiser le benchmark
    benchmark = ContextLengthBenchmark(model_name)
    
    # Exécuter le benchmark
    results = benchmark.execute()
    
    # Déterminer la longueur de contexte optimale
    optimal_context = benchmark.determine_optimal_context()
    print(f"Contexte maximal stable: {optimal_context.get('max_stable_context')}")
    print(f"Contexte recommandé: {optimal_context.get('recommended_context')}")
    print(f"Contexte recommandé avec marge de sécurité: {optimal_context.get('recommended_context_with_margin')}")
    
    # Sauvegarder les résultats
    output_path = benchmark.save_results()
    print(f"Résultats sauvegardés dans {output_path}")
    
    # Générer un rapport
    report_path = benchmark.generate_report()
    print(f"Rapport généré dans {report_path}")
    
    return results


def run_document_qa_benchmark(model_name: str) -> Dict[str, Any]:
    """
    Exécute un benchmark de QA sur documents pour le modèle spécifié.
    
    Args:
        model_name (str): Nom du modèle à tester ('micro', 'mini', 'medium')
        
    Returns:
        Dict[str, Any]: Résultats du benchmark
    """
    print(f"\n=== Exécution du benchmark de QA sur documents pour {model_name} ===")
    
    # Initialiser le benchmark
    benchmark = DocumentQABenchmark(model_name)
    
    # Exécuter le benchmark
    results = benchmark.execute()
    
    # Sauvegarder les résultats détaillés
    detailed_path = benchmark.save_detailed_results()
    print(f"Résultats détaillés sauvegardés dans {detailed_path}")
    
    # Sauvegarder les résultats
    output_path = benchmark.save_results()
    print(f"Résultats sauvegardés dans {output_path}")
    
    # Générer un rapport
    report_path = benchmark.generate_report()
    print(f"Rapport généré dans {report_path}")
    
    return results


def run_all_benchmarks(model_name: str, external_endpoint: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Exécute tous les benchmarks pour le modèle spécifié.
    
    Args:
        model_name (str): Nom du modèle à tester ('micro', 'mini', 'medium')
        external_endpoint (Dict[str, str], optional): Configuration de l'endpoint externe
        
    Returns:
        Dict[str, Any]: Résultats de tous les benchmarks
    """
    print(f"\n=== Exécution de tous les benchmarks pour {model_name} ===")
    
    results = {}
    
    # Benchmark de longueur de contexte
    print("\nExécution du benchmark de longueur de contexte...")
    context_results = run_context_length_benchmark(model_name)
    results["context_length"] = context_results
    
    # Benchmark de QA sur documents
    print("\nExécution du benchmark de QA sur documents...")
    qa_results = run_document_qa_benchmark(model_name)
    results["document_qa"] = qa_results
    
    # Benchmark de comparaison d'API (si un endpoint externe est fourni)
    if external_endpoint:
        print("\nExécution du benchmark de comparaison d'API...")
        api_results = run_api_comparison_benchmark(model_name, external_endpoint)
        results["api_comparison"] = api_results
    
    return results


def main():
    """
    Fonction principale pour exécuter les benchmarks depuis la ligne de commande.
    """
    parser = argparse.ArgumentParser(description="Exécuter des benchmarks pour les modèles Qwen3")
    
    parser.add_argument("--model", type=str, choices=get_available_models(),
                        help="Modèle à tester ('micro', 'mini', 'medium')")
    
    parser.add_argument("--benchmark", type=str, choices=["api", "context", "qa", "all"],
                        default="all", help="Type de benchmark à exécuter")
    
    parser.add_argument("--external-url", type=str,
                        help="URL de l'endpoint externe pour la comparaison d'API")
    
    parser.add_argument("--external-key", type=str,
                        help="Clé API pour l'endpoint externe")
    
    parser.add_argument("--external-model", type=str,
                        help="Nom du modèle pour l'endpoint externe")
    
    args = parser.parse_args()
    
    # Vérifier si un modèle est spécifié
    if not args.model:
        print("Erreur: Vous devez spécifier un modèle avec --model")
        parser.print_help()
        sys.exit(1)
    
    # Préparer la configuration de l'endpoint externe si nécessaire
    external_endpoint = None
    if args.benchmark in ["api", "all"] and args.external_url:
        external_endpoint = {
            "url": args.external_url,
            "api_key": args.external_key or "",
            "model": args.external_model or ""
        }
    
    # Exécuter le benchmark spécifié
    if args.benchmark == "api":
        if not external_endpoint:
            print("Erreur: Pour le benchmark API, vous devez spécifier --external-url")
            sys.exit(1)
        run_api_comparison_benchmark(args.model, external_endpoint)
    
    elif args.benchmark == "context":
        run_context_length_benchmark(args.model)
    
    elif args.benchmark == "qa":
        run_document_qa_benchmark(args.model)
    
    else:  # all
        run_all_benchmarks(args.model, external_endpoint)


if __name__ == "__main__":
    main()