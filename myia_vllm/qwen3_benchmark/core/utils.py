#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de fonctions utilitaires pour les benchmarks Qwen3.

Ce module fournit des fonctions utilitaires communes utilisées par les différents
composants de l'architecture de tests de performance Qwen3.
"""

import os
import time
import random
import logging
import string
import subprocess
from typing import Dict, Any, List, Optional, Union, Tuple, Callable, TypeVar

# Type générique pour la fonction measure_execution_time
T = TypeVar('T')


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Configure et retourne un logger avec le nom spécifié.
    
    Args:
        name (str): Nom du logger
        level (int, optional): Niveau de logging
        
    Returns:
        logging.Logger: Logger configuré
    """
    # Créer le logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Vérifier si le logger a déjà des handlers pour éviter les doublons
    if not logger.handlers:
        # Créer un handler pour la console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        
        # Définir le format
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        
        # Ajouter le handler au logger
        logger.addHandler(console_handler)
    
    return logger


def measure_execution_time(func: Callable[[], T]) -> Tuple[T, float]:
    """
    Mesure le temps d'exécution d'une fonction.
    
    Args:
        func (Callable[[], T]): Fonction à exécuter
        
    Returns:
        Tuple[T, float]: (Résultat de la fonction, Temps d'exécution en secondes)
    """
    start_time = time.time()
    result = func()
    execution_time = time.time() - start_time
    
    return result, execution_time


def format_time(seconds: float) -> str:
    """
    Formate un temps en secondes en une chaîne lisible.
    
    Args:
        seconds (float): Temps en secondes
        
    Returns:
        str: Temps formaté
    """
    if seconds < 0.001:
        return f"{seconds * 1000000:.2f} µs"
    elif seconds < 1:
        return f"{seconds * 1000:.2f} ms"
    elif seconds < 60:
        return f"{seconds:.2f} s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes} min {secs:.2f} s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours} h {minutes} min {secs:.2f} s"


def format_memory(bytes_value: int) -> str:
    """
    Formate une taille en octets en une chaîne lisible.
    
    Args:
        bytes_value (int): Taille en octets
        
    Returns:
        str: Taille formatée
    """
    if bytes_value < 1024:
        return f"{bytes_value} B"
    elif bytes_value < 1024 * 1024:
        return f"{bytes_value / 1024:.2f} KB"
    elif bytes_value < 1024 * 1024 * 1024:
        return f"{bytes_value / (1024 * 1024):.2f} MB"
    else:
        return f"{bytes_value / (1024 * 1024 * 1024):.2f} GB"


def monitor_gpu_usage() -> Dict[str, Any]:
    """
    Surveille l'utilisation GPU en utilisant nvidia-smi.
    
    Returns:
        Dict[str, Any]: Informations sur l'utilisation GPU
    """
    try:
        # Exécuter nvidia-smi pour obtenir les informations GPU
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parser la sortie
        gpu_info = []
        for line in result.stdout.strip().split('\n'):
            parts = line.split(',')
            if len(parts) >= 5:
                gpu_info.append({
                    "index": int(parts[0].strip()),
                    "name": parts[1].strip(),
                    "memory_used_mb": float(parts[2].strip()),
                    "memory_total_mb": float(parts[3].strip()),
                    "utilization_percent": float(parts[4].strip())
                })
        
        return {
            "timestamp": time.time(),
            "gpus": gpu_info,
            "success": True
        }
        
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        # En cas d'erreur (nvidia-smi non disponible ou autre)
        return {
            "timestamp": time.time(),
            "error": str(e),
            "success": False
        }


def generate_test_text(target_length: int, seed: Optional[int] = None) -> str:
    """
    Génère un texte de test de la longueur spécifiée.
    
    Args:
        target_length (int): Longueur cible en caractères
        seed (int, optional): Graine pour la génération aléatoire
        
    Returns:
        str: Texte généré
    """
    # Définir la graine aléatoire si spécifiée
    if seed is not None:
        random.seed(seed)
    
    # Texte de base pour la génération
    base_paragraphs = [
        "Les modèles de langage comme Qwen3 sont conçus pour comprendre et générer du texte de manière naturelle. "
        "Ils sont entraînés sur de vastes corpus de textes pour apprendre les structures linguistiques et les connaissances générales.",
        
        "L'architecture Transformer, sur laquelle repose Qwen3, utilise des mécanismes d'attention pour traiter efficacement "
        "les séquences de texte. Cette approche permet au modèle de capturer des dépendances à longue distance dans le texte.",
        
        "La quantification des modèles de langage permet de réduire leur taille tout en préservant leurs performances. "
        "Des techniques comme AWQ (Activation-aware Weight Quantization) permettent d'optimiser ce compromis.",
        
        "Les benchmarks de performance pour les modèles de langage évaluent différents aspects comme la vitesse d'inférence, "
        "la qualité des réponses, la gestion du contexte et l'utilisation des ressources.",
        
        "Le contexte maximal d'un modèle détermine la quantité de texte qu'il peut prendre en compte lors de la génération. "
        "Les techniques comme RoPE (Rotary Position Embedding) permettent d'étendre ce contexte.",
        
        "L'optimisation des paramètres de déploiement comme la taille du batch, l'utilisation de la mémoire GPU et "
        "les techniques de mise en cache peut significativement améliorer les performances d'inférence."
    ]
    
    # Générer le texte jusqu'à atteindre la longueur cible
    generated_text = ""
    while len(generated_text) < target_length:
        # Ajouter un paragraphe aléatoire
        paragraph = random.choice(base_paragraphs)
        
        # Ajouter des variations aléatoires pour éviter la répétition exacte
        words = paragraph.split()
        for i in range(len(words)):
            if random.random() < 0.1:  # 10% de chance de modifier un mot
                if random.random() < 0.5:
                    # Ajouter un adjectif
                    adjectives = ["important", "essentiel", "avancé", "complexe", "efficace", "puissant", "optimisé"]
                    words[i] = random.choice(adjectives) + " " + words[i]
                else:
                    # Remplacer par un synonyme ou une variation
                    if words[i] == "modèle":
                        words[i] = random.choice(["système", "modèle", "LLM", "framework"])
                    elif words[i] == "langage":
                        words[i] = random.choice(["langage", "langue", "texte", "communication"])
                    elif words[i] == "performance":
                        words[i] = random.choice(["performance", "efficacité", "rapidité", "capacité"])
        
        modified_paragraph = " ".join(words)
        
        # Ajouter le paragraphe modifié
        generated_text += modified_paragraph + "\n\n"
    
    # Tronquer à la longueur exacte
    return generated_text[:target_length]


def count_tokens(text: str, model_name: str = "gpt-3.5-turbo") -> int:
    """
    Estime le nombre de tokens dans un texte.
    
    Cette fonction utilise une approximation simple basée sur le nombre de mots.
    Pour une estimation plus précise, il faudrait utiliser le tokenizer spécifique au modèle.
    
    Args:
        text (str): Texte à analyser
        model_name (str, optional): Nom du modèle pour l'estimation
        
    Returns:
        int: Nombre estimé de tokens
    """
    # Approximation simple: 1 token ≈ 0.75 mots
    words = text.split()
    return int(len(words) * 0.75)


def generate_random_string(length: int) -> str:
    """
    Génère une chaîne aléatoire de la longueur spécifiée.
    
    Args:
        length (int): Longueur de la chaîne à générer
        
    Returns:
        str: Chaîne aléatoire
    """
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))