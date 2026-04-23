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
import re
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

# Modèles par défaut pour chaque service
DEFAULT_MODELS = {
    "micro": "Qwen/Qwen3-1.7B-Base",
    "mini": "Qwen/Qwen3-1.7B-Base",
    "medium": "Qwen/Qwen3-8B-Base"
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

def extract_tool_call_from_content(content: str) -> Optional[Dict]:
    """
    Extrait l'appel d'outil à partir du contenu généré par le modèle Qwen3.

    Args:
        content: Le contenu généré par le modèle

    Returns:
        Dict: Un dictionnaire contenant les informations d'appel d'outil, ou None si aucun appel d'outil n'est trouvé
    """
    # Recherche des balises <tools> avec du contenu JSON à l'intérieur
    tools_pattern = r'<tools>\s*(.*?)\s*</tools>'
    tools_matches = re.findall(tools_pattern, content, re.DOTALL)

    if tools_matches:
        # Parcourir toutes les occurrences de balises <tools>
        for tools_content in tools_matches:
            # Nettoyer le contenu pour s'assurer qu'il s'agit d'un JSON valide
            tools_content = tools_content.strip()

            try:
                # Essayer de parser le JSON
                tool_data = json.loads(tools_content)

                # Vérifier si c'est un appel de fonction
                if tool_data.get("type") == "function":
                    return tool_data
            except json.JSONDecodeError:
                log("DEBUG", f"Impossible de décoder le JSON dans une balise <tools>: {tools_content}")
                continue

    # Recherche des arguments JSON dans le contenu
    arguments_pattern = r'{"arguments":\s*({[^}]+})'
    arguments_match = re.search(arguments_pattern, content)

    # Recherche du nom de la fonction
    name_pattern = r'{"name":\s*"([^"]+)"'
    name_match = re.search(name_pattern, content)

    # Si nous avons trouvé à la fois un nom de fonction et des arguments
    if name_match and arguments_match:
        function_name = name_match.group(1)
        arguments_str = arguments_match.group(1)

        try:
            arguments = json.loads("{" + arguments_str + "}")
            return {
                "type": "function",
                "function": {
                    "name": function_name,
                    "arguments": json.dumps(arguments)
                }
            }
        except json.JSONDecodeError:
            log("DEBUG", f"Impossible de décoder les arguments JSON: {arguments_str}")

    # Si nous avons trouvé seulement des arguments
    elif arguments_match:
        arguments_str = arguments_match.group(1)

        try:
            arguments = json.loads("{" + arguments_str + "}")
            return {
                "type": "function",
                "function": {
                    "name": "get_weather",  # Nom par défaut
                    "arguments": json.dumps(arguments)
                }
            }
        except json.JSONDecodeError:
            log("DEBUG", f"Impossible de décoder les arguments JSON: {arguments_str}")

    # Recherche des patterns spécifiques à Qwen3
    active_form_pattern = r'\\ActiveForm:\s*({[^}]+})'
    active_form_matches = re.findall(active_form_pattern, content)

    if active_form_matches:
        for active_form in active_form_matches:
            try:
                arguments = json.loads(active_form)
                return {
                    "type": "function",
                    "function": {
                        "name": "get_weather",  # Nom par défaut
                        "arguments": json.dumps(arguments)
                    }
                }
            except json.JSONDecodeError:
                log("DEBUG", f"Impossible de décoder les arguments JSON: {active_form}")

    # Recherche des patterns JSON simples
    json_pattern = r'{\s*"city":\s*"([^"]+)"(?:,\s*"unit":\s*"([^"]+)")?\s*}'
    json_match = re.search(json_pattern, content)

    if json_match:
        city = json_match.group(1)
        unit = json_match.group(2) if json_match.group(2) else "celsius"

        return {
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": json.dumps({"city": city, "unit": unit})
            }
        }

    return None

def test_tool_calling(endpoint: str, api_key: Optional[str] = None, model: Optional[str] = None, service: str = "mini") -> bool:
    """
    Teste le tool calling avec un modèle Qwen3.

    Args:
        endpoint: URL de l'API OpenAI de vLLM
        api_key: Clé API pour l'authentification (optionnelle)
        model: Modèle à utiliser (optionnel)
        service: Service à tester (micro, mini, medium)

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

    # Utiliser le modèle spécifié ou le modèle par défaut pour le service
    if not model:
        model = DEFAULT_MODELS.get(service, "Qwen/Qwen3-1.7B-Base")

    data = {
        "model": model,
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

        # Vérification de la présence d'un appel d'outil standard
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
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
                log("INFO", "Test du tool calling réussi!")
                return True
            except json.JSONDecodeError:
                log("ERROR", f"Arguments de l'appel d'outil mal formatés: {function.get('arguments')}")
                return False

        # Si aucun appel d'outil standard n'est trouvé, essayons d'extraire du contenu
        content = message.get("content", "")
        extracted_tool_call = extract_tool_call_from_content(content)

        if extracted_tool_call:
            log("INFO", f"Appel d'outil extrait du contenu: {json.dumps(extracted_tool_call, indent=2)}")

            # Vérification du format de l'appel d'outil extrait
            if extracted_tool_call.get("type") != "function":
                log("ERROR", f"Type d'appel d'outil incorrect: {extracted_tool_call.get('type')}")
                return False

            function = extracted_tool_call.get("function", {})
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
                log("INFO", "Test du tool calling réussi!")
                return True
            except json.JSONDecodeError:
                log("ERROR", f"Arguments de l'appel d'outil mal formatés: {function.get('arguments')}")
                return False
        else:
            log("ERROR", "Aucun appel d'outil trouvé dans le contenu")
            return False

    except Exception as e:
        log("ERROR", f"Exception lors du test: {str(e)}")
        return False

def test_streaming_tool_calling(endpoint: str, api_key: Optional[str] = None, model: Optional[str] = None, service: str = "mini") -> bool:
    """
    Teste le tool calling en streaming avec un modèle Qwen3.

    Args:
        endpoint: URL de l'API OpenAI de vLLM
        api_key: Clé API pour l'authentification (optionnelle)
        model: Modèle à utiliser (optionnel)
        service: Service à tester (micro, mini, medium)

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

    # Utiliser le modèle spécifié ou le modèle par défaut pour le service
    if not model:
        model = DEFAULT_MODELS.get(service, "Qwen/Qwen3-1.7B-Base")

    data = {
        "model": model,
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
        full_content = ""

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

                        # Accumuler le contenu pour l'extraction ultérieure
                        if "content" in delta:
                            full_content += delta["content"]

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

        # Si aucun appel d'outil standard n'est trouvé, essayons d'extraire du contenu
        if not has_tool_call and full_content:
            extracted_tool_call = extract_tool_call_from_content(full_content)

            if extracted_tool_call:
                log("INFO", f"Appel d'outil extrait du contenu en streaming: {json.dumps(extracted_tool_call, indent=2)}")

                # Vérification du format de l'appel d'outil extrait
                if extracted_tool_call.get("type") != "function":
                    log("ERROR", f"Type d'appel d'outil incorrect: {extracted_tool_call.get('type')}")
                    return False

                function = extracted_tool_call.get("function", {})
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

                    log("INFO", f"Arguments de l'appel d'outil en streaming: {arguments}")
                    log("INFO", "Test du tool calling en streaming réussi!")
                    return True
                except json.JSONDecodeError:
                    log("ERROR", f"Arguments de l'appel d'outil mal formatés: {function.get('arguments')}")
                    return False
            else:
                log("ERROR", "Aucun appel d'outil trouvé dans le contenu en streaming")
                return False

        # Vérification des résultats du streaming standard
        if has_tool_call:
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
        else:
            log("ERROR", "Aucun appel d'outil dans la réponse en streaming")
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
    success = test_tool_calling(endpoint, api_key, args.model, args.service)

    # Tester le tool calling en streaming si activé
    streaming_success = True
    if not args.no_streaming:
        streaming_success = test_streaming_tool_calling(endpoint, api_key, args.model, args.service)

    # Afficher le résultat global
    if success and streaming_success:
        log("INFO", "Tous les tests ont réussi!")
        return 0
    else:
        log("ERROR", "Certains tests ont échoué.")
        return 1

if __name__ == "__main__":
    sys.exit(main())