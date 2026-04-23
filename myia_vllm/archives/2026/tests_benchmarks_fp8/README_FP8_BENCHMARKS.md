# Benchmarks FP8 - Mission 21A

## 🎯 Objectif

Ce suite de benchmarks permet de mesurer l'impact de la calibration FP8 (`--calculate-kv-scales`) sur les performances et la qualité du modèle `cpatonn/Qwen3-VL-32B-Thinking-AWQ-4bit`.

## 📋 Scripts Disponibles

### 1. `benchmark_fp8_baseline.sh`
**Benchmark de référence actuel (SANS calibration)**
- Lance le conteneur avec la configuration `medium-vl.yml` actuelle
- Mesure TTFT, throughput et qualité avec les warnings FP8 présents
- Génère `benchmark_fp8_baseline_YYYYMMDD_HHMMSS.json`

**Usage**:
```bash
cd myia_vllm/tests/benchmarks
chmod +x benchmark_fp8_baseline.sh
./benchmark_fp8_baseline.sh
```

### 2. `benchmark_fp8_calibrated.sh`
**Benchmark avec calibration FP8 (AVEC --calculate-kv-scales)**
- Crée une configuration temporaire avec `--calculate-kv-scales`
- Modifie docker-compose pour utiliser la config calibrée
- Mesure les mêmes métriques que baseline pour comparaison directe
- Génère `benchmark_fp8_calibrated_YYYYMMDD_HHMMSS.json`

**Usage**:
```bash
cd myia_vllm/tests/benchmarks
chmod +x benchmark_fp8_calibrated.sh
./benchmark_fp8_calibrated.sh
```

### 3. `compare_fp8_results.py`
**Script de comparaison des résultats**
- Analyse les différences de performance entre baseline et calibré
- Génère des recommandations basées sur l'impact mesuré
- Produit un rapport JSON détaillé avec analyse des warnings

**Usage**:
```bash
cd myia_vllm/tests/benchmarks
python compare_fp8_results.py \
  --baseline ../reports/benchmark_fp8_baseline_*.json \
  --calibrated ../reports/benchmark_fp8_calibrated_*.json \
  --output ../reports/fp8_comparison_report.json
```

## 📊 Métriques Mesurées

### Performance
- **TTFT (Time To First Token)**: Latence de première réponse en ms
- **Throughput**: Tokens générés par seconde (tok/s)
- **Duration**: Temps total d'exécution des tests

### Qualité
- **Warnings observés**: Liste des warnings dans les logs
- **Finish reasons**: Types de fin de génération
- **Prompt tokens**: Tokens d'entrée traités

### Warnings FP8 Ciblés
1. `Using KV cache scaling factor 1.0 for fp8_e4m3`
2. `Using uncalibrated q_scale 1.0 and/or prob_scale 1.0 with fp8 attention`
3. `Checkpoint does not provide a q scaling factor`

## 🔄 Workflow de Test Recommandé

### Étape 1: Baseline
```bash
# 1. Lancer benchmark baseline
./benchmark_fp8_baseline.sh

# 2. Noter le fichier de résultats généré
# Ex: benchmark_fp8_baseline_20251030_124800.json
```

### Étape 2: Calibration
```bash
# 1. Lancer benchmark calibré
./benchmark_fp8_calibrated.sh

# 2. Noter le fichier de résultats généré
# Ex: benchmark_fp8_calibrated_20251030_125500.json
```

### Étape 3: Comparaison
```bash
# 1. Comparer les résultats
python compare_fp8_results.py \
  --baseline ../reports/benchmark_fp8_baseline_20251030_124800.json \
  --calibrated ../reports/benchmark_fp8_calibrated_20251030_125500.json \
  --output ../reports/fp8_comparison_20251030_130000.json

# 2. Analyser le rapport généré
cat ../reports/fp8_comparison_20251030_130000.json | jq .recommendations
```

## 📈 Critères de Décision

### ✅ Appliquer --calculate-kv-scales si:
- Warnings FP8 résolus ≥ 3
- Impact performance < 15% (TTFT et throughput)
- Qualité des réponses maintenue

### ⚠️ Évaluer avec monitoring si:
- Warnings FP8 résolus ≥ 3
- Impact performance 15-25%
- Légère dégradation qualité acceptable

### ❌ Garder configuration actuelle si:
- Warnings FP8 non résolus
- Impact performance > 25%
- Dégradation significative qualité

## 🔧 Prérequis Techniques

### Environment
- Docker et Docker Compose installés
- Accès aux GPUs RTX 4090 (2x)
- WSL2 configuré avec GPU support
- jq pour parsing JSON

### Configuration
- Fichier `myia_vllm/configs/docker/profiles/medium-vl.yml` existant
- Modèle `cpatonn/Qwen3-VL-32B-Thinking-AWQ-4bit` téléchargé
- Ports 8000 disponibles

### Dépendances
```bash
# Installation dépendances
sudo apt update
sudo apt install -y curl jq

# Permissions scripts
chmod +x *.sh
```

## 📝 Notes d'Utilisation

### Temps d'exécution estimé
- **Baseline**: ~5 minutes
- **Calibré**: ~7 minutes (calcul des scales inclus)
- **Comparaison**: ~1 minute

### Espace disque requis
- **Résultats**: ~1MB par benchmark
- **Logs**: ~10MB par exécution
- **Total**: <50MB pour workflow complet

### Monitoring pendant tests
```bash
# Surveillance GPU
watch -n 1 nvidia-smi

# Surveillance conteneur
docker logs -f medium-vl

# Surveillance mémoire
free -h
```

## 🚨 Limitations Connues

### WSL2
- `pin_memory=False` impact <1% sur performance
- P2P GPU non disponible (impact sur custom allreduce)

### Modèle AWQ
- Nécessite calibration manuelle des scales FP8
- Pas de metadata quantization dans le checkpoint

### vLLM
- `--calculate-kv-scales` non documenté officiellement
- Temps de calibration additionnel au démarrage

## 📚 Références

- [Mission 21A Report](../../docs/missions/MISSION_21A_FP8_WARNINGS_INVESTIGATION.md)
- [vLLM FP8 Documentation](https://docs.vllm.ai/en/latest/quantization/fp8.html)
- [Qwen3-VL Model Card](https://huggingface.co/cpatonn/Qwen3-VL-32B-Thinking-AWQ-4bit)
- [Architecture Docker](../../docs/docker/ARCHITECTURE.md)