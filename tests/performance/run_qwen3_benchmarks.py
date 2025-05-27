#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script principal pour exécuter l'ensemble du processus de benchmarking
et d'optimisation des modèles Qwen3.

Ce script permet de :
1. Vérifier que les services Qwen3 sont en cours d'exécution
2. Exécuter les benchmarks avec différentes longueurs de contexte
3. Trouver le contexte maximal stable pour chaque modèle
4. Générer des configurations optimisées
5. Produire un rapport final complet

Exemple d'utilisation :
    python run_qwen3_benchmarks.py --all-models
    python run_qwen3_benchmarks.py --model medium
    python run_qwen3_benchmarks.py --quick-test
"""

import argparse
import os
import sys
import time
import json
import subprocess
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional

# Configuration des endpoints
ENDPOINTS = {
    "micro": {
        "url": "http://localhost:5000",
        "api_key": "test-key-micro",
        "model": "Qwen/Qwen3-1.7B-FP8"
    },
    "mini": {
        "url": "http://localhost:5001", 
        "api_key": "test-key-mini",
        "model": "Qwen/Qwen3-8B-AWQ"
    },
    "medium": {
        "url": "http://localhost:5002",
        "api_key": "test-key-medium", 
        "model": "Qwen/Qwen3-32B-AWQ"
    }
}

# Longueurs de contexte par défaut pour les tests rapides et complets
QUICK_TEST_CONTEXT_LENGTHS = [1000, 10000]
FULL_TEST_CONTEXT_LENGTHS = [1000, 5000, 10000, 20000, 30000, 50000, 70000]

def check_services_running() -> Dict[str, bool]:
    """
    Vérifie si les services Qwen3 sont en cours d'exécution
    """
    results = {}
    
    for model, config in ENDPOINTS.items():
        url = f"{config['url']}/v1/models"
        headers = {"Authorization": f"Bearer {config['api_key']}"}
        
        try:
            response = requests.get(url, headers=headers, timeout=5)
            results[model] = response.status_code == 200
        except Exception:
            results[model] = False
    
    return results

def run_command(command: str) -> Tuple[int, str, str]:
    """
    Exécute une commande shell et retourne le code de sortie, stdout et stderr
    """
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate()
    return process.returncode, stdout, stderr

def run_benchmark(model: Optional[str], context_lengths: List[int], find_max_context: bool, output_dir: str) -> str:
    """
    Exécute le benchmark pour un modèle spécifique ou tous les modèles
    """
    command = ["python", "tests/performance/qwen3_context_benchmark.py"]
    
    if model:
        command.extend(["--model", model])
    else:
        command.append("--all-models")
    
    if context_lengths:
        command.append("--context-lengths")
        command.append(",".join(map(str, context_lengths)))
    
    if find_max_context:
        command.append("--find-max-context")
    
    command.extend(["--output-dir", output_dir])
    
    print(f"Exécution de la commande: {' '.join(command)}")
    returncode, stdout, stderr = run_command(" ".join(command))
    
    if returncode != 0:
        print(f"Erreur lors de l'exécution du benchmark:")
        print(stderr)
        return ""
    
    # Extraire le chemin du fichier JSON des résultats
    for line in stdout.split("\n"):
        if "Résultats sauvegardés dans:" in line:
            return line.split(":", 1)[1].strip()
    
    return ""

def run_optimization(results_file: str, model: Optional[str], output_dir: str, safety_margin: float) -> str:
    """
    Exécute l'optimisation des configurations
    """
    command = ["python", "tests/performance/qwen3_optimize_config.py"]
    command.extend(["--input", results_file])
    
    if model:
        command.extend(["--model", model])
    
    command.extend(["--output-dir", output_dir])
    command.extend(["--safety-margin", str(safety_margin)])
    
    print(f"Exécution de la commande: {' '.join(command)}")
    returncode, stdout, stderr = run_command(" ".join(command))
    
    if returncode != 0:
        print(f"Erreur lors de l'exécution de l'optimisation:")
        print(stderr)
        return ""
    
    # Extraire le chemin du fichier de résumé
    for line in stdout.split("\n"):
        if "Résumé des configurations généré:" in line:
            return line.split(":", 1)[1].strip()
    
    return ""

def generate_final_report(benchmark_results: str, optimization_summary: str, output_file: str) -> bool:
    """
    Génère un rapport final combinant les résultats du benchmarking et de l'optimisation
    """
    try:
        # Charger les résultats du benchmarking
        with open(benchmark_results, 'r', encoding='utf-8') as f:
            benchmark_data = json.load(f)
        
        # Charger le résumé de l'optimisation
        with open(optimization_summary, 'r', encoding='utf-8') as f:
            optimization_content = f.read()
        
        # Générer le rapport final
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        report = f"# Rapport Final - Benchmarking et Optimisation du Contexte Maximal pour Qwen3\n\n"
        report += f"Date: {now}\n\n"
        
        # Résumé des résultats
        report += "## Résumé des résultats\n\n"
        
        # Tableau des contextes maximaux
        report += "### Contexte maximal par modèle\n\n"
        report += "| Modèle | Contexte maximal stable (tokens) | Contexte recommandé (tokens) |\n"
        report += "|--------|--------------------------------|-----------------------------|\n"
        
        for model, max_context in benchmark_data.get("max_contexts", {}).items():
            recommended = int(max_context * 0.9)  # Par défaut, 90% du maximum
            report += f"| {model.upper()} | {max_context} | {recommended} |\n"
        
        # Inclure les graphiques
        report += "\n## Graphiques de performance\n\n"
        report += "### Temps de réponse\n\n"
        report += "![Temps de réponse](./response_times.png)\n\n"
        report += "### Débit\n\n"
        report += "![Débit](./tokens_per_second.png)\n\n"
        report += "### Utilisation mémoire\n\n"
        report += "![Utilisation mémoire](./memory_usage.png)\n\n"
        
        # Inclure les configurations optimisées
        report += "\n## Configurations optimisées\n\n"
        report += optimization_content.split("# Configurations Optimisées pour Qwen3")[1]
        
        # Conclusion et recommandations
        report += "\n## Conclusion et recommandations\n\n"
        report += "### Recommandations générales\n\n"
        report += "1. **Utilisation des configurations optimisées** : Déployer les configurations optimisées pour chaque modèle afin de maximiser le contexte tout en maintenant la stabilité.\n\n"
        report += "2. **Surveillance des performances** : Surveiller régulièrement l'utilisation mémoire GPU et les performances des modèles pour détecter d'éventuels problèmes.\n\n"
        report += "3. **Tests périodiques** : Effectuer des tests périodiques avec différentes longueurs de contexte pour s'assurer que les performances restent stables.\n\n"
        report += "4. **Mise à jour des configurations** : Ajuster les configurations en fonction des mises à jour de vLLM et des modèles Qwen3.\n\n"
        
        report += "### Prochaines étapes\n\n"
        report += "1. **Tests en production** : Tester les configurations optimisées en environnement de production avec des charges réelles.\n\n"
        report += "2. **Optimisation fine** : Affiner les paramètres en fonction des retours d'expérience en production.\n\n"
        report += "3. **Exploration de techniques avancées** : Tester des techniques comme le speculative decoding pour améliorer davantage les performances.\n\n"
        
        # Écrire le rapport dans un fichier
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        return True
    except Exception as e:
        print(f"Erreur lors de la génération du rapport final: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Exécution complète du benchmarking et de l'optimisation des modèles Qwen3")
    parser.add_argument("--model", type=str, choices=["micro", "mini", "medium"], help="Modèle à tester (par défaut: tous)")
    parser.add_argument("--all-models", action="store_true", help="Tester tous les modèles")
    parser.add_argument("--quick-test", action="store_true", help="Exécuter un test rapide avec moins de longueurs de contexte")
    parser.add_argument("--skip-max-context", action="store_true", help="Ne pas rechercher le contexte maximal")
    parser.add_argument("--safety-margin", type=float, default=0.9, help="Marge de sécurité pour le contexte maximal (0.0-1.0)")
    parser.add_argument("--output-dir", type=str, default="results", help="Répertoire de sortie pour les résultats")
    args = parser.parse_args()
    
    # Vérifier les arguments
    if not args.model and not args.all_models:
        parser.error("Vous devez spécifier un modèle (--model) ou utiliser --all-models")
    
    # Créer le répertoire de sortie
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(args.output_dir, f"qwen3_benchmark_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)
    
    # Vérifier que les services sont en cours d'exécution
    print("Vérification des services Qwen3...")
    services_status = check_services_running()
    
    all_running = all(services_status.values())
    if not all_running:
        print("Attention: Certains services Qwen3 ne sont pas en cours d'exécution:")
        for model, running in services_status.items():
            status = "✓ En cours d'exécution" if running else "✗ Non disponible"
            print(f"  - {model.upper()}: {status}")
        
        if args.model and not services_status.get(args.model, False):
            print(f"Le modèle {args.model} n'est pas disponible. Impossible de continuer.")
            return
    else:
        print("Tous les services Qwen3 sont en cours d'exécution.")
    
    # Déterminer les modèles à tester
    models_to_test = []
    if args.model:
        if services_status.get(args.model, False):
            models_to_test.append(args.model)
    elif args.all_models:
        for model, running in services_status.items():
            if running:
                models_to_test.append(model)
    
    if not models_to_test:
        print("Aucun modèle disponible à tester. Veuillez démarrer les services Qwen3.")
        return
    
    print(f"Modèles à tester: {', '.join(model.upper() for model in models_to_test)}")
    
    # Déterminer les longueurs de contexte à tester
    context_lengths = QUICK_TEST_CONTEXT_LENGTHS if args.quick_test else FULL_TEST_CONTEXT_LENGTHS
    print(f"Longueurs de contexte à tester: {', '.join(map(str, context_lengths))}")
    
    # Exécuter le benchmark
    print("\n=== EXÉCUTION DU BENCHMARK ===")
    find_max_context = not args.skip_max_context
    
    if args.model:
        benchmark_results = run_benchmark(args.model, context_lengths, find_max_context, output_dir)
    else:
        benchmark_results = run_benchmark(None, context_lengths, find_max_context, output_dir)
    
    if not benchmark_results:
        print("Échec du benchmark. Impossible de continuer.")
        return
    
    print(f"Résultats du benchmark sauvegardés dans: {benchmark_results}")
    
    # Exécuter l'optimisation
    print("\n=== EXÉCUTION DE L'OPTIMISATION ===")
    optimization_dir = os.path.join(output_dir, "optimized_configs")
    
    if args.model:
        optimization_summary = run_optimization(benchmark_results, args.model, optimization_dir, args.safety_margin)
    else:
        optimization_summary = run_optimization(benchmark_results, None, optimization_dir, args.safety_margin)
    
    if not optimization_summary:
        print("Échec de l'optimisation. Impossible de continuer.")
        return
    
    print(f"Résumé de l'optimisation sauvegardé dans: {optimization_summary}")
    
    # Générer le rapport final
    print("\n=== GÉNÉRATION DU RAPPORT FINAL ===")
    final_report = os.path.join(output_dir, "qwen3_final_report.md")
    
    if generate_final_report(benchmark_results, optimization_summary, final_report):
        print(f"Rapport final généré: {final_report}")
    else:
        print("Échec de la génération du rapport final.")
    
    print("\n=== BENCHMARKING ET OPTIMISATION TERMINÉS ===")
    print(f"Tous les résultats sont disponibles dans: {output_dir}")

if __name__ == "__main__":
    main()