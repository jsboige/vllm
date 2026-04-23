# 📊 PROFILING GPU - Mission 11 Phase 8

**Date**: 2025-10-23 15:31:40
**Service**: myia-vllm-medium-qwen3
**Configuration**: chunked_only_safe
**Durée**: 5 minutes (60 échantillons)

---

## 📈 Statistiques GPU (GPU 0)

### Utilisation GPU

| Métrique | Valeur |
|----------|--------|
| **Moyenne** | 2.3% |
| **Maximum** | 5% |
| **Minimum** | 0% |
| **P95** | 4% |
| **P99** | 5% |

### VRAM

| Métrique | Valeur |
|----------|--------|
| **Moyenne** | 23943 MB |
| **Maximum** | 23964 MB |
| **Minimum** | 23943 MB |

### Température

| Métrique | Valeur |
|----------|--------|
| **Moyenne** | 33.8°C |
| **Maximum** | 38°C |
| **Minimum** | 31°C |

### Power Draw

| Métrique | Valeur |
|----------|--------|
| **Moyenne** | 40.8 W |
| **Maximum** | 129.77 W |
| **Minimum** | 21.28 W |

---

## ✅ Validation

- **GPU Utilization**: ⚠️ Hors plage optimale
- **VRAM Usage**: ⚠️ Risque OOM
- **Température**: ✅ OPTIMAL (<85°C)
- **Power Draw**: ✅ OPTIMAL (<350W)

---

**Fichiers générés**:
- JSON: `myia_vllm/test_results/gpu_profiling_20251023_152631.json`
- Rapport: `myia_vllm/test_results/GPU_PROFILING_REPORT_20251023_152631.md`
