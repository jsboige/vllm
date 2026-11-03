#!/usr/bin/env bash
# Fenetre de MESURE Ornith-1.5-9B (:5003, po-2025) — batterie de capacite.
#
# Different d'une fenetre de promotion : ici on MESURE, on ne decide pas dans le script.
# Le script laisse Ornith en service a la fin (pour que la chaine sk-agent puisse tourner
# dessus dans la meme fenetre) ; le rollback vers FrogNano est une commande explicite.
#
# Filet : si le BOOT echoue, le trap restaure FrogNano automatiquement.
set -uo pipefail
export MSYS_NO_PATHCONV=1

cd /d/dev/vllm || { echo "cd impossible"; exit 1; }
ENVF=myia_vllm/.env
PRODF=myia_vllm/configs/docker/profiles/mini-frognano-4b-po2025.yml
NEWF=myia_vllm/configs/docker/profiles/mini-ornith15-9b-po2025.yml
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG=".tmp/measure_ornith_${STAMP}.log"

log() { echo "[$(date -u +%H:%M:%S)Z] $*" | tee -a "$LOG"; }
BOOTED=0

wait_health() {
  local max=$1 i=0
  while [ "$i" -lt "$max" ]; do
    if curl -sf -m 3 http://localhost:5003/health >/dev/null 2>&1; then log "health 200 apres ${i}s"; return 0; fi
    i=$((i+5)); sleep 5
  done
  log "health JAMAIS 200 apres ${max}s"; return 1
}

restore() {
  local rc=$?
  [ "$BOOTED" = "1" ] && return 0
  log "=== BOOT ECHOUE (rc=$rc) — restauration FrogNano ==="
  docker compose -f "$NEWF" --env-file "$ENVF" down >/dev/null 2>&1 || true
  sleep 16
  docker compose -f "$PRODF" --env-file "$ENVF" up -d >/dev/null 2>&1 || log "ECHEC up FrogNano"
  wait_health 420 && log "FrogNano restaure"
}
trap restore EXIT INT TERM

log "=== MESURE ORNITH $STAMP ==="
log "--- arret FrogNano ---"
docker compose -f "$PRODF" --env-file "$ENVF" down >>"$LOG" 2>&1 && log "FrogNano arrete"
log "--- 16 s ---"
sleep 16
log "--- demarrage Ornith ---"
docker compose -f "$NEWF" --env-file "$ENVF" up -d >>"$LOG" 2>&1 || log "ECHEC up Ornith"
if ! wait_health 900; then
  log "BOOT ECHOUE — extrait :"
  docker logs myia_vllm-mini-ornith-9b 2>&1 | tail -30 | tee -a "$LOG"
  exit 2
fi
BOOTED=1
log "--- boot : KV / backend ---"
docker logs myia_vllm-mini-ornith-9b 2>&1 | grep -iE "GPU KV cache size|Maximum concurrency|Model loading took|attention backend" | tail -4 | tee -a "$LOG"
log "VRAM : $(nvidia-smi --query-gpu=memory.used,temperature.gpu --format=csv,noheader)"

log "--- batterie de capacite (identique au baseline FrogNano) ---"
python myia_vllm/scripts/testing/capability_campaign_po2025.py \
  --base http://localhost:5003 --model mini --label ornith-1.5-9b --repeat 2 \
  --out .tmp/campaign_ornith.json 2>&1 | tee -a "$LOG"

log "=== ORNITH RESTE EN SERVICE (mesure terminee) — rollback explicite si besoin ==="
log "VRAM fin : $(nvidia-smi --query-gpu=memory.used,temperature.gpu --format=csv,noheader)"
