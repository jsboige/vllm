#!/usr/bin/env bash
# Pass 23 — #18611 / CoursIA #1453, lemme 3 unknotting_11n102_upper (Lidman.lean:108, exact sorry :112).
#
# ARMÉ, NON LANCÉ (07/10 16:47Z) : marge commit hôte 88,4 % >= 85 % -> gel hôte
# (consigne coordinateur : « ne la lance pas maintenant ... lance-la au premier cycle
#  où le commit est repassé dessous, et écris la valeur lue dans le post de lancement »).
#
# DEUX corrections vs pass 22, toutes deux demandées par le coordinateur (note 12:25Z) :
#  1. NOTE DE CIBLE CORRIGÉE — la fermeture passe par l'ORGANE (verifyMoves + verifyMoves_sound
#     ReidemeisterCombinatorial.lean:235), JAMAIS par `decide` nu sur `ReidemeisterEquiv`
#     (aucune instance Decidable sur ce Prop — échec mesuré et prouvé en re-vérif offline pass 22).
#  2. BUDGET DE VÉRIFICATION RELEVÉ POUR CETTE CIBLE SEULEMENT : `LEAN_LAKE_BUILD_TIMEOUT_S`
#     (relu à chaque appel, lean_server.py:106-124, défaut 600). Aucun changement global.
#     Valeur retenue : 1800 s — la pass 22 a montré une élaboration qui court ENCORE
#     > 1500 s (LEAN_EXIT=124 sur mon kill) MÊME avec l'erreur de synthèse à :112, donc le
#     coût dominant est l'évaluation kernel des littéraux (foldl sur le PD-code 11 croisements),
#     structurel. La valeur est écrite dans la trace par le harnais lui-même (#18432 propage
#     `timeout_s = budget`).
#
# Gate de lancement (à vérifier AVANT de détacher ce script) :
#   - marge commit hôte < 85 %  (sinon NE PAS lancer)
#   - fenêtre :30Z, claire du runner nbaudit (:05Z)
set -uo pipefail
KL=/d/dev/CoursIA-prover/MyIA.AI.Notebooks/SymbolicAI/Lean/knot_lean
SCRATCH=$(dirname "$(realpath "$0")")
LOG="$SCRATCH/pass23.log"
PY=/c/Users/MYIA/miniconda3/envs/coursia-ml-training/python.exe
TARGET="$SCRATCH/run_prover_target.py"

echo "=== $(date -u +%FT%TZ) pass23 start: prebuild (LAKE_JOBS=8 lake build +Knots.Lidman +Knots.Slice)" >> "$LOG"
( cd "$KL" && LAKE_JOBS=8 LEAN_NUM_THREADS=4 lake build +Knots.Lidman +Knots.Slice ) >> "$LOG" 2>&1
echo "=== $(date -u +%FT%TZ) prebuild rc=$?" >> "$LOG"

# Window :30Z, clear of the nbaudit runner (:05Z). 10# = decimal parse (a bare "08"
# would be read as an invalid OCTAL constant by bash arithmetic).
while [ "$((10#$(date -u +%M)))" -lt 30 ]; do sleep 30; done
echo "=== $(date -u +%FT%TZ) window reached — backup + pass" >> "$LOG"

cp "$KL/Knots/Lidman.lean" "$KL/Knots/Lidman.lean.pre-pass23"
echo "=== backup Lidman.lean.pre-pass23 done" >> "$LOG"

KEY=$(grep -E '^VLLM_API_KEY_MEDIUM=' /d/vllm/myia_vllm/.env | head -1 | cut -d= -f2- | tr -d '\r"')
[ -n "$KEY" ] || { echo "=== FATAL no MEDIUM key" >> "$LOG"; exit 9; }
export LOCAL_LLM_BASE_URL=http://localhost:5002/v1 LOCAL_LLM_API_KEY="$KEY" \
       LOCAL_LLM_MODEL_ID=qwen3.6-35b-a3b PYTHONIOENCODING=utf-8 \
       LEAN_LAKE_BUILD_TIMEOUT_S=1800

cd /d/dev/CoursIA-prover/MyIA.AI.Notebooks/SymbolicAI/Lean/agent_tests
"$PY" -u "$TARGET" \
  --file 'D:/dev/CoursIA-prover/MyIA.AI.Notebooks/SymbolicAI/Lean/knot_lean/Knots/Lidman.lean' \
  --theorem unknotting_11n102_upper \
  --note 'Designation #18611 (a), PASS 23 (post pass-22). Goal: prove Knot.UnknottableIn 2 knot_11n102 (Lidman.lean:108, exact sorry :112). The target is ATTAQUABLE per the module docstring; the organ is ReidemeisterCombinatorial.lean:235 verifyMoves_sound, PROVEN (zero sorry in that file), contract at lines 264-268.

CLOSING FORM — MANDATORY, measured in pass 22 (candidate `exact <[0, 1], rfl, by decide>` was INVALID): there is NO Decidable instance for ReidemeisterEquiv, so a bare `by decide` on the third component CANNOT elaborate (verified offline: "failed to synthesize Decidable (ReidemeisterEquiv ... )"). The Prop-level equality must NOT be closed by decide. Close through the ORGAN instead: supply the witness to verifyMoves and close the resulting BOOL equation by decide/rfl (the Bool computation IS decidable), then convert with verifyMoves_sound. Shape: <indices, rfl, verifyMoves_sound (by decide)> — respecting verifyMoves exact API at ReidemeisterCombinatorial.lean:264-268. If the organ does not expose the needed form directly, add a small access lemma/instance rather than reverting to decide on the Prop.

Witness goes through Knot.changeCrossingAt (Invariant.lean:2372, modify i changeCrossing) — NOT a Reidemeister-move witness and NOT movesConnects alone (a Reidemeister-only witness would prove 11n102 already trivial, a false statement). UnknottableIn n k = exists indices, indices.length = n AND ReidemeisterEquiv (indices.foldl Knot.changeCrossingAt k).diagram unknotDiagram (Invariant.lean:2379). Method: bounded enumeration of pairs on the PD-code (C(11,2)=55); find the pair [i,j] whose double flip is ReidemeisterEquiv to unknotDiagram, then close with the ORGAN.

VERIFY BUDGET: LEAN_LAKE_BUILD_TIMEOUT_S=1800 for this target only (default 600 was structurally too short: the kernel evaluation of the concrete literals — foldl Knot.changeCrossingAt over the 11-crossing PD-code — dominates and ran > 1500 s in pass 22 even on an early synthesis error). Do not read a timeout as a proof failure.

Forbidden: weakening the statement, stub, moving the sorry, or closing the Prop by decide. Out of scope: unknotting_11n102 (theorem, sorry EFFECTIVELY PERMANENT per docstring — Heegaard Floer).' \
  -- \
  --provider local --local-provider local --coordinator-provider local \
  --tactic-provider local --search-provider local --critic-provider local \
  --max-iter 12 --workflow-timeout 5400 >> "$LOG" 2>&1
RC=$?
echo "=== $(date -u +%FT%TZ) PASS rc=$RC" >> "$LOG"
echo "PASSE 23 TERMINEE (rc=$RC)" >> "$LOG"
tail -c 2000 "$LOG" > "$LOG.exit-tail"
echo "[BG] EXIT code=$RC"
