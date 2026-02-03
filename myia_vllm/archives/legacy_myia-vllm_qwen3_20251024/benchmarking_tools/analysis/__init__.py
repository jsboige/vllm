#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module d'initialisation pour l'analyse des résultats des benchmarks Qwen3.

Ce module expose les classes et fonctions principales pour analyser les résultats
des benchmarks, visualiser les données et optimiser les configurations.
"""

from typing import Dict, Any, List, Optional, Union, Tuple

# Importer les classes et fonctions principales
from .metrics import (
    calculate_basic_metrics,
    calculate_llm_metrics,
    calculate_resource_metrics,
    compare_results
)

from .visualization import (
    generate_performance_chart,
    generate_comparison_chart,
    generate_context_impact_chart,
    export_visualization
)

from .optimization import (
    determine_optimal_parameters,
    generate_optimized_config,
    optimize_rope_parameters,
    generate_optimized_docker_compose
)

# Exposer les classes et fonctions principales
__all__ = [
    # Métriques
    'calculate_basic_metrics',
    'calculate_llm_metrics',
    'calculate_resource_metrics',
    'compare_results',
    
    # Visualisation
    'generate_performance_chart',
    'generate_comparison_chart',
    'generate_context_impact_chart',
    'export_visualization',
    
    # Optimisation
    'determine_optimal_parameters',
    'generate_optimized_config',
    'optimize_rope_parameters',
    'generate_optimized_docker_compose'
]