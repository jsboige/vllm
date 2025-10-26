#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Package qwen3_benchmark pour les tests de performance des modèles Qwen3.

Ce package fournit une architecture consolidée pour tester et optimiser
les performances des modèles Qwen3 (MICRO, MINI, MEDIUM).
"""

__version__ = "0.1.0"
__author__ = "MyIA Team"
__description__ = "Architecture consolidée pour les tests de performance Qwen3"

# Exposer les modules principaux
from . import config
from . import core
from . import benchmarks
from . import analysis
from . import reporting