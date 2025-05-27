#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module implémentant les benchmarks de longueur de contexte pour Qwen3.

Ce module fournit des classes et fonctions pour évaluer les performances
des modèles Qwen3 avec différentes longueurs de contexte.
"""

import time
import json
import logging
import numpy as np
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Tuple

from ..core import BenchmarkRunner, ContextBenchmarkRunner, ModelClient
from ..core.utils import measure_execution_time, format_time, setup_logger, generate_test_text, count_tokens
from ..config import get_model_endpoint, get_model_context_lengths


class ContextLengthBenchmark(ContextBenchmarkRunner):
    """
    Classe pour les benchmarks de longueur de contexte Qwen3.
    
    Cette classe étend ContextBenchmarkRunner pour évaluer les performances
    des modèles Qwen3 avec différentes longueurs de contexte.
    
    Attributes:
        model_name (str): Nom du modèle à tester ('micro', 'mini', 'medium')
        config (Dict[str, Any]): Configuration complète du benchmark
        client (ModelClient): Client pour interagir avec l'API du modèle
        results (Dict[str, Any]): Résultats du benchmark
        logger (logging.Logger): Logger pour les messages de benchmark
        context_lengths (List[int]): Liste des longueurs de contexte à tester
    """
    
    def setup(self) -> None:
        """
        Configure le benchmark de longueur de contexte.
        """
        self.logger.info("Configuration du benchmark de longueur de contexte")
        
        # Appeler la méthode setup de la classe parente
        super().setup()
        
        # Configuration spécifique aux tests de longueur de contexte
        self.max_context_search_params = self.config.get("test_parameters", {}).get("max_context_search", {})
        
        # Préparer les structures pour stocker les résultats détaillés
        self.detailed_results = {
            "per_context_length": {},
            "max_context_search": {},
            "stability_tests": {}
        }
    
    def run(self) -> Dict[str, Any]:
        """
        Exécute le benchmark de longueur de contexte.
        
        Returns:
            Dict[str, Any]: Résultats du benchmark
        """
        self.logger.info(f"Exécution du benchmark de longueur de contexte")
        
        # Exécuter les tests standard de contexte (utilise la méthode run de la classe parente)
        self.logger.info("Exécution des tests standard de contexte")
        standard_results = super().run()
        self.detailed_results["per_context_length"] = standard_results.get("context_results", {})
        
        # Exécuter la recherche du contexte maximal
        self.logger.info("Recherche du contexte maximal")
        max_context_results = self._find_max_context()
        self.detailed_results["max_context_search"] = max_context_results
        
        # Exécuter les tests de stabilité pour le contexte maximal trouvé
        if max_context_results.get("max_stable_context"):
            self.logger.info(f"Tests de stabilité pour le contexte maximal")
            stability_results = self._test_context_stability(max_context_results.get("max_stable_context"))
            self.detailed_results["stability_tests"] = stability_results
        
        return {"detailed_results": self.detailed_results}
    
    def _find_max_context(self) -> Dict[str, Any]:
        """
        Recherche la longueur de contexte maximale stable pour le modèle.
        
        Returns:
            Dict[str, Any]: Résultats de la recherche
        """
        self.logger.info("Recherche de la longueur de contexte maximale stable")
        
        # Paramètres de recherche
        start_length = self.max_context_search_params.get("start_length", 10000)
        step = self.max_context_search_params.get("step", 10000)
        max_attempts = self.max_context_search_params.get("max_attempts", 10)
        
        results = {
            "tests": [],
            "max_stable_context": None,
            "max_tested_context": None,
            "search_params": {
                "start_length": start_length,
                "step": step,
                "max_attempts": max_attempts
            }
        }
        
        current_length = start_length
        success = True
        attempt = 0
        
        while success and attempt < max_attempts:
            self.logger.info(f"Test avec contexte de longueur {current_length}")
            attempt += 1
            
            try:
                # Générer un texte de test de la longueur spécifiée
                test_text = generate_test_text(current_length)
                
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
                
                # Stocker les résultats du test
                test_result = {
                    "context_length": current_length,
                    "execution_time": execution_time,
                    "execution_time_formatted": format_time(execution_time),
                    "tokens_input": result.get("usage", {}).get("prompt_tokens", 0),
                    "tokens_generated": result.get("usage", {}).get("completion_tokens", 0),
                    "tokens_total": result.get("usage", {}).get("total_tokens", 0),
                    "success": True
                }
                
                results["tests"].append(test_result)
                
                # Mettre à jour la longueur de contexte maximale stable
                results["max_stable_context"] = current_length
                results["max_tested_context"] = current_length
                
                # Augmenter la longueur pour le prochain test
                current_length += step
                
            except Exception as e:
                self.logger.error(f"Erreur lors du test avec contexte de longueur {current_length}: {str(e)}")
                
                # Stocker les résultats du test échoué
                test_result = {
                    "context_length": current_length,
                    "error": str(e),
                    "success": False
                }
                
                results["tests"].append(test_result)
                results["max_tested_context"] = current_length
                
                # Arrêter la recherche en cas d'échec
                success = False
        
        self.logger.info(f"Contexte maximal stable trouvé: {results['max_stable_context']}")
        return results
    
    def _test_context_stability(self, context_length: int, num_tests: int = 5) -> Dict[str, Any]:
        """
        Teste la stabilité d'une longueur de contexte spécifique.
        
        Args:
            context_length (int): Longueur de contexte à tester
            num_tests (int, optional): Nombre de tests à effectuer
            
        Returns:
            Dict[str, Any]: Résultats des tests de stabilité
        """
        self.logger.info(f"Test de stabilité pour le contexte de longueur {context_length}")
        
        results = {
            "context_length": context_length,
            "num_tests": num_tests,
            "tests": [],
            "success_rate": 0.0,
            "avg_execution_time": 0.0,
            "avg_execution_time_formatted": "",
            "is_stable": False
        }
        
        successful_tests = 0
        execution_times = []
        
        for i in range(num_tests):
            self.logger.info(f"Test de stabilité {i+1}/{num_tests}")
            
            try:
                # Générer un texte de test de la longueur spécifiée
                # Utiliser une graine différente pour chaque test
                test_text = generate_test_text(context_length, seed=i)
                
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
                
                # Stocker les résultats du test
                test_result = {
                    "test_id": i+1,
                    "execution_time": execution_time,
                    "execution_time_formatted": format_time(execution_time),
                    "tokens_input": result.get("usage", {}).get("prompt_tokens", 0),
                    "tokens_generated": result.get("usage", {}).get("completion_tokens", 0),
                    "tokens_total": result.get("usage", {}).get("total_tokens", 0),
                    "success": True
                }
                
                results["tests"].append(test_result)
                successful_tests += 1
                execution_times.append(execution_time)
                
            except Exception as e:
                self.logger.error(f"Erreur lors du test de stabilité {i+1}: {str(e)}")
                
                # Stocker les résultats du test échoué
                test_result = {
                    "test_id": i+1,
                    "error": str(e),
                    "success": False
                }
                
                results["tests"].append(test_result)
        
        # Calculer les métriques de stabilité
        results["success_rate"] = successful_tests / num_tests if num_tests > 0 else 0.0
        
        if execution_times:
            avg_time = sum(execution_times) / len(execution_times)
            results["avg_execution_time"] = avg_time
            results["avg_execution_time_formatted"] = format_time(avg_time)
        
        # Déterminer si le contexte est stable (taux de succès >= 80%)
        results["is_stable"] = results["success_rate"] >= 0.8
        
        self.logger.info(f"Taux de succès pour le contexte de longueur {context_length}: {results['success_rate'] * 100:.1f}%")
        return results
    
    def analyze(self) -> Dict[str, Any]:
        """
        Analyse les résultats du benchmark de longueur de contexte.
        
        Returns:
            Dict[str, Any]: Analyse des résultats
        """
        self.logger.info("Analyse des résultats du benchmark de longueur de contexte")
        
        # Appeler la méthode analyze de la classe parente pour l'analyse de base
        base_analysis = super().analyze()
        
        # Analyse spécifique aux tests de longueur de contexte
        analysis = {
            "summary": base_analysis.get("summary", {}),
            "context_performance": base_analysis.get("context_performance", {}),
            "max_stable_context": base_analysis.get("max_stable_context"),
            "detailed_analysis": {}
        }
        
        # Analyser les résultats de recherche du contexte maximal
        max_context_search = self.detailed_results.get("max_context_search", {})
        max_stable_context = max_context_search.get("max_stable_context")
        
        if max_stable_context:
            analysis["detailed_analysis"]["max_context_search"] = {
                "max_stable_context": max_stable_context,
                "max_tested_context": max_context_search.get("max_tested_context"),
                "search_iterations": len(max_context_search.get("tests", [])),
                "failure_point": next((test.get("context_length") for test in max_context_search.get("tests", []) 
                                     if not test.get("success", False)), None)
            }
        
        # Analyser les résultats des tests de stabilité
        stability_tests = self.detailed_results.get("stability_tests", {})
        if stability_tests:
            analysis["detailed_analysis"]["stability"] = {
                "context_length": stability_tests.get("context_length"),
                "success_rate": stability_tests.get("success_rate", 0.0),
                "avg_execution_time": stability_tests.get("avg_execution_time", 0.0),
                "avg_execution_time_formatted": stability_tests.get("avg_execution_time_formatted", ""),
                "is_stable": stability_tests.get("is_stable", False)
            }
        
        # Analyser la relation entre la longueur de contexte et le temps d'exécution
        context_results = self.detailed_results.get("per_context_length", {})
        if context_results:
            # Calculer la corrélation entre la longueur de contexte et le temps d'exécution
            context_lengths = []
            execution_times = []
            
            for length, results in context_results.items():
                if results:
                    avg_time = sum(r.get("execution_time", 0) for r in results) / len(results)
                    context_lengths.append(int(length))
                    execution_times.append(avg_time)
            
            if context_lengths and execution_times:
                # Calculer le coefficient de corrélation
                try:
                    correlation = np.corrcoef(context_lengths, execution_times)[0, 1]
                    
                    analysis["detailed_analysis"]["correlation"] = {
                        "context_length_vs_execution_time": correlation,
                        "interpretation": self._interpret_correlation(correlation)
                    }
                except:
                    pass
        
        # Mettre à jour les métriques dans les résultats
        self.results["metrics"].update({
            "max_stable_context": max_stable_context,
            "context_stability": stability_tests.get("success_rate", 0.0) if stability_tests else 0.0
        })
        
        return analysis
    
    def _interpret_correlation(self, correlation: float) -> str:
        """
        Interprète le coefficient de corrélation entre la longueur de contexte et le temps d'exécution.
        
        Args:
            correlation (float): Coefficient de corrélation
            
        Returns:
            str: Interprétation du coefficient
        """
        if correlation > 0.8:
            return "Forte corrélation positive: le temps d'exécution augmente significativement avec la longueur de contexte."
        elif correlation > 0.5:
            return "Corrélation positive modérée: le temps d'exécution augmente avec la longueur de contexte."
        elif correlation > 0.2:
            return "Faible corrélation positive: le temps d'exécution augmente légèrement avec la longueur de contexte."
        elif correlation > -0.2:
            return "Pas de corrélation significative: le temps d'exécution est relativement indépendant de la longueur de contexte."
        elif correlation > -0.5:
            return "Faible corrélation négative: le temps d'exécution diminue légèrement avec la longueur de contexte."
        elif correlation > -0.8:
            return "Corrélation négative modérée: le temps d'exécution diminue avec la longueur de contexte."
        else:
            return "Forte corrélation négative: le temps d'exécution diminue significativement avec la longueur de contexte."
    
    def determine_optimal_context(self) -> Dict[str, Any]:
        """
        Détermine la longueur de contexte optimale en fonction des performances.
        
        Returns:
            Dict[str, Any]: Recommandations pour la longueur de contexte optimale
        """
        self.logger.info("Détermination de la longueur de contexte optimale")
        
        # Récupérer les résultats par longueur de contexte
        context_results = self.detailed_results.get("per_context_length", {})
        max_stable_context = self.detailed_results.get("max_context_search", {}).get("max_stable_context")
        
        recommendations = {
            "max_stable_context": max_stable_context,
            "recommended_context": None,
            "safety_margin": 0.9,  # Marge de sécurité par défaut
            "recommended_context_with_margin": None,
            "performance_metrics": {},
            "explanation": ""
        }
        
        if not context_results or not max_stable_context:
            return recommendations
        
        # Calculer les métriques de performance pour chaque longueur de contexte
        performance_metrics = {}
        for length_str, results in context_results.items():
            length = int(length_str)
            if results:
                avg_time = sum(r.get("execution_time", 0) for r in results) / len(results)
                success_rate = sum(1 for r in results if "error" not in r) / len(results)
                
                performance_metrics[length] = {
                    "avg_execution_time": avg_time,
                    "avg_execution_time_formatted": format_time(avg_time),
                    "success_rate": success_rate,
                    "tokens_per_second": sum(r.get("tokens_generated", 0) for r in results) / 
                                        sum(r.get("execution_time", 0.001) for r in results)
                }
        
        recommendations["performance_metrics"] = performance_metrics
        
        # Trouver la longueur de contexte avec le meilleur compromis performance/stabilité
        best_length = None
        best_score = -1
        
        for length, metrics in performance_metrics.items():
            if length <= max_stable_context and metrics["success_rate"] >= 0.9:
                # Score combinant vitesse et stabilité
                score = metrics["tokens_per_second"] * metrics["success_rate"]
                
                if score > best_score:
                    best_score = score
                    best_length = length
        
        if best_length:
            recommendations["recommended_context"] = best_length
            
            # Appliquer une marge de sécurité
            safety_margin = self.config.get("optimization", {}).get("safety_margin", 0.9)
            recommendations["safety_margin"] = safety_margin
            recommendations["recommended_context_with_margin"] = int(best_length * safety_margin)
            
            recommendations["explanation"] = (
                f"La longueur de contexte recommandée est de {best_length} tokens, offrant le meilleur "
                f"compromis entre performance ({performance_metrics[best_length]['tokens_per_second']:.2f} tokens/s) "
                f"et stabilité (taux de succès: {performance_metrics[best_length]['success_rate'] * 100:.1f}%). "
                f"Avec une marge de sécurité de {safety_margin * 100:.0f}%, la longueur recommandée "
                f"pour un usage en production est de {recommendations['recommended_context_with_margin']} tokens."
            )
        else:
            # Si aucune longueur optimale n'a été trouvée, recommander une valeur conservatrice
            conservative_context = int(max_stable_context * 0.8) if max_stable_context else None
            recommendations["recommended_context"] = conservative_context
            recommendations["recommended_context_with_margin"] = conservative_context
            
            recommendations["explanation"] = (
                f"Aucune longueur de contexte n'offre un compromis optimal. Une approche conservatrice "
                f"recommande d'utiliser {conservative_context} tokens (80% du contexte maximal stable)."
            )
        
        return recommendations