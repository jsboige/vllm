# Siège po-2028 — lane vllm (vllm-c2)

**Inauguré le 2026-11-17** (mandat user en session). 3ᵉ worker sibling du workspace vllm
après po-2025 (FrogNano) et po-2026 (Embeddings). Coordination : dashboard
**workspace-vllm** (rendez-vous unique) ; même machine = messages de session
(RooSync réservé cross-machine).

## Identité

- Session : `vllm-c2` sur po-2028 (Windows 11, Docker 29.9.3 + WSL2 Ubuntu).
- Clone **partagé** `d:/dev/vllm` avec la lane claudish-72 (harnais nb_coder) :
  checkout principal = branche sticky `nb-coder/460-sticky-worktree` (état de repos du
  driver), worktrees `wt/` au driver seul, `.tmp/mxmerge` = son scratch. **Les commits
  du siège vivent exclusivement dans le worktree dédié `d:/dev/wt-po2028-vllm`**
  (branche `po2028-vllm-eval` depuis origin/main) — jamais de `switch -c` sur le
  checkout principal : les passes du driver sont déclenchées par événement, sans
  fenêtre coordonnable (arbitrage claudish-72 du 17/11).
- Données hors repo : `D:\vllm-data\` (cache HF, artefacts d'éval).

## Matériel (mesuré 17/11/2026, ne pas réétablir)

| Élément | Valeur |
|---|---|
| GPU | **RTX 3070 Ti Laptop, 8 192 MiB** (Ampere SM86, driver 621.24) |
| KV dtype dispo | fp8 (précédent po-2025 sur SM86) ; **nvfp4 KV hors jeu** (Ada+) |
| Disques | D: 1 431 Go libres / C: 353 Go libres |
| Runtime | Docker 29.9.3 (server) + WSL2 (Ubuntu, docker-desktop Running) |

**Avertissements machine (transmis par claudish-72, 17/11)** : (a) bugcheck organique
**0x116** le 21/10, famille non diagnostiquée (dumps en attente de fenêtre UAC user) —
un crash pendant une éval GPU se rapproche d'abord de cette famille avant d'incriminer
la charge ; (b) gels machine 05-07/11 (BugcheckCode=0) = famine WSL CPU/RAM, pas GPU —
vérifier la marge commit hôte (< 85 %) avant tout boot lourd.

## Mission

1. **Vigie 6h** (cron `71cef92a`, à :17, session-only re-armé chaque cycle) : propreté
   du checkout partagé, GPU (temp × charge croisés), disques, inbox
   `myia-po-2028:vllm`, dashboards global + workspace-vllm, [DONE] en clôture.
   Ce siège n'a PAS la prod ai-01 — les gates Docker/watchdog//dev/shm de la spec
   ai-01 (`.claude/commands/vllm-surveillance.md`) sont hors périmètre ici.
2. **Éval voltron-1-mini** (finetune LFM3-1.7B BF16, `Akahsizrr/voltron-1-mini`) sur
   la GPU 8 Go : reprise du geste po-2025 (frognano/spark) adaptée à 8 Gio, avec les
   recettes d'offload KV RAM→fs d'ai-01. Support natif `lfm3` absent du fork (sync
   24/10), présent sur upstream/main → image nightly, digest épinglé après pull.
   Staging : boot simple → tier RAM (non pinné) → tier fs (+ overlay tierpin d'ai-01
   si la race amont n'est pas corrigée dans l'image).

## Non-négociables

- Tout **boot moteur = fenêtre annoncée sur workspace-vllm AVANT lancement** —
  mécanisme de droit de veto des lanes voisines (leçon ai-01 01/11).
- Offload tier : **toujours non pinné** (`VLLM_WSL2_ENABLE_PIN_MEMORY=0`) — pin=1
  falsifié sur WSL2 (ai-01, ×2 mesurés).
- Clone partagé : invariants claudish-72 — sticky intouchable, `wt/` intouchables,
  zéro rebase/reset, checkout principal rendu à la sticky, working tree propre.
- Heures UTC suffixées Z (`(Get-Date).ToUniversalTime()`) ; GitHub en REST uniquement
  (seau GraphQL flotte partagé) ; jamais de clé en clair.
- Un chiffre cité est **mesuré**, avec sa source ; qualifier VERIFIÉ / RAPPORTE /
  SUPPOSÉ.

## Chemins

| Quoi | Où |
|---|---|
| Worktree du siège | `d:/dev/wt-po2028-vllm` (branche `po2028-vllm-eval`) |
| Cache HF / données d'éval | `D:\vllm-data\hf-home` |
| Mémoire du siège | `~/.claude/projects/d--dev-vllm/memory/` (MEMORY.md + fiches) |
| Dashboards | workspace-vllm (principal), global (escalade flotte) |
