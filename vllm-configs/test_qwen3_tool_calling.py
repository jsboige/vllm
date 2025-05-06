#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script de test pour vérifier le fonctionnement du tool calling avec les modèles Qwen3.
Ce script envoie une requête à l'API OpenAI de vLLM avec un exemple de tool calling
et vérifie que la réponse est correctement traitée par notre parser Qwen3.
"""

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Optional, Union

import requests

# Configuration par défaut
DEFAULT_ENDPOINTS = {
    "micro": "http://localhost:5000/v1",
    "mini": "http://localhost:5001/v1",
    "medium": "http://localhost:5002/v1"
}

# Couleurs pour les messages
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[0;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color

def log(level: str, message: str) -> None:
    """Affiche un message formaté avec un niveau de log."""
    color = NC
    if level == "INFO":
        color = GREEN
    elif level == "WARNING":
        color = YELLOW
    elif level == "ERROR":
        color = RED
    elif level == "DEBUG":
        color = BLUE
    
    print(f"{color}[{level}] {message}{NC}")

def test_tool_calling(endpoint: str, api_key: Optional[str] = None) -> bool:
    """
    Teste le tool calling avec un modèle Qwen3.
    
    Args:
        endpoint: URL de l'API OpenAI de vLLM
        api_key: Clé API pour l'authentification (optionnelle)
    
    Returns:
        bool: True si le test est réussi, False sinon
    """
    log("INFO", f"Test du tool calling sur {endpoint}...")
    
    # Définition de l'outil de test
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Obtenir la météo actuelle pour une ville donnée",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "Nom de la ville"
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "Unité de température"
                        }
                    },
                    "required": ["city"]
                }
            }
        }
    ]
    
    # Message pour déclencher l'utilisation de l'outil
    messages = [
        {"role": "system", "content": "Vous êtes un assistant utile qui utilise des outils pour répondre aux questions."},
        {"role": "user", "content": "Quelle est la météo à Paris aujourd'hui?"}
    ]
    
    # Préparation de la requête
    headers = {
        "Content-Type": "application/json"
    }
    
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    data = {
        "model": "Qwen3",
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.7,
        "max_tokens": 1024
    }
    
    try:
        # Envoi de la requête
        log("INFO", "Envoi de la requête...")
        response = requests.post(
            f"{endpoint}/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        # Vérification du code de statut
        if response.status_code != 200:
            log("ERROR", f"Erreur lors de la requête: {response.status_code}")
            log("ERROR", f"Détails: {response.text}")
            return False
        
        # Analyse de la réponse
        result = response.json()
        log("INFO", f"Réponse reçue: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        # Vérification de la présence d'un appel d'outil
        if "choices" not in result or not result["choices"]:
            log("ERROR", "Aucune réponse dans les choix")
            return False
        
        choice = result["choices"][0]
        message = choice.get("message", {})
        
        # Vérification de la présence d'un appel d'outil
        tool_calls = message.get("tool_calls", [])
        if not tool_calls:
            log("ERROR", "Aucun appel d'outil dans la réponse")
            return False
        
        # Vérification du format de l'appel d'outil
        tool_call = tool_calls[0]
        if tool_call.get("type") != "function":
            log("ERROR", f"Type d'appel d'outil incorrect: {tool_call.get('type')}")
            return False
        
        function = tool_call.get("function", {})
        if function.get("name") != "get_weather":
            log("ERROR", f"Nom de fonction incorrect: {function.get('name')}")
            return False
        
        # Vérification des arguments
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
        
        log("INFO", "Test du tool calling réussi!")
        return True
        
    except Exception as e:
        log("ERROR", f"Exception lors du test: {str(e)}")
        return False

def test_streaming_tool_calling(endpoint: str, api_key: Optional[str] = None) -> bool:
    """
    Teste le tool calling en streaming avec un modèle Qwen3.
    
    Args:
        endpoint: URL de l'API OpenAI de vLLM
        api_key: Clé API pour l'authentification (optionnelle)
    
    Returns:
        bool: True si le test est réussi, False sinon
    """
    log("INFO", f"Test du tool calling en streaming sur {endpoint}...")
    
    # Définition de l'outil de test
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Obtenir la météo actuelle pour une ville donnée",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "Nom de la ville"
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "Unité de température"
                        }
                    },
                    "required": ["city"]
                }
            }
        }
    ]
    
    # Message pour déclencher l'utilisation de l'outil
    messages = [
        {"role": "system", "content": "Vous êtes un assistant utile qui utilise des outils pour répondre aux questions."},
        {"role": "user", "content": "Quelle est la météo à Paris aujourd'hui?"}
    ]
    
    # Préparation de la requête
    headers = {
        "Content-Type": "application/json"
    }
    
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    data = {
        "model": "Qwen3",
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.7,
        "max_tokens": 1024,
        "stream": True
    }
    
    try:
        # Envoi de la requête
        log("INFO", "Envoi de la requête en streaming...")
        response = requests.post(
            f"{endpoint}/chat/completions",
            headers=headers,
            json=data,
            stream=True,
            timeout=30
        )
        
        # Vérification du code de statut
        if response.status_code != 200:
            log("ERROR", f"Erreur lors de la requête: {response.status_code}")
            log("ERROR", f"Détails: {response.text}")
            return False
        
        # Variables pour suivre l'état du streaming
        has_tool_call = False
        tool_call_name = None
        tool_call_arguments = ""
        
        # Analyse des chunks de streaming
        log("INFO", "Réception des chunks de streaming...")
        for line in response.iter_lines():
            if not line:
                continue
            
            # Supprimer le préfixe "data: " et analyser le JSON
            if line.startswith(b"data: "):
                json_str = line[6:].decode("utf-8")
                
                # Ignorer le message [DONE]
                if json_str == "[DONE]":
                    continue
                
                try:
                    chunk = json.loads(json_str)
                    
                    # Vérifier si le chunk contient un appel d'outil
                    if "choices" in chunk and chunk["choices"]:
                        choice = chunk["choices"][0]
                        delta = choice.get("delta", {})
                        
                        # Vérifier si le delta contient un appel d'outil
                        if "tool_calls" in delta:
                            tool_calls = delta["tool_calls"]
                            if tool_calls:
                                has_tool_call = True
                                
                                # Extraire les informations de l'appel d'outil
                                tool_call = tool_calls[0]
                                
                                # Extraire le nom de la fonction si présent
                                if "function" in tool_call:
                                    function = tool_call["function"]
                                    if "name" in function:
                                        tool_call_name = function["name"]
                                    
                                    # Accumuler les arguments
                                    if "arguments" in function:
                                        tool_call_arguments += function["arguments"]
                except json.JSONDecodeError:
                    log("ERROR", f"Erreur lors de l'analyse du JSON: {json_str}")
        
        # Vérification des résultats du streaming
        if not has_tool_call:
            log("ERROR", "Aucun appel d'outil dans la réponse en streaming")
            return False
        
        if tool_call_name != "get_weather":
            log("ERROR", f"Nom de fonction incorrect: {tool_call_name}")
            return False
        
        # Vérification des arguments
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
        
        log("INFO", "Test du tool calling en streaming réussi!")
        return True
        
    except Exception as e:
        log("ERROR", f"Exception lors du test en streaming: {str(e)}")
        return False

def main():
    """Fonction principale."""
    parser = argparse.ArgumentParser(description="Test du tool calling avec les modèles Qwen3")
    parser.add_argument("--service", choices=["micro", "mini", "medium"], default="mini",
                        help="Service à tester (micro, mini, medium)")
    parser.add_argument("--endpoint", help="URL de l'API OpenAI de vLLM (par défaut: selon le service)")
    parser.add_argument("--api-key", help="Clé API pour l'authentification")
    parser.add_argument("--no-streaming", action="store_true", help="Désactiver le test en streaming")
    
    args = parser.parse_args()
    
    # Déterminer l'endpoint
    endpoint = args.endpoint
    if not endpoint:
        endpoint = DEFAULT_ENDPOINTS.get(args.service)
        if not endpoint:
            log("ERROR", f"Service inconnu: {args.service}")
            return 1
    
    # Récupérer la clé API depuis les variables d'environnement si non spécifiée
    api_key = args.api_key
    if not api_key:
        env_var = f"VLLM_API_KEY_{args.service.upper()}"
        api_key = os.environ.get(env_var)
        if not api_key:
            log("WARNING", f"Aucune clé API spécifiée et variable d'environnement {env_var} non définie")
    
    # Tester le tool calling normal
    success = test_tool_calling(endpoint, api_key)
    
    # Tester le tool calling en streaming si activé
    streaming_success = True
    if not args.no_streaming:
        streaming_success = test_streaming_tool_calling(endpoint, api_key)
    
    # Afficher le résultat global
    if success and streaming_success:
        log("INFO", "Tous les tests ont réussi!")
        return 0
    else:
        log("ERROR", "Certains tests ont échoué.")
        return 1

if __name__ == "__main__":
    sys.exit(main())