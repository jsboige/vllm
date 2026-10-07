---
description: Cycle de surveillance court du siège FrogNano po-2025 (cron 4h) — santé moteur, thermique, gouverneur, compteurs adoption, [DONE] workspace-vllm.
---

# VIGIE vllm po-2025 (siège FrogNano-4B, issue jsboige/vllm#70)

Cycle court ~3-5 min. Porté par cron session-only `33 */4 * * *` dont le prompt est une seule ligne invoquant cette commande.

## 1. Lectures (paralléliser autant que possible)

- **Dashboard** : `roosync_dashboard(read, type workspace, workspace vllm, section all)`.
- **Inbox DM** : traiter uniquement les DM adressés à `po-2025:vllm`. Les DM machine-level sont visibles par tous les workspaces (bug #3960) → hors-lane = ignorés, laissés non lus.
- **Machine** (PowerShell) : health moteur `:5003` (200 attendu), `docker stats --no-stream` (empreinte RAM/VRAM), GPU temp + util (`nvidia-smi`), vmmem host.
- **Gouverneur thermique** : se prononcer via SES PROPRES artefacts (`_logs/gpu-governor.log` heartbeat, `gpu-governor-state.json`, `governor-install-result.txt`) — jamais via l'énumération schtasks non élevée, qui est aveugle aux tâches SYSTEM. Les heartbeats de `gpu-thermal.log` sont ceux du logger (monitor-only), pas du gouverneur.

## 2. Seuils

- WARN empreinte moteur > 12/16 Gio.
- Critique : temp GPU ≥ 85 °C. WARN : temp ≥ 75 °C ET util < 10 % (signature pompe défaillante). vmmem > 20 Go → WARN.
- Gouverneur muet/hb stale → WARN sur le dashboard, JAMAIS réinstallation (UAC unique de la lane déjà consommé le 06/10).

## 3. Adoption (mandat flotte — voir mémoire project-fleet-adoption-mandate)

- Compteurs moteur (`request_success_total`, finish reasons, erreurs) : delta depuis le cycle précédent.
- Qualifier chaque requête : **interne flotte** (sondes, gates, autres sièges, ai-01 T2/T3) vs **EXTERNE** (hors sièges vllm). Identifier l'origine via `claudish_traffic` le cas échéant.
- Nouveau consommateur externe détecté → ACK sur workspace-vllm (qui consomme, volume, régularité).

## 4. Rendu

- **[DONE]** sur workspace-vllm : santé + thermique + ligne adoption (req interne/externe depuis dernier cycle) + points de watch.
- Qualificateurs systématiques : VERIFIÉ / RAPPORTE / SUPPOSE — jamais propager un fait non vérifié.
- Timestamps : le dashboard est en UTC, mes labels en locale (Paris, +2) — le préciser en cas d'ambiguïté.

## 5. Garde-fous

- JAMAIS de restart Docker sans cadre user.
- Si du travail de code a été fait dans le cycle : commit + push AVANT le rapport [DONE].
- Fin de cycle : `CronList` → si le cron vigie n'existe plus, re-créer `33 */4 * * *` (recurring, session-only) avec pour prompt une ligne invoquant `/vigie`.
