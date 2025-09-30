#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Module utilitaire pour les scripts de test.
"""

# Couleurs pour les messages
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[0;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color

def log(level: str, message: str) -> None:
    """Affiche un message formaté avec un niveau de log."""
    color = NC
    if level == "INFO":
        color = GREEN
    elif level == "WARNING":
        color = YELLOW
    elif level == "ERROR":
        color = RED
    elif level == "DEBUG":
        color = BLUE
    
    print(f"{color}[{level}] {message}{NC}")