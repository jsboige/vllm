#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour optimiser les configurations des modèles Qwen3
en fonction des résultats du benchmarking.

Ce script permet de :
1. Analyser les résultats du benchmarking
2. Générer des configurations optimisées pour chaque modèle
3. Tester les configurations optimisées
4. Générer des fichiers docker-compose optimisés

Exemple d'utilisation :
    python qwen3_optimize_config.py --input results/qwen3_context_benchmark_20250527_145523.json
    python qwen3_optimize_config.py --input results/qwen3_context_benchmark_20250527_145523.json --model medium
    python qwen3_optimize_config.py --input results/qwen3_context_benchmark_20250527_145523.json --safety-margin 0.85
"""

import argparse
import json
import os
import time
import yaml
import copy
import re
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime

# Configuration des endpoints
ENDPOINTS = {
    "micro": {
        "url": "http://localhost:5000",
        "api_key": "test-key-micro",
        "model": "Qwen/Qwen3-1.7B-FP8",
        "gpu_id": "2"
    },
    "mini": {
        "url": "http://localhost:5001", 
        "api_key": "test-key-mini",
        "model": "Qwen/Qwen3-8B-AWQ",
        "gpu_id": "1"
    },
    "medium": {
        "url": "http://localhost:5002",
        "api_key": "test-key-medium", 
        "model": "Qwen/Qwen3-32B-AWQ",
        "gpu_id": "0,1"
    }
}

# Modèles de configuration Docker Compose
DOCKER_COMPOSE_TEMPLATES = {
    "micro": "vllm-configs/docker-compose/docker-compose-micro-qwen3-optimized.yml",
    "mini": "vllm-configs/docker-compose/docker-compose-mini-qwen3-optimized.yml",
    "medium": "vllm-configs/docker-compose/docker-compose-medium-qwen3-optimized.yml"
}

def load_benchmark_results(input_file: str) -> Dict[str, Any]:
    """
    Charge les résultats du benchmarking à partir d'un fichier JSON
    """
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Erreur lors du chargement des résultats: {e}")
        return {}

def analyze_results(results: Dict[str, Any], model: str, safety_margin: float = 0.9) -> Dict[str, Any]:
    """
    Analyse les résultats du benchmarking pour un modèle spécifique
    et génère des recommandations de configuration
    """
    if model not in results.get("max_contexts", {}):
        print(f"Aucun résultat de contexte maximal trouvé pour le modèle {model}")
        return {}
    
    max_context = results["max_contexts"][model]
    model_results = results.get("results", {}).get(model, [])
    
    # Calculer le contexte recommandé avec une marge de sécurité
    recommended_context = int(max_context * safety_margin)
    
    # Trouver les performances pour le contexte le plus proche du recommandé
    closest_result = None
    min_diff = float('inf')
    
    for result in model_results:
        diff = abs(result["context_length"] - recommended_context)
        if diff < min_diff:
            min_diff = diff
            closest_result = result
    
    # Déterminer les paramètres optimaux de RoPE scaling
    # Par défaut, nous utilisons yarn avec un facteur de 4.0
    rope_scaling = {
        "rope_type": "yarn",
        "factor": 4.0,
        "original_max_position_embeddings": 32768
    }
    
    # Si le contexte recommandé est supérieur à 65536, augmenter le facteur
    if recommended_context > 65536:
        rope_scaling["factor"] = 8.0
    
    # Déterminer l'utilisation mémoire GPU optimale
    gpu_memory_utilization = 0.95  # Par défaut
    
    if closest_result and "avg_memory_usage_percent" in closest_result:
        memory_usage = closest_result["avg_memory_usage_percent"] / 100
        # Ajouter une petite marge pour éviter les OOM
        gpu_memory_utilization = min(0.99, memory_usage + 0.05)
    
    # Générer les recommandations
    recommendations = {
        "model": model,
        "max_context": max_context,
        "recommended_context": recommended_context,
        "config": {
            "max_model_len": recommended_context,
            "max_num_batched_tokens": recommended_context,
            "gpu_memory_utilization": round(gpu_memory_utilization, 2),
            "rope_scaling": rope_scaling,
            "kv_cache_dtype": "fp8",
            "enable_chunked_prefill": True,
            "enable_prefix_caching": True
        },
        "performance": closest_result if closest_result else {}
    }
    
    return recommendations

def generate_docker_compose(template_path: str, recommendations: Dict[str, Any], output_path: str) -> bool:
    """
    Génère un fichier docker-compose optimisé à partir d'un template
    et des recommandations
    """
    try:
        # Lire le template
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Remplacer les paramètres
        config = recommendations["config"]
        
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
        rope_config = json.dumps(config["rope_scaling"]).replace('"', '\\"')
        content = re.sub(
            r'--rope-scaling \'.*?\'',
            f'--rope-scaling \'{rope_config}\'',
            content
        )
        
        # Écrire le fichier optimisé
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return True
    except Exception as e:
        print(f"Erreur lors de la génération du fichier docker-compose: {e}")
        return False

def generate_config_file(recommendations: Dict[str, Any], output_path: str) -> bool:
    """
    Génère un fichier de configuration YAML avec les paramètres optimisés
    """
    try:
        config = {
            "model": recommendations["model"],
            "max_context": recommendations["max_context"],
            "recommended_context": recommendations["recommended_context"],
            "parameters": recommendations["config"],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "notes": "Configuration optimisée générée automatiquement"
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        
        return True
    except Exception as e:
        print(f"Erreur lors de la génération du fichier de configuration: {e}")
        return False

def generate_markdown_summary(recommendations_list: List[Dict[str, Any]], output_path: str) -> bool:
    """
    Génère un résumé au format markdown des configurations optimisées
    """
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        md = f"# Configurations Optimisées pour Qwen3\n\n"
        md += f"Date: {now}\n\n"
        
        # Tableau récapitulatif
        md += "## Résumé des configurations\n\n"
        md += "| Modèle | Contexte maximal | Contexte recommandé | Utilisation mémoire |\n"
        md += "|--------|-----------------|--------------------|--------------------|n"
        
        for rec in recommendations_list:
            model = rec["model"].upper()
            max_context = rec["max_context"]
            recommended_context = rec["recommended_context"]
            gpu_memory = rec["config"]["gpu_memory_utilization"] * 100
            
            md += f"| {model} | {max_context} | {recommended_context} | {gpu_memory:.0f}% |\n"
        
        # Détails par modèle
        for rec in recommendations_list:
            model = rec["model"].upper()
            md += f"\n## Configuration pour {model}\n\n"
            
            md += "```yaml\n"
            md += f"max_model_len: {rec['config']['max_model_len']}\n"
            md += f"max_num_batched_tokens: {rec['config']['max_num_batched_tokens']}\n"
            md += f"gpu_memory_utilization: {rec['config']['gpu_memory_utilization']}\n"
            md += f"rope_scaling: {json.dumps(rec['config']['rope_scaling'], indent=2)}\n"
            md += f"kv_cache_dtype: {rec['config']['kv_cache_dtype']}\n"
            md += f"enable_chunked_prefill: {rec['config']['enable_chunked_prefill']}\n"
            md += f"enable_prefix_caching: {rec['config']['enable_prefix_caching']}\n"
            md += "```\n\n"
            
            # Commande Docker Compose
            md += "### Commande de démarrage\n\n"
            md += "```bash\n"
            md += f"docker-compose -f docker-compose-{rec['model']}-qwen3-optimized-max-context.yml up -d\n"
            md += "```\n\n"
        
        # Notes d'implémentation
        md += "\n## Notes d'implémentation\n\n"
        md += "- Les configurations ci-dessus ont été optimisées pour maximiser le contexte tout en maintenant la stabilité.\n"
        md += "- Une marge de sécurité a été appliquée pour éviter les erreurs OOM (Out of Memory).\n"
        md += "- Les paramètres RoPE ont été ajustés pour supporter les longs contextes.\n"
        md += "- L'utilisation du cache KV en fp8 permet d'économiser de la mémoire GPU.\n"
        md += "- L'activation de chunked_prefill et prefix_caching améliore les performances avec les longs contextes.\n"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md)
        
        return True
    except Exception as e:
        print(f"Erreur lors de la génération du résumé markdown: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Optimisation des configurations Qwen3 basée sur les résultats de benchmarking")
    parser.add_argument("--input", type=str, required=True, help="Fichier JSON contenant les résultats du benchmarking")
    parser.add_argument("--model", type=str, choices=["micro", "mini", "medium"], help="Modèle à optimiser (par défaut: tous)")
    parser.add_argument("--output-dir", type=str, default="optimized_configs", help="Répertoire de sortie pour les configurations")
    parser.add_argument("--safety-margin", type=float, default=0.9, help="Marge de sécurité pour le contexte maximal (0.0-1.0)")
    args = parser.parse_args()
    
    # Charger les résultats
    results = load_benchmark_results(args.input)
    if not results:
        print("Impossible de continuer sans résultats valides.")
        return
    
    # Déterminer les modèles à optimiser
    models_to_optimize = [args.model] if args.model else ["micro", "mini", "medium"]
    
    # Créer le répertoire de sortie
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Générer les recommandations et les fichiers de configuration
    all_recommendations = []
    
    for model in models_to_optimize:
        if model in results.get("max_contexts", {}):
            print(f"\n=== Optimisation de la configuration pour {model.upper()} ===")
            
            # Analyser les résultats et générer des recommandations
            recommendations = analyze_results(results, model, args.safety_margin)
            if not recommendations:
                print(f"Impossible de générer des recommandations pour {model}")
                continue
            
            all_recommendations.append(recommendations)
            
            # Afficher les recommandations
            print(f"Contexte maximal: {recommendations['max_context']} tokens")
            print(f"Contexte recommandé: {recommendations['recommended_context']} tokens")
            print(f"Utilisation mémoire GPU: {recommendations['config']['gpu_memory_utilization'] * 100:.0f}%")
            print(f"Configuration RoPE: {json.dumps(recommendations['config']['rope_scaling'])}")
            
            # Générer le fichier de configuration YAML
            config_file = os.path.join(args.output_dir, f"qwen3_{model}_optimized_config.yaml")
            if generate_config_file(recommendations, config_file):
                print(f"Configuration YAML générée: {config_file}")
            
            # Générer le fichier docker-compose
            if model in DOCKER_COMPOSE_TEMPLATES:
                template_path = DOCKER_COMPOSE_TEMPLATES[model]
                if os.path.exists(template_path):
                    docker_file = os.path.join(args.output_dir, f"docker-compose-{model}-qwen3-optimized-max-context.yml")
                    if generate_docker_compose(template_path, recommendations, docker_file):
                        print(f"Fichier docker-compose généré: {docker_file}")
                else:
                    print(f"Template docker-compose introuvable: {template_path}")
        else:
            print(f"Aucun résultat de contexte maximal trouvé pour {model}")
    
    # Générer le résumé markdown
    if all_recommendations:
        summary_file = os.path.join(args.output_dir, "qwen3_optimized_configs_summary.md")
        if generate_markdown_summary(all_recommendations, summary_file):
            print(f"\nRésumé des configurations généré: {summary_file}")

if __name__ == "__main__":
    main()