#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de benchmarking pour tester les performances des modèles Qwen3
avec différentes longueurs de contexte.

Ce script permet de :
1. Tester différentes longueurs de contexte (1k, 5k, 10k, 20k, 30k, 50k, 70k, 100k tokens)
2. Mesurer la latence, le débit, l'utilisation mémoire et la qualité des réponses
3. Déterminer le contexte maximal stable pour chaque modèle
4. Générer des rapports détaillés avec graphiques

Exemple d'utilisation :
    python qwen3_context_benchmark.py --model micro --context-lengths 1000,5000,10000,20000
    python qwen3_context_benchmark.py --model mini --context-lengths 1000,5000,10000,20000,30000,50000
    python qwen3_context_benchmark.py --model medium --context-lengths 1000,5000,10000,20000,30000,50000,70000
    python qwen3_context_benchmark.py --all-models --find-max-context
"""

import argparse
import json
import os
import time
import statistics
import subprocess
import platform
import sys
import requests
import matplotlib.pyplot as plt
import numpy as np
from typing import Dict, Any, List, Tuple, Optional, Union
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

# Longueurs de contexte par défaut à tester
DEFAULT_CONTEXT_LENGTHS = [1000, 5000, 10000, 20000, 30000, 50000, 70000]

# Nombre d'itérations pour chaque test
NUM_ITERATIONS = 3

def get_gpu_memory_usage(gpu_id: str) -> Dict[str, float]:
    """
    Récupère l'utilisation mémoire du GPU spécifié
    Retourne un dictionnaire avec total, used et free en MB
    """
    try:
        if platform.system() == "Windows":
            # Sur Windows, utiliser nvidia-smi avec des options spécifiques
            cmd = f'nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv,noheader,nounits -i {gpu_id}'
        else:
            # Sur Linux/autres, commande standard
            cmd = f'nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv,noheader,nounits -i {gpu_id}'
        
        output = subprocess.check_output(cmd, shell=True).decode('utf-8').strip()
        
        # Si plusieurs GPUs sont spécifiés, prendre la moyenne
        if ',' in gpu_id:
            total_mem = 0
            used_mem = 0
            free_mem = 0
            count = 0
            
            for line in output.split('\n'):
                if line.strip():
                    mem_total, mem_used, mem_free = map(int, line.split(','))
                    total_mem += mem_total
                    used_mem += mem_used
                    free_mem += mem_free
                    count += 1
            
            if count > 0:
                return {
                    "total_mb": total_mem / count,
                    "used_mb": used_mem / count,
                    "free_mb": free_mem / count,
                    "utilization_percent": (used_mem / total_mem) * 100 if total_mem > 0 else 0
                }
        else:
            # Un seul GPU
            mem_total, mem_used, mem_free = map(int, output.split(','))
            return {
                "total_mb": mem_total,
                "used_mb": mem_used,
                "free_mb": mem_free,
                "utilization_percent": (mem_used / mem_total) * 100 if mem_total > 0 else 0
            }
    except Exception as e:
        print(f"Erreur lors de la récupération de l'utilisation mémoire GPU: {e}")
        return {
            "total_mb": 0,
            "used_mb": 0,
            "free_mb": 0,
            "utilization_percent": 0,
            "error": str(e)
        }

def generate_context(length: int) -> str:
    """
    Génère un contexte de la longueur spécifiée (approximative en tokens)
    """
    # En moyenne, un token correspond à environ 4 caractères en français
    chars_per_token = 4
    
    # Générer un texte avec des phrases de longueur variable
    sentences = [
        "Ceci est une phrase courte. ",
        "Voici une phrase un peu plus longue avec quelques mots supplémentaires. ",
        "Cette phrase contient encore plus de mots pour augmenter la variabilité du texte généré et éviter la répétition. ",
        "Dans ce test de performance, nous cherchons à évaluer les capacités des modèles Qwen3 avec différentes longueurs de contexte. "
    ]
    
    # Calculer le nombre approximatif de caractères nécessaires
    target_chars = length * chars_per_token
    
    # Générer le texte
    result = ""
    while len(result) < target_chars:
        for sentence in sentences:
            result += sentence
            if len(result) >= target_chars:
                break
    
    # Ajouter une question à la fin pour que le modèle ait quelque chose à répondre
    result += "\n\nRésumez ce texte en quelques phrases."
    
    return result

def test_chat_completion(config: Dict[str, str], context_length: int, gpu_id: str) -> Dict[str, Any]:
    """
    Teste l'endpoint /v1/chat/completions avec un contexte de longueur spécifique
    """
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }
    
    # Générer un contexte de la longueur spécifiée
    context = generate_context(context_length)
    
    chat_data = {
        "model": config["model"],
        "messages": [
            {"role": "user", "content": context}
        ],
        "max_tokens": 100,
        "temperature": 0.7
    }
    
    # Mesurer l'utilisation mémoire avant
    mem_before = get_gpu_memory_usage(gpu_id)
    
    try:
        start_time = time.time()
        
        response = requests.post(
            f"{config['url']}/v1/chat/completions",
            headers=headers,
            json=chat_data,
            timeout=120  # Timeout plus long pour les longs contextes
        )
        
        end_time = time.time()
        response_time = (end_time - start_time) * 1000  # en ms
        
        # Mesurer l'utilisation mémoire après
        mem_after = get_gpu_memory_usage(gpu_id)
        
        if response.status_code == 200:
            data = response.json()
            usage = data.get("usage", {})
            
            # Extraire le contenu de la réponse
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            result = {
                "status": "success",
                "response_time_ms": round(response_time, 2),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "content": content,
                "memory_before": mem_before,
                "memory_after": mem_after,
                "memory_increase_mb": mem_after.get("used_mb", 0) - mem_before.get("used_mb", 0)
            }
            
            if usage.get("completion_tokens", 0) > 0 and response_time > 0:
                tokens_per_second = (usage["completion_tokens"] / response_time) * 1000
                result["tokens_per_second"] = round(tokens_per_second, 2)
            
            return result
        else:
            return {
                "status": "failed",
                "error": f"HTTP {response.status_code}",
                "response_time_ms": round(response_time, 2),
                "memory_before": mem_before,
                "memory_after": mem_after
            }
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
            "memory_before": mem_before
        }

def test_context_length(model_name: str, config: Dict[str, str], context_length: int) -> Dict[str, Any]:
    """
    Teste un modèle avec une longueur de contexte spécifique
    """
    print(f"\n=== Test de {model_name.upper()} avec contexte de {context_length} tokens ===")
    
    results = {
        "model": model_name,
        "context_length": context_length,
        "iterations": []
    }
    
    all_response_times = []
    all_tokens_per_second = []
    all_memory_usage = []
    
    for i in range(NUM_ITERATIONS):
        print(f"  Itération {i+1}/{NUM_ITERATIONS}...", end="", flush=True)
        
        result = test_chat_completion(config, context_length, config["gpu_id"])
        results["iterations"].append(result)
        
        if result["status"] == "success":
            all_response_times.append(result["response_time_ms"])
            if "tokens_per_second" in result:
                all_tokens_per_second.append(result["tokens_per_second"])
            if "memory_after" in result:
                all_memory_usage.append(result["memory_after"].get("utilization_percent", 0))
            print(f" {result['response_time_ms']:.0f}ms, {result.get('tokens_per_second', 0):.1f} tokens/s")
        else:
            print(f" ÉCHEC ({result.get('error', 'Erreur inconnue')})")
    
    # Calcul des statistiques
    if all_response_times:
        results["avg_response_time_ms"] = round(statistics.mean(all_response_times), 2)
        results["min_response_time_ms"] = round(min(all_response_times), 2)
        results["max_response_time_ms"] = round(max(all_response_times), 2)
        
        if all_tokens_per_second:
            results["avg_tokens_per_second"] = round(statistics.mean(all_tokens_per_second), 2)
            results["min_tokens_per_second"] = round(min(all_tokens_per_second), 2)
            results["max_tokens_per_second"] = round(max(all_tokens_per_second), 2)
        
        if all_memory_usage:
            results["avg_memory_usage_percent"] = round(statistics.mean(all_memory_usage), 2)
    
    # Affichage du résumé
    print(f"\n  Résumé:")
    if "avg_response_time_ms" in results:
        print(f"    Temps de réponse moyen: {results['avg_response_time_ms']:.0f}ms")
    if "avg_tokens_per_second" in results:
        print(f"    Débit moyen: {results['avg_tokens_per_second']:.1f} tokens/s")
    if "avg_memory_usage_percent" in results:
        print(f"    Utilisation mémoire moyenne: {results['avg_memory_usage_percent']:.1f}%")
    
    return results

def find_max_context(model_name: str, config: Dict[str, str], start_length: int = 10000, step: int = 10000, max_attempts: int = 10) -> int:
    """
    Trouve la longueur de contexte maximale stable pour un modèle
    en augmentant progressivement la longueur jusqu'à ce qu'une erreur se produise
    """
    print(f"\n=== Recherche du contexte maximal pour {model_name.upper()} ===")
    
    current_length = start_length
    max_stable_length = 0
    
    for attempt in range(max_attempts):
        print(f"  Test avec contexte de {current_length} tokens...")
        
        result = test_chat_completion(config, current_length, config["gpu_id"])
        
        if result["status"] == "success":
            print(f"  ✓ Succès avec {current_length} tokens")
            max_stable_length = current_length
            current_length += step
        else:
            print(f"  ✗ Échec avec {current_length} tokens: {result.get('error', 'Erreur inconnue')}")
            # Si on a échoué au premier essai, réduire le pas et recommencer
            if attempt == 0:
                current_length = start_length // 2
                step = step // 2
            else:
                # Sinon, faire une recherche binaire pour affiner le résultat
                binary_step = step // 2
                if binary_step > 1000:  # Continuer la recherche binaire si le pas est assez grand
                    test_length = max_stable_length + binary_step
                    print(f"  Test binaire avec contexte de {test_length} tokens...")
                    result = test_chat_completion(config, test_length, config["gpu_id"])
                    if result["status"] == "success":
                        max_stable_length = test_length
                break
    
    print(f"\n=== Contexte maximal stable pour {model_name.upper()}: {max_stable_length} tokens ===")
    return max_stable_length

def generate_plots(results: Dict[str, List[Dict[str, Any]]], output_dir: str):
    """
    Génère des graphiques à partir des résultats
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Préparer les données pour les graphiques
    models = list(results.keys())
    context_lengths = {}
    response_times = {}
    tokens_per_second = {}
    memory_usage = {}
    
    for model in models:
        context_lengths[model] = []
        response_times[model] = []
        tokens_per_second[model] = []
        memory_usage[model] = []
        
        for result in results[model]:
            context_lengths[model].append(result["context_length"])
            response_times[model].append(result.get("avg_response_time_ms", 0))
            tokens_per_second[model].append(result.get("avg_tokens_per_second", 0))
            memory_usage[model].append(result.get("avg_memory_usage_percent", 0))
    
    # Graphique des temps de réponse
    plt.figure(figsize=(12, 8))
    for model in models:
        plt.plot(context_lengths[model], response_times[model], marker='o', label=model)
    plt.xlabel('Longueur de contexte (tokens)')
    plt.ylabel('Temps de réponse moyen (ms)')
    plt.title('Temps de réponse en fonction de la longueur de contexte')
    plt.grid(True)
    plt.legend()
    plt.savefig(os.path.join(output_dir, 'response_times.png'))
    
    # Graphique des débits
    plt.figure(figsize=(12, 8))
    for model in models:
        plt.plot(context_lengths[model], tokens_per_second[model], marker='o', label=model)
    plt.xlabel('Longueur de contexte (tokens)')
    plt.ylabel('Débit moyen (tokens/s)')
    plt.title('Débit en fonction de la longueur de contexte')
    plt.grid(True)
    plt.legend()
    plt.savefig(os.path.join(output_dir, 'tokens_per_second.png'))
    
    # Graphique de l'utilisation mémoire
    plt.figure(figsize=(12, 8))
    for model in models:
        plt.plot(context_lengths[model], memory_usage[model], marker='o', label=model)
    plt.xlabel('Longueur de contexte (tokens)')
    plt.ylabel('Utilisation mémoire moyenne (%)')
    plt.title('Utilisation mémoire en fonction de la longueur de contexte')
    plt.grid(True)
    plt.legend()
    plt.savefig(os.path.join(output_dir, 'memory_usage.png'))

def generate_markdown_report(results: Dict[str, List[Dict[str, Any]]], max_contexts: Dict[str, int], output_file: str):
    """
    Génère un rapport au format markdown
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    md = f"# Rapport de Benchmarking Qwen3 - Contexte Maximal\n\n"
    md += f"Date: {now}\n\n"
    
    # Résumé des contextes maximaux
    md += "## Contexte maximal par modèle\n\n"
    md += "| Modèle | Contexte maximal stable (tokens) |\n"
    md += "|--------|--------------------------------|\n"
    
    for model, max_context in max_contexts.items():
        md += f"| {model.upper()} | {max_context} |\n"
    
    # Résultats détaillés par modèle
    for model, model_results in results.items():
        md += f"\n## Résultats détaillés pour {model.upper()}\n\n"
        
        # Tableau des performances
        md += "| Longueur de contexte | Temps de réponse (ms) | Débit (tokens/s) | Utilisation mémoire (%) |\n"
        md += "|----------------------|----------------------|-----------------|------------------------|\n"
        
        for result in model_results:
            context_length = result["context_length"]
            response_time = result.get("avg_response_time_ms", "N/A")
            tokens_per_second = result.get("avg_tokens_per_second", "N/A")
            memory_usage = result.get("avg_memory_usage_percent", "N/A")
            
            md += f"| {context_length} | {response_time} | {tokens_per_second} | {memory_usage} |\n"
    
    # Méthodologie
    md += "\n## Méthodologie\n\n"
    md += f"- **Nombre d'itérations par test**: {NUM_ITERATIONS}\n"
    md += "- **Métriques mesurées**:\n"
    md += "  - Latence (temps de réponse en ms)\n"
    md += "  - Débit (tokens générés par seconde)\n"
    md += "  - Utilisation mémoire GPU\n"
    
    # Recommandations
    md += "\n## Recommandations\n\n"
    
    for model, max_context in max_contexts.items():
        md += f"### {model.upper()}\n\n"
        md += f"- **Contexte maximal recommandé**: {int(max_context * 0.9)} tokens (90% du maximum stable)\n"
        md += f"- **Configuration recommandée**:\n"
        md += "```yaml\n"
        md += f"--max-model-len {int(max_context * 0.9)}\n"
        md += f"--max-num-batched-tokens {int(max_context * 0.9)}\n"
        md += "--rope-scaling '{\"rope_type\":\"yarn\",\"factor\":4.0,\"original_max_position_embeddings\":32768}'\n"
        md += "--kv_cache_dtype fp8\n"
        md += "```\n\n"
    
    # Écrire le rapport dans un fichier
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(md)

def main():
    parser = argparse.ArgumentParser(description="Benchmark des modèles Qwen3 avec différentes longueurs de contexte")
    parser.add_argument("--model", type=str, choices=["micro", "mini", "medium"], help="Modèle à tester")
    parser.add_argument("--all-models", action="store_true", help="Tester tous les modèles")
    parser.add_argument("--context-lengths", type=str, help="Longueurs de contexte à tester, séparées par des virgules (ex: 1000,5000,10000)")
    parser.add_argument("--find-max-context", action="store_true", help="Trouver le contexte maximal stable pour chaque modèle")
    parser.add_argument("--output-dir", type=str, default="results", help="Répertoire de sortie pour les résultats")
    args = parser.parse_args()
    
    # Vérifier les arguments
    if not args.model and not args.all_models:
        parser.error("Vous devez spécifier un modèle (--model) ou utiliser --all-models")
    
    # Déterminer les modèles à tester
    models_to_test = list(ENDPOINTS.keys()) if args.all_models else [args.model]
    
    # Déterminer les longueurs de contexte à tester
    if args.context_lengths:
        context_lengths = [int(length) for length in args.context_lengths.split(",")]
    else:
        context_lengths = DEFAULT_CONTEXT_LENGTHS
    
    # Créer le répertoire de sortie
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Exécuter les tests
    results = {}
    max_contexts = {}
    
    for model in models_to_test:
        print(f"\n=== BENCHMARKING DE {model.upper()} ===")
        
        config = ENDPOINTS[model]
        model_results = []
        
        # Trouver le contexte maximal si demandé
        if args.find_max_context:
            max_context = find_max_context(model, config)
            max_contexts[model] = max_context
        
        # Tester chaque longueur de contexte
        for length in context_lengths:
            result = test_context_length(model, config, length)
            model_results.append(result)
        
        results[model] = model_results
    
    # Générer les graphiques
    generate_plots(results, args.output_dir)
    
    # Générer le rapport markdown
    report_file = os.path.join(args.output_dir, "qwen3_context_benchmark_report.md")
    generate_markdown_report(results, max_contexts, report_file)
    
    # Sauvegarder les résultats bruts en JSON
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    json_file = os.path.join(args.output_dir, f"qwen3_context_benchmark_{timestamp}.json")
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": timestamp,
            "models_tested": models_to_test,
            "context_lengths": context_lengths,
            "results": results,
            "max_contexts": max_contexts
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\nRésultats sauvegardés dans: {json_file}")
    print(f"Rapport généré dans: {report_file}")
    print(f"Graphiques générés dans: {args.output_dir}")

if __name__ == "__main__":
    main()