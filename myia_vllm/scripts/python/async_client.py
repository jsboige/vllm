#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Client asynchrone pour interagir avec l'API vLLM.
"""

import aiohttp
import json
from typing import Dict, Optional

from .utils import log

class AsyncVLLMClient:
    """Un client asynchrone simple pour l'API vLLM."""

    def __init__(self, endpoint: str, api_key: Optional[str] = None):
        """
        Initialise le client.
        
        Args:
            endpoint: URL de base de l'API vLLM (ex: http://localhost:5000/v1)
            api_key: Clé API pour l'authentification (optionnelle)
        """
        self.endpoint = endpoint
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json"
        }
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    async def chat_completion(self, **kwargs) -> Optional[Dict]:
        """
        Effectue une requête de chat completion asynchrone.
        
        Args:
            **kwargs: Arguments à passer à l'API (model, messages, etc.)
        
        Returns:
            Un dictionnaire contenant la réponse de l'API, ou None en cas d'erreur.
        """
        url = f"{self.endpoint}/chat/completions"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=self.headers, json=kwargs, timeout=60) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        log("ERROR", f"Erreur de l'API (chat_completion): {response.status} - {error_text}")
                        return None
            except Exception as e:
                log("ERROR", f"Exception lors de la requête (chat_completion): {e}")
                return None
