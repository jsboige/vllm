#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script pour tester la taille de contexte maximale des modèles Qwen3
Ce script génère un texte de longueur variable et vérifie si le modèle peut le traiter
"""

import argparse
import json
import time
import sys

from ..client import VLLMClient
from ..utils import log

def count_tokens(text, model_name):
    """Estimation approximative du nombre de tokens dans un texte"""
    # Approximation simple: 1 token ≈ 4 caractères pour l'anglais, 2.5 caractères pour le français
    # Cette fonction est une approximation, pour une mesure précise il faudrait utiliser le tokenizer du modèle
    if any(ord(c) > 127 for c in text):  # Détection grossière de caractères non-ASCII (probablement français)
        return len(text) // 2.5
    return len(text) // 4

def generate_test_text(token_count, use_french=False):
    """Génère un texte de test avec le nombre approximatif de tokens spécifié"""
    if use_french:
        # Texte en français (plus de caractères par token)
        base_text = "Ceci est un test pour vérifier la capacité de traitement de contexte long. "
        # Environ 15 tokens
    else:
        # Texte en anglais (moins de caractères par token)
        base_text = "This is a test to check the long context processing capability. "
        # Environ 12 tokens
    
    # Répéter le texte pour atteindre le nombre de tokens souhaité
    repetitions = token_count // count_tokens(base_text, None)
    test_text = base_text * repetitions
    
    # Ajouter une question à la fin pour vérifier que le modèle peut traiter l'ensemble du contexte
    if use_french:
        test_text += "\n\nAprès avoir lu tout ce texte, pouvez-vous confirmer que vous avez pu traiter l'intégralité du contexte? Répondez par 'Oui, j'ai pu traiter X tokens' où X est votre estimation du nombre de tokens dans ce message."
    else:
        test_text += "\n\nAfter reading all this text, can you confirm that you were able to process the entire context? Please respond with 'Yes, I was able to process X tokens' where X is your estimate of the number of tokens in this message."
    
    return test_text

def test_model_context(client: VLLMClient, model_name: str, target_tokens: int, use_french: bool = False) -> bool:
    """Teste si le modèle peut traiter un contexte de la taille spécifiée"""
    log("INFO", f"Test de la taille de contexte pour {model_name} (cible: {target_tokens} tokens)")
    
    test_text = generate_test_text(target_tokens, use_french)
    estimated_tokens = count_tokens(test_text, model_name)
    log("INFO", f"Texte de test généré: ~{estimated_tokens} tokens estimés")
    
    data = {
        "model": model_name,
        "messages": [{"role": "user", "content": test_text}],
        "max_tokens": 100,
        "temperature": 0.7
    }
    
    start_time = time.time()
    
    try:
        result = client.chat_completion(**data)
        elapsed_time = time.time() - start_time
        
        log("INFO", f"Réponse reçue en {elapsed_time:.2f} secondes:")
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        log("INFO", f"\n{content}\n")
        
        log("INFO", f"Test réussi! Le modèle {model_name} peut traiter au moins {target_tokens} tokens.")
        return True
    except Exception as e:
        log("ERROR", f"Erreur lors de la requête: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Test de la taille de contexte des modèles Qwen3")
    parser.add_argument("--model", choices=["32b", "8b", "micro"], required=True, help="Modèle à tester")
    parser.add_argument("--tokens", type=int, help="Nombre de tokens à tester (par défaut: dépend du modèle)")
    parser.add_argument("--french", action="store_true", help="Utiliser du texte en français")
    parser.add_argument("--api-key", help="Clé API pour le modèle")
    args = parser.parse_args()
    
    # Configuration par défaut
    model_configs = {
        "32b": {
            "name": "vllm-qwen3-32b-awq",
            "url": "http://localhost:5001",
            "default_tokens": 70000,
            "api_key": "X0EC4YYP068CPD5TGARP9VQB5U4MAGHY"
        },
        "8b": {
            "name": "vllm-qwen3-8b-awq",
            "url": "http://localhost:5002",
            "default_tokens": 128000,
            "api_key": "2NEQLFX1OONFHLFCMMW9U7L15DOC9ECB"
        },
        "micro": {
            "name": "vllm-qwen3-micro-awq",
            "url": "http://localhost:5003",
            "default_tokens": 32000,
            "api_key": "LFXNQWMVP9OONFH1O7L15DOC9ECBEC2B"
        }
    }
    
    config = model_configs[args.model]
    tokens = args.tokens if args.tokens else config["default_tokens"]
    api_key = args.api_key if args.api_key else config["api_key"]
    
    log("INFO", f"=== Test de contexte pour {config['name']} ===")
    log("INFO", f"URL de l'API: {config['url']}")
    log("INFO", f"Taille de contexte cible: {tokens} tokens")
    log("INFO", f"Langue: {'Français' if args.french else 'Anglais'}")
    
    client = VLLMClient(endpoint=config["url"], api_key=api_key)
    
    # Exécuter le test
    success = test_model_context(client, config["name"], tokens, args.french)
    
    if success:
        log("INFO", "\n✅ Test réussi!")
        sys.exit(0)
    else:
        log("ERROR", "\n❌ Test échoué!")
        sys.exit(1)

if __name__ == "__main__":
    main()