#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module implémentant les benchmarks de comparaison des API Qwen3.

Ce module fournit des classes et fonctions pour comparer les performances
des différentes API (locale vs externe) des modèles Qwen3.
"""

import time
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Tuple

from ..core import BenchmarkRunner, APIBenchmarkRunner, ModelClient
from ..core.utils import measure_execution_time, format_time, setup_logger
from ..config import get_model_endpoint


class APIComparisonBenchmark(APIBenchmarkRunner):
    """
    Classe pour les benchmarks de comparaison des API Qwen3.
    
    Cette classe étend APIBenchmarkRunner pour comparer les performances
    entre différentes API (locale vs externe) des modèles Qwen3.
    
    Attributes:
        model_name (str): Nom du modèle à tester ('micro', 'mini', 'medium')
        config (Dict[str, Any]): Configuration complète du benchmark
        client (ModelClient): Client pour interagir avec l'API du modèle
        external_client (ModelClient): Client pour interagir avec l'API externe
        results (Dict[str, Any]): Résultats du benchmark
        logger (logging.Logger): Logger pour les messages de benchmark
    """
    
    def __init__(self, model_name: str, external_endpoint: Dict[str, str], 
                 config_override: Optional[Dict[str, Any]] = None):
        """
        Initialise un nouveau benchmark de comparaison d'API.
        
        Args:
            model_name (str): Nom du modèle à tester ('micro', 'mini', 'medium')
            external_endpoint (Dict[str, str]): Configuration de l'endpoint externe
            config_override (Dict[str, Any], optional): Paramètres de configuration à remplacer
        """
        super().__init__(model_name, config_override)
        
        # Initialiser le client API externe
        self.logger.info(f"Initialisation du client API externe")
        self.external_client = ModelClient(
            url=external_endpoint.get("url", ""),
            api_key=external_endpoint.get("api_key", ""),
            model=external_endpoint.get("model", "")
        )
        
        # Stocker les informations sur l'endpoint externe
        self.external_endpoint_info = external_endpoint
        
        # Préparer les structures pour stocker les résultats de comparaison
        self.comparison_results = {
            "local": {},
            "external": {},
            "difference": {}
        }
    
    def setup(self) -> None:
        """
        Configure le benchmark de comparaison d'API.
        """
        self.logger.info("Configuration du benchmark de comparaison d'API")
        
        # Appeler la méthode setup de la classe parente
        super().setup()
        
        # Configuration spécifique à la comparaison d'API
        self.api_types = ["completions", "chat", "embeddings", "tool_calling"]
        
        # Préparer les structures pour stocker les résultats de comparaison
        for api_type in self.api_types:
            self.comparison_results["local"][api_type] = []
            self.comparison_results["external"][api_type] = []
    
    def run(self) -> Dict[str, Any]:
        """
        Exécute le benchmark de comparaison d'API.
        
        Returns:
            Dict[str, Any]: Résultats du benchmark
        """
        self.logger.info(f"Exécution du benchmark de comparaison d'API")
        
        # Tester l'API locale (utilise la méthode run de la classe parente)
        self.logger.info("Test de l'API locale")
        local_results = super().run()
        self.comparison_results["local"] = local_results.get("api_results", {})
        
        # Sauvegarder temporairement le client local
        local_client = self.client
        
        try:
            # Remplacer le client par le client externe
            self.client = self.external_client
            
            # Tester l'API externe
            self.logger.info("Test de l'API externe")
            self.api_results = {
                "completions": [],
                "chat": [],
                "embeddings": [],
                "tool_calling": []
            }
            
            # Exécuter les mêmes tests avec le client externe
            self._test_completions_api()
            self._test_chat_api()
            self._test_embeddings_api()
            self._test_tool_calling_api()
            
            # Stocker les résultats externes
            self.comparison_results["external"] = self.api_results
            
        finally:
            # Restaurer le client local
            self.client = local_client
        
        return {"comparison_results": self.comparison_results}
    
    def analyze(self) -> Dict[str, Any]:
        """
        Analyse les résultats du benchmark de comparaison d'API.
        
        Returns:
            Dict[str, Any]: Analyse des résultats
        """
        self.logger.info("Analyse des résultats du benchmark de comparaison d'API")
        
        analysis = {
            "summary": {},
            "api_comparison": {},
            "recommendations": []
        }
        
        # Analyser les performances pour chaque type d'API
        for api_type in self.api_types:
            local_results = self.comparison_results["local"].get(api_type, [])
            external_results = self.comparison_results["external"].get(api_type, [])
            
            if not local_results or not external_results:
                continue
            
            # Calculer les temps d'exécution moyens
            local_times = [r.get("execution_time", 0) for r in local_results]
            external_times = [r.get("execution_time", 0) for r in external_results]
            
            if local_times and external_times:
                local_avg = sum(local_times) / len(local_times)
                external_avg = sum(external_times) / len(external_times)
                
                # Calculer la différence en pourcentage
                if external_avg > 0:
                    diff_percent = ((local_avg - external_avg) / external_avg) * 100
                else:
                    diff_percent = 0
                
                # Déterminer quelle API est plus rapide
                faster_api = "locale" if local_avg < external_avg else "externe"
                
                # Stocker les métriques de comparaison
                analysis["api_comparison"][api_type] = {
                    "local_avg_time": local_avg,
                    "external_avg_time": external_avg,
                    "local_avg_time_formatted": format_time(local_avg),
                    "external_avg_time_formatted": format_time(external_avg),
                    "difference_percent": abs(diff_percent),
                    "faster_api": faster_api
                }
                
                # Ajouter des recommandations basées sur les résultats
                if abs(diff_percent) > 20:  # Différence significative (>20%)
                    analysis["recommendations"].append(
                        f"Pour l'API {api_type}, utiliser l'API {faster_api} qui est "
                        f"{abs(diff_percent):.1f}% plus rapide."
                    )
        
        # Calculer les métriques globales
        local_all_times = []
        external_all_times = []
        
        for api_type in self.api_types:
            local_results = self.comparison_results["local"].get(api_type, [])
            external_results = self.comparison_results["external"].get(api_type, [])
            
            local_all_times.extend([r.get("execution_time", 0) for r in local_results])
            external_all_times.extend([r.get("execution_time", 0) for r in external_results])
        
        if local_all_times and external_all_times:
            local_global_avg = sum(local_all_times) / len(local_all_times)
            external_global_avg = sum(external_all_times) / len(external_all_times)
            
            # Calculer la différence globale en pourcentage
            if external_global_avg > 0:
                global_diff_percent = ((local_global_avg - external_global_avg) / external_global_avg) * 100
            else:
                global_diff_percent = 0
            
            # Déterminer quelle API est globalement plus rapide
            global_faster_api = "locale" if local_global_avg < external_global_avg else "externe"
            
            analysis["summary"] = {
                "local_global_avg_time": local_global_avg,
                "external_global_avg_time": external_global_avg,
                "local_global_avg_time_formatted": format_time(local_global_avg),
                "external_global_avg_time_formatted": format_time(external_global_avg),
                "global_difference_percent": abs(global_diff_percent),
                "global_faster_api": global_faster_api
            }
            
            # Ajouter une recommandation globale
            analysis["recommendations"].append(
                f"Globalement, l'API {global_faster_api} est {abs(global_diff_percent):.1f}% plus rapide "
                f"que l'API {'externe' if global_faster_api == 'locale' else 'locale'}."
            )
        
        # Mettre à jour les métriques dans les résultats
        self.results["metrics"] = {
            "local_avg_time": local_global_avg if local_all_times else 0,
            "external_avg_time": external_global_avg if external_all_times else 0,
            "difference_percent": abs(global_diff_percent) if local_all_times and external_all_times else 0
        }
        
        return analysis
    
    def compare_api_latency(self, api_type: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Compare la latence entre l'API locale et externe pour un prompt spécifique.
        
        Args:
            api_type (str): Type d'API à tester ('completions', 'chat', etc.)
            prompt (str): Prompt à utiliser pour le test
            **kwargs: Paramètres supplémentaires pour l'API
            
        Returns:
            Dict[str, Any]: Résultats de la comparaison
        """
        self.logger.info(f"Comparaison de latence pour l'API {api_type}")
        
        results = {
            "local": {},
            "external": {},
            "difference": {}
        }
        
        # Tester l'API locale
        try:
            if api_type == "completions":
                local_result, local_time = measure_execution_time(
                    lambda: self.client.completions(prompt=prompt, **kwargs)
                )
            elif api_type == "chat":
                local_result, local_time = measure_execution_time(
                    lambda: self.client.chat(messages=[{"role": "user", "content": prompt}], **kwargs)
                )
            else:
                raise ValueError(f"Type d'API non supporté: {api_type}")
            
            results["local"] = {
                "execution_time": local_time,
                "execution_time_formatted": format_time(local_time),
                "tokens_generated": local_result.get("usage", {}).get("completion_tokens", 0)
            }
        except Exception as e:
            self.logger.error(f"Erreur lors du test de l'API locale: {str(e)}")
            results["local"] = {"error": str(e)}
        
        # Tester l'API externe
        try:
            if api_type == "completions":
                external_result, external_time = measure_execution_time(
                    lambda: self.external_client.completions(prompt=prompt, **kwargs)
                )
            elif api_type == "chat":
                external_result, external_time = measure_execution_time(
                    lambda: self.external_client.chat(messages=[{"role": "user", "content": prompt}], **kwargs)
                )
            else:
                raise ValueError(f"Type d'API non supporté: {api_type}")
            
            results["external"] = {
                "execution_time": external_time,
                "execution_time_formatted": format_time(external_time),
                "tokens_generated": external_result.get("usage", {}).get("completion_tokens", 0)
            }
        except Exception as e:
            self.logger.error(f"Erreur lors du test de l'API externe: {str(e)}")
            results["external"] = {"error": str(e)}
        
        # Calculer la différence
        if "error" not in results["local"] and "error" not in results["external"]:
            local_time = results["local"]["execution_time"]
            external_time = results["external"]["execution_time"]
            
            diff_time = local_time - external_time
            if external_time > 0:
                diff_percent = (diff_time / external_time) * 100
            else:
                diff_percent = 0
            
            results["difference"] = {
                "time_difference": diff_time,
                "time_difference_formatted": format_time(abs(diff_time)),
                "percent_difference": diff_percent,
                "faster_api": "locale" if diff_time < 0 else "externe"
            }
        
        return results