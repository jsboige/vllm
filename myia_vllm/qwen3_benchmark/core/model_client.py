#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module définissant le client API unifié pour interagir avec les modèles Qwen3.

Ce module fournit une interface unifiée pour interagir avec les différentes API
des modèles Qwen3, qu'ils soient déployés localement ou sur des endpoints externes.
"""

import json
import time
import logging
import requests
from typing import Dict, Any, List, Optional, Union, Tuple
from urllib.parse import urljoin

from .utils import setup_logger, measure_execution_time


class ModelClient:
    """
    Client API unifié pour interagir avec les modèles Qwen3.
    
    Cette classe fournit une interface unifiée pour interagir avec les différentes
    API des modèles Qwen3, en gérant les erreurs, les timeouts et en collectant
    des métriques de performance.
    
    Attributes:
        url (str): URL de base de l'API
        api_key (str): Clé API pour l'authentification
        model (str): Nom du modèle à utiliser
        timeout (int): Timeout pour les requêtes API en secondes
        logger (logging.Logger): Logger pour les messages du client
    """
    
    def __init__(self, url: str, api_key: str, model: str, timeout: int = 120):
        """
        Initialise un nouveau client API pour les modèles Qwen3.
        
        Args:
            url (str): URL de base de l'API
            api_key (str): Clé API pour l'authentification
            model (str): Nom du modèle à utiliser
            timeout (int, optional): Timeout pour les requêtes API en secondes
        """
        self.url = url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.logger = setup_logger("model_client")
        
        # Vérifier que l'URL se termine par /v1 pour la compatibilité OpenAI
        if not self.url.endswith('/v1'):
            self.url = f"{self.url}/v1"
        
        self.logger.info(f"Client API initialisé pour le modèle {model} sur {url}")
    
    def _make_request(self, endpoint: str, payload: Dict[str, Any], method: str = "POST") -> Dict[str, Any]:
        """
        Effectue une requête à l'API avec gestion des erreurs et des timeouts.
        
        Args:
            endpoint (str): Endpoint API à appeler (sans le /v1 initial)
            payload (Dict[str, Any]): Données à envoyer dans la requête
            method (str, optional): Méthode HTTP à utiliser
            
        Returns:
            Dict[str, Any]: Réponse de l'API
            
        Raises:
            Exception: Si la requête échoue ou timeout
        """
        # Construire l'URL complète
        url = urljoin(self.url, endpoint.lstrip('/'))
        
        # Préparer les headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # Effectuer la requête avec gestion des erreurs
        try:
            self.logger.debug(f"Envoi de requête à {url}")
            
            if method.upper() == "POST":
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )
            elif method.upper() == "GET":
                response = requests.get(
                    url,
                    headers=headers,
                    params=payload,
                    timeout=self.timeout
                )
            else:
                raise ValueError(f"Méthode HTTP non supportée: {method}")
            
            # Vérifier le code de statut
            response.raise_for_status()
            
            # Parser la réponse JSON
            return response.json()
            
        except requests.exceptions.Timeout:
            self.logger.error(f"Timeout lors de la requête à {url} après {self.timeout} secondes")
            raise Exception(f"Timeout lors de la requête à l'API après {self.timeout} secondes")
            
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"Erreur HTTP {e.response.status_code} lors de la requête à {url}: {e}")
            
            # Essayer de récupérer les détails de l'erreur dans la réponse
            error_detail = ""
            try:
                error_json = e.response.json()
                error_detail = error_json.get("error", {}).get("message", str(e))
            except:
                error_detail = str(e)
            
            raise Exception(f"Erreur HTTP {e.response.status_code}: {error_detail}")
            
        except Exception as e:
            self.logger.error(f"Erreur lors de la requête à {url}: {str(e)}")
            raise Exception(f"Erreur lors de la requête à l'API: {str(e)}")
    
    def models(self) -> Dict[str, Any]:
        """
        Récupère la liste des modèles disponibles.
        
        Returns:
            Dict[str, Any]: Liste des modèles disponibles
        """
        self.logger.info("Récupération de la liste des modèles")
        return self._make_request("/models", {}, method="GET")
    
    def completions(self, prompt: str, max_tokens: int = 100, temperature: float = 0.7,
                   top_p: float = 1.0, n: int = 1, stop: Optional[List[str]] = None,
                   **kwargs) -> Dict[str, Any]:
        """
        Génère une complétion de texte à partir d'un prompt.
        
        Args:
            prompt (str): Texte d'entrée pour la génération
            max_tokens (int, optional): Nombre maximum de tokens à générer
            temperature (float, optional): Température pour l'échantillonnage
            top_p (float, optional): Valeur de top-p pour l'échantillonnage nucleus
            n (int, optional): Nombre de complétions à générer
            stop (List[str], optional): Séquences qui arrêtent la génération
            **kwargs: Paramètres supplémentaires pour l'API
            
        Returns:
            Dict[str, Any]: Résultat de la génération
        """
        self.logger.info(f"Génération de complétion avec prompt de {len(prompt)} caractères")
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "n": n
        }
        
        if stop:
            payload["stop"] = stop
        
        # Ajouter les paramètres supplémentaires
        payload.update(kwargs)
        
        return self._make_request("/completions", payload)
    
    def chat(self, messages: List[Dict[str, str]], max_tokens: int = 100,
             temperature: float = 0.7, top_p: float = 1.0, n: int = 1,
             stop: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
        """
        Génère une réponse de chat à partir d'une liste de messages.
        
        Args:
            messages (List[Dict[str, str]]): Liste des messages de la conversation
            max_tokens (int, optional): Nombre maximum de tokens à générer
            temperature (float, optional): Température pour l'échantillonnage
            top_p (float, optional): Valeur de top-p pour l'échantillonnage nucleus
            n (int, optional): Nombre de complétions à générer
            stop (List[str], optional): Séquences qui arrêtent la génération
            **kwargs: Paramètres supplémentaires pour l'API
            
        Returns:
            Dict[str, Any]: Résultat de la génération
        """
        self.logger.info(f"Génération de chat avec {len(messages)} messages")
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "n": n
        }
        
        if stop:
            payload["stop"] = stop
        
        # Ajouter les paramètres supplémentaires
        payload.update(kwargs)
        
        return self._make_request("/chat/completions", payload)
    
    def embeddings(self, texts: Union[str, List[str]], **kwargs) -> Dict[str, Any]:
        """
        Génère des embeddings pour un ou plusieurs textes.
        
        Args:
            texts (Union[str, List[str]]): Texte(s) pour lesquels générer des embeddings
            **kwargs: Paramètres supplémentaires pour l'API
            
        Returns:
            Dict[str, Any]: Embeddings générés
        """
        if isinstance(texts, str):
            texts = [texts]
        
        self.logger.info(f"Génération d'embeddings pour {len(texts)} textes")
        
        payload = {
            "model": self.model,
            "input": texts
        }
        
        # Ajouter les paramètres supplémentaires
        payload.update(kwargs)
        
        return self._make_request("/embeddings", payload)
    
    def tool_calling(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]],
                    max_tokens: int = 100, temperature: float = 0.7, top_p: float = 1.0,
                    n: int = 1, stop: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
        """
        Génère une réponse avec appel d'outils à partir d'une liste de messages.
        
        Args:
            messages (List[Dict[str, str]]): Liste des messages de la conversation
            tools (List[Dict[str, Any]]): Liste des outils disponibles
            max_tokens (int, optional): Nombre maximum de tokens à générer
            temperature (float, optional): Température pour l'échantillonnage
            top_p (float, optional): Valeur de top-p pour l'échantillonnage nucleus
            n (int, optional): Nombre de complétions à générer
            stop (List[str], optional): Séquences qui arrêtent la génération
            **kwargs: Paramètres supplémentaires pour l'API
            
        Returns:
            Dict[str, Any]: Résultat de la génération avec appels d'outils
        """
        self.logger.info(f"Génération avec appel d'outils pour {len(messages)} messages et {len(tools)} outils")
        
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "n": n
        }
        
        if stop:
            payload["stop"] = stop
        
        # Ajouter les paramètres supplémentaires
        payload.update(kwargs)
        
        return self._make_request("/chat/completions", payload)
    
    def check_health(self) -> Tuple[bool, str]:
        """
        Vérifie la santé de l'API en effectuant une requête simple.
        
        Returns:
            Tuple[bool, str]: (Statut de santé, Message)
        """
        self.logger.info("Vérification de la santé de l'API")
        
        try:
            # Essayer de récupérer la liste des modèles
            response = self.models()
            
            # Vérifier que le modèle actuel est dans la liste
            models = [model.get("id") for model in response.get("data", [])]
            
            if self.model in models:
                return True, f"API en ligne, modèle {self.model} disponible"
            else:
                return False, f"API en ligne, mais le modèle {self.model} n'est pas disponible"
            
        except Exception as e:
            return False, f"API inaccessible: {str(e)}"