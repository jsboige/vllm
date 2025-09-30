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
from ..parsers import extract_tool_call_from_content
from ..test_data import WEATHER_MESSAGES, WEATHER_TOOL
from ..utils import log

# Configuration par défaut
DEFAULT_ENDPOINTS = {
    "micro": "http://localhost:5000/v1",
    "mini": "http://localhost:5001/v1",
    "medium": "http://localhost:5002/v1"
}

# Modèles par défaut pour chaque service
DEFAULT_MODELS = {
    "micro": "Qwen/Qwen3-1.7B-Base",
    "mini": "Qwen/Qwen3-1.7B-Base",
    "medium": "Qwen/Qwen3-8B-Base"
}

def test_tool_calling(client: VLLMClient, model: str) -> bool:
    """
    Teste le tool calling avec un modèle Qwen3.
    
    Args:
        client: Instance du client VLLM
        model: Modèle à utiliser
    
    Returns:
        bool: True si le test est réussi, False sinon
    """
    log("INFO", f"Test du tool calling sur {client.endpoint}...")
    
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
        
        message = result["choices"][0].get("message", {})
        
        # Vérification de l'appel d'outil standard ou extrait
        tool_call = message.get("tool_calls", [None])[0]
        if not tool_call:
            content = message.get("content", "")
            tool_call = extract_tool_call_from_content(content)
            if tool_call:
                log("INFO", f"Appel d'outil extrait du contenu: {json.dumps(tool_call, indent=2)}")
        
        if not tool_call:
            log("ERROR", "Aucun appel d'outil trouvé")
            return False

        # Validation de l'appel d'outil
        if tool_call.get("type") != "function" or tool_call.get("function", {}).get("name") != "get_weather":
            log("ERROR", f"Appel d'outil invalide: {tool_call}")
            return False
            
        try:
            arguments = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
            if "city" not in arguments:
                log("ERROR", "Argument 'city' manquant")
                return False
            log("INFO", "Test du tool calling réussi!")
            return True
        except json.JSONDecodeError:
            log("ERROR", f"Arguments mal formatés: {tool_call.get('function', {}).get('arguments')}")
            return False
            
    except Exception as e:
        log("ERROR", f"Exception lors du test: {str(e)}")
        return False

def test_streaming_tool_calling(client: VLLMClient, model: str) -> bool:
    """
    Teste le tool calling en streaming avec un modèle Qwen3.
    
    Args:
        client: Instance du client VLLM
        model: Modèle à utiliser
    
    Returns:
        bool: True si le test est réussi, False sinon
    """
    log("INFO", f"Test du tool calling en streaming sur {client.endpoint}...")
    
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
        full_content = ""
        
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
                
                full_content += delta.get("content", "") or ""
                
                if "tool_calls" in delta and delta["tool_calls"]:
                    has_tool_call = True
                    tool_call = delta["tool_calls"][0]["function"]
                    tool_call_name = tool_call.get("name") or tool_call_name
                    tool_call_arguments += tool_call.get("arguments", "")
            except json.JSONDecodeError:
                log("ERROR", f"Erreur lors de l'analyse du JSON: {json_str}")

        # Vérification finale
        if not has_tool_call:
            log("INFO", "Aucun appel d'outil direct, tentative d'extraction du contenu.")
            extracted_call = extract_tool_call_from_content(full_content)
            if not extracted_call:
                log("ERROR", "Aucun appel d'outil trouvé dans le contenu en streaming")
                return False
            tool_call_name = extracted_call.get("function", {}).get("name")
            tool_call_arguments = extracted_call.get("function", {}).get("arguments", "{}")

        if tool_call_name != "get_weather":
            log("ERROR", f"Nom de fonction incorrect: {tool_call_name}")
            return False
            
        try:
            arguments = json.loads(tool_call_arguments)
            if "city" not in arguments:
                log("ERROR", "Argument 'city' manquant")
                return False
            log("INFO", "Test du tool calling en streaming réussi!")
            return True
        except json.JSONDecodeError:
            log("ERROR", f"Arguments mal formatés: {tool_call_arguments}")
            return False
            
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
    parser.add_argument("--model", help="Modèle à utiliser (par défaut: selon le service)")
    
    args = parser.parse_args()
    
    endpoint = args.endpoint or DEFAULT_ENDPOINTS.get(args.service)
    if not endpoint:
        log("ERROR", f"Service inconnu: {args.service}")
        return 1
        
    model = args.model or DEFAULT_MODELS.get(args.service)
    if not model:
        log("ERROR", f"Modèle inconnu pour le service: {args.service}")
        return 1

    api_key = args.api_key or os.environ.get(f"VLLM_API_KEY_{args.service.upper()}")
    if not api_key:
        log("WARNING", f"Aucune clé API spécifiée ou trouvée pour le service {args.service}")

    client = VLLMClient(endpoint=endpoint, api_key=api_key)
    
    # Tester le tool calling normal
    success = test_tool_calling(client, model)
    
    # Tester le tool calling en streaming si activé
    streaming_success = True
    if not args.no_streaming:
        streaming_success = test_streaming_tool_calling(client, model)
    
    # Afficher le résultat global
    if success and streaming_success:
        log("INFO", "Tous les tests ont réussi!")
        return 0
    else:
        log("ERROR", "Certains tests ont échoué.")
        return 1

if __name__ == "__main__":
    sys.exit(main())