#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de test rapide pour les endpoints Qwen3 actuels
"""

import requests
import time
import json
from typing import Dict, Any

# Configuration des endpoints actuels
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

def test_endpoint(name: str, config: Dict[str, str]) -> Dict[str, Any]:
    """Test un endpoint spécifique"""
    print(f"\n=== Test de {name.upper()} ({config['model']}) ===")
    
    results = {
        "name": name,
        "model": config["model"],
        "connectivity": False,
        "models_api": {},
        "chat_completion": {}
    }
    
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }
    
    # Test de connectivité
    try:
        response = requests.get(f"{config['url']}/v1/models", headers=headers, timeout=10)
        if response.status_code == 200:
            results["connectivity"] = True
            print(f"✓ Connectivité: OK")
            models_data = response.json()
            results["models_api"]["status"] = "success"
            results["models_api"]["models_count"] = len(models_data.get("data", []))
        else:
            print(f"✗ Connectivité: ÉCHEC (Status: {response.status_code})")
            results["models_api"]["status"] = "failed"
            results["models_api"]["error"] = f"HTTP {response.status_code}"
    except Exception as e:
        print(f"✗ Connectivité: ÉCHEC ({str(e)})")
        results["models_api"]["status"] = "failed"
        results["models_api"]["error"] = str(e)
        return results
    
    # Test de génération de texte
    try:
        start_time = time.time()
        
        chat_data = {
            "model": config["model"],
            "messages": [
                {"role": "user", "content": "Bonjour, comment allez-vous? Répondez en une phrase."}
            ],
            "max_tokens": 50,
            "temperature": 0.7
        }
        
        response = requests.post(
            f"{config['url']}/v1/chat/completions",
            headers=headers,
            json=chat_data,
            timeout=30
        )
        
        end_time = time.time()
        response_time = (end_time - start_time) * 1000  # en ms
        
        if response.status_code == 200:
            data = response.json()
            usage = data.get("usage", {})
            
            results["chat_completion"] = {
                "status": "success",
                "response_time_ms": round(response_time, 2),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0)
            }
            
            if usage.get("total_tokens", 0) > 0 and response_time > 0:
                tokens_per_second = (usage["total_tokens"] / response_time) * 1000
                results["chat_completion"]["tokens_per_second"] = round(tokens_per_second, 2)
            
            print(f"✓ Chat completion: {response_time:.0f}ms")
            print(f"  - Tokens: {usage.get('prompt_tokens', 0)} prompt + {usage.get('completion_tokens', 0)} completion = {usage.get('total_tokens', 0)} total")
            if "tokens_per_second" in results["chat_completion"]:
                print(f"  - Débit: {results['chat_completion']['tokens_per_second']:.1f} tokens/s")
                
        else:
            print(f"✗ Chat completion: ÉCHEC (Status: {response.status_code})")
            results["chat_completion"]["status"] = "failed"
            results["chat_completion"]["error"] = f"HTTP {response.status_code}"
            
    except Exception as e:
        print(f"✗ Chat completion: ÉCHEC ({str(e)})")
        results["chat_completion"]["status"] = "failed"
        results["chat_completion"]["error"] = str(e)
    
    return results

def main():
    """Fonction principale"""
    print("=== TEST DE PERFORMANCE QWEN3 ===")
    print("Configuration des endpoints et métriques de performance")
    print()
    
    all_results = []
    
    for name, config in ENDPOINTS.items():
        result = test_endpoint(name, config)
        all_results.append(result)
    
    # Résumé des résultats
    print("\n" + "="*60)
    print("RÉSUMÉ DES RÉSULTATS")
    print("="*60)
    
    for result in all_results:
        print(f"\n{result['name'].upper()} ({result['model']}):")
        print(f"  Connectivité: {'✓' if result['connectivity'] else '✗'}")
        
        if result['chat_completion'].get('status') == 'success':
            cc = result['chat_completion']
            print(f"  Chat completion: ✓ {cc['response_time_ms']:.0f}ms")
            print(f"    Tokens: {cc['total_tokens']} total")
            if 'tokens_per_second' in cc:
                print(f"    Débit: {cc['tokens_per_second']:.1f} tokens/s")
        else:
            print(f"  Chat completion: ✗")
    
    # Configuration des endpoints
    print("\n" + "="*60)
    print("CONFIGURATION DES ENDPOINTS")
    print("="*60)
    
    for name, config in ENDPOINTS.items():
        print(f"\n{name.upper()}:")
        print(f"  URL: {config['url']}")
        print(f"  Modèle: {config['model']}")
        print(f"  Clé API: {config['api_key']}")
    
    # Sauvegarde des résultats
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    results_file = f"results/qwen3_performance_{timestamp}.json"
    
    try:
        import os
        os.makedirs("results", exist_ok=True)
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({
                "timestamp": timestamp,
                "endpoints": ENDPOINTS,
                "results": all_results
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\nRésultats sauvegardés dans: {results_file}")
    except Exception as e:
        print(f"\nErreur lors de la sauvegarde: {e}")

if __name__ == "__main__":
    main()