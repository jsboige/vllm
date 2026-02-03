#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module pour le calcul des métriques de performance des benchmarks Qwen3.

Ce module fournit des fonctions pour calculer diverses métriques de performance
à partir des résultats des benchmarks, y compris des métriques standard,
des métriques spécifiques aux LLM et des métriques d'utilisation des ressources.
"""

import numpy as np
import math
import json
from typing import Dict, Any, List, Optional, Union, Tuple
from pathlib import Path


def calculate_basic_metrics(data: List[float], 
                           include_percentiles: bool = True) -> Dict[str, float]:
    """
    Calcule les métriques statistiques de base pour une série de données.
    
    Args:
        data (List[float]): Liste des valeurs à analyser
        include_percentiles (bool, optional): Si True, inclut les percentiles 
                                             (25%, 50%, 75%, 95%, 99%)
    
    Returns:
        Dict[str, float]: Dictionnaire contenant les métriques calculées
    """
    if not data:
        return {}
    
    metrics = {
        "mean": float(np.mean(data)),
        "median": float(np.median(data)),
        "min": float(np.min(data)),
        "max": float(np.max(data)),
        "std_dev": float(np.std(data)),
        "variance": float(np.var(data)),
        "count": len(data)
    }
    
    if include_percentiles:
        percentiles = [25, 50, 75, 95, 99]
        for p in percentiles:
            metrics[f"p{p}"] = float(np.percentile(data, p))
    
    return metrics


def calculate_llm_metrics(results: Dict[str, Any], 
                         reference_texts: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Calcule les métriques spécifiques pour l'évaluation des modèles LLM.
    
    Args:
        results (Dict[str, Any]): Résultats du benchmark
        reference_texts (List[str], optional): Textes de référence pour les métriques 
                                              comme BLEU, ROUGE, etc.
    
    Returns:
        Dict[str, Any]: Dictionnaire contenant les métriques calculées
    """
    metrics = {}
    
    # Extraire les données pertinentes des résultats
    if "api_results" in results:
        # Métriques pour les API
        api_metrics = {}
        
        # Traiter les résultats de complétion
        if "completions" in results["api_results"]:
            completion_times = [r.get("execution_time", 0) for r in results["api_results"]["completions"]]
            tokens_generated = [r.get("tokens_generated", 0) for r in results["api_results"]["completions"]]
            
            if completion_times and tokens_generated:
                # Calculer les tokens par seconde
                tokens_per_second = []
                for time, tokens in zip(completion_times, tokens_generated):
                    if time > 0:
                        tokens_per_second.append(tokens / time)
                
                if tokens_per_second:
                    api_metrics["completions"] = {
                        "avg_tokens_per_second": float(np.mean(tokens_per_second)),
                        "median_tokens_per_second": float(np.median(tokens_per_second)),
                        "max_tokens_per_second": float(np.max(tokens_per_second)),
                        "total_tokens_generated": sum(tokens_generated)
                    }
        
        # Traiter les résultats de chat
        if "chat" in results["api_results"]:
            chat_times = [r.get("execution_time", 0) for r in results["api_results"]["chat"]]
            chat_tokens = [r.get("tokens_generated", 0) for r in results["api_results"]["chat"]]
            
            if chat_times and chat_tokens:
                # Calculer les tokens par seconde
                tokens_per_second = []
                for time, tokens in zip(chat_times, chat_tokens):
                    if time > 0:
                        tokens_per_second.append(tokens / time)
                
                if tokens_per_second:
                    api_metrics["chat"] = {
                        "avg_tokens_per_second": float(np.mean(tokens_per_second)),
                        "median_tokens_per_second": float(np.median(tokens_per_second)),
                        "max_tokens_per_second": float(np.max(tokens_per_second)),
                        "total_tokens_generated": sum(chat_tokens)
                    }
        
        if api_metrics:
            metrics["api_metrics"] = api_metrics
    
    # Traiter les résultats de contexte
    if "context_results" in results:
        context_metrics = {}
        
        for context_length, context_data in results["context_results"].items():
            if not context_data:
                continue
            
            times = [r.get("execution_time", 0) for r in context_data]
            tokens_input = [r.get("tokens_input", 0) for r in context_data]
            tokens_generated = [r.get("tokens_generated", 0) for r in context_data]
            
            if times and tokens_generated:
                # Calculer les tokens par seconde
                tokens_per_second = []
                for time, tokens in zip(times, tokens_generated):
                    if time > 0:
                        tokens_per_second.append(tokens / time)
                
                context_metrics[context_length] = {
                    "avg_tokens_per_second": float(np.mean(tokens_per_second)) if tokens_per_second else 0,
                    "avg_execution_time": float(np.mean(times)),
                    "avg_tokens_input": float(np.mean(tokens_input)) if tokens_input else 0,
                    "avg_tokens_generated": float(np.mean(tokens_generated)) if tokens_generated else 0
                }
        
        if context_metrics:
            metrics["context_metrics"] = context_metrics
    
    # Traiter les résultats de QA documentaire
    if "qa_results" in results:
        qa_data = results["qa_results"]
        
        if qa_data:
            times = [r.get("execution_time", 0) for r in qa_data]
            tokens_generated = [r.get("tokens_generated", 0) for r in qa_data]
            
            if times and tokens_generated:
                # Calculer les tokens par seconde
                tokens_per_second = []
                for time, tokens in zip(times, tokens_generated):
                    if time > 0:
                        tokens_per_second.append(tokens / time)
                
                metrics["qa_metrics"] = {
                    "avg_tokens_per_second": float(np.mean(tokens_per_second)) if tokens_per_second else 0,
                    "avg_execution_time": float(np.mean(times)),
                    "avg_tokens_generated": float(np.mean(tokens_generated)) if tokens_generated else 0,
                    "total_questions": len(qa_data)
                }
    
    # Calculer la perplexité si des textes de référence sont fournis
    if reference_texts and "qa_results" in results:
        # Cette implémentation est simplifiée et nécessiterait une bibliothèque comme nltk ou transformers
        # pour une implémentation complète de la perplexité, BLEU, ROUGE, etc.
        metrics["nlp_metrics"] = {
            "perplexity": "Non implémenté - nécessite une bibliothèque NLP",
            "bleu": "Non implémenté - nécessite une bibliothèque NLP",
            "rouge": "Non implémenté - nécessite une bibliothèque NLP"
        }
    
    return metrics


def calculate_resource_metrics(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calcule les métriques d'utilisation des ressources (mémoire, CPU, GPU).
    
    Args:
        results (Dict[str, Any]): Résultats du benchmark contenant des données d'utilisation des ressources
    
    Returns:
        Dict[str, Any]: Dictionnaire contenant les métriques d'utilisation des ressources
    """
    resource_metrics = {}
    
    # Extraire les données d'utilisation des ressources si disponibles
    if "resource_usage" in results:
        resource_data = results["resource_usage"]
        
        # Métriques de mémoire
        if "memory" in resource_data:
            memory_values = resource_data["memory"]
            if isinstance(memory_values, list) and memory_values:
                resource_metrics["memory"] = calculate_basic_metrics(memory_values)
        
        # Métriques CPU
        if "cpu" in resource_data:
            cpu_values = resource_data["cpu"]
            if isinstance(cpu_values, list) and cpu_values:
                resource_metrics["cpu"] = calculate_basic_metrics(cpu_values)
        
        # Métriques GPU
        if "gpu" in resource_data:
            gpu_data = resource_data["gpu"]
            
            # Utilisation GPU
            if "utilization" in gpu_data:
                gpu_util = gpu_data["utilization"]
                if isinstance(gpu_util, list) and gpu_util:
                    resource_metrics["gpu_utilization"] = calculate_basic_metrics(gpu_util)
            
            # Mémoire GPU
            if "memory" in gpu_data:
                gpu_mem = gpu_data["memory"]
                if isinstance(gpu_mem, list) and gpu_mem:
                    resource_metrics["gpu_memory"] = calculate_basic_metrics(gpu_mem)
            
            # Température GPU
            if "temperature" in gpu_data:
                gpu_temp = gpu_data["temperature"]
                if isinstance(gpu_temp, list) and gpu_temp:
                    resource_metrics["gpu_temperature"] = calculate_basic_metrics(gpu_temp)
    
    # Calculer l'efficacité des ressources
    if "api_metrics" in results and "resource_metrics" in results:
        api_metrics = results["api_metrics"]
        
        # Calculer les tokens par unité de ressource
        if "completions" in api_metrics and "gpu_utilization" in resource_metrics:
            tokens_per_second = api_metrics["completions"].get("avg_tokens_per_second", 0)
            avg_gpu_util = resource_metrics["gpu_utilization"].get("mean", 1)
            
            if avg_gpu_util > 0:
                resource_metrics["efficiency"] = {
                    "tokens_per_gpu_percent": tokens_per_second / avg_gpu_util
                }
    
    return resource_metrics


def compare_results(results1: Dict[str, Any], 
                   results2: Dict[str, Any], 
                   name1: str = "model1", 
                   name2: str = "model2") -> Dict[str, Any]:
    """
    Compare les résultats entre deux modèles ou configurations.
    
    Args:
        results1 (Dict[str, Any]): Résultats du premier benchmark
        results2 (Dict[str, Any]): Résultats du deuxième benchmark
        name1 (str, optional): Nom du premier modèle/configuration
        name2 (str, optional): Nom du deuxième modèle/configuration
    
    Returns:
        Dict[str, Any]: Dictionnaire contenant les comparaisons
    """
    comparison = {
        "models": {
            name1: results1.get("model", name1),
            name2: results2.get("model", name2)
        },
        "execution_time": {},
        "throughput": {},
        "context_length": {},
        "resource_usage": {}
    }
    
    # Comparer les temps d'exécution
    time1 = results1.get("execution_time", 0)
    time2 = results2.get("execution_time", 0)
    
    if time1 > 0 and time2 > 0:
        time_diff = time2 - time1
        time_ratio = time2 / time1 if time1 > 0 else float('inf')
        
        comparison["execution_time"] = {
            name1: time1,
            name2: time2,
            "difference": time_diff,
            "ratio": time_ratio,
            "faster": name1 if time1 < time2 else name2
        }
    
    # Comparer les métriques d'API si disponibles
    metrics1 = calculate_llm_metrics(results1)
    metrics2 = calculate_llm_metrics(results2)
    
    api_metrics1 = metrics1.get("api_metrics", {}).get("completions", {})
    api_metrics2 = metrics2.get("api_metrics", {}).get("completions", {})
    
    if api_metrics1 and api_metrics2:
        tps1 = api_metrics1.get("avg_tokens_per_second", 0)
        tps2 = api_metrics2.get("avg_tokens_per_second", 0)
        
        if tps1 > 0 and tps2 > 0:
            tps_diff = tps2 - tps1
            tps_ratio = tps2 / tps1 if tps1 > 0 else float('inf')
            
            comparison["throughput"] = {
                name1: tps1,
                name2: tps2,
                "difference": tps_diff,
                "ratio": tps_ratio,
                "faster": name1 if tps1 > tps2 else name2
            }
    
    # Comparer les métriques de contexte si disponibles
    context_metrics1 = metrics1.get("context_metrics", {})
    context_metrics2 = metrics2.get("context_metrics", {})
    
    if context_metrics1 and context_metrics2:
        common_lengths = set(context_metrics1.keys()).intersection(set(context_metrics2.keys()))
        
        for length in common_lengths:
            cm1 = context_metrics1[length]
            cm2 = context_metrics2[length]
            
            tps1 = cm1.get("avg_tokens_per_second", 0)
            tps2 = cm2.get("avg_tokens_per_second", 0)
            
            if tps1 > 0 and tps2 > 0:
                comparison["context_length"][length] = {
                    name1: tps1,
                    name2: tps2,
                    "ratio": tps2 / tps1 if tps1 > 0 else float('inf'),
                    "faster": name1 if tps1 > tps2 else name2
                }
    
    # Comparer l'utilisation des ressources si disponible
    resource_metrics1 = calculate_resource_metrics(results1)
    resource_metrics2 = calculate_resource_metrics(results2)
    
    if resource_metrics1 and resource_metrics2:
        # Comparer l'utilisation GPU
        if "gpu_utilization" in resource_metrics1 and "gpu_utilization" in resource_metrics2:
            gpu1 = resource_metrics1["gpu_utilization"].get("mean", 0)
            gpu2 = resource_metrics2["gpu_utilization"].get("mean", 0)
            
            comparison["resource_usage"]["gpu_utilization"] = {
                name1: gpu1,
                name2: gpu2,
                "difference": gpu2 - gpu1,
                "ratio": gpu2 / gpu1 if gpu1 > 0 else float('inf'),
                "more_efficient": name1 if gpu1 < gpu2 else name2
            }
        
        # Comparer la mémoire GPU
        if "gpu_memory" in resource_metrics1 and "gpu_memory" in resource_metrics2:
            mem1 = resource_metrics1["gpu_memory"].get("mean", 0)
            mem2 = resource_metrics2["gpu_memory"].get("mean", 0)
            
            comparison["resource_usage"]["gpu_memory"] = {
                name1: mem1,
                name2: mem2,
                "difference": mem2 - mem1,
                "ratio": mem2 / mem1 if mem1 > 0 else float('inf'),
                "more_efficient": name1 if mem1 < mem2 else name2
            }
    
    return comparison


def load_benchmark_results(file_path: str) -> Dict[str, Any]:
    """
    Charge les résultats d'un benchmark à partir d'un fichier JSON.
    
    Args:
        file_path (str): Chemin vers le fichier de résultats
    
    Returns:
        Dict[str, Any]: Résultats du benchmark
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Erreur lors du chargement des résultats: {str(e)}")
        return {}


def aggregate_results(results_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Agrège les résultats de plusieurs benchmarks.
    
    Args:
        results_list (List[Dict[str, Any]]): Liste des résultats de benchmark à agréger
    
    Returns:
        Dict[str, Any]: Résultats agrégés
    """
    if not results_list:
        return {}
    
    # Initialiser les structures pour l'agrégation
    aggregated = {
        "models": [],
        "execution_times": [],
        "api_results": {
            "completions": [],
            "chat": [],
            "embeddings": [],
            "tool_calling": []
        },
        "context_results": {},
        "qa_results": []
    }
    
    # Agréger les résultats
    for result in results_list:
        # Ajouter le modèle
        model = result.get("model", "unknown")
        if model not in aggregated["models"]:
            aggregated["models"].append(model)
        
        # Ajouter le temps d'exécution
        if "execution_time" in result:
            aggregated["execution_times"].append({
                "model": model,
                "execution_time": result["execution_time"]
            })
        
        # Agréger les résultats d'API
        if "api_results" in result:
            api_results = result["api_results"]
            
            for api_type in ["completions", "chat", "embeddings", "tool_calling"]:
                if api_type in api_results:
                    for item in api_results[api_type]:
                        item_with_model = item.copy()
                        item_with_model["model"] = model
                        aggregated["api_results"][api_type].append(item_with_model)
        
        # Agréger les résultats de contexte
        if "context_results" in result:
            context_results = result["context_results"]
            
            for length, items in context_results.items():
                if length not in aggregated["context_results"]:
                    aggregated["context_results"][length] = []
                
                for item in items:
                    item_with_model = item.copy()
                    item_with_model["model"] = model
                    aggregated["context_results"][length].append(item_with_model)
        
        # Agréger les résultats de QA
        if "qa_results" in result:
            for item in result["qa_results"]:
                item_with_model = item.copy()
                item_with_model["model"] = model
                aggregated["qa_results"].append(item_with_model)
    
    return aggregated