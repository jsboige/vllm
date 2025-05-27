#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de test de performance pour les endpoints Qwen3
Mesure la latence, le débit, l'utilisation mémoire et la qualité des réponses
"""

import requests
import time
import json
import os
import statistics
import subprocess
import platform
from typing import Dict, Any, List, Tuple
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

# Prompts de test pour évaluer la qualité des réponses
TEST_PROMPTS = [
    {
        "name": "simple_greeting",
        "content": "Bonjour, comment allez-vous? Répondez en une phrase.",
        "max_tokens": 50,
        "description": "Salutation simple"
    },
    {
        "name": "factual_question",
        "content": "Quelle est la capitale de la France et quand la Tour Eiffel a-t-elle été construite?",
        "max_tokens": 100,
        "description": "Question factuelle"
    },
    {
        "name": "code_generation",
        "content": "Écrivez une fonction Python qui calcule la factorielle d'un nombre.",
        "max_tokens": 150,
        "description": "Génération de code"
    },
    {
        "name": "reasoning",
        "content": "Si un train part de Paris à 8h et roule à 200 km/h vers Marseille qui est à 800 km, à quelle heure arrive-t-il?",
        "max_tokens": 200,
        "description": "Raisonnement logique"
    }
]

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

def test_models_endpoint(config: Dict[str, str]) -> Dict[str, Any]:
    """Teste l'endpoint /v1/models"""
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(f"{config['url']}/v1/models", headers=headers, timeout=10)
        if response.status_code == 200:
            models_data = response.json()
            return {
                "status": "success",
                "models_count": len(models_data.get("data", [])),
                "response_time_ms": response.elapsed.total_seconds() * 1000
            }
        else:
            return {
                "status": "failed",
                "error": f"HTTP {response.status_code}",
                "response_time_ms": response.elapsed.total_seconds() * 1000
            }
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e)
        }

def test_chat_completion(config: Dict[str, str], prompt: Dict[str, str], gpu_id: str) -> Dict[str, Any]:
    """Teste l'endpoint /v1/chat/completions avec un prompt spécifique"""
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }
    
    chat_data = {
        "model": config["model"],
        "messages": [
            {"role": "user", "content": prompt["content"]}
        ],
        "max_tokens": prompt["max_tokens"],
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
            timeout=60
        )
        
        end_time = time.time()
        response_time = (end_time - start_time) * 1000  # en ms
        
        # Mesurer l'utilisation mémoire après
        mem_after = get_gpu_memory_usage(gpu_id)
        
        if response.status_code == 200:
            data = response.json()
            usage = data.get("usage", {})
            
            # Extraire le contenu du champ reasoning_content au lieu de content
            content = data.get("choices", [{}])[0].get("message", {}).get("reasoning_content", "")
            
            # Si reasoning_content est vide, essayer avec content
            if not content:
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Afficher un extrait du contenu
            print(f"    Contenu extrait: {content[:50]}..." if content else "    Contenu vide!")
            
            result = {
                "status": "success",
                "response_time_ms": round(response_time, 2),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "content": content,  # Maintenant contient reasoning_content ou content
                "memory_before": mem_before,
                "memory_after": mem_after,
                "memory_increase_mb": mem_after.get("used_mb", 0) - mem_before.get("used_mb", 0)
            }
            
            if usage.get("total_tokens", 0) > 0 and response_time > 0:
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

def test_endpoint_performance(name: str, config: Dict[str, str]) -> Dict[str, Any]:
    """Teste les performances d'un endpoint spécifique avec plusieurs prompts et itérations"""
    print(f"\n=== Test de performance de {name.upper()} ({config['model']}) ===")
    
    results = {
        "name": name,
        "model": config["model"],
        "connectivity": False,
        "models_api": {},
        "chat_completions": {},
        "summary": {}
    }
    
    # Test de connectivité via l'endpoint models
    models_result = test_models_endpoint(config)
    if models_result["status"] == "success":
        results["connectivity"] = True
        results["models_api"] = models_result
        print(f"+ Connectivité: OK ({models_result['response_time_ms']:.0f}ms)")
    else:
        print(f"- Connectivité: ÉCHEC ({models_result.get('error', 'Erreur inconnue')})")
        return results
    
    # Tests de chat completion pour chaque prompt
    all_response_times = []
    all_tokens_per_second = []
    
    for prompt in TEST_PROMPTS:
        prompt_name = prompt["name"]
        results["chat_completions"][prompt_name] = {
            "description": prompt["description"],
            "iterations": []
        }
        
        print(f"\n  Test: {prompt['description']}")
        
        for i in range(NUM_ITERATIONS):
            print(f"    Itération {i+1}/{NUM_ITERATIONS}...", end="", flush=True)
            
            result = test_chat_completion(config, prompt, config["gpu_id"])
            results["chat_completions"][prompt_name]["iterations"].append(result)
            
            if result["status"] == "success":
                all_response_times.append(result["response_time_ms"])
                if "tokens_per_second" in result:
                    all_tokens_per_second.append(result["tokens_per_second"])
                print(f" {result['response_time_ms']:.0f}ms, {result.get('tokens_per_second', 0):.1f} tokens/s")
            else:
                print(f" ÉCHEC ({result.get('error', 'Erreur inconnue')})")
    
    # Calcul des statistiques
    if all_response_times:
        results["summary"]["avg_response_time_ms"] = round(statistics.mean(all_response_times), 2)
        results["summary"]["min_response_time_ms"] = round(min(all_response_times), 2)
        results["summary"]["max_response_time_ms"] = round(max(all_response_times), 2)
        
        if all_tokens_per_second:
            results["summary"]["avg_tokens_per_second"] = round(statistics.mean(all_tokens_per_second), 2)
            results["summary"]["min_tokens_per_second"] = round(min(all_tokens_per_second), 2)
            results["summary"]["max_tokens_per_second"] = round(max(all_tokens_per_second), 2)
    
    # Affichage du résumé
    print(f"\n  Résumé:")
    if "avg_response_time_ms" in results["summary"]:
        print(f"    Temps de réponse moyen: {results['summary']['avg_response_time_ms']:.0f}ms")
    if "avg_tokens_per_second" in results["summary"]:
        print(f"    Débit moyen: {results['summary']['avg_tokens_per_second']:.1f} tokens/s")
    
    return results

def generate_markdown_report(results: List[Dict[str, Any]]) -> str:
    """Génère un rapport de performance au format markdown"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    md = f"# Rapport de Performance Qwen3\n\n"
    md += f"Date: {now}\n\n"
    
    # Tableau de résumé
    md += "## Résumé des performances\n\n"
    md += "| Modèle | Latence moyenne (ms) | Débit moyen (tokens/s) | Utilisation mémoire |\n"
    md += "|--------|----------------------|------------------------|--------------------|\n"
    
    for result in results:
        name = result["name"]
        model = result["model"]
        
        latency = result["summary"].get("avg_response_time_ms", "N/A")
        throughput = result["summary"].get("avg_tokens_per_second", "N/A")
        
        # Calculer l'utilisation mémoire moyenne
        memory_usage = "N/A"
        memory_samples = []
        
        for prompt_results in result["chat_completions"].values():
            for iteration in prompt_results["iterations"]:
                if iteration["status"] == "success" and "memory_after" in iteration:
                    memory_samples.append(iteration["memory_after"].get("utilization_percent", 0))
        
        if memory_samples:
            memory_usage = f"{statistics.mean(memory_samples):.1f}%"
        
        md += f"| {name} ({model}) | {latency} | {throughput} | {memory_usage} |\n"
    
    # Détails par modèle
    for result in results:
        name = result["name"]
        model = result["model"]
        
        md += f"\n## Détails pour {name} ({model})\n\n"
        
        # Connectivité
        md += "### Connectivité\n\n"
        if result["connectivity"]:
            md += f"- **Statut**: OK\n"
            md += f"- **Temps de réponse**: {result['models_api']['response_time_ms']:.1f}ms\n"
            md += f"- **Nombre de modèles**: {result['models_api']['models_count']}\n"
        else:
            md += f"- **Statut**: ÉCHEC\n"
            if "error" in result["models_api"]:
                md += f"- **Erreur**: {result['models_api']['error']}\n"
        
        # Performances
        md += "\n### Performances\n\n"
        md += f"- **Temps de réponse moyen**: {result['summary'].get('avg_response_time_ms', 'N/A')}ms\n"
        md += f"- **Temps de réponse min**: {result['summary'].get('min_response_time_ms', 'N/A')}ms\n"
        md += f"- **Temps de réponse max**: {result['summary'].get('max_response_time_ms', 'N/A')}ms\n"
        md += f"- **Débit moyen**: {result['summary'].get('avg_tokens_per_second', 'N/A')} tokens/s\n"
        md += f"- **Débit min**: {result['summary'].get('min_tokens_per_second', 'N/A')} tokens/s\n"
        md += f"- **Débit max**: {result['summary'].get('max_tokens_per_second', 'N/A')} tokens/s\n"
        
        # Résultats par prompt
        md += "\n### Résultats par type de prompt\n\n"
        
        for prompt_name, prompt_results in result["chat_completions"].items():
            description = prompt_results["description"]
            iterations = prompt_results["iterations"]
            
            md += f"#### {description}\n\n"
            
            # Calculer les moyennes
            response_times = [it["response_time_ms"] for it in iterations if it["status"] == "success"]
            tokens_per_second = [it["tokens_per_second"] for it in iterations if it["status"] == "success" and "tokens_per_second" in it]
            
            if response_times:
                avg_response_time = statistics.mean(response_times)
                md += f"- **Temps de réponse moyen**: {avg_response_time:.1f}ms\n"
            
            if tokens_per_second:
                avg_throughput = statistics.mean(tokens_per_second)
                md += f"- **Débit moyen**: {avg_throughput:.1f} tokens/s\n"
            
            # Exemple de réponse (première itération réussie)
            for iteration in iterations:
                if iteration["status"] == "success" and "content" in iteration:
                    md += f"\n**Exemple de réponse**:\n\n```\n{iteration['content']}\n```\n\n"
                    break
    
    # Méthodologie
    md += "\n## Méthodologie\n\n"
    md += f"- **Nombre d'itérations par test**: {NUM_ITERATIONS}\n"
    md += "- **Types de prompts testés**:\n"
    
    for prompt in TEST_PROMPTS:
        md += f"  - {prompt['description']}: \"{prompt['content']}\"\n"
    
    md += "\n- **Métriques mesurées**:\n"
    md += "  - Latence (temps de réponse en ms)\n"
    md += "  - Débit (tokens générés par seconde)\n"
    md += "  - Utilisation mémoire GPU\n"
    md += "  - Qualité des réponses (exemples fournis)\n"
    
    return md

def main():
    """Fonction principale"""
    print("=== TEST DE PERFORMANCE QWEN3 ===")
    print(f"Configuration des endpoints et métriques de performance")
    print(f"Nombre d'itérations par test: {NUM_ITERATIONS}")
    print()
    
    all_results = []
    
    for name, config in ENDPOINTS.items():
        result = test_endpoint_performance(name, config)
        all_results.append(result)
    
    # Générer le rapport markdown
    report_md = generate_markdown_report(all_results)
    
    # Créer le dossier results s'il n'existe pas
    os.makedirs("results", exist_ok=True)
    
    # Sauvegarder les résultats bruts en JSON
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    json_file = f"results/qwen3_performance_{timestamp}.json"
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": timestamp,
            "endpoints": ENDPOINTS,
            "results": all_results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\nRésultats bruts sauvegardés dans: {json_file}")
    
    # Sauvegarder le rapport markdown
    md_file = "qwen3-performance-report.md"
    
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(report_md)
    
    print(f"Rapport de performance sauvegardé dans: {md_file}")

if __name__ == "__main__":
    main()