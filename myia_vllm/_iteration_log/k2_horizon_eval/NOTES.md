# K2-Horizon-MoVA-36B-A4B — quantification maison + batterie d'éval

**Statut : REPORTÉ (2026-09-06, décision user).** Le quant a été perdu à la couche 27/49
lors du crash machine du 05-09 ~21:49Z ; le créneau GPU 2 restant (fin 02:00Z) ne
couvrait pas les ~9 h nécessaires à une reprise depuis zéro.

## Pourquoi il faut tout refaire

`llmcompressor.oneshot` **ne checkpointe pas** : il n'existe aucun point de reprise
intermédiaire. Une relance repart de la couche 0. Mesuré : 27 couches en 5 h 04
(16:43Z → 21:47Z) ≈ **11 min/couche → ~9 h pour les 49 couches**.

## Ce qui est préservé (ne PAS supprimer)

| Artefact | Emplacement | Taille |
|---|---|---|
| Poids BF16 K2-Horizon (snapshot `05cab0a4`) | `\wsl.localhost\Ubuntu\home\jesse\.cache\huggingface` | 70 Go |
| venv de quantification (torch 2.13 cu130, llmcompressor 0.13.0, transformers 5.14.1) | `/home/jesse/k2-quant-venv` | 5,2 Go |
| Lanceur | `/home/jesse/k2_run_quant.sh` | — |
| Image d'éval nightly (protégée du GC ~5 j) | `D:\vllm_image_backups\vllm-openai_nightly-e962733e0_k2horizon.tar` | 8,7 Go |

Disque WSL : 403 Go libres — aucune pression, rien à nettoyer. Re-télécharger les 70 Go
coûterait plusieurs heures : **conserver**.

## Pour reprendre (fenêtre GPU 2 d'au moins 10 h, à re-demander à CoursIA)

```bash
# 1. quantification (~9 h) — GPU 2 STRICT, jamais 0/1 (prod)
MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- setsid nohup bash /home/jesse/k2_run_quant.sh \
  > /home/jesse/k2_quant_run.log 2>&1 < /dev/null &

# 2. servir le quant (attendre "Application startup complete", ~5-10 min à froid)
MSYS_NO_PATHCONV=1 bash myia_vllm/_iteration_log/k2_horizon_eval/serve_k2.sh

# 3. perf puis qualité
python myia_vllm/_iteration_log/k2_horizon_eval/bench_k2.py
python myia_vllm/_iteration_log/k2_horizon_eval/quality_k2.py \
  --benchmarks gsm8k ifeval \
  --output-dir myia_vllm/_iteration_log/k2_horizon_eval/results/k2-horizon-36b
python myia_vllm/_iteration_log/k2_horizon_eval/paired_k2.py \
  --new myia_vllm/_iteration_log/k2_horizon_eval/results/k2-horizon-36b
```

## Scripts

- `serve_k2.sh` — boot du quant sur GPU 2 strict (`--gpus '"device=2"'`), port 5022 localhost,
  parseurs `k2_horizon`, ctx 8192, image nightly `e962733e08d1…` (seule à porter #55063).
- `bench_k2.py` — débit N=1/2/4/8. **Chiffres indicatifs mono-GPU TP=1** : l'A/B réel contre la
  prod (TP=2) exige une fenêtre dédiée et une comparaison même-fenêtre (le bruit machine domine).
- `quality_k2.py` — GSM8K + IFEval **concurrents**. Le harness historique
  (`qwen3_benchmark/benchmarks/lmms_quality.py`) est séquentiel à timeout 60 s : inadapté à un
  36B mono-GPU. Réutilise ses fonctions de scoring et son schéma JSONL. Pas de
  `chat_template_kwargs` (`enable_thinking` est spécifique à Qwen). Capture `reasoning` :
  **si K2 place sa réponse dans `reasoning` plutôt que `content`, adapter l'extraction.**
- `paired_k2.py` — McNemar apparié par index vs les refs full-run Qwen3.6. Apparier par index
  est impératif (leçon Ornith-1.5, 08-22).

## Rappel de la décision d'éval

Vision sacrifiée (GO user 09-04) ; aucun quant W4A16 public n'existe → maison obligatoire ;
support vLLM natif mergé le 09-03 (#55063) donc **v0.28.1+ minimum**. Détail : memory
`project_k2_horizon_evaluation.md`.
