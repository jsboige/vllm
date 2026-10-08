---
description: Cycle surveillance vllm 6h (prod read-only + G: + sécurité IP + coordination + clôture) — la spec versionnée du cron
---

# Cycle surveillance vLLM (6 h) — spec versionnée

**Le cron ne porte qu'une ligne : `/vllm-surveillance`** (+ fallback chemin ci-dessous). Tout changement de spec passe par un commit/PR sur ce fichier — plus de spec volumineuse inline dans le prompt cron. Convention flotte 07-08/10/2026 (« la spec vit dans le dépôt »), fermée à 3/3 sièges.

Fallback si le skill ne charge pas : lire ce fichier (`d:/vllm/.claude/commands/vllm-surveillance.md`) et l'exécuter tel quel. **Fin de cycle : re- armer le cron** (`CronCreate`, cadence 6 h à :17, session-only) et vérifier par `CronList`.

## Prod concernée (état 2026-10-08)

**Swift-1.5-Qwen3.8-27B W4A16-AWQ + FP8 KV sur stock `vllm/vllm-openai:v0.31.0` + offload KV RAM 24 GiB (TOUJOURS non pinné)** — localhost:5002, GPUs 0/1 TP=2, profil `medium-swift15-27b.yml`, gpu-util 0.70, batch 4096, 262K, KV 456 004 tok, `max-num-seqs 32`, noms duaux `swift-1.5-27b` + `qwen3.6-35b-a3b` (alias). Rollback armé : `medium-qwen36-stock-tq.yml`. Conteneurs : `myia_vllm-medium-swift15-27b` · `myia_vllm-watchdog-swift15-27b` (v5, **GEN_TIMEOUT 90 s**) · `myia_vllm-wedge-telemetry-swift15`. **GPU 2 = CoursIA** (training quand occupé, 78-300 MiB quand libre — un GPU 2 chargé n'est PAS une anomalie vllm).

**NE JAMAIS modifier/redémarrer sans GO user.** Jamais `pin=1` avec l'offload (`cudaHostRegister` WSL2 falsifié ×2). Si un boot-OOM récidive malgré 0.70 : fait nouveau majeur — diagnostiquer GPU 0 au moment du boot, ne pas rebaisser mécaniquement.

## ⚠️ Discipline fuseaux (piège vérifié)

Hôte = UTC+2 ; conteneurs, `StartedAt`, logs RSM = UTC ; `docker logs --since/--until` prend l'heure LOCALE. Ancrer sur l'epoch, suffixer les heures citées (`12:32Z`).

## ⚠️ `docker logs --since` INFIBLE depuis le 30/08 → `--tail` uniquement

Le chemin lecture-complète (`--since`, `--tail` géant) voit le segment MORT du journal ; le petit `--tail N` (≈2 500-4 000 lignes watchdog, 20 000 moteur) atteint le segment vivant. Symptôme : `--since 12h | grep -c` = 0 alors que `--tail 2` est frais → c'est CE bug, pas un service arrêté. Borner chaque segment lu et raisonner en comptes absolus.

## (1) Check prod read-only

```bash
curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" --max-time 8 http://localhost:5002/health
docker inspect myia_vllm-medium-swift15-27b --format 'RC={{.RestartCount}} status={{.State.Status}} health={{.State.Health.Status}} StartedAt={{.State.StartedAt}}'
docker logs --tail 20000 myia_vllm-medium-swift15-27b 2>&1 | grep -ac 'out of memory'
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader
docker ps --filter name=myia_vllm --format '{{.Names}}\t{{.Status}}'
# wedge : le signal faisant autorité = la sonde décodage du watchdog (pas la télémétrie seule)
docker logs --tail 4000 myia_vllm-watchdog-swift15-27b 2>&1 | grep -E "WEDGE health|CRASH-LOOP|RESTARTING|BOOT-STALL" | grep -vE '^\s'
docker logs --tail 4000 myia_vllm-watchdog-swift15-27b 2>&1 | grep -c 'OK health=200 decode=200'
```

Attendu : health 200 (<10 ms), RC stable, OOM 0, 3 conteneurs Up, sondes OK. **VRAM référence @0.70/N=32** : GPU 0 ≈ 20 700-21 400 MiB (21 388 mesuré), GPU 1 ≈ 19 700-19 900. **GPU 0 > 23 000 MiB → alerter** (marge < 1,5 GiB = boot-OOM au prochain restart + pagination WDDM qui imite un wedge). `StartedAt` stable vs cycle précédent ; un déplacement avec RC=0 = restart externe → identifier la cause (penser à `autoheal` : `docker ps | grep -i heal`, redémarreur concurrent INVISIBLE, RestartCount flat).

Comportement documenté, PAS une panne : toute requête ≥ ~100K tokens **affame les nouvelles arrivées 130-170 s** (dense 27B) — le watchdog tolère 90 s et le 235K mesuré passe en ~179 s. Un WEDGE pendant un gros prefill = attendre le post-mortem avant d'agir ; le moteur est sain.

## (2) Condensation (logs roosync)

Fichier `roosync-<date>.log` nommé d'après le DÉMARRAGE du process (pas rotaté à minuit — lire jour + veille). Burst ≥ 12 évts/min = jest (paths `dashboard-test-*`/`__test-data__`) ; vrai échec prod = minute isolée à 1-2 évts. `cloud fallback condensation succeeded` isolé pendant une indispo vLLM = nominal (dégradation gracieuse). Le banner « Condensation LLM config » n'est jamais dans le log (stderr) — check invalide, ne pas rapporter.

## (3) Santé G:/ DriveFS (fail-closed RSM si pathologique)

```bash
df -h /g | tail -1
timeout 30 sh -c "echo probe > '/g/Mon Drive/Synchronisation/RooSync/.vllm-probe.tmp'" && rm -f '/g/Mon Drive/Synchronisation/RooSync/.vllm-probe.tmp' && echo OK || echo KO
```

Écriture KO/timeout > 30 s = DriveFS hang → le noter au rapport, ne pas boucler sur les posts dashboard (ils échoueront), et le signaler à roo-extensions (le dossier #4131 suit la bascule PG). Marge commit hôte au passage (seuil 85 % pour tout travail lourd : `Get-CimInstance Win32_PerfRawData_PerfOS_Memory` → CommittedBytes/CommitLimit).

## (4) Prouveur Lean (#1453) — état : AUCUNE passe armée

Passe 23 close le 08/10 : **le blocage est un trou de bibliothèque, pas de harnais** — `oneStepWitnesses` retourne `[]` (`ReidemeisterCombinatorial.lean:166-172`) → `verifyMoves ≡ decide (d₁ = d₂)` réflexif seul, `verifyMoves_sound` vacuous. **Ne pas relancer de passe sur `unknotting_11n102_upper`** tant que l'énumération n'est pas implémentée (verrou = réponse coordinateur / tâche bibliothèque). Leçon consignée : vérifier l'organe AU SOURCE avant d'en faire un chemin de clôture — une docstring décrit l'intention, pas le code.

Si une NOUVELLE passe est armée un jour (lanceur `myia_vllm/scripts/adoption/prover_1453/`, pattern `run_passNN_*.sh`) : lancement **seulement** si marge < 85 % **ET** à la fenêtre **:30Z** (jamais à cheval sur le runner nbaudit :05Z — chevauchement = ~50 tok/s/flux et le cap client 240 s tue le tour de réflexion) ; `cp` backup `.pre-passNN` avant ; **écrire la marge lue dans le post de lancement** ; compter TRUE_PLACEHOLDER avant/après ; verdict honnête sur #1453 + DM coordinateur (si la passe échoue, le dire tel quel).

## (5) SÉCURITÉ standing — delta IP externes avec 200

Source : `/logs/error_sources.jsonl` DANS le conteneur (toutes requêtes). **Aggréger sur `x_forwarded_for`, JAMAIS sur `client`** (le champ client ne montre que la passerelle Docker 172.19.0.1).

```bash
MSYS_NO_PATHCONV=1 docker exec myia_vllm-medium-swift15-27b python3 -c "
import json,time,collections
now=time.time(); W=7*3600; tot=collections.Counter(); ok=collections.Counter()
for line in open('/logs/error_sources.jsonl',errors='ignore'):
    try: r=json.loads(line)
    except: continue
    if now-(r.get('ts') or 0)>W: continue
    ip=(r.get('x_forwarded_for') or '?').split(',')[0].strip()
    tot[ip]+=1
    if (r.get('status') or 0)==200: ok[ip]+=1
[print('%16s tot=%-5d 200=%d'%(i,t,ok[i])) for i,t in tot.most_common(25) if ok[i]>0 and not i.startswith('172.')]
"
```

**Carte connue (mise à jour 08/10)** : **Jamin** = `88.183.141.187` + `176.172.94.128` (RGAA, confirmé user 08/10 — PAS Candy) + IPv6 déclarée `2001:861:8ac2:e3f0:8602:b5b8:31ab:6424` (jamais observée au 08/10 ; toute apparition = Jamin, ne pas alerter) · **Candy : PAS encore observée** (annoncée plus mesurée ; attribution future par clé scopée, plus par IP) · site (hairpin) `90.65.170.144` · poste user Paris `82.66.89.184` (Q13 répondue 08/10 : « sans doute mon IP parisienne », SUPPOSÉ, Free, trafic arrêté depuis le 01/10) · po-2027 `92.150.81.115` · web1/web2 `37.187.180.135`/`51.75.200.22` · familles mobiles Free `92.184.x`/`88.183.x`. **Nouvelle IP non réclamée avec des 200 = alerte user immédiate dans le cycle + entrée registre.** Jamais d'attribution par géoloc registre seule (leçon : l'IP « allemande » était le site lui-même). Le census complet vit en mémoire : `project_vllm_external_ip_census_20261007.md`.

### (5bis) Consommateurs externes — clé scopée `external-vllm` (Jamin / Candy)

**Active depuis 08/10 13:03Z** (empreinte `45BDC569E1E3`), remise aux deux externes par le user le 08/10. Noms autorisés : `frognano-4b`, `mini`, `swift-1.5-27b`, `qwen3.6-35b-a3b` — les deux derniers sont **le même moteur** (vérifié 08/10 : les deux rendent `200` en OpenAI **et** en Anthropic, `served_by=qwen3.6-35b-a3b`). Tout cloud (`glm-5.3`…) = **403**, sans clé = **401**. Cap **2 requêtes concurrentes** par clé.

À relever chaque cycle (mandat user 08/10 : « tu relèveras régulièrement les traces ») :

- **Delta d'IP avec 200** (script §5) — Jamin a ≥2 IPv4 mesurées + 1 IPv6 déclarée ; **Candy n'a jamais été observée**, sa première attribution se fera **par clé**, pas par IP. Toute IP hors carte avec des 200 reste une **alerte user immédiate**.
- **Volumétrie** : le census **par clé** (`inbound_key`) vit côté hub → à demander à po-2025:claudish (campagne 30 j en cours, non bloquante). Côté moteur, on ne voit que l'IP.
- **Piège de lecture** : `max_tokens < 256` ⇒ **réponse vide** (`content` null, budget entièrement consommé par le thinking) alors que le moteur est sain — ne pas le lire comme une panne de lane (leçon partagée 08/10, claudish s'y est fait prendre aussi). Idem sur `/v1/messages` : le premier bloc est `type=thinking`.
- **Levier si dérapage** : la clé se **révoque seule**, sans toucher `VLLM_API_KEY_MEDIUM` — c'est le contrôle prévu (le user soupçonne Jamin de chercher à « maxer »).

## (6) Triage coordination

Inbox `roosync_messages` : lire l'adressé `myia-ai-01:vllm`, répondre/ack, `mark_read` ciblé (**`bulk_mark_read` exige un filtre `from`/`subject` — sans filtre il marque TOUT l'inbox**). Adressage machine-only = bug #3960 : ignorer les dispatchs d'autres workspaces. Dashboards : lire global + workspace-vllm ; rendre les lignes demandées (split-brain, matrices, etc.) ; relayer à l'user les réponses aux issues ouvertes par la lane.

## Clôture (OBLIGATOIRE, cet ordre)

1. **Commit + PR AVANT le rapport** — jamais annoncer du non-committé (`gh auth switch -u jsboige`, PR `--repo jsboige/vllm`, merge `--merge` ; si gh GraphQL limited → fallback REST).
2. `append` **[DONE]** sur workspace-vllm (prod, condensation, G:, prover, sécurité, registre restitué).
3. Ligne Active Work Log dans `MEMORY.md` (mémoire `~/.claude/projects/d--vllm/memory/`).
4. **Re-arm le cron** (6 h à :17, session-only, prompt = `/vllm-surveillance` + fallback) + `CronList` vérifié.
5. Zéro question bloquante au user : toute question va au registre `user-question-registry.md` (5 champs, dont l'attendu et le mécanisme de retrait), restitué en bloc au rapport.

Règles standing : famille spec-dec CLOSE (0/4, ne pas re-tester) · jamais de valeur de clé en clair (empreintes sha256[:12] uniquement) · infra d'un autre workspace = demander, pas appliquer.
