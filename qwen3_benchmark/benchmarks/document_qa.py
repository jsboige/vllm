#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module implémentant les benchmarks de QA sur documents pour Qwen3.

Ce module fournit des classes et fonctions pour évaluer les performances
des modèles Qwen3 sur des tâches de question-réponse avec documents longs.
"""

import os
import time
import json
import logging
import numpy as np
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Tuple

from ..core import BenchmarkRunner, DocumentQABenchmarkRunner, ModelClient
from ..core.utils import measure_execution_time, format_time, setup_logger, generate_test_text, count_tokens
from ..config import get_model_endpoint, get_output_paths


class DocumentQABenchmark(DocumentQABenchmarkRunner):
    """
    Classe pour les benchmarks de QA sur documents avec Qwen3.
    
    Cette classe étend DocumentQABenchmarkRunner pour évaluer les performances
    des modèles Qwen3 sur des tâches de question-réponse avec documents longs.
    
    Attributes:
        model_name (str): Nom du modèle à tester ('micro', 'mini', 'medium')
        config (Dict[str, Any]): Configuration complète du benchmark
        client (ModelClient): Client pour interagir avec l'API du modèle
        results (Dict[str, Any]): Résultats du benchmark
        logger (logging.Logger): Logger pour les messages de benchmark
        test_cases (List[Dict[str, Any]]): Cas de test pour le benchmark
    """
    
    def setup(self) -> None:
        """
        Configure le benchmark de QA sur documents.
        """
        self.logger.info("Configuration du benchmark de QA sur documents")
        
        # Appeler la méthode setup de la classe parente
        super().setup()
        
        # Configuration spécifique aux tests de QA sur documents
        self.document_lengths = [1000, 2000, 5000, 10000]
        
        # Charger ou générer des documents de test de différentes longueurs
        self.test_documents = self._prepare_test_documents()
        
        # Préparer les questions pour chaque document
        self.test_questions = self._prepare_test_questions()
        
        # Préparer les structures pour stocker les résultats détaillés
        self.detailed_results = {
            "per_document_length": {},
            "per_question_type": {},
            "accuracy_metrics": {}
        }
    
    def _prepare_test_documents(self) -> Dict[int, str]:
        """
        Prépare des documents de test de différentes longueurs.
        
        Returns:
            Dict[int, str]: Documents de test indexés par longueur
        """
        self.logger.info("Préparation des documents de test")
        
        documents = {}
        
        # Générer des documents de différentes longueurs
        for length in self.document_lengths:
            self.logger.info(f"Génération d'un document de test de longueur {length}")
            documents[length] = generate_test_text(length, seed=length)
        
        return documents
    
    def _prepare_test_questions(self) -> Dict[int, List[Dict[str, str]]]:
        """
        Prépare des questions de test pour chaque document.
        
        Returns:
            Dict[int, List[Dict[str, str]]]: Questions de test indexées par longueur de document
        """
        self.logger.info("Préparation des questions de test")
        
        questions = {}
        
        # Pour chaque document, préparer différents types de questions
        for length, document in self.test_documents.items():
            self.logger.info(f"Préparation des questions pour le document de longueur {length}")
            
            # Diviser le document en paragraphes
            paragraphs = document.split("\n\n")
            
            # Préparer différents types de questions
            doc_questions = []
            
            # 1. Question sur le début du document
            if paragraphs:
                doc_questions.append({
                    "type": "début",
                    "question": "Quel est le sujet principal abordé au début du document?",
                    "context_location": "début",
                    "paragraph_index": 0
                })
            
            # 2. Question sur le milieu du document
            if len(paragraphs) > 2:
                middle_idx = len(paragraphs) // 2
                doc_questions.append({
                    "type": "milieu",
                    "question": "Quelle information importante est mentionnée au milieu du document?",
                    "context_location": "milieu",
                    "paragraph_index": middle_idx
                })
            
            # 3. Question sur la fin du document
            if len(paragraphs) > 1:
                doc_questions.append({
                    "type": "fin",
                    "question": "Quelle conclusion ou point final est présenté dans le document?",
                    "context_location": "fin",
                    "paragraph_index": len(paragraphs) - 1
                })
            
            # 4. Question de synthèse sur l'ensemble du document
            doc_questions.append({
                "type": "synthèse",
                "question": "Résumez les points principaux abordés dans l'ensemble du document.",
                "context_location": "global",
                "paragraph_index": -1
            })
            
            questions[length] = doc_questions
        
        return questions
    
    def run(self) -> Dict[str, Any]:
        """
        Exécute le benchmark de QA sur documents.
        
        Returns:
            Dict[str, Any]: Résultats du benchmark
        """
        self.logger.info(f"Exécution du benchmark de QA sur documents")
        
        # Exécuter les tests standard de QA (utilise la méthode run de la classe parente)
        self.logger.info("Exécution des tests standard de QA sur documents")
        standard_results = super().run()
        
        # Exécuter les tests spécifiques par longueur de document
        self.logger.info("Exécution des tests par longueur de document")
        
        for length, document in self.test_documents.items():
            self.logger.info(f"Test avec document de longueur {length}")
            
            # Récupérer les questions pour ce document
            questions = self.test_questions.get(length, [])
            
            # Initialiser les résultats pour cette longueur de document
            self.detailed_results["per_document_length"][length] = []
            
            for question_data in questions:
                question_type = question_data["type"]
                question = question_data["question"]
                
                self.logger.info(f"Test de la question de type '{question_type}': {question}")
                
                # Initialiser les résultats pour ce type de question s'il n'existe pas encore
                if question_type not in self.detailed_results["per_question_type"]:
                    self.detailed_results["per_question_type"][question_type] = []
                
                for i in range(self.iterations):
                    try:
                        self.logger.info(f"Itération {i+1}/{self.iterations}")
                        
                        # Construire le prompt
                        prompt = f"Document:\n{document}\n\nQuestion: {question}\n\nRéponse:"
                        
                        # Mesurer le temps d'exécution
                        result, execution_time = measure_execution_time(
                            lambda: self.client.completions(
                                prompt=prompt,
                                max_tokens=self.generation_params.get("max_tokens", 100),
                                temperature=self.generation_params.get("temperature", 0.7)
                            )
                        )
                        
                        # Extraire la réponse générée
                        answer = result.get("choices", [{}])[0].get("text", "").strip()
                        
                        # Stocker les résultats
                        test_result = {
                            "document_length": length,
                            "question_type": question_type,
                            "question": question,
                            "iteration": i+1,
                            "execution_time": execution_time,
                            "execution_time_formatted": format_time(execution_time),
                            "tokens_input": result.get("usage", {}).get("prompt_tokens", 0),
                            "tokens_generated": result.get("usage", {}).get("completion_tokens", 0),
                            "tokens_total": result.get("usage", {}).get("total_tokens", 0),
                            "answer": answer,
                            "success": True
                        }
                        
                        # Ajouter aux résultats par longueur de document
                        self.detailed_results["per_document_length"][length].append(test_result)
                        
                        # Ajouter aux résultats par type de question
                        self.detailed_results["per_question_type"][question_type].append(test_result)
                        
                    except Exception as e:
                        self.logger.error(f"Erreur lors du test de QA: {str(e)}")
                        
                        # Stocker les résultats du test échoué
                        test_result = {
                            "document_length": length,
                            "question_type": question_type,
                            "question": question,
                            "iteration": i+1,
                            "error": str(e),
                            "success": False
                        }
                        
                        # Ajouter aux résultats par longueur de document
                        self.detailed_results["per_document_length"][length].append(test_result)
                        
                        # Ajouter aux résultats par type de question
                        self.detailed_results["per_question_type"][question_type].append(test_result)
                        
                        # Ajouter aux erreurs globales
                        self.results["errors"].append({
                            "phase": "document_qa",
                            "document_length": length,
                            "question_type": question_type,
                            "iteration": i+1,
                            "error": str(e),
                            "timestamp": datetime.now().isoformat()
                        })
        
        return {"detailed_results": self.detailed_results}
    
    def analyze(self) -> Dict[str, Any]:
        """
        Analyse les résultats du benchmark de QA sur documents.
        
        Returns:
            Dict[str, Any]: Analyse des résultats
        """
        self.logger.info("Analyse des résultats du benchmark de QA sur documents")
        
        # Appeler la méthode analyze de la classe parente pour l'analyse de base
        base_analysis = super().analyze()
        
        # Analyse spécifique aux tests de QA sur documents
        analysis = {
            "summary": base_analysis.get("summary", {}),
            "per_document": base_analysis.get("per_document", {}),
            "detailed_analysis": {
                "per_document_length": {},
                "per_question_type": {},
                "correlation": {}
            }
        }
        
        # Analyser les résultats par longueur de document
        for length, results in self.detailed_results["per_document_length"].items():
            successful_results = [r for r in results if r.get("success", False)]
            
            if successful_results:
                # Calculer les métriques moyennes
                avg_time = sum(r.get("execution_time", 0) for r in successful_results) / len(successful_results)
                avg_tokens_input = sum(r.get("tokens_input", 0) for r in successful_results) / len(successful_results)
                avg_tokens_generated = sum(r.get("tokens_generated", 0) for r in successful_results) / len(successful_results)
                
                # Calculer le taux de succès
                success_rate = len(successful_results) / len(results)
                
                # Stocker les métriques
                analysis["detailed_analysis"]["per_document_length"][length] = {
                    "avg_execution_time": avg_time,
                    "avg_execution_time_formatted": format_time(avg_time),
                    "avg_tokens_input": avg_tokens_input,
                    "avg_tokens_generated": avg_tokens_generated,
                    "tokens_per_second": avg_tokens_generated / avg_time if avg_time > 0 else 0,
                    "success_rate": success_rate,
                    "num_tests": len(results)
                }
        
        # Analyser les résultats par type de question
        for question_type, results in self.detailed_results["per_question_type"].items():
            successful_results = [r for r in results if r.get("success", False)]
            
            if successful_results:
                # Calculer les métriques moyennes
                avg_time = sum(r.get("execution_time", 0) for r in successful_results) / len(successful_results)
                avg_tokens_generated = sum(r.get("tokens_generated", 0) for r in successful_results) / len(successful_results)
                
                # Calculer le taux de succès
                success_rate = len(successful_results) / len(results)
                
                # Stocker les métriques
                analysis["detailed_analysis"]["per_question_type"][question_type] = {
                    "avg_execution_time": avg_time,
                    "avg_execution_time_formatted": format_time(avg_time),
                    "avg_tokens_generated": avg_tokens_generated,
                    "tokens_per_second": avg_tokens_generated / avg_time if avg_time > 0 else 0,
                    "success_rate": success_rate,
                    "num_tests": len(results)
                }
        
        # Analyser la corrélation entre la longueur du document et le temps d'exécution
        document_lengths = []
        execution_times = []
        
        for length, metrics in analysis["detailed_analysis"]["per_document_length"].items():
            document_lengths.append(int(length))
            execution_times.append(metrics["avg_execution_time"])
        
        if document_lengths and execution_times:
            # Calculer le coefficient de corrélation
            try:
                correlation = np.corrcoef(document_lengths, execution_times)[0, 1]
                
                analysis["detailed_analysis"]["correlation"]["document_length_vs_execution_time"] = {
                    "correlation": correlation,
                    "interpretation": self._interpret_correlation(correlation)
                }
            except:
                pass
        
        # Mettre à jour les métriques dans les résultats
        all_successful_results = []
        for results in self.detailed_results["per_document_length"].values():
            all_successful_results.extend([r for r in results if r.get("success", False)])
        
        if all_successful_results:
            avg_time = sum(r.get("execution_time", 0) for r in all_successful_results) / len(all_successful_results)
            avg_tokens_generated = sum(r.get("tokens_generated", 0) for r in all_successful_results) / len(all_successful_results)
            
            self.results["metrics"].update({
                "avg_execution_time": avg_time,
                "avg_tokens_generated": avg_tokens_generated,
                "tokens_per_second": avg_tokens_generated / avg_time if avg_time > 0 else 0,
                "success_rate": len(all_successful_results) / sum(len(results) for results in self.detailed_results["per_document_length"].values())
            })
        
        return analysis
    
    def _interpret_correlation(self, correlation: float) -> str:
        """
        Interprète le coefficient de corrélation entre la longueur du document et le temps d'exécution.
        
        Args:
            correlation (float): Coefficient de corrélation
            
        Returns:
            str: Interprétation du coefficient
        """
        if correlation > 0.8:
            return "Forte corrélation positive: le temps d'exécution augmente significativement avec la longueur du document."
        elif correlation > 0.5:
            return "Corrélation positive modérée: le temps d'exécution augmente avec la longueur du document."
        elif correlation > 0.2:
            return "Faible corrélation positive: le temps d'exécution augmente légèrement avec la longueur du document."
        elif correlation > -0.2:
            return "Pas de corrélation significative: le temps d'exécution est relativement indépendant de la longueur du document."
        elif correlation > -0.5:
            return "Faible corrélation négative: le temps d'exécution diminue légèrement avec la longueur du document."
        elif correlation > -0.8:
            return "Corrélation négative modérée: le temps d'exécution diminue avec la longueur du document."
        else:
            return "Forte corrélation négative: le temps d'exécution diminue significativement avec la longueur du document."
    
    def evaluate_answer_quality(self, reference_answers: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
        """
        Évalue la qualité des réponses générées par rapport à des réponses de référence.
        
        Args:
            reference_answers (Dict[str, Dict[str, str]]): Réponses de référence indexées par longueur de document et type de question
            
        Returns:
            Dict[str, Any]: Métriques d'évaluation de la qualité des réponses
        """
        self.logger.info("Évaluation de la qualité des réponses")
        
        evaluation = {
            "per_document_length": {},
            "per_question_type": {},
            "overall": {
                "relevance_score": 0.0,
                "accuracy_score": 0.0,
                "num_evaluated": 0
            }
        }
        
        # Dans une implémentation réelle, on utiliserait un modèle d'évaluation
        # Pour cet exemple, nous simulons une évaluation basique
        
        total_relevance = 0.0
        total_accuracy = 0.0
        num_evaluated = 0
        
        # Évaluer les réponses par longueur de document
        for length, results in self.detailed_results["per_document_length"].items():
            length_str = str(length)
            evaluation["per_document_length"][length] = {
                "relevance_score": 0.0,
                "accuracy_score": 0.0,
                "num_evaluated": 0
            }
            
            length_relevance = 0.0
            length_accuracy = 0.0
            length_evaluated = 0
            
            for result in results:
                if not result.get("success", False):
                    continue
                
                question_type = result.get("question_type")
                answer = result.get("answer", "")
                
                # Vérifier si nous avons une réponse de référence
                if length_str in reference_answers and question_type in reference_answers[length_str]:
                    reference = reference_answers[length_str][question_type]
                    
                    # Simuler une évaluation de pertinence (0.0-1.0)
                    # Dans une implémentation réelle, on utiliserait un modèle d'évaluation
                    relevance = min(0.5 + len(answer) / 200, 1.0)  # Simulation simpliste
                    
                    # Simuler une évaluation de précision (0.0-1.0)
                    # Dans une implémentation réelle, on utiliserait un modèle d'évaluation
                    accuracy = 0.7  # Valeur fixe pour la simulation
                    
                    # Accumuler les scores
                    length_relevance += relevance
                    length_accuracy += accuracy
                    length_evaluated += 1
                    
                    total_relevance += relevance
                    total_accuracy += accuracy
                    num_evaluated += 1
            
            # Calculer les moyennes pour cette longueur de document
            if length_evaluated > 0:
                evaluation["per_document_length"][length]["relevance_score"] = length_relevance / length_evaluated
                evaluation["per_document_length"][length]["accuracy_score"] = length_accuracy / length_evaluated
                evaluation["per_document_length"][length]["num_evaluated"] = length_evaluated
        
        # Évaluer les réponses par type de question
        for question_type, results in self.detailed_results["per_question_type"].items():
            evaluation["per_question_type"][question_type] = {
                "relevance_score": 0.0,
                "accuracy_score": 0.0,
                "num_evaluated": 0
            }
            
            type_relevance = 0.0
            type_accuracy = 0.0
            type_evaluated = 0
            
            for result in results:
                if not result.get("success", False):
                    continue
                
                length = str(result.get("document_length"))
                answer = result.get("answer", "")
                
                # Vérifier si nous avons une réponse de référence
                if length in reference_answers and question_type in reference_answers[length]:
                    reference = reference_answers[length][question_type]
                    
                    # Simuler une évaluation de pertinence (0.0-1.0)
                    relevance = min(0.5 + len(answer) / 200, 1.0)  # Simulation simpliste
                    
                    # Simuler une évaluation de précision (0.0-1.0)
                    accuracy = 0.7  # Valeur fixe pour la simulation
                    
                    # Accumuler les scores
                    type_relevance += relevance
                    type_accuracy += accuracy
                    type_evaluated += 1
            
            # Calculer les moyennes pour ce type de question
            if type_evaluated > 0:
                evaluation["per_question_type"][question_type]["relevance_score"] = type_relevance / type_evaluated
                evaluation["per_question_type"][question_type]["accuracy_score"] = type_accuracy / type_evaluated
                evaluation["per_question_type"][question_type]["num_evaluated"] = type_evaluated
        
        # Calculer les moyennes globales
        if num_evaluated > 0:
            evaluation["overall"]["relevance_score"] = total_relevance / num_evaluated
            evaluation["overall"]["accuracy_score"] = total_accuracy / num_evaluated
            evaluation["overall"]["num_evaluated"] = num_evaluated
        
        # Stocker les métriques d'évaluation
        self.detailed_results["accuracy_metrics"] = evaluation
        
        return evaluation
    
    def save_detailed_results(self, output_path: Optional[str] = None) -> str:
        """
        Sauvegarde les résultats détaillés du benchmark dans un fichier JSON.
        
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
            filename = f"qwen3_{self.model_name}_document_qa_detailed_{timestamp}.json"
            output_path = os.path.join(results_dir, filename)
        
        # Créer le répertoire si nécessaire
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Sauvegarder les résultats
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.detailed_results, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Résultats détaillés sauvegardés dans {output_path}")
            return output_path
        
        except Exception as e:
            self.logger.error(f"Erreur lors de la sauvegarde des résultats détaillés: {str(e)}")
            return ""