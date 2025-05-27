#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module définissant la classe de base abstraite pour tous les benchmarks Qwen3.

Ce module fournit une classe abstraite qui sert de base pour tous les types
de benchmarks spécifiques (API, contexte, document QA, etc.).
"""

import os
import json
import time
import logging
import abc
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Tuple
from pathlib import Path

from ..config import (
    load_config,
    get_model_config,
    get_model_endpoint,
    get_test_parameters,
    get_output_paths
)
from .model_client import ModelClient
from .utils import measure_execution_time, setup_logger, format_time


class BenchmarkRunner(abc.ABC):
    """
    Classe abstraite de base pour tous les benchmarks Qwen3.
    
    Cette classe fournit l'infrastructure commune pour initialiser, exécuter
    et analyser les benchmarks sur les modèles Qwen3.
    
    Attributes:
        model_name (str): Nom du modèle à tester ('micro', 'mini', 'medium')
        config (Dict[str, Any]): Configuration complète du benchmark
        client (ModelClient): Client pour interagir avec l'API du modèle
        results (Dict[str, Any]): Résultats du benchmark
        logger (logging.Logger): Logger pour les messages de benchmark
    """
    
    def __init__(self, model_name: str, config_override: Optional[Dict[str, Any]] = None):
        """
        Initialise un nouveau benchmark runner.
        
        Args:
            model_name (str): Nom du modèle à tester ('micro', 'mini', 'medium')
            config_override (Dict[str, Any], optional): Paramètres de configuration à remplacer
        
        Raises:
            ValueError: Si le modèle spécifié n'est pas valide
        """
        self.model_name = model_name
        self.logger = setup_logger(f"benchmark_{model_name}")
        
        # Charger la configuration
        self.logger.info(f"Initialisation du benchmark pour le modèle {model_name}")
        self.config = self._load_configuration(config_override)
        
        # Initialiser le client API
        endpoint_config = get_model_endpoint(model_name)
        self.client = ModelClient(
            url=endpoint_config.get("url", ""),
            api_key=endpoint_config.get("api_key", ""),
            model=endpoint_config.get("model", "")
        )
        
        # Initialiser le dictionnaire de résultats
        self.results = {
            "model": model_name,
            "timestamp": datetime.now().isoformat(),
            "config": self.config,
            "metrics": {},
            "errors": []
        }
    
    def _load_configuration(self, config_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Charge la configuration du benchmark en combinant les paramètres par défaut
        et les remplacements spécifiés.
        
        Args:
            config_override (Dict[str, Any], optional): Paramètres de configuration à remplacer
            
        Returns:
            Dict[str, Any]: Configuration complète du benchmark
        """
        # Charger la configuration du modèle
        model_config = get_model_config(self.model_name)
        
        # Charger les paramètres de test généraux
        test_params = get_test_parameters()
        
        # Combiner les configurations
        config = {
            "model_info": model_config.get("model_info", {}),
            "endpoint": model_config.get("endpoint", {}),
            "test_parameters": test_params
        }
        
        # Appliquer les remplacements de configuration
        if config_override:
            self.logger.info("Application des remplacements de configuration")
            
            # Mise à jour récursive des paramètres
            def update_recursive(target, source):
                for key, value in source.items():
                    if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                        update_recursive(target[key], value)
                    else:
                        target[key] = value
            
            update_recursive(config, config_override)
        
        return config
    
    @abc.abstractmethod
    def setup(self) -> None:
        """
        Configure le benchmark avant l'exécution.
        
        Cette méthode doit être implémentée par les sous-classes pour
        préparer les données et ressources nécessaires au benchmark.
        """
        pass
    
    @abc.abstractmethod
    def run(self) -> Dict[str, Any]:
        """
        Exécute le benchmark.
        
        Cette méthode doit être implémentée par les sous-classes pour
        exécuter les tests spécifiques au type de benchmark.
        
        Returns:
            Dict[str, Any]: Résultats du benchmark
        """
        pass
    
    @abc.abstractmethod
    def analyze(self) -> Dict[str, Any]:
        """
        Analyse les résultats du benchmark.
        
        Cette méthode doit être implémentée par les sous-classes pour
        analyser les résultats bruts et calculer des métriques pertinentes.
        
        Returns:
            Dict[str, Any]: Métriques et analyses du benchmark
        """
        pass
    
    def execute(self) -> Dict[str, Any]:
        """
        Exécute le benchmark complet (setup, run, analyze).
        
        Cette méthode orchestre l'exécution complète du benchmark
        et gère la mesure du temps d'exécution.
        
        Returns:
            Dict[str, Any]: Résultats complets du benchmark
        """
        start_time = time.time()
        
        try:
            self.logger.info("Démarrage du benchmark")
            
            # Étape 1: Configuration
            self.logger.info("Configuration du benchmark")
            self.setup()
            
            # Étape 2: Exécution
            self.logger.info("Exécution du benchmark")
            run_results = self.run()
            self.results.update(run_results)
            
            # Étape 3: Analyse
            self.logger.info("Analyse des résultats")
            analysis = self.analyze()
            self.results["analysis"] = analysis
            
        except Exception as e:
            self.logger.error(f"Erreur lors de l'exécution du benchmark: {str(e)}", exc_info=True)
            self.results["errors"].append({
                "phase": "execution",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
        
        # Calculer le temps total d'exécution
        total_time = time.time() - start_time
        self.results["execution_time"] = total_time
        self.results["execution_time_formatted"] = format_time(total_time)
        
        self.logger.info(f"Benchmark terminé en {format_time(total_time)}")
        
        return self.results
    
    def save_results(self, output_path: Optional[str] = None) -> str:
        """
        Sauvegarde les résultats du benchmark dans un fichier JSON.
        
        Args:
            output_path (str, optional): Chemin où sauvegarder les résultats.
                Si non spécifié, utilise le chemin par défaut de la configuration.
                
        Returns:
            str: Chemin du fichier de résultats
        """
        # Déterminer le chemin de sortie
        if not output_path:
            paths = get_output_paths()
            results_dir = paths.get("results_dir", "results")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"qwen3_{self.model_name}_benchmark_{timestamp}.json"
            output_path = os.path.join(results_dir, filename)
        
        # Créer le répertoire si nécessaire
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Sauvegarder les résultats
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Résultats sauvegardés dans {output_path}")
            return output_path
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la sauvegarde des résultats: {str(e)}")
            return ""
    
    def generate_report(self, output_path: Optional[str] = None) -> str:
        """
        Génère un rapport Markdown à partir des résultats du benchmark.
        
        Args:
            output_path (str, optional): Chemin où sauvegarder le rapport.
                Si non spécifié, utilise le chemin par défaut de la configuration.
                
        Returns:
            str: Chemin du fichier de rapport
        """
        # Déterminer le chemin de sortie
        if not output_path:
            paths = get_output_paths()
            results_dir = paths.get("results_dir", "results")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"qwen3_{self.model_name}_benchmark_report_{timestamp}.md"
            output_path = os.path.join(results_dir, filename)
        
        # Créer le répertoire si nécessaire
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Générer le rapport
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                # En-tête du rapport
                f.write(f"# Rapport de benchmark Qwen3 {self.model_name.upper()}\n\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                # Informations sur le modèle
                f.write("## Informations sur le modèle\n\n")
                model_info = self.config.get("model_info", {})
                f.write(f"- **Modèle**: {model_info.get('name', self.model_name)}\n")
                f.write(f"- **Taille**: {model_info.get('size', 'N/A')}\n")
                f.write(f"- **Quantization**: {model_info.get('quantization', 'N/A')}\n")
                f.write(f"- **Description**: {model_info.get('description', 'N/A')}\n\n")
                
                # Configuration du test
                f.write("## Configuration du test\n\n")
                test_params = self.config.get("test_parameters", {})
                f.write(f"- **Nombre d'itérations**: {test_params.get('num_iterations', 'N/A')}\n")
                f.write(f"- **Timeout**: {test_params.get('request_timeout', 'N/A')} secondes\n\n")
                
                # Résultats
                f.write("## Résultats\n\n")
                f.write(f"- **Temps d'exécution total**: {self.results.get('execution_time_formatted', 'N/A')}\n\n")
                
                # Métriques
                f.write("### Métriques\n\n")
                metrics = self.results.get("metrics", {})
                if metrics:
                    f.write("| Métrique | Valeur |\n")
                    f.write("|----------|--------|\n")
                    for key, value in metrics.items():
                        f.write(f"| {key} | {value} |\n")
                else:
                    f.write("Aucune métrique disponible.\n")
                
                f.write("\n")
                
                # Analyse
                f.write("### Analyse\n\n")
                analysis = self.results.get("analysis", {})
                if analysis:
                    for section, content in analysis.items():
                        f.write(f"#### {section}\n\n")
                        if isinstance(content, dict):
                            for key, value in content.items():
                                f.write(f"- **{key}**: {value}\n")
                        elif isinstance(content, list):
                            for item in content:
                                f.write(f"- {item}\n")
                        else:
                            f.write(f"{content}\n")
                        f.write("\n")
                else:
                    f.write("Aucune analyse disponible.\n")
                
                # Erreurs
                errors = self.results.get("errors", [])
                if errors:
                    f.write("## Erreurs\n\n")
                    for error in errors:
                        f.write(f"- **Phase**: {error.get('phase', 'N/A')}\n")
                        f.write(f"- **Erreur**: {error.get('error', 'N/A')}\n")
                        f.write(f"- **Timestamp**: {error.get('timestamp', 'N/A')}\n\n")
            
            self.logger.info(f"Rapport généré dans {output_path}")
            return output_path
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la génération du rapport: {str(e)}")
class APIBenchmarkRunner(BenchmarkRunner):
    """
    Classe pour les benchmarks d'API Qwen3.
    
    Cette classe implémente les méthodes spécifiques pour tester
    les performances des API des modèles Qwen3.
    """
    
    def setup(self) -> None:
        """
        Configure le benchmark d'API.
        """
        self.logger.info("Configuration du benchmark d'API")
        # Initialisation spécifique aux benchmarks d'API
        self.iterations = self.config.get("test_parameters", {}).get("num_iterations", 3)
        self.timeout = self.config.get("test_parameters", {}).get("request_timeout", 120)
        
        # Paramètres de génération
        self.generation_params = self.config.get("test_parameters", {}).get("generation", {})
        
        # Préparer les structures pour stocker les résultats
        self.api_results = {
            "completions": [],
            "chat": [],
            "embeddings": [],
            "tool_calling": []
        }
    
    def run(self) -> Dict[str, Any]:
        """
        Exécute le benchmark d'API.
        
        Returns:
            Dict[str, Any]: Résultats du benchmark
        """
        self.logger.info(f"Exécution du benchmark d'API avec {self.iterations} itérations")
        
        # Tester l'API de complétion
        self._test_completions_api()
        
        # Tester l'API de chat
        self._test_chat_api()
        
        # Tester l'API d'embeddings (si disponible)
        self._test_embeddings_api()
        
        # Tester l'API de tool calling (si disponible)
        self._test_tool_calling_api()
        
        return {"api_results": self.api_results}
    
    def _test_completions_api(self) -> None:
        """
        Teste l'API de complétion.
        """
        self.logger.info("Test de l'API de complétion")
        
        prompt = "Qwen3 est un modèle de langage développé par "
        
        for i in range(self.iterations):
            try:
                self.logger.info(f"Itération {i+1}/{self.iterations}")
                
                # Mesurer le temps d'exécution
                result, execution_time = measure_execution_time(
                    lambda: self.client.completions(
                        prompt=prompt,
                        max_tokens=self.generation_params.get("max_tokens", 100),
                        temperature=self.generation_params.get("temperature", 0.7)
                    )
                )
                
                # Stocker les résultats
                self.api_results["completions"].append({
                    "iteration": i+1,
                    "execution_time": execution_time,
                    "tokens_generated": result.get("usage", {}).get("completion_tokens", 0),
                    "tokens_total": result.get("usage", {}).get("total_tokens", 0)
                })
                
            except Exception as e:
                self.logger.error(f"Erreur lors du test de l'API de complétion: {str(e)}")
                self.results["errors"].append({
                    "phase": "completions_api",
                    "iteration": i+1,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
    
    def _test_chat_api(self) -> None:
        """
        Teste l'API de chat.
        """
        self.logger.info("Test de l'API de chat")
        
        messages = [
            {"role": "system", "content": "Vous êtes un assistant IA utile et concis."},
            {"role": "user", "content": "Expliquez brièvement ce qu'est Qwen3."}
        ]
        
        for i in range(self.iterations):
            try:
                self.logger.info(f"Itération {i+1}/{self.iterations}")
                
                # Mesurer le temps d'exécution
                result, execution_time = measure_execution_time(
                    lambda: self.client.chat(
                        messages=messages,
                        max_tokens=self.generation_params.get("max_tokens", 100),
                        temperature=self.generation_params.get("temperature", 0.7)
                    )
                )
                
                # Stocker les résultats
                self.api_results["chat"].append({
                    "iteration": i+1,
                    "execution_time": execution_time,
                    "tokens_generated": result.get("usage", {}).get("completion_tokens", 0),
                    "tokens_total": result.get("usage", {}).get("total_tokens", 0)
                })
                
            except Exception as e:
                self.logger.error(f"Erreur lors du test de l'API de chat: {str(e)}")
                self.results["errors"].append({
                    "phase": "chat_api",
                    "iteration": i+1,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
    
    def _test_embeddings_api(self) -> None:
        """
        Teste l'API d'embeddings (si disponible).
        """
        self.logger.info("Test de l'API d'embeddings")
        
        # Vérifier si l'API d'embeddings est disponible
        if not hasattr(self.client, "embeddings"):
            self.logger.info("API d'embeddings non disponible, test ignoré")
            return
        
        texts = [
            "Qwen3 est un modèle de langage avancé.",
            "Les modèles de langage sont utilisés pour diverses tâches de NLP.",
            "L'architecture Transformer a révolutionné le traitement du langage naturel."
        ]
        
        for i in range(self.iterations):
            try:
                self.logger.info(f"Itération {i+1}/{self.iterations}")
                
                # Mesurer le temps d'exécution
                result, execution_time = measure_execution_time(
                    lambda: self.client.embeddings(texts=texts)
                )
                
                # Stocker les résultats
                self.api_results["embeddings"].append({
                    "iteration": i+1,
                    "execution_time": execution_time,
                    "num_texts": len(texts),
                    "embedding_dimensions": len(result.get("data", [{}])[0].get("embedding", [])) if result.get("data") else 0
                })
                
            except Exception as e:
                self.logger.error(f"Erreur lors du test de l'API d'embeddings: {str(e)}")
                self.results["errors"].append({
                    "phase": "embeddings_api",
                    "iteration": i+1,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
    
    def _test_tool_calling_api(self) -> None:
        """
        Teste l'API de tool calling (si disponible).
        """
        self.logger.info("Test de l'API de tool calling")
        
        # Vérifier si l'API de tool calling est disponible
        if not hasattr(self.client, "tool_calling"):
            self.logger.info("API de tool calling non disponible, test ignoré")
            return
        
        messages = [
            {"role": "system", "content": "Vous êtes un assistant IA utile."},
            {"role": "user", "content": "Quelle est la météo à Paris aujourd'hui?"}
        ]
        
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Obtenir la météo actuelle pour une ville",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {
                                "type": "string",
                                "description": "La ville pour laquelle obtenir la météo"
                            },
                            "unit": {
                                "type": "string",
                                "enum": ["celsius", "fahrenheit"],
                                "description": "L'unité de température"
                            }
                        },
                        "required": ["city"]
                    }
                }
            }
        ]
        
        for i in range(self.iterations):
            try:
                self.logger.info(f"Itération {i+1}/{self.iterations}")
                
                # Mesurer le temps d'exécution
                result, execution_time = measure_execution_time(
                    lambda: self.client.tool_calling(
                        messages=messages,
                        tools=tools,
                        max_tokens=self.generation_params.get("max_tokens", 100),
                        temperature=self.generation_params.get("temperature", 0.7)
                    )
                )
                
                # Stocker les résultats
                tool_calls = result.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
                
                self.api_results["tool_calling"].append({
                    "iteration": i+1,
                    "execution_time": execution_time,
                    "tokens_generated": result.get("usage", {}).get("completion_tokens", 0),
                    "tokens_total": result.get("usage", {}).get("total_tokens", 0),
                    "num_tool_calls": len(tool_calls)
                })
                
            except Exception as e:
                self.logger.error(f"Erreur lors du test de l'API de tool calling: {str(e)}")
                self.results["errors"].append({
                    "phase": "tool_calling_api",
                    "iteration": i+1,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
    
    def analyze(self) -> Dict[str, Any]:
        """
        Analyse les résultats du benchmark d'API.
        
        Returns:
            Dict[str, Any]: Analyse des résultats
        """
        self.logger.info("Analyse des résultats du benchmark d'API")
        
        analysis = {
            "summary": {},
            "api_performance": {}
        }
        
        # Calculer les métriques pour chaque API
        for api_name, results in self.api_results.items():
            if not results:
                continue
            
            # Calculer les temps d'exécution moyens, min et max
            execution_times = [r.get("execution_time", 0) for r in results]
            
            if execution_times:
                avg_time = sum(execution_times) / len(execution_times)
                min_time = min(execution_times)
                max_time = max(execution_times)
                
                # Stocker les métriques
                analysis["api_performance"][api_name] = {
                    "avg_execution_time": avg_time,
                    "min_execution_time": min_time,
                    "max_execution_time": max_time,
                    "avg_execution_time_formatted": format_time(avg_time),
                    "min_execution_time_formatted": format_time(min_time),
                    "max_execution_time_formatted": format_time(max_time),
                    "num_iterations": len(results)
                }
                
                # Calculer les métriques de tokens si disponibles
                if "tokens_generated" in results[0]:
                    tokens_generated = [r.get("tokens_generated", 0) for r in results]
                    tokens_total = [r.get("tokens_total", 0) for r in results]
                    
                    analysis["api_performance"][api_name].update({
                        "avg_tokens_generated": sum(tokens_generated) / len(tokens_generated),
                        "avg_tokens_total": sum(tokens_total) / len(tokens_total),
                        "tokens_per_second": sum(tokens_generated) / sum(execution_times) if sum(execution_times) > 0 else 0
                    })
        
        # Calculer les métriques globales
        all_execution_times = []
        for results in self.api_results.values():
            all_execution_times.extend([r.get("execution_time", 0) for r in results])
        
        if all_execution_times:
            analysis["summary"] = {
                "total_api_calls": len(all_execution_times),
                "avg_execution_time": sum(all_execution_times) / len(all_execution_times),
                "min_execution_time": min(all_execution_times),
                "max_execution_time": max(all_execution_times)
            }
        
        # Mettre à jour les métriques dans les résultats
        self.results["metrics"] = {
            "total_api_calls": len(all_execution_times),
            "avg_execution_time": sum(all_execution_times) / len(all_execution_times) if all_execution_times else 0,
            "min_execution_time": min(all_execution_times) if all_execution_times else 0,
            "max_execution_time": max(all_execution_times) if all_execution_times else 0
        }
        
        return analysis


class ContextBenchmarkRunner(BenchmarkRunner):
    """
    Classe pour les benchmarks de contexte Qwen3.
    
    Cette classe implémente les méthodes spécifiques pour tester
    les performances des modèles Qwen3 avec différentes longueurs de contexte.
    """
    
    def setup(self) -> None:
        """
        Configure le benchmark de contexte.
        """
        self.logger.info("Configuration du benchmark de contexte")
        
        # Récupérer les longueurs de contexte à tester
        from ..config import get_model_context_lengths
        self.context_lengths = get_model_context_lengths(self.model_name)
        
        # Paramètres de test
        self.iterations = self.config.get("test_parameters", {}).get("num_iterations", 3)
        self.timeout = self.config.get("test_parameters", {}).get("request_timeout", 120)
        
        # Paramètres de génération
        self.generation_params = self.config.get("test_parameters", {}).get("generation", {})
        
        # Préparer les structures pour stocker les résultats
        self.context_results = {length: [] for length in self.context_lengths}
    
    def run(self) -> Dict[str, Any]:
        """
        Exécute le benchmark de contexte.
        
        Returns:
            Dict[str, Any]: Résultats du benchmark
        """
        self.logger.info(f"Exécution du benchmark de contexte avec {len(self.context_lengths)} longueurs de contexte")
        
        from .utils import generate_test_text
        
        for context_length in self.context_lengths:
            self.logger.info(f"Test avec contexte de longueur {context_length}")
            
            # Générer un texte de test de la longueur spécifiée
            test_text = generate_test_text(context_length)
            
            for i in range(self.iterations):
                try:
                    self.logger.info(f"Itération {i+1}/{self.iterations}")
                    
                    # Construire le prompt avec le texte de contexte
                    prompt = f"{test_text}\n\nRésumez le texte ci-dessus en une phrase:"
                    
                    # Mesurer le temps d'exécution
                    result, execution_time = measure_execution_time(
                        lambda: self.client.completions(
                            prompt=prompt,
                            max_tokens=self.generation_params.get("max_tokens", 100),
                            temperature=self.generation_params.get("temperature", 0.7)
                        )
                    )
                    
                    # Stocker les résultats
                    self.context_results[context_length].append({
                        "iteration": i+1,
                        "execution_time": execution_time,
                        "tokens_input": result.get("usage", {}).get("prompt_tokens", 0),
                        "tokens_generated": result.get("usage", {}).get("completion_tokens", 0),
                        "tokens_total": result.get("usage", {}).get("total_tokens", 0)
                    })
                    
                except Exception as e:
                    self.logger.error(f"Erreur lors du test avec contexte de longueur {context_length}: {str(e)}")
                    self.results["errors"].append({
                        "phase": "context_benchmark",
                        "context_length": context_length,
                        "iteration": i+1,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
        
        return {"context_results": self.context_results}
    
    def analyze(self) -> Dict[str, Any]:
        """
        Analyse les résultats du benchmark de contexte.
        
        Returns:
            Dict[str, Any]: Analyse des résultats
        """
        self.logger.info("Analyse des résultats du benchmark de contexte")
        
        analysis = {
            "summary": {},
            "context_performance": {},
            "max_stable_context": None
        }
        
        # Analyser les performances pour chaque longueur de contexte
        for context_length, results in self.context_results.items():
            if not results:
                continue
            
            # Calculer les temps d'exécution moyens, min et max
            execution_times = [r.get("execution_time", 0) for r in results]
            
            if execution_times:
                avg_time = sum(execution_times) / len(execution_times)
                min_time = min(execution_times)
                max_time = max(execution_times)
                
                # Stocker les métriques
                analysis["context_performance"][context_length] = {
                    "avg_execution_time": avg_time,
                    "min_execution_time": min_time,
                    "max_execution_time": max_time,
                    "avg_execution_time_formatted": format_time(avg_time),
                    "min_execution_time_formatted": format_time(min_time),
                    "max_execution_time_formatted": format_time(max_time),
                    "num_iterations": len(results),
                    "success_rate": sum(1 for r in results if "error" not in r) / len(results)
                }
        
        # Déterminer la longueur de contexte maximale stable
        max_stable_context = 0
        for context_length, perf in analysis["context_performance"].items():
            if perf["success_rate"] >= 0.9 and context_length > max_stable_context:
                max_stable_context = context_length
        
        analysis["max_stable_context"] = max_stable_context
        
        # Calculer les métriques globales
        all_execution_times = []
        for results in self.context_results.values():
            all_execution_times.extend([r.get("execution_time", 0) for r in results])
        
        if all_execution_times:
            analysis["summary"] = {
                "total_tests": len(all_execution_times),
                "avg_execution_time": sum(all_execution_times) / len(all_execution_times),
                "min_execution_time": min(all_execution_times),
                "max_execution_time": max(all_execution_times)
            }
        
        # Mettre à jour les métriques dans les résultats
        self.results["metrics"] = {
            "max_stable_context": max_stable_context,
            "total_tests": len(all_execution_times),
            "avg_execution_time": sum(all_execution_times) / len(all_execution_times) if all_execution_times else 0
        }
        
        return analysis


class DocumentQABenchmarkRunner(BenchmarkRunner):
    """
    Classe pour les benchmarks de question-réponse sur documents avec Qwen3.
    
    Cette classe implémente les méthodes spécifiques pour tester
    les performances des modèles Qwen3 sur des tâches de QA documentaire.
    """
    
    def setup(self) -> None:
        """
        Configure le benchmark de QA documentaire.
        """
        self.logger.info("Configuration du benchmark de QA documentaire")
        
        # Paramètres de test
        self.iterations = self.config.get("test_parameters", {}).get("num_iterations", 3)
        self.timeout = self.config.get("test_parameters", {}).get("request_timeout", 120)
        
        # Paramètres de génération
        self.generation_params = self.config.get("test_parameters", {}).get("generation", {})
        
        # Préparer les structures pour stocker les résultats
        self.qa_results = []
        
        # Charger les documents et questions de test
        self.test_cases = self._load_test_cases()
    
    def _load_test_cases(self) -> List[Dict[str, Any]]:
        """
        Charge les cas de test pour le benchmark de QA documentaire.
        
        Returns:
            List[Dict[str, Any]]: Liste des cas de test
        """
        # Dans une implémentation réelle, ces données seraient chargées depuis un fichier
        # Pour cet exemple, nous utilisons des données statiques
        return [
            {
                "document": "Qwen3 est une famille de modèles de langage développée par Alibaba. "
                           "Elle comprend plusieurs variantes de tailles différentes : MICRO (1.7B), "
                           "MINI (8B) et MEDIUM (32B). Ces modèles sont optimisés pour différents "
                           "cas d'utilisation et contraintes de ressources.",
                "questions": [
                    "Qui a développé Qwen3 ?",
                    "Quelles sont les variantes de Qwen3 ?",
                    "Quelle est la taille du modèle Qwen3 MEDIUM ?"
                ]
            },
            {
                "document": "Les modèles de langage comme Qwen3 utilisent l'architecture Transformer. "
                           "Cette architecture repose sur des mécanismes d'attention qui permettent "
                           "au modèle de traiter efficacement les séquences de texte. Les modèles "
                           "quantifiés comme Qwen3-AWQ offrent un bon compromis entre performance "
                           "et utilisation des ressources.",
                "questions": [
                    "Quelle architecture est utilisée par Qwen3 ?",
                    "Qu'est-ce qui permet aux modèles Transformer de traiter efficacement le texte ?",
                    "Quel avantage offrent les modèles quantifiés comme Qwen3-AWQ ?"
                ]
            }
        ]
    
    def run(self) -> Dict[str, Any]:
        """
        Exécute le benchmark de QA documentaire.
        
        Returns:
            Dict[str, Any]: Résultats du benchmark
        """
        self.logger.info(f"Exécution du benchmark de QA documentaire avec {len(self.test_cases)} documents")
        
        for i, test_case in enumerate(self.test_cases):
            document = test_case["document"]
            questions = test_case["questions"]
            
            self.logger.info(f"Test du document {i+1}/{len(self.test_cases)}")
            
            for j, question in enumerate(questions):
                self.logger.info(f"Question {j+1}/{len(questions)}")
                
                # Construire le prompt
                prompt = f"Document: {document}\n\nQuestion: {question}\n\nRéponse:"
                
                for k in range(self.iterations):
                    try:
                        self.logger.info(f"Itération {k+1}/{self.iterations}")
                        
                        # Mesurer le temps d'exécution
                        result, execution_time = measure_execution_time(
                            lambda: self.client.completions(
                                prompt=prompt,
                                max_tokens=self.generation_params.get("max_tokens", 100),
                                temperature=self.generation_params.get("temperature", 0.7)
                            )
                        )
                        
                        # Stocker les résultats
                        self.qa_results.append({
                            "document_id": i+1,
                            "question_id": j+1,
                            "iteration": k+1,
                            "execution_time": execution_time,
                            "tokens_input": result.get("usage", {}).get("prompt_tokens", 0),
                            "tokens_generated": result.get("usage", {}).get("completion_tokens", 0),
                            "tokens_total": result.get("usage", {}).get("total_tokens", 0),
                            "question": question,
                            "answer": result.get("choices", [{}])[0].get("text", "").strip()
                        })
                        
                    except Exception as e:
                        self.logger.error(f"Erreur lors du test de QA documentaire: {str(e)}")
                        self.results["errors"].append({
                            "phase": "document_qa",
                            "document_id": i+1,
                            "question_id": j+1,
                            "iteration": k+1,
                            "error": str(e),
                            "timestamp": datetime.now().isoformat()
                        })
        
        return {"qa_results": self.qa_results}
    
    def analyze(self) -> Dict[str, Any]:
        """
        Analyse les résultats du benchmark de QA documentaire.
        
        Returns:
            Dict[str, Any]: Analyse des résultats
        """
        self.logger.info("Analyse des résultats du benchmark de QA documentaire")
        
        analysis = {
            "summary": {},
            "per_document": {}
        }
        
        if not self.qa_results:
            return analysis
        
        # Calculer les temps d'exécution moyens, min et max
        execution_times = [r.get("execution_time", 0) for r in self.qa_results]
        
        if execution_times:
            avg_time = sum(execution_times) / len(execution_times)
            min_time = min(execution_times)
            max_time = max(execution_times)
            
            # Stocker les métriques globales
            analysis["summary"] = {
                "total_questions": len(self.qa_results),
                "avg_execution_time": avg_time,
                "min_execution_time": min_time,
                "max_execution_time": max_time,
                "avg_execution_time_formatted": format_time(avg_time),
                "min_execution_time_formatted": format_time(min_time),
                "max_execution_time_formatted": format_time(max_time)
            }
            
            # Calculer les métriques de tokens
            tokens_generated = [r.get("tokens_generated", 0) for r in self.qa_results]
            tokens_total = [r.get("tokens_total", 0) for r in self.qa_results]
            
            analysis["summary"].update({
                "avg_tokens_generated": sum(tokens_generated) / len(tokens_generated),
                "avg_tokens_total": sum(tokens_total) / len(tokens_total),
                "tokens_per_second": sum(tokens_generated) / sum(execution_times) if sum(execution_times) > 0 else 0
            })
        
        # Analyser les performances par document
        for doc_id in set(r.get("document_id") for r in self.qa_results):
            doc_results = [r for r in self.qa_results if r.get("document_id") == doc_id]
            
            if doc_results:
                doc_execution_times = [r.get("execution_time", 0) for r in doc_results]
                
                analysis["per_document"][doc_id] = {
                    "num_questions": len(set(r.get("question_id") for r in doc_results)),
                    "avg_execution_time": sum(doc_execution_times) / len(doc_execution_times),
                    "min_execution_time": min(doc_execution_times),
                    "max_execution_time": max(doc_execution_times)
                }
        
        # Mettre à jour les métriques dans les résultats
        self.results["metrics"] = {
            "total_questions": len(self.qa_results),
            "avg_execution_time": avg_time if execution_times else 0,
            "tokens_per_second": analysis["summary"].get("tokens_per_second", 0)
        }
        
        return analysis
            