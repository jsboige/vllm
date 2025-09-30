#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Module contenant des parsers spécifiques pour les réponses des modèles.
"""

import json
import re
from typing import Dict, Optional

from .utils import log

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