#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Module contenant les données de test partagées (prompts, outils, etc.).
"""

# Définition de l'outil de test pour la météo
WEATHER_TOOL = [
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

# Message pour déclencher l'utilisation de l'outil météo
WEATHER_MESSAGES = [
    {"role": "system", "content": "Vous êtes un assistant utile qui utilise des outils pour répondre aux questions."},
    {"role": "user", "content": "Quelle est la météo à Paris aujourd'hui?"}
]

# Message pour déclencher le raisonnement
REASONING_MESSAGES = [
    {"role": "system", "content": "Vous êtes un assistant utile qui utilise le raisonnement pour résoudre des problèmes."},
    {"role": "user", "content": """
    Résous ce problème étape par étape:
    
    Jean a 5 pommes. Marie lui en donne 3 de plus.
    Jean mange 2 pommes puis donne la moitié des pommes restantes à Pierre.
    Combien de pommes Jean a-t-il maintenant?
    """}
]