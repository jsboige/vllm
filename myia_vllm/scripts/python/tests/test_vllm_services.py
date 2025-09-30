#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script de test pour les services vLLM
Ce script permet de tester les trois configurations de vLLM (micro, mini, medium)
et leurs fonctionnalités spécifiques (outils, raisonnement, décodage spéculatif).
"""

import os
import time
import json
import argparse
import requests
from dotenv import load_dotenv
import asyncio
import aiohttp
import random
from typing import Dict, List, Optional, Tuple, Union, Any

from ..utils import log
from ..test_data import WEATHER_TOOL, WEATHER_MESSAGES, REASONING_MESSAGES
from ..client import VLLMClient
from ..async_client import AsyncVLLMClient

# Chargement des variables d'environnement
load_dotenv()

# Configuration des endpoints
endpoints = []

# Fonction pour charger les endpoints depuis le fichier .env
def load_endpoints():
    """
    Charge les endpoints depuis le fichier .env
    Format attendu:
    OPENAI_ENDPOINT_NAME_X=nom
    OPENAI_API_KEY_X=clé
    OPENAI_BASE_URL_X=url
    OPENAI_CHAT_MODEL_ID_X=modèle
    """
    global endpoints
    endpoints = []
    
    # Chercher les endpoints dans les variables d'environnement
    for i in range(1, 10):  # Chercher jusqu'à 10 endpoints
        suffix = f"_{i}" if i > 1 else ""
        name = os.environ.get(f"OPENAI_ENDPOINT_NAME{suffix}")
        api_key = os.environ.get(f"OPENAI_API_KEY{suffix}")
        api_base = os.environ.get(f"OPENAI_BASE_URL{suffix}")
        model = os.environ.get(f"OPENAI_CHAT_MODEL_ID{suffix}")
        
        if name and api_key and api_base:
            endpoints.append({
                "name": name,
                "api_key": api_key,
                "api_base": api_base,
                "model": model
            })
    
    logger.info(f"Endpoints chargés: {[ep['name'] for ep in endpoints]}")
    return endpoints

# Test de connexion simple
def test_connection(endpoint):
    """
    Teste la connexion à un endpoint en récupérant la liste des modèles disponibles
    """
    log("INFO", f"Test de connexion pour {endpoint['name']}...")
    
    try:
        url = f"{endpoint['api_base']}/models"
        headers = {
            "Authorization": f"Bearer {endpoint['api_key']}"
        }
        
        start_time = time.time()
        response = requests.get(url, headers=headers, timeout=10)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            models = response.json()
            log("INFO", f"  ✅ Connexion réussie à {endpoint['name']} en {elapsed:.2f}s")
            log("INFO", f"  📋 Modèles disponibles: {models.get('data', [])}")
            return True
        else:
            log("ERROR", f"  ❌ Échec de connexion à {endpoint['name']}: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        log("ERROR", f"  ❌ Exception lors de la connexion à {endpoint['name']}: {e}")
        return False

# Test de génération de texte simple
def test_text_generation(endpoint, prompt="Bonjour, comment vas-tu aujourd'hui?"):
    """
    Teste la génération de texte simple
    """
    log("INFO", f"Test de génération de texte pour {endpoint['name']}...")
    
    client = VLLMClient(endpoint=endpoint['api_base'], api_key=endpoint['api_key'])
    
    try:
        start_time = time.time()
        response = client.chat_completion(
            model=endpoint.get('model', 'default'),
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=100
        )
        elapsed = time.time() - start_time
        
        if not response:
            return False, None, None, None

        content = response["choices"][0]["message"]["content"]
        tokens = response["usage"]["total_tokens"] if "usage" in response else None
        
        log("INFO", f"  ✅ Génération réussie en {elapsed:.2f}s")
        log("INFO", f"  📋 Réponse: {content[:100]}...")
        if tokens:
            log("INFO", f"  📊 Tokens: {tokens}, Vitesse: {tokens/elapsed:.2f} tokens/s")
        
        return True, content, elapsed, tokens
    except Exception as e:
        log("ERROR", f"  ❌ Exception lors de la génération de texte: {e}")
        return False, None, None, None

# Test d'utilisation d'outils
def test_tool_usage(endpoint):
    """
    Teste l'utilisation d'outils (function calling)
    """
    log("INFO", f"Test d'utilisation d'outils pour {endpoint['name']}...")
    
    client = VLLMClient(endpoint=endpoint['api_base'], api_key=endpoint['api_key'])
    
    try:
        start_time = time.time()
        response = client.chat_completion(
            model=endpoint.get('model', 'default'),
            messages=WEATHER_MESSAGES,
            tools=WEATHER_TOOL,
            tool_choice="auto",
            max_tokens=200
        )
        elapsed = time.time() - start_time
        
        if not response:
            return False

        tool_calls = response["choices"][0]["message"].get("tool_calls")
        
        if tool_calls:
            log("INFO", f"  ✅ Utilisation d'outils réussie en {elapsed:.2f}s")
            for tool_call in tool_calls:
                function_name = tool_call["function"]["name"]
                function_args = json.loads(tool_call["function"]["arguments"])
                log("INFO", f"  📋 Fonction appelée: {function_name}")
                log("INFO", f"  📋 Arguments: {function_args}")
            return True
        else:
            log("WARNING", f"  ⚠️ Pas d'appel d'outil détecté dans la réponse")
            log("INFO", f"  📋 Contenu: {response['choices'][0]['message']['content']}")
            return False
    except Exception as e:
        log("ERROR", f"  ❌ Exception lors du test d'outils: {e}")
        return False

# Test de raisonnement
def test_reasoning(endpoint):
    """
    Teste la capacité de raisonnement du modèle
    """
    log("INFO", f"Test de raisonnement pour {endpoint['name']}...")
    
    client = VLLMClient(endpoint=endpoint['api_base'], api_key=endpoint['api_key'])
    
    try:
        start_time = time.time()
        response = client.chat_completion(
            model=endpoint.get('model', 'default'),
            messages=REASONING_MESSAGES,
            max_tokens=300
        )
        elapsed = time.time() - start_time
        
        if not response:
            return False

        content = response["choices"][0]["message"]["content"]
        
        log("INFO", f"  ✅ Test de raisonnement terminé en {elapsed:.2f}s")
        log("INFO", f"  📋 Réponse: {content}")
        
        # Vérifier si la réponse contient "3 pommes" qui est la bonne réponse
        if "3 pommes" in content.lower():
            log("INFO", f"  ✅ La réponse semble correcte (contient '3 pommes')")
            return True
        else:
            log("WARNING", f"  ⚠️ La réponse ne contient pas explicitement '3 pommes'")
            return False
    except Exception as e:
        log("ERROR", f"  ❌ Exception lors du test de raisonnement: {e}")
        return False

# Benchmark de performance
def benchmark_performance(endpoint, prompt=None, repeats=3):
    """
    Effectue un benchmark de performance
    """
    if prompt is None:
        prompt = (
            "Rédige un texte d'environ 500 mots sur l'IA, "
            "en évoquant l'apprentissage machine, les grands modèles de langage, "
            "et quelques perspectives d'évolution."
        )
    
    log("INFO", f"Benchmark de performance pour {endpoint['name']} ({repeats} répétitions)...")
    
    client = VLLMClient(endpoint=endpoint['api_base'], api_key=endpoint['api_key'])
    
    # Warm-up
    log("INFO", "  🔄 Warm-up...")
    try:
        client.chat_completion(
            model=endpoint.get('model', 'default'),
            messages=[
                {"role": "user", "content": "Warm up. Ignorez ce message."}
            ],
            max_tokens=10
        )
    except Exception as e:
        log("WARNING", f"  ⚠️ Échec du warm-up: {e}")
    
    total_time = 0
    total_tokens = 0
    success_count = 0
    
    for i in range(repeats):
        log("INFO", f"  🔄 Itération {i+1}/{repeats}")
        
        try:
            start_time = time.time()
            response = client.chat_completion(
                model=endpoint.get('model', 'default'),
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500
            )
            elapsed = time.time() - start_time
            
            if not response:
                continue
            
            tokens = response["usage"]["total_tokens"] if "usage" in response else None
            
            log("INFO", f"    ⏱️ Durée: {elapsed:.2f}s, tokens: {tokens}")
            
            total_time += elapsed
            if tokens:
                total_tokens += tokens
            success_count += 1
            
        except Exception as e:
            log("ERROR", f"    ❌ Exception: {e}")
    
    if success_count == 0:
        log("ERROR", f"  ❌ Toutes les itérations ont échoué")
        return None
    
    avg_time = total_time / success_count
    tokens_per_sec = total_tokens / total_time if total_time > 0 else 0
    
    log("INFO", f"  📊 Résultats du benchmark:")
    log("INFO", f"    ⏱️ Temps moyen: {avg_time:.2f}s")
    log("INFO", f"    📈 Vitesse: {tokens_per_sec:.2f} tokens/s")
    
    return {
        "avg_time": avg_time,
        "tokens_per_sec": tokens_per_sec,
        "total_tokens": total_tokens,
        "success_count": success_count
    }

# Test de traitement parallèle (batching)
async def test_parallel_processing(endpoint, n_parallel=5):
    """
    Teste le traitement parallèle (batching)
    """
    log("INFO", f"Test de traitement parallèle pour {endpoint['name']} ({n_parallel} requêtes)...")
    
    prompt = "Bonjour, ceci est un test de requêtes parallèles. Peux-tu me donner quelques idées créatives pour un week-end ?"
    client = AsyncVLLMClient(endpoint=endpoint['api_base'], api_key=endpoint['api_key'])

    async def run_request(p):
        start_t = time.time()
        response = await client.chat_completion(
            model=endpoint.get("model", "default"),
            messages=[{"role": "user", "content": p}],
            max_tokens=200
        )
        elapsed = time.time() - start_t
        if response and "usage" in response:
            return elapsed, response["usage"].get("total_tokens")
        return None, None

    tasks = []
    for _ in range(n_parallel):
        prefix = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=5))
        modified_prompt = f"{prefix} {prompt}"
        tasks.append(asyncio.create_task(run_request(modified_prompt)))
    
    start_time = time.time()
    results = await asyncio.gather(*tasks)
    total_time = time.time() - start_time
    
    nb_ok = 0
    sum_tokens = 0
    for (elapsed, tokens) in results:
        if elapsed is not None and tokens is not None:
            nb_ok += 1
            sum_tokens += tokens
    
    log("INFO", f"  📊 Résultats du test parallèle:")
    log("INFO", f"    ✅ {nb_ok}/{n_parallel} requêtes réussies")
    log("INFO", f"    ⏱️ Durée totale: {total_time:.2f}s")
    log("INFO", f"    📈 Tokens cumulés: {sum_tokens}")
    
    speed = sum_tokens / total_time if total_time > 0 else 0
    log("INFO", f"    📈 Vitesse globale: {speed:.2f} tokens/s")
    
    return {
        "success_count": nb_ok,
        "total_time": total_time,
        "total_tokens": sum_tokens,
        "tokens_per_sec": speed
    }

# Fonction principale
async def main():
    parser = argparse.ArgumentParser(description="Tests des services vLLM")
    parser.add_argument("--connection", action="store_true", help="Tester la connexion")
    parser.add_argument("--generation", action="store_true", help="Tester la génération de texte")
    parser.add_argument("--tools", action="store_true", help="Tester l'utilisation d'outils")
    parser.add_argument("--reasoning", action="store_true", help="Tester le raisonnement")
    parser.add_argument("--benchmark", action="store_true", help="Effectuer un benchmark de performance")
    parser.add_argument("--parallel", action="store_true", help="Tester le traitement parallèle")
    parser.add_argument("--all", action="store_true", help="Exécuter tous les tests")
    parser.add_argument("--repeats", type=int, default=3, help="Nombre de répétitions pour le benchmark")
    parser.add_argument("--parallel-requests", type=int, default=5, help="Nombre de requêtes parallèles")
    
    args = parser.parse_args()
    
    # Si aucun test n'est spécifié, exécuter tous les tests
    if not (args.connection or args.generation or args.tools or args.reasoning or args.benchmark or args.parallel):
        args.all = True
    
    # Charger les endpoints
    load_endpoints()
    
    if not endpoints:
        logger.error("❌ Aucun endpoint trouvé dans le fichier .env")
        return
    
    # Résultats des tests
    results = {ep["name"]: {} for ep in endpoints}
    
    # Exécuter les tests pour chaque endpoint
    for endpoint in endpoints:
        logger.info(f"\n=== Tests pour {endpoint['name']} ===\n")
        
        # Test de connexion
        if args.connection or args.all:
            connection_ok = test_connection(endpoint)
            results[endpoint["name"]]["connection"] = connection_ok
            
            # Si la connexion échoue, passer à l'endpoint suivant
            if not connection_ok:
                logger.error(f"❌ Impossible de se connecter à {endpoint['name']}, tests suivants ignorés")
                continue
        
        # Test de génération de texte
        if args.generation or args.all:
            gen_ok, _, _, _ = test_text_generation(endpoint)
            results[endpoint["name"]]["generation"] = gen_ok
        
        # Test d'utilisation d'outils
        if args.tools or args.all:
            tools_ok = test_tool_usage(endpoint)
            results[endpoint["name"]]["tools"] = tools_ok
        
        # Test de raisonnement
        if args.reasoning or args.all:
            reasoning_ok = test_reasoning(endpoint)
            results[endpoint["name"]]["reasoning"] = reasoning_ok
        
        # Benchmark de performance
        if args.benchmark or args.all:
            benchmark_results = benchmark_performance(endpoint, repeats=args.repeats)
            results[endpoint["name"]]["benchmark"] = benchmark_results
        
        # Test de traitement parallèle
        if args.parallel or args.all:
            parallel_results = await test_parallel_processing(endpoint, n_parallel=args.parallel_requests)
            results[endpoint["name"]]["parallel"] = parallel_results
    
    # Afficher le résumé des tests
    logger.info("\n=== Résumé des tests ===\n")
    
    for name, result in results.items():
        logger.info(f"Endpoint: {name}")
        
        if "connection" in result:
            status = "✅" if result["connection"] else "❌"
            logger.info(f"  Connexion: {status}")
        
        if "generation" in result:
            status = "✅" if result["generation"] else "❌"
            logger.info(f"  Génération de texte: {status}")
        
        if "tools" in result:
            status = "✅" if result["tools"] else "❌"
            logger.info(f"  Utilisation d'outils: {status}")
        
        if "reasoning" in result:
            status = "✅" if result["reasoning"] else "❌"
            logger.info(f"  Raisonnement: {status}")
        
        if "benchmark" in result and result["benchmark"]:
            logger.info(f"  Benchmark: {result['benchmark']['tokens_per_sec']:.2f} tokens/s")
        
        if "parallel" in result and result["parallel"]:
            logger.info(f"  Traitement parallèle: {result['parallel']['tokens_per_sec']:.2f} tokens/s")
    
    logger.info("\nTests terminés.")

if __name__ == "__main__":
    asyncio.run(main())