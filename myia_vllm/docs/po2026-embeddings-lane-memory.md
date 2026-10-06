# Mémoire opérationnelle — lane embeddings po-2026 (portée par le dépôt)

Condensé des mémoires de session validées 08-10/2026. Chaque point = doctrine éprouvée
en production. Détail technique : `embeddings-po2026-runbook.md` (même dossier).

## Rôles & doctrines

- **RÔLE VIGIE** (incident 250 Go, 08/2026) : ce service est le point de convergence
  du trafic d'indexation de TOUTE la flotte. Une cadence anormale n'est PAS
  automatiquement une bonne nouvelle — un pic sans cause identifiée = ASK immédiat
  (« qui consomme ? »), JAMAIS « pic nominal, flotte très active ». Une mesure locale
  ne prouve jamais qui consomme (l'IP client n'est pas loggée).
- **Santé Qdrant AVANT analyse de trafic** : `healthz` sur les DEUX endpoints (LAN
  `192.168.0.47:6333` + proxy `qdrant.myia.io`). Proxy down + LAN OK = problème
  po-2023, pas Qdrant ; les deux down = Qdrant down (ROUGE, wake signal).
  Timeout ≠ connection reset : RST = service mort, timeout = réseau/VM.
- **Dashboards** : vigie → workspace `Embeddings` ; collectif vllm → workspace `vllm` ;
  cross-workspace → `global` + cross-post désignant LE point de rendez-vous unique ;
  DM = décision/urgence uniquement. `[WAKE-CLAUDE]` = global uniquement.
- **Crons session-only** : meurent à chaque reboot/fermeture VS Code. Le skill vérifie
  via CronList (idempotent, jamais de doublon). Réarmement sur instruction user
  (doctrine ghost-crons : le harness peut ressusciter un cron session-only au reboot —
  un cron dupliqué = leak à auditer). Chaîne historique po-2026 : `831c80b9` →
  `53fb1b20` → `890d21a3` → `7f3d5392` (session Embeddings, retirée à la passation).
- **UAC** : l'agent déclenche le popup (`Start-Process powershell -Verb RunAs`), le
  user clique Oui — JAMAIS demander à l'user de taper la commande. Dry-run AVANT tout
  geste UAC-touching, sortie du dry-run postée sur le dashboard.

## Signature & causes racines (toutes vérifiées)

- **Docker daemon down** : HTTP 000 + GPU 0 MiB. Cold start : kill Docker Desktop +
  `wsl --shutdown` + relance, ~160 s, conteneurs auto-restart.
- **Wedge sidecar « SLOW-not-dead »** : `/health` 200 ne prouve RIEN (angle mort n°9).
  Signature : vLLM `:8005` direct = 200 MAIS `:8004` refuse + logs docker gelés à une
  seq fixe. Cause racine (06/10) : écriture log synchrone gRPC-FUSE gelait l'event
  loop. **Fix = LOG_POOL (2 threads)** — un stall volume ne pendent plus que les logs.
  Fallback : `docker restart embedding-proxy-logger`.
- **Gels host SPOF n°4/5 (04/10)** : `vmmemWSL` 22,4 Go/35,3 Go commit → pagefile-thrash.
  `autoMemoryReclaim=gradual` insuffisant seul. **Fix (05/10, GO user)** : `.wslconfig`
  `memory=16GB` (swap 32 Go inchangé → plafond commit VM 48 Go = levier résiduel,
  touche la remediation Mathlib → arbitrer seul). Premier test : host jamais gelé
  depuis ; la pression s'est manifestée côté partage de fichiers (wedges).
- **Le jsonl du sidecar se VIDE à chaque restart** (`on_startup` unlink) — copier avant
  tout restart si le brut doit être conservé.
- **Toujours `--no-deps`** en `docker compose up -d` sur le compose prod (sinon il
  tente de créer qdrant-local → pull proxy → abort).

## Conventions mesures

- **Double baromètre obligatoire** : `roo_tasks_semantic_index` ET total partitions
  `ws-*` (une vague ws-* de +1,3 M a été invisible sur roo_tasks seul, 01/10).
- Warm embeddings : 2 requêtes (cold ~600 ms après restart), cible <250 ms, >300 ms
  sur 2 cycles = JAUNE. Vérif post-incident = POST réel via l'edge public, dims 2560.
- `SYNC_STALE` = artefact heartbeat, pas une panne (la progression Qdrant est la
  preuve). Convention flotte : po-2023/po-2024, jamais po-203/po-204.
- Compteur sidecar `/​_proxy_stats` reset à chaque restart — dater les resets avant
  d'interpréter un delta.

## Historique utile (condensé)

- 08/2026 : incident 250 Go (pics 3 273 pts/h étiquetés « nominaux » à tort —
  ~50 % doublons d'une boucle d'indexation) → doctrine vigie.
- 09/2026 : rotation clé API (exposition git) — préfixes 8 chars max ; un one-shot
  critique ne vit jamais dans un cron session-only. Upgrade vLLM v0.23.0 (30/09) :
  warm ~x10, VRAM 12,2→6,7 Go ; image v0.21 purgée 06/10 (re-pull skopeo si besoin).
- 10/2026 : SPOF n°5 (freeze 13,5 h) → cap vmmem ; wedges → LOG_POOL ; siège vllm
  posé 06/10 (PR #78), passation vigie de la session historique Embeddings.
