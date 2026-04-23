#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module pour la génération de visualisations des résultats des benchmarks Qwen3.

Ce module fournit des fonctions pour générer des graphiques standardisés
à partir des résultats des benchmarks, permettant de visualiser les performances
et de comparer différents modèles ou configurations.
"""

import os
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns
from typing import Dict, Any, List, Optional, Union, Tuple
from pathlib import Path

# Configuration globale des graphiques
plt.style.use('seaborn-v0_8-darkgrid')
COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
FIGURE_SIZE = (12, 8)
DPI = 100


def generate_performance_chart(results: Dict[str, Any], 
                              metric_type: str = 'execution_time',
                              title: Optional[str] = None,
                              output_path: Optional[str] = None) -> plt.Figure:
    """
    Génère un graphique de performance basé sur les résultats du benchmark.
    
    Args:
        results (Dict[str, Any]): Résultats du benchmark
        metric_type (str, optional): Type de métrique à visualiser 
                                    ('execution_time', 'tokens_per_second', etc.)
        title (str, optional): Titre du graphique
        output_path (str, optional): Chemin où sauvegarder le graphique
    
    Returns:
        plt.Figure: Figure matplotlib générée
    """
    fig, ax = plt.subplots(figsize=FIGURE_SIZE, dpi=DPI)
    
    # Déterminer le titre si non spécifié
    if title is None:
        if metric_type == 'execution_time':
            title = "Temps d'exécution"
        elif metric_type == 'tokens_per_second':
            title = "Débit (tokens/seconde)"
        else:
            title = f"Performance - {metric_type}"
    
    # Extraire les données pertinentes en fonction du type de métrique
    data = {}
    labels = []
    values = []
    
    if metric_type == 'execution_time':
        # Temps d'exécution global
        if "execution_time" in results:
            labels.append("Total")
            values.append(results["execution_time"])
        
        # Temps d'exécution par API
        if "api_results" in results:
            api_results = results["api_results"]
            
            for api_type in ["completions", "chat", "embeddings", "tool_calling"]:
                if api_type in api_results and api_results[api_type]:
                    times = [r.get("execution_time", 0) for r in api_results[api_type]]
                    if times:
                        avg_time = sum(times) / len(times)
                        labels.append(f"API {api_type}")
                        values.append(avg_time)
        
        # Temps d'exécution par longueur de contexte
        if "context_results" in results:
            context_results = results["context_results"]
            
            for length, items in context_results.items():
                if items:
                    times = [r.get("execution_time", 0) for r in items]
                    if times:
                        avg_time = sum(times) / len(times)
                        labels.append(f"Contexte {length}")
                        values.append(avg_time)
    
    elif metric_type == 'tokens_per_second':
        # Débit par API
        if "api_results" in results:
            api_results = results["api_results"]
            
            for api_type in ["completions", "chat"]:
                if api_type in api_results and api_results[api_type]:
                    times = [r.get("execution_time", 0) for r in api_results[api_type]]
                    tokens = [r.get("tokens_generated", 0) for r in api_results[api_type]]
                    
                    if times and tokens and all(t > 0 for t in times):
                        tps_values = [tok / time for tok, time in zip(tokens, times)]
                        avg_tps = sum(tps_values) / len(tps_values)
                        labels.append(f"API {api_type}")
                        values.append(avg_tps)
        
        # Débit par longueur de contexte
        if "context_results" in results:
            context_results = results["context_results"]
            
            for length, items in context_results.items():
                if items:
                    times = [r.get("execution_time", 0) for r in items]
                    tokens = [r.get("tokens_generated", 0) for r in items]
                    
                    if times and tokens and all(t > 0 for t in times):
                        tps_values = [tok / time for tok, time in zip(tokens, times)]
                        avg_tps = sum(tps_values) / len(tps_values)
                        labels.append(f"Contexte {length}")
                        values.append(avg_tps)
    
    # Créer le graphique en fonction des données disponibles
    if labels and values:
        # Trier les données par valeur
        sorted_data = sorted(zip(labels, values), key=lambda x: x[1], reverse=(metric_type != 'execution_time'))
        labels, values = zip(*sorted_data)
        
        # Créer le graphique à barres
        bars = ax.bar(labels, values, color=COLORS[:len(labels)])
        
        # Ajouter les valeurs sur les barres
        for bar in bars:
            height = bar.get_height()
            if metric_type == 'execution_time':
                value_text = f"{height:.2f}s"
            else:
                value_text = f"{height:.2f}"
            
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                    value_text, ha='center', va='bottom', fontsize=10)
        
        # Configurer les axes et les étiquettes
        ax.set_title(title, fontsize=16)
        
        if metric_type == 'execution_time':
            ax.set_ylabel("Temps (secondes)", fontsize=12)
        elif metric_type == 'tokens_per_second':
            ax.set_ylabel("Tokens par seconde", fontsize=12)
        else:
            ax.set_ylabel(metric_type, fontsize=12)
        
        # Rotation des étiquettes si nécessaire
        if len(labels) > 4:
            plt.xticks(rotation=45, ha='right')
        
        plt.tight_layout()
        
        # Sauvegarder le graphique si un chemin est spécifié
        if output_path:
            plt.savefig(output_path, dpi=DPI, bbox_inches='tight')
    else:
        ax.text(0.5, 0.5, f"Pas de données disponibles pour {metric_type}",
                ha='center', va='center', fontsize=14)
        plt.tight_layout()
    
    return fig
def generate_comparison_chart(results1: Dict[str, Any], 
                             results2: Dict[str, Any],
                             metric_type: str = 'tokens_per_second',
                             name1: str = "Model 1",
                             name2: str = "Model 2",
                             title: Optional[str] = None,
                             output_path: Optional[str] = None) -> plt.Figure:
    """
    Génère un graphique comparant les performances de deux modèles ou configurations.
    
    Args:
        results1 (Dict[str, Any]): Résultats du premier benchmark
        results2 (Dict[str, Any]): Résultats du deuxième benchmark
        metric_type (str, optional): Type de métrique à visualiser
        name1 (str, optional): Nom du premier modèle/configuration
        name2 (str, optional): Nom du deuxième modèle/configuration
        title (str, optional): Titre du graphique
        output_path (str, optional): Chemin où sauvegarder le graphique
    
    Returns:
        plt.Figure: Figure matplotlib générée
    """
    fig, ax = plt.subplots(figsize=FIGURE_SIZE, dpi=DPI)
    
    # Déterminer le titre si non spécifié
    if title is None:
        if metric_type == 'execution_time':
            title = f"Comparaison des temps d'exécution: {name1} vs {name2}"
        elif metric_type == 'tokens_per_second':
            title = f"Comparaison du débit: {name1} vs {name2}"
        else:
            title = f"Comparaison de {metric_type}: {name1} vs {name2}"
    
    # Extraire les données pertinentes en fonction du type de métrique
    categories = []
    values1 = []
    values2 = []
    
    if metric_type == 'execution_time':
        # Temps d'exécution global
        if "execution_time" in results1 and "execution_time" in results2:
            categories.append("Total")
            values1.append(results1["execution_time"])
            values2.append(results2["execution_time"])
        
        # Temps d'exécution par API
        api_types = ["completions", "chat", "embeddings", "tool_calling"]
        
        for api_type in api_types:
            # Vérifier si les deux résultats ont des données pour ce type d'API
            has_data1 = "api_results" in results1 and api_type in results1["api_results"] and results1["api_results"][api_type]
            has_data2 = "api_results" in results2 and api_type in results2["api_results"] and results2["api_results"][api_type]
            
            if has_data1 and has_data2:
                times1 = [r.get("execution_time", 0) for r in results1["api_results"][api_type]]
                times2 = [r.get("execution_time", 0) for r in results2["api_results"][api_type]]
                
                if times1 and times2:
                    avg_time1 = sum(times1) / len(times1)
                    avg_time2 = sum(times2) / len(times2)
                    
                    categories.append(f"API {api_type}")
                    values1.append(avg_time1)
                    values2.append(avg_time2)
    
    elif metric_type == 'tokens_per_second':
        # Débit par API
        api_types = ["completions", "chat"]
        
        for api_type in api_types:
            # Vérifier si les deux résultats ont des données pour ce type d'API
            has_data1 = "api_results" in results1 and api_type in results1["api_results"] and results1["api_results"][api_type]
            has_data2 = "api_results" in results2 and api_type in results2["api_results"] and results2["api_results"][api_type]
            
            if has_data1 and has_data2:
                times1 = [r.get("execution_time", 0) for r in results1["api_results"][api_type]]
                tokens1 = [r.get("tokens_generated", 0) for r in results1["api_results"][api_type]]
                
                times2 = [r.get("execution_time", 0) for r in results2["api_results"][api_type]]
                tokens2 = [r.get("tokens_generated", 0) for r in results2["api_results"][api_type]]
                
                if times1 and tokens1 and times2 and tokens2:
                    tps_values1 = [tok / time for tok, time in zip(tokens1, times1) if time > 0]
                    tps_values2 = [tok / time for tok, time in zip(tokens2, times2) if time > 0]
                    
                    if tps_values1 and tps_values2:
                        avg_tps1 = sum(tps_values1) / len(tps_values1)
                        avg_tps2 = sum(tps_values2) / len(tps_values2)
                        
                        categories.append(f"API {api_type}")
                        values1.append(avg_tps1)
                        values2.append(avg_tps2)
        
        # Comparer les longueurs de contexte communes
        if "context_results" in results1 and "context_results" in results2:
            context_lengths1 = set(results1["context_results"].keys())
            context_lengths2 = set(results2["context_results"].keys())
            common_lengths = context_lengths1.intersection(context_lengths2)
            
            for length in common_lengths:
                items1 = results1["context_results"][length]
                items2 = results2["context_results"][length]
                
                if items1 and items2:
                    times1 = [r.get("execution_time", 0) for r in items1]
                    tokens1 = [r.get("tokens_generated", 0) for r in items1]
                    
                    times2 = [r.get("execution_time", 0) for r in items2]
                    tokens2 = [r.get("tokens_generated", 0) for r in items2]
                    
                    if times1 and tokens1 and times2 and tokens2:
                        tps_values1 = [tok / time for tok, time in zip(tokens1, times1) if time > 0]
                        tps_values2 = [tok / time for tok, time in zip(tokens2, times2) if time > 0]
                        
                        if tps_values1 and tps_values2:
                            avg_tps1 = sum(tps_values1) / len(tps_values1)
                            avg_tps2 = sum(tps_values2) / len(tps_values2)
                            
                            categories.append(f"Contexte {length}")
                            values1.append(avg_tps1)
                            values2.append(avg_tps2)
    
    # Créer le graphique en fonction des données disponibles
    if categories and values1 and values2:
        x = np.arange(len(categories))
        width = 0.35
        
        # Créer les barres
        bars1 = ax.bar(x - width/2, values1, width, label=name1, color=COLORS[0])
        bars2 = ax.bar(x + width/2, values2, width, label=name2, color=COLORS[1])
        
        # Ajouter les valeurs sur les barres
        for bars, values in [(bars1, values1), (bars2, values2)]:
            for bar, value in zip(bars, values):
                height = bar.get_height()
                if metric_type == 'execution_time':
                    value_text = f"{value:.2f}s"
                else:
                    value_text = f"{value:.2f}"
                
                ax.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                        value_text, ha='center', va='bottom', fontsize=9)
        
        # Configurer les axes et les étiquettes
        ax.set_title(title, fontsize=16)
        ax.set_xticks(x)
        ax.set_xticklabels(categories)
        
        if metric_type == 'execution_time':
            ax.set_ylabel("Temps (secondes)", fontsize=12)
        elif metric_type == 'tokens_per_second':
            ax.set_ylabel("Tokens par seconde", fontsize=12)
        else:
            ax.set_ylabel(metric_type, fontsize=12)
        
        ax.legend()
        
        # Rotation des étiquettes si nécessaire
        if len(categories) > 4:
            plt.xticks(rotation=45, ha='right')
        
        plt.tight_layout()
        
        # Sauvegarder le graphique si un chemin est spécifié
        if output_path:
            plt.savefig(output_path, dpi=DPI, bbox_inches='tight')
    else:
        ax.text(0.5, 0.5, f"Pas de données comparables disponibles pour {metric_type}",
                ha='center', va='center', fontsize=14)
        plt.tight_layout()
    
    return fig


def generate_context_impact_chart(results: Dict[str, Any],
                                 metric_type: str = 'tokens_per_second',
                                 title: Optional[str] = None,
                                 output_path: Optional[str] = None) -> plt.Figure:
    """
    Génère un graphique analysant l'impact de la longueur de contexte sur les performances.
    
    Args:
        results (Dict[str, Any]): Résultats du benchmark
        metric_type (str, optional): Type de métrique à visualiser
        title (str, optional): Titre du graphique
        output_path (str, optional): Chemin où sauvegarder le graphique
    
    Returns:
        plt.Figure: Figure matplotlib générée
    """
    fig, ax = plt.subplots(figsize=FIGURE_SIZE, dpi=DPI)
    
    # Déterminer le titre si non spécifié
    if title is None:
        model_name = results.get("model", "").upper()
        if metric_type == 'execution_time':
            title = f"Impact de la longueur de contexte sur le temps d'exécution - {model_name}"
        elif metric_type == 'tokens_per_second':
            title = f"Impact de la longueur de contexte sur le débit - {model_name}"
        else:
            title = f"Impact de la longueur de contexte sur {metric_type} - {model_name}"
    
    # Vérifier si les résultats contiennent des données de contexte
    if "context_results" not in results:
        ax.text(0.5, 0.5, "Pas de données de contexte disponibles",
                ha='center', va='center', fontsize=14)
        plt.tight_layout()
        return fig
    
    context_results = results["context_results"]
    
    # Extraire les longueurs de contexte et les métriques correspondantes
    context_lengths = []
    metric_values = []
    
    for length_str, items in context_results.items():
        if not items:
            continue
        
        try:
            length = int(length_str)
        except ValueError:
            continue
        
        if metric_type == 'execution_time':
            times = [r.get("execution_time", 0) for r in items]
            if times:
                avg_time = sum(times) / len(times)
                context_lengths.append(length)
                metric_values.append(avg_time)
        
        elif metric_type == 'tokens_per_second':
            times = [r.get("execution_time", 0) for r in items]
            tokens = [r.get("tokens_generated", 0) for r in items]
            
            if times and tokens and all(t > 0 for t in times):
                tps_values = [tok / time for tok, time in zip(tokens, times)]
                avg_tps = sum(tps_values) / len(tps_values)
                context_lengths.append(length)
                metric_values.append(avg_tps)
    
    # Créer le graphique en fonction des données disponibles
    if context_lengths and metric_values:
        # Trier les données par longueur de contexte
        sorted_data = sorted(zip(context_lengths, metric_values))
        context_lengths, metric_values = zip(*sorted_data)
        
        # Créer le graphique linéaire
        ax.plot(context_lengths, metric_values, marker='o', linestyle='-', color=COLORS[0], linewidth=2, markersize=8)
        
        # Ajouter les valeurs sur les points
        for x, y in zip(context_lengths, metric_values):
            if metric_type == 'execution_time':
                value_text = f"{y:.2f}s"
            else:
                value_text = f"{y:.2f}"
            
            ax.annotate(value_text, (x, y), textcoords="offset points", 
                        xytext=(0, 10), ha='center', fontsize=9)
        
        # Configurer les axes et les étiquettes
        ax.set_title(title, fontsize=16)
        ax.set_xlabel("Longueur de contexte (tokens)", fontsize=12)
        
        if metric_type == 'execution_time':
            ax.set_ylabel("Temps d'exécution (secondes)", fontsize=12)
        elif metric_type == 'tokens_per_second':
            ax.set_ylabel("Débit (tokens par seconde)", fontsize=12)
        else:
            ax.set_ylabel(metric_type, fontsize=12)
        
        # Formater l'axe x pour afficher les longueurs de contexte sans notation scientifique
        ax.xaxis.set_major_formatter(ticker.StrMethodFormatter('{x:,.0f}'))
        
        # Ajouter une grille pour faciliter la lecture
        ax.grid(True, linestyle='--', alpha=0.7)
        
        plt.tight_layout()
        
        # Sauvegarder le graphique si un chemin est spécifié
        if output_path:
            plt.savefig(output_path, dpi=DPI, bbox_inches='tight')
    else:
        ax.text(0.5, 0.5, f"Pas de données disponibles pour analyser l'impact du contexte sur {metric_type}",
                ha='center', va='center', fontsize=14)
        plt.tight_layout()
    
    return fig
def generate_resource_usage_chart(results: Dict[str, Any],
                                 resource_type: str = 'gpu',
                                 title: Optional[str] = None,
                                 output_path: Optional[str] = None) -> plt.Figure:
    """
    Génère un graphique d'utilisation des ressources.
    
    Args:
        results (Dict[str, Any]): Résultats du benchmark
        resource_type (str, optional): Type de ressource à visualiser ('gpu', 'memory', 'cpu')
        title (str, optional): Titre du graphique
        output_path (str, optional): Chemin où sauvegarder le graphique
    
    Returns:
        plt.Figure: Figure matplotlib générée
    """
    fig, ax = plt.subplots(figsize=FIGURE_SIZE, dpi=DPI)
    
    # Déterminer le titre si non spécifié
    if title is None:
        model_name = results.get("model", "").upper()
        if resource_type == 'gpu':
            title = f"Utilisation GPU - {model_name}"
        elif resource_type == 'memory':
            title = f"Utilisation mémoire - {model_name}"
        elif resource_type == 'cpu':
            title = f"Utilisation CPU - {model_name}"
        else:
            title = f"Utilisation des ressources ({resource_type}) - {model_name}"
    
    # Vérifier si les résultats contiennent des données d'utilisation des ressources
    if "resource_usage" not in results:
        ax.text(0.5, 0.5, "Pas de données d'utilisation des ressources disponibles",
                ha='center', va='center', fontsize=14)
        plt.tight_layout()
        return fig
    
    resource_data = results["resource_usage"]
    
    # Extraire les données en fonction du type de ressource
    timestamps = []
    usage_values = []
    
    if resource_type == 'gpu' and "gpu" in resource_data:
        gpu_data = resource_data["gpu"]
        
        if "timestamps" in gpu_data and "utilization" in gpu_data:
            timestamps = gpu_data["timestamps"]
            usage_values = gpu_data["utilization"]
        
        y_label = "Utilisation GPU (%)"
    
    elif resource_type == 'memory' and "memory" in resource_data:
        memory_data = resource_data["memory"]
        
        if "timestamps" in memory_data and "usage" in memory_data:
            timestamps = memory_data["timestamps"]
            usage_values = memory_data["usage"]
        
        y_label = "Utilisation mémoire (MB)"
    
    elif resource_type == 'cpu' and "cpu" in resource_data:
        cpu_data = resource_data["cpu"]
        
        if "timestamps" in cpu_data and "usage" in cpu_data:
            timestamps = cpu_data["timestamps"]
            usage_values = cpu_data["usage"]
        
        y_label = "Utilisation CPU (%)"
    
    # Créer le graphique en fonction des données disponibles
    if timestamps and usage_values and len(timestamps) == len(usage_values):
        # Convertir les timestamps en indices pour simplifier
        x = list(range(len(timestamps)))
        
        # Créer le graphique linéaire
        ax.plot(x, usage_values, linestyle='-', color=COLORS[0], linewidth=2)
        
        # Ajouter une zone ombrée sous la courbe
        ax.fill_between(x, 0, usage_values, alpha=0.3, color=COLORS[0])
        
        # Configurer les axes et les étiquettes
        ax.set_title(title, fontsize=16)
        ax.set_xlabel("Temps", fontsize=12)
        ax.set_ylabel(y_label, fontsize=12)
        
        # Formater l'axe x pour afficher quelques timestamps
        if len(timestamps) > 10:
            step = len(timestamps) // 10
            tick_positions = x[::step]
            tick_labels = [timestamps[i] for i in range(0, len(timestamps), step)]
            ax.set_xticks(tick_positions)
            ax.set_xticklabels(tick_labels, rotation=45, ha='right')
        else:
            ax.set_xticks(x)
            ax.set_xticklabels(timestamps, rotation=45, ha='right')
        
        # Ajouter des statistiques sur le graphique
        if usage_values:
            avg_usage = sum(usage_values) / len(usage_values)
            max_usage = max(usage_values)
            min_usage = min(usage_values)
            
            stats_text = f"Moyenne: {avg_usage:.2f}\nMax: {max_usage:.2f}\nMin: {min_usage:.2f}"
            ax.text(0.02, 0.95, stats_text, transform=ax.transAxes,
                    verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        # Ajouter une grille pour faciliter la lecture
        ax.grid(True, linestyle='--', alpha=0.7)
        
        plt.tight_layout()
        
        # Sauvegarder le graphique si un chemin est spécifié
        if output_path:
            plt.savefig(output_path, dpi=DPI, bbox_inches='tight')
    else:
        ax.text(0.5, 0.5, f"Pas de données d'utilisation {resource_type} disponibles",
                ha='center', va='center', fontsize=14)
        plt.tight_layout()
    
    return fig


def export_visualization(fig: plt.Figure, 
                        output_path: str, 
                        format: str = 'png',
                        dpi: int = 100) -> str:
    """
    Exporte une visualisation dans le format spécifié.
    
    Args:
        fig (plt.Figure): Figure matplotlib à exporter
        output_path (str): Chemin de base pour le fichier de sortie (sans extension)
        format (str, optional): Format d'export ('png', 'pdf', 'svg', 'jpg')
        dpi (int, optional): Résolution pour les formats raster
    
    Returns:
        str: Chemin du fichier exporté
    """
    # Vérifier le format
    format = format.lower()
    if format not in ['png', 'pdf', 'svg', 'jpg']:
        print(f"Format {format} non supporté, utilisation de PNG par défaut")
        format = 'png'
    
    # Construire le chemin complet
    full_path = f"{output_path}.{format}"
    
    # Créer le répertoire si nécessaire
    os.makedirs(os.path.dirname(os.path.abspath(full_path)), exist_ok=True)
    
    # Exporter la figure
    fig.savefig(full_path, format=format, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    
    return full_path


def generate_dashboard(results: Dict[str, Any], 
                      output_dir: str,
                      model_name: Optional[str] = None) -> List[str]:
    """
    Génère un tableau de bord complet avec plusieurs visualisations.
    
    Args:
        results (Dict[str, Any]): Résultats du benchmark
        output_dir (str): Répertoire où sauvegarder les graphiques
        model_name (str, optional): Nom du modèle pour les titres
    
    Returns:
        List[str]: Liste des chemins des fichiers générés
    """
    if model_name is None:
        model_name = results.get("model", "").upper()
    
    # Créer le répertoire de sortie
    os.makedirs(output_dir, exist_ok=True)
    
    generated_files = []
    
    # 1. Graphique de temps d'exécution
    fig1 = generate_performance_chart(
        results, 
        metric_type='execution_time',
        title=f"Temps d'exécution - {model_name}"
    )
    path1 = os.path.join(output_dir, f"{model_name.lower()}_execution_time")
    file1 = export_visualization(fig1, path1, 'png')
    generated_files.append(file1)
    
    # 2. Graphique de débit
    fig2 = generate_performance_chart(
        results, 
        metric_type='tokens_per_second',
        title=f"Débit - {model_name}"
    )
    path2 = os.path.join(output_dir, f"{model_name.lower()}_throughput")
    file2 = export_visualization(fig2, path2, 'png')
    generated_files.append(file2)
    
    # 3. Graphique d'impact de la longueur de contexte
    if "context_results" in results:
        fig3 = generate_context_impact_chart(
            results,
            title=f"Impact de la longueur de contexte - {model_name}"
        )
        path3 = os.path.join(output_dir, f"{model_name.lower()}_context_impact")
        file3 = export_visualization(fig3, path3, 'png')
        generated_files.append(file3)
    
    # 4. Graphique d'utilisation des ressources
    if "resource_usage" in results:
        # GPU
        if "gpu" in results["resource_usage"]:
            fig4 = generate_resource_usage_chart(
                results,
                resource_type='gpu',
                title=f"Utilisation GPU - {model_name}"
            )
            path4 = os.path.join(output_dir, f"{model_name.lower()}_gpu_usage")
            file4 = export_visualization(fig4, path4, 'png')
            generated_files.append(file4)
        
        # Mémoire
        if "memory" in results["resource_usage"]:
            fig5 = generate_resource_usage_chart(
                results,
                resource_type='memory',
                title=f"Utilisation mémoire - {model_name}"
            )
            path5 = os.path.join(output_dir, f"{model_name.lower()}_memory_usage")
            file5 = export_visualization(fig5, path5, 'png')
            generated_files.append(file5)
    
    return generated_files