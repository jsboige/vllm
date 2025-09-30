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
from typing import Optional

from ..client import VLLMClient
from ..test_data import WEATHER_MESSAGES, WEATHER_TOOL
from ..utils import log

# Configuration par défaut
DEFAULT_ENDPOINTS = {
    "micro": "http://localhost:5000/v1",
    "mini": "http://localhost:5001/v1",
    "medium": "http://localhost:5002/v1"
}

def test_tool_calling(client: VLLMClient) -> bool:
    """
    Teste le tool calling avec un modèle Qwen3.
    
    Args:
        client: Instance du client VLLM
    
    Returns:
        bool: True si le test est réussi, False sinon
    """
    log("INFO", f"Test du tool calling sur {client.endpoint}...")
    
    data = {
        "model": "Qwen3",
        "messages": WEATHER_MESSAGES,
        "tools": WEATHER_TOOL,
        "tool_choice": "auto",
        "temperature": 0.7,
        "max_tokens": 1024
    }
    
    try:
        result = client.chat_completion(**data)
        log("INFO", f"Réponse reçue: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        message = result.get("choices", [{}])[0].get("message", {})
        tool_calls = message.get("tool_calls", [])
        
        if not tool_calls:
            log("ERROR", "Aucun appel d'outil dans la réponse")
            return False
            
        tool_call = tool_calls[0]
        function = tool_call.get("function", {})
        
        if tool_call.get("type") != "function" or function.get("name") != "get_weather":
            log("ERROR", f"Appel d'outil invalide: {tool_call}")
            return False
            
        try:
            arguments = json.loads(function.get("arguments", "{}"))
            if "city" not in arguments:
                log("ERROR", "Argument 'city' manquant")
                return False
        except json.JSONDecodeError:
            log("ERROR", f"Arguments mal formatés: {function.get('arguments')}")
            return False
            
        log("INFO", "Test du tool calling réussi!")
        return True
        
    except Exception as e:
        log("ERROR", f"Exception lors du test: {str(e)}")
        return False

def test_streaming_tool_calling(client: VLLMClient) -> bool:
    """
    Teste le tool calling en streaming avec un modèle Qwen3.
    
    Args:
        client: Instance du client VLLM
    
    Returns:
        bool: True si le test est réussi, False sinon
    """
    log("INFO", f"Test du tool calling en streaming sur {client.endpoint}...")
    
    data = {
        "model": "Qwen3",
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
            if not line or not line.startswith(b"data: "):
                continue
            
            json_str = line[6:].decode("utf-8")
            if json_str == "[DONE]":
                continue
            
            try:
                chunk = json.loads(json_str)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                if "tool_calls" in delta and delta["tool_calls"]:
                    has_tool_call = True
                    function_chunk = delta["tool_calls"][0].get("function", {})
                    if "name" in function_chunk:
                        tool_call_name = function_chunk["name"]
                    if "arguments" in function_chunk:
                        tool_call_arguments += function_chunk["arguments"]
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
                log("ERROR", "Argument 'city' manquant")
                return False
        except json.JSONDecodeError:
            log("ERROR", f"Arguments mal formatés: {tool_call_arguments}")
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
    endpoint = args.endpoint or DEFAULT_ENDPOINTS.get(args.service)
    if not endpoint:
        log("ERROR", f"Service inconnu: {args.service}")
        return 1
    
    # Récupérer la clé API
    api_key = args.api_key or os.environ.get(f"VLLM_API_KEY_{args.service.upper()}")
    if not api_key:
        log("WARNING", f"Aucune clé API spécifiée ou trouvée pour le service {args.service}")

    client = VLLMClient(endpoint=endpoint, api_key=api_key)
    
    # Tester le tool calling normal
    success = test_tool_calling(client)
    
    # Tester le tool calling en streaming si activé
    streaming_success = True
    if not args.no_streaming:
        streaming_success = test_streaming_tool_calling(client)
    
    # Afficher le résultat global
    if success and streaming_success:
        log("INFO", "Tous les tests ont réussi!")
        return 0
    else:
        log("ERROR", "Certains tests ont échoué.")
        return 1

if __name__ == "__main__":
    sys.exit(main())