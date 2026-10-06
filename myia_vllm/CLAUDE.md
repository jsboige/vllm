# Lane po-2025:vllm — instructions du siège (FrogNano-4B, tier mini)

## Identité

- **Ce siège** (clone `D:\dev\vllm`, branche de travail `po2025/frognano-seat`)
  = lane **FrogNano-4B / tier mini de la flotte**, sibling #1 sur le fork
  `jsboige/vllm` (cf. `../FLEET-WORKSPACE.md` — le lire d'abord, il porte les
  conventions flotte).
- **Mission** : héberger `microsoft/FrogNano-4B-2609` sur po-2025 « à haute
  vitesse, disponibilité et parallélisme » avec garde thermale obligatoire,
  puis le faire utiliser à la hauteur de sa capacité (issue
  [jsboige/vllm#70](https://github.com/jsboige/vllm/issues/70) = suivi unique).
- Inauguré le 2026-10-06 (mandat user). Phases : P0 inventaire (faite) · P1
  workspace+profil+garde · P2 déploiement+gates · P3 bench capacités · P4
  exposition flotte (claudish + domaine Mini + sk-agent dédié) · P5 adoption.

## Surveillance

- **Cron vigie siège : 4 h à :33** (session-only — CronList d'abord, réarmer si
  absent après un reboot ; le prompt du cron porte la check-list complète).
- Rapports → **dashboard `workspace-vllm`** (RDV des 3 sièges vllm). DM
  toujours adressés `machine:workspace` (bug RooSync #3960). Escalade
  cross-workspace → dashboard `global` + crossPost.
- Télémétrie thermique : task user-level `vllm-po2025-thermal-logger` (/5 min,
  log `myia_vllm/_logs/gpu-thermal.log`). Gouverneur SYSTEM en attente UAC
  (registre Q2) — scripts : `scripts/gpu-thermal-{logger,governor}-po2025.ps1`.

## Non-négociables

1. **Garde thermale AVANT toute charge GPU soutenue** (incidents passés :
  83 °C en banc, 85 °C à vide en avril). Chaque fenêtre de charge est
  **annoncée sur workspace-vllm avant le geste**, effets de bord compris.
2. **Le hub claudish (même machine) est prioritaire** CPU/RAM — moteur plafonné
  (OMP_NUM_THREADS=4, mem limit, gpu-util ≤0.80), RAM libre hôte ≥ ~4 Go.
3. **Clés dans `myia_vllm/.env` (gitignored) — JAMAIS dans un commit, dashboard
  ou DM** ; distribution par DM privé autodestructif uniquement.
4. Jamais de restart Docker automatisé sans cadre user ; jamais de suppression
  sans preuve de preservation.
5. Un chiffre cité est mesuré, avec sa source ; qualifier VERIFIIE / RAPPORTE /
  SUPPOSE. Commits conventionnels ; PR vers `jsboige/vllm` (`--merge`, jamais
  squash) ; jamais pousser vers `upstream`.
6. Convention flotte : écrire **po-2023/po-2024** (jamais po-203/po-204).

## Documents & chemins du siège

- Profil canonique : `configs/docker/profiles/mini-frognano-4b-po2025.yml`
  (contrat + dimensionnement + rollback en en-tête — le lire avant tout geste).
- Faits modèle : config décodée + paysage quants dans la mémoire du siège
  (`~/.claude/projects/d--dev-vllm/memory/`).
- Logs runtime : `myia_vllm/_logs/` (gitignored).
- Modèle : cache HF Windows `C:\Users\jsboi\.cache\huggingface` (pattern twin
  po-2026) ; image `vllm/vllm-openai:v0.31.0`.
- Registre questions user : mémoire siège `user-question-registry.md`
  (licence Apache/mit, UAC gouverneur, alias servi).
