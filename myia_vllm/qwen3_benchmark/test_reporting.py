#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de test pour démontrer l'utilisation du module de reporting Qwen3.

Ce script montre comment utiliser les différentes fonctionnalités du module
pour générer des rapports standardisés à partir des résultats des benchmarks.
"""

import os
import sys
import json
import argparse
import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

# Ajouter le répertoire parent au PYTHONPATH pour importer les modules qwen3_benchmark
current_dir = Path(__file__).resolve().parent
sys.path.append(str(current_dir.parent))

from qwen3_benchmark.config import load_config, get_output_paths
from qwen3_benchmark.reporting import (
    ReportGenerator,
    generate_markdown_report,
    generate_html_report,
    generate_pdf_report,
    export_report
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


def create_sample_results(model_name: str = "QWEN3-MEDIUM") -> Dict[str, Any]:
    """
    Crée un exemple de résultats de benchmark pour les tests.
    
    Args:
        model_name (str): Nom du modèle
        
    Returns:
        Dict[str, Any]: Exemple de résultats de benchmark
    """
    return {
        "model": model_name,
        "timestamp": datetime.datetime.now().isoformat(),
        "version": "0.1.0",
        "environment": "Test Environment",
        "execution_time": 123.45,
        "metrics": {
            "llm_metrics": {
                "tokens_per_second": 150.75,
                "latency_p50": 0.8,
                "latency_p90": 1.2,
                "latency_p99": 1.5,
                "throughput": 1000,
                "accuracy": 0.95,
                "recommended_batch_size": 16,
                "recommended_context_length": 8192,
                "overall_performance_score": 8.5
            },
            "resource_metrics": {
                "gpu_utilization_avg": 75.5,
                "gpu_memory_used_avg": 8192,
                "cpu_utilization_avg": 45.0,
                "recommended_memory": 16384
            }
        },
        "api_results": {
            "completions": [
                {"execution_time": 10.5, "tokens_generated": 1000},
                {"execution_time": 12.0, "tokens_generated": 1200}
            ],
            "chat": [
                {"execution_time": 15.2, "tokens_generated": 1500},
                {"execution_time": 18.7, "tokens_generated": 1800}
            ]
        },
        "context_results": {
            "4096": [
                {"execution_time": 20.0, "tokens_generated": 2000},
                {"execution_time": 22.5, "tokens_generated": 2200}
            ],
            "8192": [
                {"execution_time": 30.5, "tokens_generated": 3000},
                {"execution_time": 33.0, "tokens_generated": 3200}
            ]
        },
        "resource_usage": {
            "gpu": {
                "timestamps": ["t1", "t2", "t3"],
                "utilization": [70, 75, 80]
            },
            "memory": {
                "timestamps": ["t1", "t2", "t3"],
                "usage": [8000, 8192, 8200]
            }
        }
    }


def test_report_generation(results: Dict[str, Any], output_dir: str):
    """
    Teste la génération de rapports dans différents formats.
    
    Args:
        results (Dict[str, Any]): Résultats du benchmark
        output_dir (str): Répertoire où sauvegarder les rapports
    """
    print(f"\n=== Test de la génération de rapports ===")
    model_name = results.get("model", "unknown").lower()
    
    # Créer le répertoire de sortie
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Générer un rapport Markdown
    print("\nGénération du rapport Markdown...")
    md_path = os.path.join(output_dir, f"{model_name}_report.md")
    generate_markdown_report(results, output_path=md_path)
    print(f"Rapport Markdown sauvegardé dans {md_path}")
    
    # 2. Générer un rapport HTML
    print("\nGénération du rapport HTML...")
    html_path = os.path.join(output_dir, f"{model_name}_report.html")
    generate_html_report(results, output_path=html_path)
    print(f"Rapport HTML sauvegardé dans {html_path}")
    
    # 3. Générer un rapport PDF (nécessite weasyprint)
    try:
        print("\nGénération du rapport PDF...")
        pdf_path = os.path.join(output_dir, f"{model_name}_report.pdf")
        generate_pdf_report(results, output_path=pdf_path)
        print(f"Rapport PDF sauvegardé dans {pdf_path}")
    except ImportError as e:
        print(f"Impossible de générer le rapport PDF: {e}")
    except Exception as e:
        print(f"Erreur inattendue lors de la génération du PDF: {e}")

    # 4. Utiliser la fonction d'export générique
    print("\nTest de la fonction d'export générique...")
    export_report(results, format='md', output_path=os.path.join(output_dir, f"{model_name}_export.md"))
    export_report(results, format='html', output_path=os.path.join(output_dir, f"{model_name}_export.html"))
    try:
        export_report(results, format='pdf', output_path=os.path.join(output_dir, f"{model_name}_export.pdf"))
    except ImportError:
        print("Export PDF sauté (weasyprint non installé).")
    except Exception as e:
        print(f"Erreur inattendue lors de l'export PDF: {e}")
        
    print("\nTests de génération de rapports terminés.")


def main():
    """
    Fonction principale pour exécuter les tests de reporting depuis la ligne de commande.
    """
    parser = argparse.ArgumentParser(description="Tester le module de reporting Qwen3")
    
    parser.add_argument("--results-file", type=str,
                        help="Chemin vers un fichier de résultats JSON à utiliser pour les tests")
    parser.add_argument("--output-dir", type=str,
                        help="Répertoire où sauvegarder les rapports générés")
    parser.add_argument("--model-name", type=str, default="QWEN3-MEDIUM",
                        help="Nom du modèle à utiliser pour les résultats d'exemple")
    
    args = parser.parse_args()
    
    # Charger la configuration globale
    config = load_config()
    
    # Déterminer le répertoire de sortie
    if args.output_dir:
        output_dir = args.output_dir
    else:
        paths = get_output_paths()
        output_dir = os.path.join(paths.get("reports_dir", "reports"), "test_reports")
        
    print(f"Les rapports de test seront sauvegardés dans: {output_dir}")
    
    # Charger les résultats ou créer un exemple
    if args.results_file:
        print(f"Chargement des résultats depuis: {args.results_file}")
        results = load_benchmark_results(args.results_file)
        if not results:
            print("Impossible de charger les résultats, utilisation d'un exemple.")
            results = create_sample_results(args.model_name)
    else:
        print("Utilisation de résultats d'exemple.")
        results = create_sample_results(args.model_name)
        
    # Exécuter les tests de génération de rapports
    test_report_generation(results, output_dir)


if __name__ == "__main__":
    main()