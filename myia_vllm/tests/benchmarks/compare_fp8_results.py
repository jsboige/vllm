#!/usr/bin/env python3
"""
Script de comparaison des résultats de benchmarks FP8
Objectif: Analyser l'impact de --calculate-kv-scales sur performance et qualité
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional

def load_benchmark_results(file_path: str) -> Optional[Dict]:
    """Charger un fichier de résultats de benchmark"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Fichier non trouvé: {file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Erreur JSON dans {file_path}: {e}")
        return None

def calculate_metrics_difference(baseline: Dict, calibrated: Dict) -> Dict:
    """Calculer les différences de métriques entre baseline et calibré"""
    diff = {}
    
    # Métriques TTFT
    if 'ttft' in baseline and 'ttft' in calibrated:
        baseline_ttft = baseline['ttft']['duration_ms']
        calibrated_ttft = calibrated['ttft']['duration_ms']
        diff['ttft'] = {
            'baseline_ms': baseline_ttft,
            'calibrated_ms': calibrated_ttft,
            'difference_ms': calibrated_ttft - baseline_ttft,
            'difference_percent': ((calibrated_ttft - baseline_ttft) / baseline_ttft) * 100 if baseline_ttft > 0 else 0
        }
    
    # Métriques Throughput
    if 'throughput' in baseline and 'throughput' in calibrated:
        baseline_tps = baseline['throughput']['tokens_per_second']
        calibrated_tps = calibrated['throughput']['tokens_per_second']
        diff['throughput'] = {
            'baseline_tps': baseline_tps,
            'calibrated_tps': calibrated_tps,
            'difference_tps': calibrated_tps - baseline_tps,
            'difference_percent': ((calibrated_tps - baseline_tps) / baseline_tps) * 100 if baseline_tps > 0 else 0
        }
    
    return diff

def analyze_warnings(baseline: Dict, calibrated: Dict) -> Dict:
    """Analyser les warnings entre baseline et calibré"""
    analysis = {
        'baseline_warnings': baseline.get('warnings_observed', []),
        'calibrated_warnings': calibrated.get('warnings_observed', []),
        'warnings_resolved': [],
        'warnings_remaining': []
    }
    
    baseline_warnings = set(analysis['baseline_warnings'])
    calibrated_warnings = set(analysis['calibrated_warnings'])
    
    # Warnings résolus par calibration
    analysis['warnings_resolved'] = list(baseline_warnings - calibrated_warnings)
    
    # Warnings restants après calibration
    analysis['warnings_remaining'] = list(calibrated_warnings)
    
    return analysis

def generate_comparison_report(baseline_file: str, calibrated_file: str, output_file: str):
    """Générer un rapport de comparaison complet"""
    
    print(f"🔍 Analyse comparaison FP8")
    print(f"   Baseline: {baseline_file}")
    print(f"   Calibré: {calibrated_file}")
    print(f"   Sortie: {output_file}")
    
    # Charger les résultats
    baseline_results = load_benchmark_results(baseline_file)
    calibrated_results = load_benchmark_results(calibrated_file)
    
    if not baseline_results or not calibrated_results:
        print("❌ Impossible de charger les fichiers de résultats")
        return False
    
    # Calculer les différences
    metrics_diff = calculate_metrics_difference(baseline_results, calibrated_results)
    warnings_analysis = analyze_warnings(baseline_results, calibrated_results)
    
    # Générer le rapport
    report = {
        "comparison_metadata": {
            "timestamp": "2025-10-30T12:48:00Z",
            "baseline_file": baseline_file,
            "calibrated_file": calibrated_file,
            "model": baseline_results.get('model', 'Unknown'),
            "objective": "Analyser impact de --calculate-kv-scales sur FP8 KV cache"
        },
        "performance_impact": metrics_diff,
        "warnings_analysis": warnings_analysis,
        "recommendations": []
    }
    
    # Générer recommandations basées sur les résultats
    recommendations = []
    
    # Analyse TTFT
    if 'ttft' in metrics_diff:
        ttft_diff = metrics_diff['ttft']['difference_percent']
        if abs(ttft_diff) < 5:
            recommendations.append("✅ TTFT: Impact négligeable de la calibration (<5%)")
        elif abs(ttft_diff) < 15:
            recommendations.append("⚠️ TTFT: Impact modéré de la calibration (5-15%)")
        else:
            recommendations.append("❌ TTFT: Impact significatif de la calibration (>15%)")
    
    # Analyse Throughput
    if 'throughput' in metrics_diff:
        tps_diff = metrics_diff['throughput']['difference_percent']
        if abs(tps_diff) < 5:
            recommendations.append("✅ Throughput: Impact négligeable de la calibration (<5%)")
        elif abs(tps_diff) < 15:
            recommendations.append("⚠️ Throughput: Impact modéré de la calibration (5-15%)")
        else:
            recommendations.append("❌ Throughput: Impact significatif de la calibration (>15%)")
    
    # Analyse Warnings
    if warnings_analysis['warnings_resolved']:
        recommendations.append(f"✅ Warnings FP8 résolus: {len(warnings_analysis['warnings_resolved'])}")
    
    if warnings_analysis['warnings_remaining']:
        recommendations.append(f"⚠️ Warnings restants: {len(warnings_analysis['warnings_remaining'])}")
    
    # Recommandation finale
    fp8_warnings_resolved = len(warnings_analysis['warnings_resolved']) >= 3  # Au moins 3 warnings FP8 résolus
    performance_impact_acceptable = True
    
    if fp8_warnings_resolved and performance_impact_acceptable:
        recommendations.append("🎯 RECOMMANDATION: Appliquer --calculate-kv-scales en production")
    elif fp8_warnings_resolved:
        recommendations.append("🔄 RECOMMANDATION: Appliquer --calculate-kv-scales avec monitoring performance")
    else:
        recommendations.append("❌ RECOMMANDATION: Garder configuration actuelle (calibration inefficace)")
    
    report["recommendations"] = recommendations
    
    # Sauvegarder le rapport
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    # Afficher résumé
    print("\n📊 RÉSUMÉ DE LA COMPARAISON")
    print("=" * 50)
    
    if 'ttft' in metrics_diff:
        ttft = metrics_diff['ttft']
        print(f"TTFT: {ttft['baseline_ms']}ms → {ttft['calibrated_ms']}ms ({ttft['difference_percent']:+.1f}%)")
    
    if 'throughput' in metrics_diff:
        tps = metrics_diff['throughput']
        print(f"Throughput: {tps['baseline_tps']} → {tps['calibrated_tps']} tok/s ({tps['difference_percent']:+.1f}%)")
    
    print(f"Warnings résolus: {len(warnings_analysis['warnings_resolved'])}")
    print(f"Warnings restants: {len(warnings_analysis['warnings_remaining'])}")
    
    print("\n🎯 RECOMMANDATION FINALE:")
    for rec in recommendations:
        if "RECOMMANDATION" in rec:
            print(f"  {rec}")
    
    print(f"\n📄 Rapport détaillé sauvegardé: {output_file}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Comparaison des benchmarks FP8")
    parser.add_argument("--baseline", required=True, help="Fichier benchmark baseline")
    parser.add_argument("--calibrated", required=True, help="Fichier benchmark calibré")
    parser.add_argument("--output", required=True, help="Fichier de sortie du rapport")
    
    args = parser.parse_args()
    
    success = generate_comparison_report(
        args.baseline,
        args.calibrated,
        args.output
    )
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()