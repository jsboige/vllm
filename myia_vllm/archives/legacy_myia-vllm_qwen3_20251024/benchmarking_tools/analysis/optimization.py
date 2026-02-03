#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module pour l'optimisation des configurations basées sur les résultats des benchmarks Qwen3.

Ce module fournit des fonctions pour déterminer les paramètres optimaux,
générer des configurations optimisées et optimiser les paramètres RoPE
pour les longs contextes.
"""

import os
import json
import yaml
import math
import copy
from typing import Dict, Any, List, Optional, Union, Tuple
from pathlib import Path


def determine_optimal_parameters(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Détermine les paramètres optimaux basés sur les résultats des benchmarks.
    
    Args:
        results (Dict[str, Any]): Résultats du benchmark
    
    Returns:
        Dict[str, Any]: Paramètres optimaux
    """
    optimal_params = {
        "model": results.get("model", ""),
        "execution": {},
        "memory": {},
        "context_length": {}
    }
    
    # Paramètres d'exécution optimaux
    if "metrics" in results:
        metrics = results["metrics"]
        
        # Tokens par seconde
        if "tokens_per_second" in metrics:
            optimal_params["execution"]["tokens_per_second"] = metrics["tokens_per_second"]
        
        # Temps d'exécution moyen
        if "avg_execution_time" in metrics:
            optimal_params["execution"]["avg_execution_time"] = metrics["avg_execution_time"]
    
    # Paramètres de contexte optimaux
    if "analysis" in results and "context_performance" in results["analysis"]:
        context_perf = results["analysis"]["context_performance"]
        
        # Trouver la longueur de contexte avec le meilleur débit
        best_tps = 0
        best_length = 0
        
        for length_str, perf in context_perf.items():
            try:
                length = int(length_str)
                tps = perf.get("avg_tokens_per_second", 0)
                
                if tps > best_tps:
                    best_tps = tps
                    best_length = length
            except ValueError:
                continue
        
        if best_length > 0:
            optimal_params["context_length"]["optimal_length"] = best_length
            optimal_params["context_length"]["optimal_throughput"] = best_tps
        
        # Longueur de contexte maximale stable
        if "max_stable_context" in results["analysis"]:
            optimal_params["context_length"]["max_stable_context"] = results["analysis"]["max_stable_context"]
    
    # Paramètres de mémoire optimaux
    if "resource_usage" in results and "gpu" in results["resource_usage"]:
        gpu_data = results["resource_usage"]["gpu"]
        
        if "memory" in gpu_data:
            memory_values = gpu_data["memory"]
            
            if isinstance(memory_values, list) and memory_values:
                avg_memory = sum(memory_values) / len(memory_values)
                max_memory = max(memory_values)
                
                optimal_params["memory"]["avg_gpu_memory"] = avg_memory
                optimal_params["memory"]["max_gpu_memory"] = max_memory
    
    return optimal_params


def generate_optimized_config(results: Dict[str, Any], 
                             base_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Génère une configuration optimisée basée sur les résultats des benchmarks.
    
    Args:
        results (Dict[str, Any]): Résultats du benchmark
        base_config (Dict[str, Any]): Configuration de base à optimiser
    
    Returns:
        Dict[str, Any]: Configuration optimisée
    """
    # Copier la configuration de base
    optimized_config = copy.deepcopy(base_config)
    
    # Déterminer les paramètres optimaux
    optimal_params = determine_optimal_parameters(results)
    
    # Appliquer les optimisations
    model_name = results.get("model", "").lower()
    
    # Optimiser les paramètres de génération
    if "generation" in optimized_config:
        # Ajuster la taille du batch en fonction des performances
        if "execution" in optimal_params and "tokens_per_second" in optimal_params["execution"]:
            tps = optimal_params["execution"]["tokens_per_second"]
            
            # Heuristique pour déterminer la taille de batch optimale
            if tps < 10:
                optimized_config["generation"]["batch_size"] = 1
            elif tps < 50:
                optimized_config["generation"]["batch_size"] = 4
            elif tps < 100:
                optimized_config["generation"]["batch_size"] = 8
            else:
                optimized_config["generation"]["batch_size"] = 16
    
    # Optimiser les paramètres de contexte
    if "context_length" in optimal_params:
        max_stable_context = optimal_params["context_length"].get("max_stable_context", 0)
        
        if max_stable_context > 0:
            # Appliquer une marge de sécurité de 10%
            safe_context = int(max_stable_context * 0.9)
            
            if "model_params" in optimized_config:
                optimized_config["model_params"]["max_seq_len"] = safe_context
    
    # Optimiser les paramètres de mémoire
    if "memory" in optimal_params and "max_gpu_memory" in optimal_params["memory"]:
        max_memory = optimal_params["memory"]["max_gpu_memory"]
        
        # Ajouter une marge de sécurité de 20%
        safe_memory = int(max_memory * 1.2)
        
        if "hardware" in optimized_config:
            optimized_config["hardware"]["gpu_memory_utilization"] = safe_memory
    
    # Ajouter des métadonnées sur l'optimisation
    optimized_config["optimization_info"] = {
        "based_on_benchmark": True,
        "model": model_name,
        "timestamp": results.get("timestamp", ""),
        "optimal_params": optimal_params
    }
    
    return optimized_config


def optimize_rope_parameters(results: Dict[str, Any], 
                            base_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Optimise les paramètres RoPE pour les longs contextes.
    
    Args:
        results (Dict[str, Any]): Résultats du benchmark
        base_config (Dict[str, Any]): Configuration de base à optimiser
    
    Returns:
        Dict[str, Any]: Configuration avec paramètres RoPE optimisés
    """
    # Copier la configuration de base
    optimized_config = copy.deepcopy(base_config)
    
    # Vérifier si les résultats contiennent des données de contexte
    if "analysis" not in results or "context_performance" not in results["analysis"]:
        return optimized_config
    
    context_perf = results["analysis"]["context_performance"]
    
    # Trouver la longueur de contexte maximale stable
    max_stable_context = 0
    if "max_stable_context" in results["analysis"]:
        max_stable_context = results["analysis"]["max_stable_context"]
    
    # Si aucune longueur de contexte stable n'est trouvée, utiliser la plus grande longueur testée
    if max_stable_context == 0:
        for length_str in context_perf.keys():
            try:
                length = int(length_str)
                if length > max_stable_context:
                    max_stable_context = length
            except ValueError:
                continue
    
    # Si nous avons une longueur de contexte maximale, optimiser les paramètres RoPE
    if max_stable_context > 0:
        # Calculer le facteur d'échelle RoPE optimal
        base_context_length = 4096  # Longueur de contexte de base pour Qwen3
        
        if max_stable_context > base_context_length:
            # Formule pour le facteur d'échelle: (max_context / base_context)^0.6
            # Cette formule est basée sur des recherches empiriques pour l'extension de contexte
            scale_factor = (max_stable_context / base_context_length) ** 0.6
            
            # Arrondir à 2 décimales
            scale_factor = round(scale_factor, 2)
            
            # Appliquer le facteur d'échelle à la configuration
            if "model_params" not in optimized_config:
                optimized_config["model_params"] = {}
            
            optimized_config["model_params"]["rope_scaling"] = {
                "type": "dynamic",
                "factor": scale_factor
            }
            
            # Mettre à jour la longueur de séquence maximale
            optimized_config["model_params"]["max_seq_len"] = max_stable_context
    
    return optimized_config


def generate_optimized_docker_compose(results: Dict[str, Any], 
                                     template_path: str,
                                     output_path: Optional[str] = None) -> str:
    """
    Génère un fichier docker-compose optimisé basé sur les résultats des benchmarks.
    
    Args:
        results (Dict[str, Any]): Résultats du benchmark
        template_path (str): Chemin vers le fichier docker-compose template
        output_path (str, optional): Chemin où sauvegarder le fichier généré
    
    Returns:
        str: Contenu du fichier docker-compose optimisé
    """
    # Charger le template docker-compose
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            docker_compose = yaml.safe_load(f)
    except Exception as e:
        print(f"Erreur lors du chargement du template docker-compose: {str(e)}")
        return ""
    
    # Déterminer les paramètres optimaux
    optimal_params = determine_optimal_parameters(results)
    model_name = results.get("model", "").lower()
    
    # Trouver le service correspondant au modèle
    model_service = None
    for service_name, service_config in docker_compose.get("services", {}).items():
        if model_name in service_name.lower():
            model_service = service_name
            break
    
    if model_service is None:
        print(f"Aucun service correspondant au modèle {model_name} trouvé dans le template")
        return yaml.dump(docker_compose, default_flow_style=False)
    
    # Optimiser les paramètres du service
    service = docker_compose["services"][model_service]
    
    # Optimiser les paramètres de l'environnement
    if "environment" not in service:
        service["environment"] = []
    
    # Convertir l'environnement en dictionnaire si c'est une liste
    env_dict = {}
    if isinstance(service["environment"], list):
        for item in service["environment"]:
            if "=" in item:
                key, value = item.split("=", 1)
                env_dict[key] = value
        
        # Convertir en liste de chaînes "key=value"
        env_list = []
    else:
        env_dict = service["environment"]
        env_list = None
    
    # Optimiser la longueur de contexte
    if "context_length" in optimal_params and "max_stable_context" in optimal_params["context_length"]:
        max_context = optimal_params["context_length"]["max_stable_context"]
        
        # Appliquer une marge de sécurité de 10%
        safe_context = int(max_context * 0.9)
        
        env_dict["MAX_SEQ_LEN"] = str(safe_context)
        
        # Si le modèle utilise RoPE scaling pour les longs contextes
        if max_context > 4096:
            # Calculer le facteur d'échelle RoPE
            scale_factor = (max_context / 4096) ** 0.6
            scale_factor = round(scale_factor, 2)
            
            env_dict["ROPE_SCALING_TYPE"] = "dynamic"
            env_dict["ROPE_SCALING_FACTOR"] = str(scale_factor)
    
    # Optimiser l'utilisation de la mémoire GPU
    if "memory" in optimal_params and "max_gpu_memory" in optimal_params["memory"]:
        max_memory = optimal_params["memory"]["max_gpu_memory"]
        
        # Ajouter une marge de sécurité de 20%
        safe_memory = int(max_memory * 1.2)
        
        # Convertir en GB si nécessaire
        if safe_memory > 1000:
            safe_memory_gb = safe_memory / 1024
            env_dict["GPU_MEMORY_UTILIZATION"] = f"{safe_memory_gb:.1f}GiB"
        else:
            env_dict["GPU_MEMORY_UTILIZATION"] = f"{safe_memory}MiB"
    
    # Optimiser la taille du batch
    if "execution" in optimal_params and "tokens_per_second" in optimal_params["execution"]:
        tps = optimal_params["execution"]["tokens_per_second"]
        
        # Heuristique pour déterminer la taille de batch optimale
        if tps < 10:
            batch_size = 1
        elif tps < 50:
            batch_size = 4
        elif tps < 100:
            batch_size = 8
        else:
            batch_size = 16
        
        env_dict["BATCH_SIZE"] = str(batch_size)
    
    # Mettre à jour l'environnement dans le service
    if env_list is not None:
        # Convertir le dictionnaire en liste
        service["environment"] = [f"{key}={value}" for key, value in env_dict.items()]
    else:
        service["environment"] = env_dict
    
    # Ajouter un label avec les informations d'optimisation
    if "labels" not in service:
        service["labels"] = []
    
    service["labels"].append(f"org.qwen3.optimized=true")
    service["labels"].append(f"org.qwen3.model={model_name}")
    service["labels"].append(f"org.qwen3.benchmark_timestamp={results.get('timestamp', '')}")
    
    # Générer le contenu YAML
    optimized_content = yaml.dump(docker_compose, default_flow_style=False)
    
    # Sauvegarder le fichier si un chemin est spécifié
    if output_path:
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(optimized_content)
            print(f"Fichier docker-compose optimisé sauvegardé dans {output_path}")
        except Exception as e:
            print(f"Erreur lors de la sauvegarde du fichier docker-compose: {str(e)}")
    
    return optimized_content


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Charge une configuration à partir d'un fichier YAML ou JSON.
    
    Args:
        config_path (str): Chemin vers le fichier de configuration
    
    Returns:
        Dict[str, Any]: Configuration chargée
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                return yaml.safe_load(f)
            elif config_path.endswith('.json'):
                return json.load(f)
            else:
                # Essayer YAML par défaut
                return yaml.safe_load(f)
    except Exception as e:
        print(f"Erreur lors du chargement de la configuration: {str(e)}")
        return {}


def save_config(config: Dict[str, Any], output_path: str) -> bool:
    """
    Sauvegarde une configuration dans un fichier YAML ou JSON.
    
    Args:
        config (Dict[str, Any]): Configuration à sauvegarder
        output_path (str): Chemin où sauvegarder la configuration
    
    Returns:
        bool: True si la sauvegarde a réussi, False sinon
    """
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            if output_path.endswith('.yaml') or output_path.endswith('.yml'):
                yaml.dump(config, f, default_flow_style=False)
            elif output_path.endswith('.json'):
                json.dump(config, f, indent=2, ensure_ascii=False)
            else:
                # Utiliser YAML par défaut
                yaml.dump(config, f, default_flow_style=False)
        return True
    except Exception as e:
        print(f"Erreur lors de la sauvegarde de la configuration: {str(e)}")
        return False