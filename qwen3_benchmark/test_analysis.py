#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de test pour démontrer l'utilisation du module d'analyse Qwen3.

Ce script montre comment utiliser les différentes fonctionnalités du module
pour analyser les résultats des benchmarks, générer des visualisations
et optimiser les configurations.
"""

import os
import sys
import json
import argparse
from typing import Dict, Any, List, Optional
from pathlib import Path

from qwen3_benchmark.config import (
    load_config,
    get_output_paths
)
from qwen3_benchmark.analysis import (
    # Métriques
    calculate_basic_metrics,
    calculate_llm_metrics,
    calculate_resource_metrics,
    compare_results,
    
    # Visualisation
    generate_performance_chart,
    generate_comparison_chart,
    generate_context_impact_chart,
    export_visualization,
    
    # Optimisation
    determine_optimal_parameters,
    generate_optimized_config,
    optimize_rope_parameters,
    generate_optimized_docker_compose
)


def load_benchmark_results(results_path: str) -> Dict[str, Any]:
    """
    Charge les résultats d'un benchmark à partir d'un fichier JSON.
    
    Args:
        results_path (str): Chemin vers le fichier de résultats
    
    Returns:
        Dict[str, Any]: Résultats du benchmark
    """
    try:
        with open(results_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Erreur lors du chargement des résultats: {str(e)}")
        return {}


def analyze_benchmark_results(results_path: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Analyse les résultats d'un benchmark et génère des métriques.
    
    Args:
        results_path (str): Chemin vers le fichier de résultats
        output_dir (str, optional): Répertoire où sauvegarder les résultats d'analyse
    
    Returns:
        Dict[str, Any]: Métriques calculées
    """
    print(f"\n=== Analyse des résultats du benchmark: {results_path} ===")
    
    # Charger les résultats
    results = load_benchmark_results(results_path)
    if not results:
        print("Aucun résultat à analyser")
        return {}
    
    model_name = results.get("model", "unknown").upper()
    print(f"Modèle: {model_name}")
    
    # Calculer les métriques LLM
    print("\nCalcul des métriques LLM...")
    llm_metrics = calculate_llm_metrics(results)
    
    # Calculer les métriques de ressources
    print("Calcul des métriques de ressources...")
    resource_metrics = calculate_resource_metrics(results)
    
    # Combiner les métriques
    metrics = {
        "llm_metrics": llm_metrics,
        "resource_metrics": resource_metrics
    }
    
    # Sauvegarder les métriques si un répertoire de sortie est spécifié
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        metrics_path = os.path.join(output_dir, f"{model_name.lower()}_metrics.json")
        
        try:
            with open(metrics_path, 'w', encoding='utf-8') as f:
                json.dump(metrics, f, indent=2, ensure_ascii=False)
            print(f"Métriques sauvegardées dans {metrics_path}")
        except Exception as e:
            print(f"Erreur lors de la sauvegarde des métriques: {str(e)}")
    
    return metrics


def visualize_benchmark_results(results_path: str, output_dir: Optional[str] = None) -> List[str]:
    """
    Génère des visualisations à partir des résultats d'un benchmark.
    
    Args:
        results_path (str): Chemin vers le fichier de résultats
        output_dir (str, optional): Répertoire où sauvegarder les visualisations
    
    Returns:
        List[str]: Liste des chemins des fichiers générés
    """
    print(f"\n=== Visualisation des résultats du benchmark: {results_path} ===")
    
    # Charger les résultats
    results = load_benchmark_results(results_path)
    if not results:
        print("Aucun résultat à visualiser")
        return []
    
    model_name = results.get("model", "unknown").upper()
    print(f"Modèle: {model_name}")
    
    # Déterminer le répertoire de sortie
    if not output_dir:
        paths = get_output_paths()
        output_dir = os.path.join(paths.get("results_dir", "results"), "visualizations")
    
    os.makedirs(output_dir, exist_ok=True)
    
    generated_files = []
    
    # Générer un graphique de temps d'exécution
    print("\nGénération du graphique de temps d'exécution...")
    exec_chart = generate_performance_chart(
        results, 
        metric_type='execution_time',
        title=f"Temps d'exécution - {model_name}"
    )
    
    exec_path = os.path.join(output_dir, f"{model_name.lower()}_execution_time")
    exec_file = export_visualization(exec_chart, exec_path, 'png')
    generated_files.append(exec_file)
    print(f"Graphique sauvegardé dans {exec_file}")
    
    # Générer un graphique de débit
    print("Génération du graphique de débit...")
    tps_chart = generate_performance_chart(
        results, 
        metric_type='tokens_per_second',
        title=f"Débit - {model_name}"
    )
    
    tps_path = os.path.join(output_dir, f"{model_name.lower()}_throughput")
    tps_file = export_visualization(tps_chart, tps_path, 'png')
    generated_files.append(tps_file)
    print(f"Graphique sauvegardé dans {tps_file}")
    
    # Générer un graphique d'impact de la longueur de contexte si disponible
    if "context_results" in results:
        print("Génération du graphique d'impact de la longueur de contexte...")
        context_chart = generate_context_impact_chart(
            results,
            title=f"Impact de la longueur de contexte - {model_name}"
        )
        
        context_path = os.path.join(output_dir, f"{model_name.lower()}_context_impact")
        context_file = export_visualization(context_chart, context_path, 'png')
        generated_files.append(context_file)
        print(f"Graphique sauvegardé dans {context_file}")
    
    return generated_files


def compare_benchmark_results(results_path1: str, 
                             results_path2: str, 
                             output_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Compare les résultats de deux benchmarks.
    
    Args:
        results_path1 (str): Chemin vers le premier fichier de résultats
        results_path2 (str): Chemin vers le deuxième fichier de résultats
        output_dir (str, optional): Répertoire où sauvegarder les résultats de comparaison
    
    Returns:
        Dict[str, Any]: Résultats de la comparaison
    """
    print(f"\n=== Comparaison des résultats de benchmarks ===")
    print(f"Benchmark 1: {results_path1}")
    print(f"Benchmark 2: {results_path2}")
    
    # Charger les résultats
    results1 = load_benchmark_results(results_path1)
    results2 = load_benchmark_results(results_path2)
    
    if not results1 or not results2:
        print("Impossible de comparer les résultats: un ou plusieurs fichiers sont manquants ou invalides")
        return {}
    
    model1 = results1.get("model", "model1").upper()
    model2 = results2.get("model", "model2").upper()
    
    print(f"Comparaison entre {model1} et {model2}")
    
    # Comparer les résultats
    comparison = compare_results(results1, results2, model1, model2)
    
    # Déterminer le répertoire de sortie
    if not output_dir:
        paths = get_output_paths()
        output_dir = os.path.join(paths.get("results_dir", "results"), "comparisons")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Sauvegarder les résultats de la comparaison
    comparison_path = os.path.join(output_dir, f"comparison_{model1.lower()}_vs_{model2.lower()}.json")
    
    try:
        with open(comparison_path, 'w', encoding='utf-8') as f:
            json.dump(comparison, f, indent=2, ensure_ascii=False)
        print(f"Résultats de la comparaison sauvegardés dans {comparison_path}")
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des résultats de la comparaison: {str(e)}")
    
    # Générer un graphique de comparaison
    print("\nGénération du graphique de comparaison de débit...")
    comparison_chart = generate_comparison_chart(
        results1, 
        results2,
        metric_type='tokens_per_second',
        name1=model1,
        name2=model2,
        title=f"Comparaison du débit: {model1} vs {model2}"
    )
    
    chart_path = os.path.join(output_dir, f"comparison_{model1.lower()}_vs_{model2.lower()}_throughput")
    chart_file = export_visualization(comparison_chart, chart_path, 'png')
    print(f"Graphique sauvegardé dans {chart_file}")
    
    return comparison


def optimize_model_config(results_path: str, 
                         config_path: str,
                         output_dir: Optional[str] = None) -> str:
    """
    Optimise la configuration d'un modèle basée sur les résultats d'un benchmark.
    
    Args:
        results_path (str): Chemin vers le fichier de résultats
        config_path (str): Chemin vers le fichier de configuration à optimiser
        output_dir (str, optional): Répertoire où sauvegarder la configuration optimisée
    
    Returns:
        str: Chemin de la configuration optimisée
    """
    print(f"\n=== Optimisation de la configuration du modèle ===")
    print(f"Résultats: {results_path}")
    print(f"Configuration: {config_path}")
    
    # Charger les résultats et la configuration
    results = load_benchmark_results(results_path)
    
    if not results:
        print("Impossible d'optimiser la configuration: résultats manquants ou invalides")
        return ""
    
    # Charger la configuration
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            if config_path.endswith('.json'):
                base_config = json.load(f)
            else:
                import yaml
                base_config = yaml.safe_load(f)
    except Exception as e:
        print(f"Erreur lors du chargement de la configuration: {str(e)}")
        return ""
    
    model_name = results.get("model", "unknown").lower()
    print(f"Modèle: {model_name.upper()}")
    
    # Optimiser la configuration
    print("\nOptimisation des paramètres généraux...")
    optimized_config = generate_optimized_config(results, base_config)
    
    print("Optimisation des paramètres RoPE pour les longs contextes...")
    optimized_config = optimize_rope_parameters(results, optimized_config)
    
    # Déterminer le répertoire de sortie
    if not output_dir:
        paths = get_output_paths()
        output_dir = os.path.join(paths.get("configs_dir", "configs"), "optimized")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Sauvegarder la configuration optimisée
    config_filename = os.path.basename(config_path)
    optimized_path = os.path.join(output_dir, f"optimized_{model_name}_{config_filename}")
    
    try:
        with open(optimized_path, 'w', encoding='utf-8') as f:
            if optimized_path.endswith('.json'):
                json.dump(optimized_config, f, indent=2, ensure_ascii=False)
            else:
                import yaml
                yaml.dump(optimized_config, f, default_flow_style=False)
        print(f"Configuration optimisée sauvegardée dans {optimized_path}")
    except Exception as e:
        print(f"Erreur lors de la sauvegarde de la configuration optimisée: {str(e)}")
        return ""
    
    return optimized_path


def generate_docker_compose(results_path: str, 
                           template_path: str,
                           output_dir: Optional[str] = None) -> str:
    """
    Génère un fichier docker-compose optimisé basé sur les résultats d'un benchmark.
    
    Args:
        results_path (str): Chemin vers le fichier de résultats
        template_path (str): Chemin vers le fichier docker-compose template
        output_dir (str, optional): Répertoire où sauvegarder le fichier généré
    
    Returns:
        str: Chemin du fichier docker-compose généré
    """
    print(f"\n=== Génération du fichier docker-compose optimisé ===")
    print(f"Résultats: {results_path}")
    print(f"Template: {template_path}")
    
    # Charger les résultats
    results = load_benchmark_results(results_path)
    
    if not results:
        print("Impossible de générer le fichier docker-compose: résultats manquants ou invalides")
        return ""
    
    model_name = results.get("model", "unknown").lower()
    print(f"Modèle: {model_name.upper()}")
    
    # Déterminer le répertoire de sortie
    if not output_dir:
        paths = get_output_paths()
        output_dir = os.path.join(paths.get("configs_dir", "configs"), "docker-compose")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Générer le fichier docker-compose optimisé
    output_path = os.path.join(output_dir, f"docker-compose-{model_name}-optimized.yml")
    
    # Générer le contenu du fichier docker-compose
    docker_compose_content = generate_optimized_docker_compose(results, template_path, output_path)
    
    if docker_compose_content:
        print(f"Fichier docker-compose optimisé généré dans {output_path}")
        return output_path
    else:
        print("Erreur lors de la génération du fichier docker-compose")
        return ""


def main():
    """
    Fonction principale pour exécuter les analyses depuis la ligne de commande.
    """
    parser = argparse.ArgumentParser(description="Analyser les résultats des benchmarks Qwen3")
    
    subparsers = parser.add_subparsers(dest="command", help="Commande à exécuter")
    
    # Commande pour analyser les résultats
    analyze_parser = subparsers.add_parser("analyze", help="Analyser les résultats d'un benchmark")
    analyze_parser.add_argument("--results", type=str, required=True,
                              help="Chemin vers le fichier de résultats")
    analyze_parser.add_argument("--output-dir", type=str,
                              help="Répertoire où sauvegarder les résultats d'analyse")
    
    # Commande pour visualiser les résultats
    visualize_parser = subparsers.add_parser("visualize", help="Générer des visualisations")
    visualize_parser.add_argument("--results", type=str, required=True,
                                help="Chemin vers le fichier de résultats")
    visualize_parser.add_argument("--output-dir", type=str,
                                help="Répertoire où sauvegarder les visualisations")
    
    # Commande pour comparer les résultats
    compare_parser = subparsers.add_parser("compare", help="Comparer deux benchmarks")
    compare_parser.add_argument("--results1", type=str, required=True,
                              help="Chemin vers le premier fichier de résultats")
    compare_parser.add_argument("--results2", type=str, required=True,
                              help="Chemin vers le deuxième fichier de résultats")
    compare_parser.add_argument("--output-dir", type=str,
                              help="Répertoire où sauvegarder les résultats de comparaison")
    
    # Commande pour optimiser la configuration
    optimize_parser = subparsers.add_parser("optimize", help="Optimiser la configuration")
    optimize_parser.add_argument("--results", type=str, required=True,
                               help="Chemin vers le fichier de résultats")
    optimize_parser.add_argument("--config", type=str, required=True,
                               help="Chemin vers le fichier de configuration à optimiser")
    optimize_parser.add_argument("--output-dir", type=str,
                               help="Répertoire où sauvegarder la configuration optimisée")
    
    # Commande pour générer un fichier docker-compose
    docker_parser = subparsers.add_parser("docker", help="Générer un fichier docker-compose optimisé")
    docker_parser.add_argument("--results", type=str, required=True,
                             help="Chemin vers le fichier de résultats")
    docker_parser.add_argument("--template", type=str, required=True,
                             help="Chemin vers le fichier docker-compose template")
    docker_parser.add_argument("--output-dir", type=str,
                             help="Répertoire où sauvegarder le fichier généré")
    
    args = parser.parse_args()
    
    # Exécuter la commande spécifiée
    if args.command == "analyze":
        analyze_benchmark_results(args.results, args.output_dir)
    
    elif args.command == "visualize":
        visualize_benchmark_results(args.results, args.output_dir)
    
    elif args.command == "compare":
        compare_benchmark_results(args.results1, args.results2, args.output_dir)
    
    elif args.command == "optimize":
        optimize_model_config(args.results, args.config, args.output_dir)
    
    elif args.command == "docker":
        generate_docker_compose(args.results, args.template, args.output_dir)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()