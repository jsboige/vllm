---
name: surveillance-embeddings
description: Surveillance 12h du service d'embeddings (vLLM + Qdrant + indexation + indexateurs workspaces + outils SDDD) sur myia-po-2026. Siège : D:\Dev\vllm\myia_vllm (lane vllm, passation 2026-10-06). Service prod : C:\Production\Embeddings. Rapport dashboard workspace Embeddings + lead VERT/JAUNE/ROUGE + (ré)armement cron.
---

# Skill : Surveillance Embeddings (12h)

Surveillance sémantique et équilibrée du service d'embeddings myia-po-2026, exécutée
depuis le siège vllm (`myia_vllm/`). **Source unique de vérité** : ce skill, invoqué
manuellement (`/surveillance-embeddings`) ou par le cron 12h.

## Contexte infrastructure

- **vLLM** : Qwen3-4B AWQ, container `qwen3_4b_awq_embedding_server`, port **8005**
  (derrière sidecar capture :8004) — dépôt prod `C:\Production\Embeddings`
- **Sidecar** : `embedding-proxy-logger` sur **8004** (chaîne publique :
  embeddings.myia.io → 8004 → 8005) — runbook : `../../docs/embeddings-po2026-runbook.md`
- **Qdrant** : distant **192.168.0.47:6333** (LAN direct) + proxy `https://qdrant.myia.io`
  (po-2023) — santé Qdrant AVANT toute analyse de trafic
- **Clés** : `C:\Production\Embeddings\.env` (`VLLM_API_KEY`, `QDRANT_API_KEY`) —
  jamais dans un commit/dashboard/DM
- **Dashboard rapports** : workspace **Embeddings** (fil vigie + baselines).
  Collectif vllm → workspace `vllm`. Wake signals `[WAKE-CLAUDE]` → global.
- **Passation** : ce siège a repris la vigie de la session historique
  `c--Production-Embeddings` le 2026-10-06. Premier run = validation de passation
  (le mentionner dans le rapport).

---

## Procédure OBLIGATOIRE

### Étape 0 — (Ré)armement du cron (idempotent)

1. `CronList` — chercher un job dont le prompt mentionne `surveillance-embeddings`
2. Si absent → `CronCreate` : `cron` `17 */12 * * *` (jitter :17 anti-collision
   flotte), `recurring: true`, prompt `"Exécute la skill surveillance-embeddings
   (surveillance 12h embeddings + indexation Qdrant + indexateurs workspaces +
   outils SDDD + prise de lead VERT/JAUNE/ROUGE + (ré)armement cron)."`
3. Si présent → ne rien faire (jamais de doublon).

> Crons session-only : ils meurent au reboot/fermeture. La doctrine flotte
> (ghost-crons) réserve le RÉARMEMENT après reboot à une instruction user explicite ;
> le réarmement par le skill ne vaut que pour la session vivante qui porte la vigie.

### Étape 1 — Triple grounding SDDD (les outils fonctionnent-ils ?)

En parallèle :
- `roosync_search(action:"semantic", search_query:"embeddings vLLM Qdrant indexation", max_results:5)`
  — `semantic_degraded:true` + `embedding_api_error` = endpoint embedding MCP down (cf. étape 2).
- `roosync_inventory(type:"status")` — `SYNC_STALE` = artefact heartbeat ;
  `UNKNOWN:<machine>` = probablement down (web2 = artefact mirror #3160, arbitré VIVANT).
- `codebase_search(query:"embedding service config vLLM", workspace:"c:/Production/Embeddings", limit:5)`

### Étape 2 — Chaîne embeddings (check #0 Docker d'abord)

```
docker info --format "OK Server={{.ServerVersion}} running={{.ContainersRunning}}"
```
- KO → **ROUGE** : signature HTTP 000 + GPU 0 MiB → cold start (kill Docker Desktop +
  `wsl --shutdown` + relance, ~160 s, auto-restart).

Puis en parallèle :
```
# health sidecar (⚠️ un /health 200 ne prouve rien — angle mort n°9)
curl -s -o /dev/null -w "%{time_total}s HTTP %{http_code}" http://localhost:8004/health
# vLLM direct (discriminant wedge : 8005 OK + 8004 mort = sidecar, cf. runbook)
curl -s -o /dev/null -w "%{time_total}s HTTP %{http_code}" http://localhost:8005/health
# warm ×2 (cible <250 ms ; >300 ms = JAUNE) — 2e requête obligatoire (cold ~600 ms)
curl -s -o /dev/null -w "%{time_total}s HTTP %{http_code}" -X POST http://localhost:8004/v1/embeddings \
  -H "Authorization: Bearer $(grep VLLM_API_KEY /c/Production/Embeddings/.env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"input":"surveillance cron test","model":"qwen3-4b-awq-embedding"}'
# proxy public (000 = po-2023 down)
curl -s -o /dev/null -w "%{time_total}s HTTP %{http_code}" https://embeddings.myia.io/health --max-time 30
# GPU + gouverneur (heartbeat logs/gpu-governor.log — silence = tâche morte)
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader
```

### Étape 3 — Indexation Qdrant (les DEUX endpoints + double baromètre)

```
API=$(grep QDRANT_API_KEY /c/Production/Embeddings/.env | cut -d= -f2)
curl -s -o /dev/null -w "%{http_code}" http://192.168.0.47:6333/healthz    # LAN
curl -s -o /dev/null -w "%{http_code}" https://qdrant.myia.io/healthz     # proxy
curl -s "http://192.168.0.47:6333/collections/roo_tasks_semantic_index" -H "api-key: $API" | python -c "import sys,json; print(json.load(sys.stdin).get('result',{}).get('points_count'))"
# ws_total (lent : lancer en tâche de fond) :
curl -s "http://192.168.0.47:6333/collections" -H "api-key: $API" | python -c "
import sys, json, urllib.request
API='$API'
d = json.load(sys.stdin)
ws = [c['name'] for c in d.get('result',{}).get('collections',[]) if c['name'].startswith('ws-')]
total = 0
for name in ws:
    req = urllib.request.Request(f'http://192.168.0.47:6333/collections/{name}', headers={'api-key':API})
    total += json.load(urllib.request.urlopen(req, timeout=10)).get('result',{}).get('points_count',0)
print(f'ws_count={len(ws)} ws_total={total}')
"
```

- Proxy KO + LAN OK → po-2023 down : quick fix `.env` MCP vers backends directs
  (`EMBEDDING_API_BASE_URL=http://localhost:8004/v1`, `QDRANT_URL=http://192.168.0.47:6333`),
  restaurer ensuite (endpoint canonique flotte).
- DEUX down → **ROUGE** wake signal global (intervention physique .47).

**⚠️ RÔLE VIGIE** : un pic de cadence sans cause identifiée = ASK immédiat, jamais
« flotte très active » (incident fondateur 250 Go : pics « nominaux » = 50 % doublons
d'une boucle). Cause identifiée + documentée (rattrapage post-panne, flush dominical
annoncé) = OK avec note. Cadence normale récente : 0,3-8 k pts/h ws-*.

### Étape 4 — Indexateurs

- `roosync_diagnose(action:"lifecycle")` — `BOOTSTRAPPING → undefined` = indexer local
  stuck **P3** (PR #618, code-level) : PAS récupérable par infra, la flotte porte.
  Ne pas gaspiller sur le lock indexer (futile, prouvé 4 cycles).

### Étape 5 — Verdict

| Cas | Critères | Action |
|-----|----------|--------|
| 🟢 VERT | Services OK + cadence >100 pts/h | Rien. Rapport [DONE]. |
| 🟡 JAUNE | Cadence <100 OU latence >300 ms OU trafic anormal non expliqué | Latence → `docker stats --no-stream`. Wedge sidecar (8005 OK, 8004 mort) → `docker restart embedding-proxy-logger` (fix racine LOG_POOL déployé 06/10 — restart = fallback). Rapport WARN. |
| 🔴 ROUGE | Stagnation >6 h OU Docker down OU Qdrant LAN+proxy down | Docker → cold start. Qdrant double-down → `[WAKE-CLAUDE]` global. Rapport ERROR. |

> Pas d'escalade ROUGE pour un proxy po-2023 down seul (dégradation, pas panne).

### Étape 6 — Rapport dashboard

`roosync_dashboard(action:"append", type:"workspace", workspace:"Embeddings", tags:[TAG])` :
tableau services, baromètres doubles + cadence vs baseline, indexer, fleet, SDDD,
verdict + action, **baseline en dernière ligne** (`roo_tasks = N` · `ws_total = N / 64 coll.` @ timestamp).

## Mémoire du siège

Après chaque cycle significatif : mettre à jour `docs/po2026-embeddings-lane-memory.md`
(historique) et, pour les événements de service, le dépôt prod si doc concernée.
Mémoire session locale : `~/.claude/projects/<hash-du-siège>/memory/MEMORY.md`.
