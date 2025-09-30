#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script de test complet pour vérifier le déploiement des services Qwen3.
Ce script combine les tests du parser de raisonnement et du parser d'outils.
"""

import argparse
import json
import os
import sys
from typing import Dict, Optional

from ..client import VLLMClient
from ..test_data import REASONING_MESSAGES, WEATHER_MESSAGES, WEATHER_TOOL
from ..utils import log

# Configuration par défaut
DEFAULT_ENDPOINTS = {
    "micro": "http://localhost:5000/v1",
    "mini": "http://localhost:5001/v1",
    "medium": "http://localhost:5002/v1"
}

DEFAULT_MODELS = {
    "micro": "vllm-micro-qwen3",
    "mini": "vllm-mini-qwen3",
    "medium": "vllm-medium-qwen3"
}

def test_model_info(client: VLLMClient) -> bool:
    """
    Teste l'accès aux informations du modèle.
    
    Args:
        client: Instance du client VLLM
    
    Returns:
        bool: True si le test est réussi, False sinon
    """
    log("INFO", f"Test de l'accès aux informations du modèle sur {client.endpoint}...")
    try:
        result = client.get_models()
        log("INFO", f"Modèles disponibles: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        if "data" not in result or not result["data"]:
            log("ERROR", "Aucun modèle disponible")
            return False
            
        log("INFO", "Test de l'accès aux informations du modèle réussi!")
        return True
    except Exception as e:
        log("ERROR", f"Exception lors du test: {str(e)}")
        return False

def test_reasoning_parser(client: VLLMClient, model: str) -> bool:
    """
    Teste le parser de raisonnement avec un modèle Qwen3.
    
    Args:
        client: Instance du client VLLM
        model: Nom du modèle à utiliser
    
    Returns:
        bool: True si le test est réussi, False sinon
    """
    log("INFO", f"Test du parser de raisonnement sur {client.endpoint} avec le modèle {model}...")
    
    data = {
        "model": model,
        "messages": REASONING_MESSAGES,
        "temperature": 0.7,
        "max_tokens": 1024
    }
    
    try:
        result = client.chat_completion(**data)
        log("INFO", f"Réponse reçue: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        if "choices" not in result or not result["choices"]:
            log("ERROR", "Aucune réponse dans les choix")
            return False
        
        choice = result["choices"][0]
        message = choice.get("message", {})
        
        if "reasoning_content" not in message and "content" not in message:
            log("ERROR", "Aucun contenu de raisonnement ou contenu normal dans la réponse")
            return False
            
        if "reasoning_content" in message and not message.get("reasoning_content"):
            log("ERROR", "Le contenu de raisonnement est vide")
            return False
            
        if "content" not in message or not message.get("content"):
            log("ERROR", "Aucun contenu normal dans la réponse")
            return False
            
        log("INFO", "Test du parser de raisonnement réussi!")
        return True
        
    except Exception as e:
        log("ERROR", f"Exception lors du test: {str(e)}")
        return False

def test_tool_parser(client: VLLMClient, model: str) -> bool:
    """
    Teste le parser d'outils avec un modèle Qwen3.
    
    Args:
        client: Instance du client VLLM
        model: Nom du modèle à utiliser
    
    Returns:
        bool: True si le test est réussi, False sinon
    """
    log("INFO", f"Test du parser d'outils sur {client.endpoint} avec le modèle {model}...")
    
    data = {
        "model": model,
        "messages": WEATHER_MESSAGES,
        "tools": WEATHER_TOOL,
        "tool_choice": "auto",
        "temperature": 0.7,
        "max_tokens": 1024
    }
    
    try:
        result = client.chat_completion(**data)
        log("INFO", f"Réponse reçue: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        if "choices" not in result or not result["choices"]:
            log("ERROR", "Aucune réponse dans les choix")
            return False
        
        choice = result["choices"][0]
        message = choice.get("message", {})
        
        tool_calls = message.get("tool_calls", [])
        if not tool_calls:
            log("ERROR", "Aucun appel d'outil dans la réponse")
            return False
            
        tool_call = tool_calls[0]
        if tool_call.get("type") != "function":
            log("ERROR", f"Type d'appel d'outil incorrect: {tool_call.get('type')}")
            return False
            
        function = tool_call.get("function", {})
        if function.get("name") != "get_weather":
            log("ERROR", f"Nom de fonction incorrect: {function.get('name')}")
            return False
            
        try:
            arguments = json.loads(function.get("arguments", "{}"))
            if "city" not in arguments:
                log("ERROR", "Argument 'city' manquant dans l'appel d'outil")
                return False
            
            if arguments.get("city").lower() != "paris":
                log("WARNING", f"La ville dans l'appel d'outil n'est pas 'Paris': {arguments.get('city')}")
                
            log("INFO", f"Arguments de l'appel d'outil: {arguments}")
        except json.JSONDecodeError:
            log("ERROR", f"Arguments de l'appel d'outil mal formatés: {function.get('arguments')}")
            return False
            
        log("INFO", "Test du parser d'outils réussi!")
        return True
        
    except Exception as e:
        log("ERROR", f"Exception lors du test: {str(e)}")
        return False

def test_streaming_tool_parser(client: VLLMClient, model: str) -> bool:
    """
    Teste le parser d'outils en streaming avec un modèle Qwen3.
    
    Args:
        client: Instance du client VLLM
        model: Nom du modèle à utiliser
    
    Returns:
        bool: True si le test est réussi, False sinon
    """
    log("INFO", f"Test du parser d'outils en streaming sur {client.endpoint} avec le modèle {model}...")
    
    data = {
        "model": model,
        "messages": WEATHER_MESSAGES,
        "tools": WEATHER_TOOL,
        "tool_choice": "auto",
        "temperature": 0.7,
        "max_tokens": 1024
    }
    
    try:
        response = client.stream_chat_completion(**data)
        
        has_tool_call = False
        tool_call_name = None
        tool_call_arguments = ""
        
        log("INFO", "Réception des chunks de streaming...")
        for line in response.iter_lines():
            if not line:
                continue
            
            if line.startswith(b"data: "):
                json_str = line[6:].decode("utf-8")
                if json_str == "[DONE]":
                    continue
                
                try:
                    chunk = json.loads(json_str)
                    if "choices" in chunk and chunk["choices"]:
                        delta = chunk["choices"][0].get("delta", {})
                        if "tool_calls" in delta and delta["tool_calls"]:
                            has_tool_call = True
                            tool_call = delta["tool_calls"][0]
                            if "function" in tool_call:
                                function = tool_call["function"]
                                if "name" in function:
                                    tool_call_name = function["name"]
                                if "arguments" in function:
                                    tool_call_arguments += function["arguments"]
                except json.JSONDecodeError:
                    log("ERROR", f"Erreur lors de l'analyse du JSON: {json_str}")

        if not has_tool_call:
            log("ERROR", "Aucun appel d'outil dans la réponse en streaming")
            return False
            
        if tool_call_name != "get_weather":
            log("ERROR", f"Nom de fonction incorrect: {tool_call_name}")
            return False
            
        try:
            arguments = json.loads(tool_call_arguments)
            if "city" not in arguments:
                log("ERROR", "Argument 'city' manquant dans l'appel d'outil")
                return False
            
            if arguments.get("city").lower() != "paris":
                log("WARNING", f"La ville dans l'appel d'outil n'est pas 'Paris': {arguments.get('city')}")
                
            log("INFO", f"Arguments de l'appel d'outil en streaming: {arguments}")
        except json.JSONDecodeError:
            log("ERROR", f"Arguments de l'appel d'outil mal formatés: {tool_call_arguments}")
            return False
            
        log("INFO", "Test du parser d'outils en streaming réussi!")
        return True
        
    except Exception as e:
        log("ERROR", f"Exception lors du test en streaming: {str(e)}")
        return False

def main():
    """Fonction principale."""
    parser = argparse.ArgumentParser(description="Test complet du déploiement des services Qwen3")
    parser.add_argument("--service", choices=["micro", "mini", "medium"], default="mini",
                        help="Service à tester (micro, mini, medium)")
    parser.add_argument("--endpoint", help="URL de l'API OpenAI de vLLM (par défaut: selon le service)")
    parser.add_argument("--model", help="Modèle à utiliser (par défaut: selon le service)")
    parser.add_argument("--api-key", help="Clé API pour l'authentification")
    parser.add_argument("--no-streaming", action="store_true", help="Désactiver les tests en streaming")
    parser.add_argument("--test-info", action="store_true", help="Tester uniquement l'accès aux informations du modèle")
    parser.add_argument("--test-reasoning", action="store_true", help="Tester uniquement le parser de raisonnement")
    parser.add_argument("--test-tools", action="store_true", help="Tester uniquement le parser d'outils")
    
    args = parser.parse_args()
    
    # Déterminer l'endpoint
    endpoint = args.endpoint
    if not endpoint:
        endpoint = DEFAULT_ENDPOINTS.get(args.service)
        if not endpoint:
            log("ERROR", f"Service inconnu: {args.service}")
            return 1
    
    # Déterminer le modèle
    model = args.model
    if not model:
        model = DEFAULT_MODELS.get(args.service)
        if not model:
            log("ERROR", f"Service inconnu: {args.service}")
            return 1
    
    # Récupérer la clé API depuis les variables d'environnement si non spécifiée
    api_key = args.api_key
    if not api_key:
        env_var = f"VLLM_API_KEY_{args.service.upper()}"
        api_key = os.environ.get(env_var)
        if not api_key:
            log("WARNING", f"Aucune clé API spécifiée et variable d'environnement {env_var} non définie")

    # Créer le client
    client = VLLMClient(endpoint=endpoint, api_key=api_key)
    
    # Déterminer les tests à exécuter
    test_info = args.test_info
    test_reasoning = args.test_reasoning
    test_tools = args.test_tools
    
    # Si aucun test spécifique n'est demandé, exécuter tous les tests
    if not test_info and not test_reasoning and not test_tools:
        test_info = True
        test_reasoning = True
        test_tools = True
    
    # Résultats des tests
    results = []
    
    # Tester l'accès aux informations du modèle
    if test_info:
        info_success = test_model_info(client)
        results.append(("Accès aux informations du modèle", info_success))
    
    # Tester le parser de raisonnement
    if test_reasoning:
        reasoning_success = test_reasoning_parser(client, model)
        results.append(("Parser de raisonnement", reasoning_success))
    
    # Tester le parser d'outils
    if test_tools:
        tools_success = test_tool_parser(client, model)
        results.append(("Parser d'outils", tools_success))
        
        # Tester le parser d'outils en streaming si activé
        if not args.no_streaming:
            streaming_tools_success = test_streaming_tool_parser(client, model)
            results.append(("Parser d'outils en streaming", streaming_tools_success))
    
    # Afficher le résultat global
    log("INFO", "Résultats des tests:")
    all_success = True
    for test_name, success in results:
        status = f"{GREEN}RÉUSSI{NC}" if success else f"{RED}ÉCHOUÉ{NC}"
        log("INFO", f"  {test_name}: {status}")
        all_success = all_success and success
    
    if all_success:
        log("INFO", "Tous les tests ont réussi!")
        return 0
    else:
        log("ERROR", "Certains tests ont échoué.")
        return 1

if __name__ == "__main__":
    sys.exit(main())