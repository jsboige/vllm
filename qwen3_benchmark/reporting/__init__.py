#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module d'initialisation pour la génération de rapports des benchmarks Qwen3.

Ce module expose les classes et fonctions principales pour générer des rapports
standardisés basés sur les résultats des benchmarks et des analyses.
"""

from typing import Dict, Any, List, Optional, Union, Tuple

# Importer les classes et fonctions principales
from .report_generator import (
    ReportGenerator,
    generate_markdown_report,
    generate_html_report,
    generate_pdf_report,
    export_report
)

# Exposer les classes et fonctions principales
__all__ = [
    # Générateur de rapports
    'ReportGenerator',
    
    # Fonctions de génération de rapports
    'generate_markdown_report',
    'generate_html_report',
    'generate_pdf_report',
    'export_report'
]