# Lane po-2026:Embeddings — instructions du siège vllm

## Identité

- **Ce siège** (`myia_vllm/` du clone `D:\Dev\vllm`) = poste de travail de la lane
  **embeddings de la flotte** sur le fork `jsboige/vllm`, sibling #2 (cf.
  `../FLEET-WORKSPACE.md` — le lire d'abord, il porte les conventions flotte).
- **Runtime de service** : le service d'embeddings tourne dans le dépôt prod
  `C:\Production\Embeddings` (compose, sidecar, logs, `.env`) — **on ne le déplace
  pas**. Ce siège porte : profil canonique, scripts mutualisés, doc, vigie.
- Passation : ce siège a repris la vigie embeddings le 2026-10-06 de la session
  historique `c--Production-Embeddings` (mandat user).

## Surveillance (mission première)

- Skill **`/surveillance-embeddings`** (`.claude/skills/` ici), cadence 12 h à :17.
  Le cron est session-only : il meurt à chaque reboot — le skill le vérifie/arme
  (idempotent, CronList d'abord). Réarmement après reboot = sur instruction user.
- **Rapports de vigie → dashboard workspace `Embeddings`** (continuité du fil et des
  baselines ; les lanes qdrant/OWUI y ont leur RDV). Sujets collectif vllm →
  workspace `vllm`. Escalade cross-workspace → `global` + cross-post (règle flotte).
- Baseline à stocker en dernière ligne de chaque rapport (double baromètre
  `roo_tasks` + `ws_total`).

## Non-négociables

1. **`https://embeddings.myia.io` + modèle `qwen3-4b-awq-embedding` + dims 2560
   stables** — tout changement = réindexation flotte (6M+ points).
2. **Clés dans `C:\Production\Embeddings\.env` (gitignored) — JAMAIS dans un commit,
   dashboard ou DM.**
3. Jamais de suppression sans preuve de préservation ; jamais de restart Docker
   automatisé sur po-2026 sans cadre user (interdiction en vigueur, cf. global).
4. Un chiffre cité est mesuré, avec sa source ; qualifier VERIFIIE / RAPPORTE / SUPPOSE.
5. Commits conventionnels ; PR vers `jsboige/vllm` ; ne jamais pousser vers `upstream`.
6. Convention flotte : écrire **po-2023/po-2024** (jamais po-203/po-204).

## Documents du siège

- `docs/embeddings-po2026-runbook.md` — pièges vLLM v0.23 pooling/cudagraphs,
  recovery éprouvés, cause racine des wedges sidecar (fix LOG_POOL 06/10), cap vmmem.
- `docs/po2026-embeddings-lane-memory.md` — mémoire opérationnelle condensée
  (rôles, doctrines, incidents fondateurs) portée par le dépôt.
- `configs/docker/profiles/embeddings-qwen3-4b-awq-po2026.yml` — profil canonique.
- `scripts/embedding-proxy-logger.py`, `scripts/gpu-thermal-governor.ps1`.

## Chemins de service (dépôt prod, lecture/écriture OK)

- `.env` : `C:\Production\Embeddings\.env` (`VLLM_API_KEY`, `QDRANT_API_KEY`)
- Compose actif : `C:\Production\Embeddings\docker-compose.qwen3-4b-awq.yml`
- Chaîne : proxy public → sidecar `:8004` (`embedding-proxy-logger`) → vLLM `:8005`
- Gouverneur thermique : schtask /5 min, heartbeat `C:\Production\Embeddings\logs\gpu-governor.log`
- Logs capture : `C:\Production\Embeddings\logs\capture-20260906\`
- Qdrant prod : `https://qdrant.myia.io` + LAN `http://192.168.0.47:6333`
