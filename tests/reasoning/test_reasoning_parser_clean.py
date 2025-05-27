#!/usr/bin/env python3
"""
Test script for verifying reasoning parser functionality with Qwen3 models.
This script sends a reasoning-enabled request to different vLLM API servers and checks the responses.

Usage:
    python -m tests.reasoning.test_reasoning_parser_clean [MODEL_TYPE]

Arguments:
    MODEL_TYPE: Type of model to test (default: micro)
                Supported values: micro, mini, medium

Example:
    # Test against the micro model
    python -m tests.reasoning.test_reasoning_parser_clean micro
    
    # Test against the medium model
    python -m tests.reasoning.test_reasoning_parser_clean medium

Note:
    This script requires active vLLM API servers with Qwen3 models loaded.
    The API endpoints and keys are loaded from the .env file.
"""

import requests
import json
import sys
import os
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path)

def test_reasoning_parser(model_type="micro"):
    # Définir la clé API et l'URL de base en fonction du type de modèle
    model_type = model_type.lower()
    
    if model_type == "micro":
        api_key = os.getenv("OPENAI_API_KEY_MICRO")
        base_url = os.getenv("OPENAI_BASE_URL_MICRO")
        model_name = "vllm-qwen3-1.7b-awq"
    elif model_type == "mini":
        api_key = os.getenv("OPENAI_API_KEY_MINI")
        base_url = os.getenv("OPENAI_BASE_URL_MINI")
        model_name = "vllm-qwen3-8b-awq"
    elif model_type == "medium":
        api_key = os.getenv("OPENAI_API_KEY_MEDIUM")
        base_url = os.getenv("OPENAI_BASE_URL_MEDIUM")
        model_name = "vllm-qwen3-32b-awq"
    else:
        print(f"Type de modèle non reconnu: {model_type}")
        print("Types valides: micro, mini, medium")
        return False
    
    if not api_key or not base_url:
        print(f"Erreur: Clé API ou URL de base non trouvée pour le modèle {model_type}")
        print("Assurez-vous que le fichier .env est correctement configuré")
        return False
    
    url = f"{base_url}/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # Problème mathématique qui nécessite un raisonnement étape par étape
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Résoudre l'équation suivante étape par étape: 3x² + 6x - 24 = 0"}
        ],
        "temperature": 0.3,
        "max_tokens": 500
    }
    
    try:
        print(f"Envoi d'une requête à {url}")
        print(f"Modèle: {model_name}")
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        print(f"Réponse pour le modèle {model_type}:")
        print(json.dumps(response.json(), indent=2))
        
        # Vérifier si la réponse contient un raisonnement étape par étape
        content = response.json()["choices"][0]["message"]["content"]
        print("\nAnalyse du raisonnement:")
        if "étape" in content.lower() or "step" in content.lower():
            print("✓ Le modèle a fourni un raisonnement étape par étape")
        else:
            print("✗ Le modèle n'a pas fourni un raisonnement étape par étape clair")
        
        return True
    except Exception as e:
        print(f"Erreur lors du test du modèle {model_type}: {e}")
        return False

if __name__ == "__main__":
    model_type = sys.argv[1] if len(sys.argv) > 1 else "micro"
    test_reasoning_parser(model_type)