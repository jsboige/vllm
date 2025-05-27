#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module pour la génération de rapports standardisés basés sur les résultats des benchmarks Qwen3.

Ce module fournit des classes et fonctions pour générer des rapports dans différents
formats (Markdown, HTML, PDF) à partir des résultats des benchmarks et des analyses.
"""

import os
import json
import datetime
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Tuple
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Import des modules nécessaires
from qwen3_benchmark.config import load_config, get_output_paths
from qwen3_benchmark.analysis import (
    calculate_basic_metrics,
    calculate_llm_metrics,
    calculate_resource_metrics,
    generate_performance_chart,
    generate_comparison_chart,
    generate_context_impact_chart,
    export_visualization
)


class ReportGenerator:
    """
    Classe pour générer des rapports standardisés à partir des résultats des benchmarks.
    
    Cette classe fournit des méthodes pour créer des rapports dans différents formats
    (Markdown, HTML, PDF) et pour personnaliser le contenu et la structure des rapports.
    """
    
    def __init__(self, 
                results: Dict[str, Any],
                config: Optional[Dict[str, Any]] = None,
                template_dir: Optional[str] = None):
        """
        Initialise le générateur de rapports.
        
        Args:
            results (Dict[str, Any]): Résultats du benchmark
            config (Dict[str, Any], optional): Configuration personnalisée
            template_dir (str, optional): Répertoire contenant les templates
        """
        self.results = results
        self.config = config or load_config()
        
        # Déterminer le répertoire des templates
        if template_dir:
            self.template_dir = template_dir
        else:
            # Utiliser le répertoire de templates par défaut
            module_dir = os.path.dirname(os.path.abspath(__file__))
            self.template_dir = os.path.join(module_dir, "templates")
        
        # Initialiser l'environnement Jinja2
        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True,
            extensions=['jinja2.ext.do']
        )
        
        # Extraire les informations de base
        self.model_name = results.get("model", "unknown").upper()
        self.timestamp = results.get("timestamp", datetime.datetime.now().isoformat())
        
        # Préparer les métriques
        self.metrics = self._prepare_metrics()
        
        # Répertoire temporaire pour les ressources (graphiques, etc.)
        self.temp_dir = None
        # self.resources = {} # Commenté car non utilisé pour l'instant
    
    def _prepare_metrics(self) -> Dict[str, Any]:
        """
        Prépare les métriques à partir des résultats du benchmark.
        
        Returns:
            Dict[str, Any]: Métriques calculées
        """
        # Calculer les métriques de base si elles ne sont pas déjà présentes
        if "metrics" in self.results:
            return self.results["metrics"]
        
        # Calculer les métriques
        llm_metrics = calculate_llm_metrics(self.results)
        resource_metrics = calculate_resource_metrics(self.results)
        
        return {
            "llm_metrics": llm_metrics,
            "resource_metrics": resource_metrics
        }
    
    def _generate_visualizations(self) -> Dict[str, str]:
        """
        Génère les visualisations nécessaires pour le rapport.
        
        Returns:
            Dict[str, str]: Dictionnaire des chemins des visualisations générées
        """
        # Créer un répertoire temporaire pour les visualisations
        if not self.temp_dir:
            self.temp_dir = tempfile.mkdtemp(prefix="qwen3_report_")
        
        visualizations_paths = {} # Renommé pour clarté
        
        # Générer un graphique de temps d'exécution
        exec_chart = generate_performance_chart(
            self.results, 
            metric_type='execution_time',
            title=f"Temps d'exécution - {self.model_name}"
        )
        # Utiliser un nom de fichier cohérent, le chemin complet sera dans self.temp_dir
        exec_filename = f"{self.model_name.lower()}_execution_time.png"
        exec_path = os.path.join(self.temp_dir, exec_filename)
        export_visualization(exec_chart, exec_path, 'png') # export_visualization retourne le chemin complet
        visualizations_paths["execution_time"] = exec_path # Stocker le chemin complet
        
        # Générer un graphique de débit
        tps_chart = generate_performance_chart(
            self.results, 
            metric_type='tokens_per_second',
            title=f"Débit - {self.model_name}"
        )
        tps_filename = f"{self.model_name.lower()}_throughput.png"
        tps_path = os.path.join(self.temp_dir, tps_filename)
        export_visualization(tps_chart, tps_path, 'png')
        visualizations_paths["throughput"] = tps_path
        
        # Générer un graphique d'impact de la longueur de contexte si disponible
        if "context_results" in self.results:
            context_chart = generate_context_impact_chart(
                self.results,
                title=f"Impact de la longueur de contexte - {self.model_name}"
            )
            context_filename = f"{self.model_name.lower()}_context_impact.png"
            context_path = os.path.join(self.temp_dir, context_filename)
            export_visualization(context_chart, context_path, 'png')
            visualizations_paths["context_impact"] = context_path
        
        return visualizations_paths
    
    def _prepare_template_data(self) -> Dict[str, Any]:
        """
        Prépare les données pour le template.
        
        Returns:
            Dict[str, Any]: Données pour le template
        """
        # Générer les visualisations (stocke les chemins complets dans self.temp_dir)
        visualizations_paths = self._generate_visualizations()
        
        # Préparer les noms de fichiers pour les templates
        # Les templates s'attendront à trouver les images dans un sous-dossier "resources"
        # ou directement si c'est pour le PDF (géré par le chemin relatif au HTML temporaire)
        visualizations_for_template = {
            key: os.path.basename(path) for key, path in visualizations_paths.items()
        }
        
        # Préparer les données pour le template
        template_data = {
            "title": f"Rapport de benchmark - {self.model_name}",
            "model_name": self.model_name,
            "timestamp": self.timestamp,
            "results": self.results,
            "metrics": self.metrics,
            "visualizations": visualizations_for_template, # Contient les noms de fichiers
            "config": self.config,
            "visualization_full_paths": visualizations_paths # Pour la conversion PDF
        }
        
        return template_data
    
    def generate_markdown_report(self, output_path: Optional[str] = None) -> str:
        """
        Génère un rapport au format Markdown.
        
        Args:
            output_path (str, optional): Chemin où sauvegarder le rapport
        
        Returns:
            str: Contenu du rapport ou chemin du fichier généré
        """
        # Charger le template Markdown
        template = self.env.get_template("markdown_template.md")
        
        # Préparer les données
        template_data = self._prepare_template_data()
        
        # Générer le rapport
        report_content = template.render(**template_data)
        
        # Sauvegarder le rapport si un chemin est spécifié
        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            
            # Copier les ressources si nécessaire
            if self.temp_dir and template_data.get("visualization_full_paths"):
                resources_dir = os.path.join(os.path.dirname(output_path), "resources")
                os.makedirs(resources_dir, exist_ok=True)
                
                for key, viz_full_path in template_data["visualization_full_paths"].items():
                    if os.path.exists(viz_full_path):
                        # Le nom de fichier est déjà dans template_data["visualizations"][key]
                        dest_filename = template_data["visualizations"][key]
                        dest_path = os.path.join(resources_dir, dest_filename)
                        shutil.copy2(viz_full_path, dest_path)
            
            return output_path
        
        return report_content
    
    def generate_html_report(self, output_path: Optional[str] = None, for_pdf: bool = False) -> str:
        """
        Génère un rapport au format HTML.
        
        Args:
            output_path (str, optional): Chemin où sauvegarder le rapport
            for_pdf (bool, optional): Si True, les chemins des images seront relatifs au temp_dir
                                      pour la conversion PDF. Sinon, relatifs au sous-dossier 'resources'.
        
        Returns:
            str: Contenu du rapport ou chemin du fichier généré
        """
        # Charger le template HTML
        # Pour le PDF, nous utilisons le même template HTML, mais les chemins des images seront gérés différemment
        template_name = "pdf_template.html" if for_pdf else "html_template.html"
        template = self.env.get_template(template_name)
        
        # Préparer les données
        template_data = self._prepare_template_data()

        # Ajuster les chemins des visualisations pour le template HTML/PDF
        # Si c'est pour PDF, les chemins dans `visualizations_for_template` (noms de fichiers)
        # seront utilisés par weasyprint relativement au HTML temporaire (qui est dans temp_dir).
        # Si c'est pour HTML autonome, les chemins doivent pointer vers "resources/nom_fichier.png".
        # La logique actuelle dans _prepare_template_data donne déjà les noms de fichiers.
        # Les templates HTML/PDF ont été modifiés pour utiliser "resources/{{ viz_filename }}"
        # ou "{{ viz_filename }}" pour PDF (car le HTML est dans temp_dir).

        # Pour PDF, les images sont référencées par leur nom de fichier,
        # et WeasyPrint les trouvera car le HTML temporaire est dans le même temp_dir.
        # Pour HTML, les images sont copiées dans "resources" et référencées comme "resources/nom_fichier.png".
        # Les templates ont été mis à jour pour refléter cela.

        # Générer le rapport
        report_content = template.render(**template_data)
        
        # Sauvegarder le rapport si un chemin est spécifié
        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            
            # Copier les ressources si nécessaire (seulement pour HTML autonome, pas pour le HTML temporaire du PDF)
            if not for_pdf and self.temp_dir and template_data.get("visualization_full_paths"):
                resources_dir = os.path.join(os.path.dirname(output_path), "resources")
                os.makedirs(resources_dir, exist_ok=True)
                
                for key, viz_full_path in template_data["visualization_full_paths"].items():
                    if os.path.exists(viz_full_path):
                        dest_filename = template_data["visualizations"][key] # nom de fichier
                        dest_path = os.path.join(resources_dir, dest_filename)
                        shutil.copy2(viz_full_path, dest_path)
            
            return output_path
        
        return report_content
    
    def generate_pdf_report(self, output_path: Optional[str] = None) -> str:
        """
        Génère un rapport au format PDF (via HTML).
        
        Args:
            output_path (str, optional): Chemin où sauvegarder le rapport
        
        Returns:
            str: Chemin du fichier PDF généré
        """
        # Vérifier si weasyprint est disponible
        try:
            from weasyprint import HTML, CSS
            from weasyprint.fonts import FontConfiguration
        except ImportError:
            raise ImportError("Le module 'weasyprint' est requis pour générer des rapports PDF. "
                             "Installez-le avec 'pip install weasyprint'.")
        
        # S'assurer que temp_dir est créé pour stocker le HTML temporaire et les images
        if not self.temp_dir:
             # _prepare_template_data (appelé par generate_html_report) créera temp_dir si besoin
            pass

        # Générer d'abord un rapport HTML temporaire dans temp_dir
        # Les images seront référencées par leur nom de fichier simple.
        temp_html_filename = f"{self.model_name.lower()}_report_for_pdf.html"
        # S'assurer que temp_dir est initialisé avant de l'utiliser
        if not self.temp_dir:
             self.temp_dir = tempfile.mkdtemp(prefix="qwen3_report_")
        temp_html_path = os.path.join(self.temp_dir, temp_html_filename)
        
        # Appeler generate_html_report avec for_pdf=True
        # Cela utilisera pdf_template.html et s'assurera que les chemins d'images sont corrects pour weasyprint
        self.generate_html_report(output_path=temp_html_path, for_pdf=True)
        
        # Déterminer le chemin de sortie pour le PDF
        if not output_path:
            paths = get_output_paths()
            reports_dir = paths.get("reports_dir", "reports")
            output_path = os.path.join(reports_dir, f"{self.model_name.lower()}_report.pdf")
        
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # Convertir HTML en PDF
        # WeasyPrint cherchera les images (ex: "image.png") relativement au base_url (temp_html_path)
        font_config = FontConfiguration()
        html = HTML(filename=temp_html_path, base_url=self.temp_dir) # base_url est crucial pour les ressources relatives
        html.write_pdf(output_path, font_config=font_config)
        
        return output_path
    
    def cleanup(self):
        """
        Nettoie les ressources temporaires.
        """
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            self.temp_dir = None


def generate_markdown_report(results: Dict[str, Any], 
                           output_path: Optional[str] = None,
                           config: Optional[Dict[str, Any]] = None,
                           template_dir: Optional[str] = None) -> str:
    """
    Fonction utilitaire pour générer un rapport Markdown.
    """
    generator = ReportGenerator(results, config, template_dir)
    report_path_or_content = generator.generate_markdown_report(output_path)
    generator.cleanup()
    return report_path_or_content


def generate_html_report(results: Dict[str, Any], 
                        output_path: Optional[str] = None,
                        config: Optional[Dict[str, Any]] = None,
                        template_dir: Optional[str] = None) -> str:
    """
    Fonction utilitaire pour générer un rapport HTML.
    """
    generator = ReportGenerator(results, config, template_dir)
    report_path_or_content = generator.generate_html_report(output_path)
    generator.cleanup()
    return report_path_or_content


def generate_pdf_report(results: Dict[str, Any], 
                       output_path: Optional[str] = None,
                       config: Optional[Dict[str, Any]] = None,
                       template_dir: Optional[str] = None) -> str:
    """
    Fonction utilitaire pour générer un rapport PDF.
    """
    generator = ReportGenerator(results, config, template_dir)
    report_path = generator.generate_pdf_report(output_path)
    generator.cleanup()
    return report_path


def export_report(results: Dict[str, Any], 
                 format: str = 'markdown',
                 output_path: Optional[str] = None,
                 config: Optional[Dict[str, Any]] = None,
                 template_dir: Optional[str] = None) -> str:
    """
    Fonction utilitaire pour exporter un rapport dans le format spécifié.
    """
    generator = ReportGenerator(results, config, template_dir)
    
    format = format.lower()
    report_path_or_content = ""
    if format == 'markdown' or format == 'md':
        report_path_or_content = generator.generate_markdown_report(output_path)
    elif format == 'html':
        report_path_or_content = generator.generate_html_report(output_path)
    elif format == 'pdf':
        report_path_or_content = generator.generate_pdf_report(output_path)
    else:
        generator.cleanup() # Nettoyer même en cas d'erreur de format
        raise ValueError(f"Format non supporté: {format}. Utilisez 'markdown', 'html' ou 'pdf'.")
    
    generator.cleanup()
    return report_path_or_content