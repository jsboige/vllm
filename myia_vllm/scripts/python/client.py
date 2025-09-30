#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Client pour interagir avec l'API OpenAI de vLLM.
"""

import json
from typing import Dict, Optional

import requests

from .utils import log

class VLLMClient:
    """Un client simple pour l'API vLLM."""

    def __init__(self, endpoint: str, api_key: Optional[str] = None):
        """
        Initialise le client.
        
        Args:
            endpoint: URL de base de l'API (ex: http://localhost:5000/v1)
            api_key: Clé API pour l'authentification (optionnelle)
        """
        self.endpoint = endpoint
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json"
        }
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    def _send_request(self, method: str, path: str, **kwargs) -> requests.Response:
        """
        Méthode interne pour envoyer des requêtes.
        
        Args:
            method: Méthode HTTP (GET, POST, etc.)
            path: Chemin de l'API (ex: /models)
            **kwargs: Arguments supplémentaires pour requests
        
        Returns:
            requests.Response: La réponse de la requête
        
        Raises:
            requests.exceptions.RequestException: En cas d'erreur de requête
        """
        url = f"{self.endpoint}{path}"
        log("DEBUG", f"Envoi de la requête {method} à {url}...")
        log("DEBUG", f"Données: {json.dumps(kwargs.get('json', {}), indent=2, ensure_ascii=False)}")
        
        response = requests.request(
            method,
            url,
            headers=self.headers,
            timeout=30,
            **kwargs
        )
        response.raise_for_status()  # Lève une exception pour les codes d'erreur HTTP
        return response

    def get_models(self) -> Dict:
        """Récupère la liste des modèles disponibles."""
        log("INFO", "Récupération de la liste des modèles...")
        response = self._send_request("GET", "/models")
        return response.json()

    def chat_completion(self, **kwargs) -> Dict:
        """
        Effectue une requête de chat completion.
        
        Args:
            **kwargs: Arguments pour la requête de chat completion (model, messages, etc.)
        
        Returns:
            Dict: La réponse JSON de l'API
        """
        log("INFO", "Envoi d'une requête de chat completion...")
        response = self._send_request("POST", "/chat/completions", json=kwargs)
        return response.json()

    def stream_chat_completion(self, **kwargs) -> requests.Response:
        """
        Effectue une requête de chat completion en streaming.
        
        Args:
            **kwargs: Arguments pour la requête de chat completion (model, messages, etc.)
        
        Returns:
            requests.Response: La réponse en streaming
        """
        log("INFO", "Envoi d'une requête de chat completion en streaming...")
        kwargs["stream"] = True
        return self._send_request("POST", "/chat/completions", json=kwargs, stream=True)
