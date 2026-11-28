---
description: Cycle surveillance vllm (6 h à :17) — la spec versionnée du cron, prod ai-01 UNIQUEMENT (tout autre siège → wrapper du siège)
---

# Cycle surveillance vLLM (6 h à :17) — spec versionnée

**Le cron ne porte qu'une ligne : `/vllm-surveillance`** (+ fallback chemin ci-dessous). Tout changement de spec passe par un commit/PR sur ce fichier — plus de spec volumineuse inline dans le prompt cron. Convention flotte 07-08/10/2026 (« la spec vit dans le dépôt »), fermée à 3/3 sièges.

Fallback si le skill ne charge pas : lire ce fichier (`d:/vllm/.claude/commands/vllm-surveillance.md`) et l'exécuter tel quel. **Fin de cycle : re-armer le cron** (`CronCreate`, **cadence 6 h à :17**, session-only) et vérifier par `CronList`.

**⏱ CADENCE 6 h à :17.** La cadence provisoire 2 h du pilote haiku→swift (20-26/10) est historique : le cron vivant est « Every 6 hours at :17 » (`CronList`, vérifié le 24/11 ; l'heure affichée du prochain tir comprend le décalage propre au job). À chaque cycle : watch §5quater (prefix-hit, preemptions, re-prefill) + **marge commit hôte (§3, seuil 85 %)**.

## ⚠️ Portée : à n'exécuter que sur le siège qui porte cette prod (ai-01)

Tout ce qui suit décrit la prod **ai-01** : `127.0.0.1:5002`, les conteneurs `myia_vllm-*`, le watchdog hôte, `/dev/shm`, `fstier-prune`. **Sur un siège qui ne porte pas cette prod, ces objets sont absents par conception** — mesuré sur po-2028 le 26/11 : `:5002` refuse la connexion, aucun conteneur `myia_vllm-*`, le moteur est `voltron-harness` sur `127.0.0.1:5028` derrière le service `:5029`. Un `:5002` muet, un `docker ps --filter name=myia_vllm` vide ou un conteneur `myia_vllm-medium-swift15-27b` introuvable y sont **l'état nominal, pas une panne** :

- ne pas en poster d'escalade ;
- ne pas demander de GO pour « recréer » un service que ce siège ne porte pas ;
- exécuter le wrapper du siège au lieu de cette spec : po-2028 → `vigie-vllm-po2028` (moteur `voltron-harness` sur `127.0.0.1:5028` derrière le service `:5029`, loopback, sans clé) ; po-2025 → `vigie` (FrogNano sur `:5003`) ; service d'embeddings → `myia_vllm:surveillance-embeddings` (12 h, écrit pour le siège po-2026 ; le service tourne sur po-2023 depuis le 20/10). La liste n'est pas exhaustive : `vigie` est versionné dans ce dépôt (`.claude/commands/`), `vigie-vllm-po2028` vit hors dépôt, dans le `~/.claude/commands/` du siège po-2028.

Si le doute subsiste, la question à se poser avant tout signalement est : **ce siège est-il censé porter cet objet ?** Deux fausses escalades « `:5002` attendu, indisponible » ont été postées depuis po-2028 (25/11 05:57Z, 26/11 11:49Z) ; la lane du siège les a fermées sans rien réparer — rien n'était cassé. Déclencheur probable, non établi : cette spec exécutée hors d'ai-01.

## Prod concernée (état 2026-11-24)

**Swift-1.5-Qwen3.8-27B W4A16-AWQ + NVFP4 KV + multi-tier GPU→RAM→fs** — `127.0.0.1:5002` (sonder par IPv4, jamais `localhost` : voir l'encadré de §1), GPUs 0/1 TP=2, profil **`medium-swift15-27b-fstier.yml`**, gpu-util 0.71, batch 8192 + `max-num-seqs 48`, 262K, noms duaux `swift-1.5-27b` + `qwen3.6-35b-a3b` (alias). **Image overlay `vllm-openai-v0340-fsadmit:v1`** (stock v0.34.0 + race tiering corrigée + filtre d'admission fs `MYIA_FS_ADMIT_MIN_HITS=2`, PR #589), `--disable-extensible-kv-cache`. Rollback armé : `medium-qwen36-stock-tq.yml` ; image seule : `VLLM_IMAGE_SWIFT15=…v0340-tierpin:v1`. Conteneurs : `myia_vllm-medium-swift15-27b` · `myia_vllm-watchdog-swift15-27b` · `myia_vllm-wedge-telemetry-swift15`. **GPU 2 = CoursIA** (training quand occupé, 78-300 MiB quand libre — un GPU 2 chargé n'est PAS une anomalie vllm).

**★ Limites du conteneur (`Maintenance#303`, mesurées 24/11)** : `mem_limit 48g`, `memswap_limit 48g`, `pids_limit 512` dans le profil `-fstier`. À l'intérieur : 32,8 GiB de **shmem = le tier KV RAM de 32 GiB en entier** (`--kv-offloading-size 32`), 8,9 GiB anon, 0,4 noyau ; `memory.events.max = 65 912` refus d'allocation à la limite, `oom 0`. **Toute baisse de plafond sans baisse du tier aggrave ces refus.** Le rollback `medium-swift15-27b.yml` porte les mêmes limites (moteur et sidecars) depuis la PR de cette correction.

**NE JAMAIS modifier/redémarrer sans GO user.** Jamais `pin=1` avec l'offload (`cudaHostRegister` WSL2 falsifié ×2). Si un boot-OOM récidive malgré 0.70 : fait nouveau majeur — diagnostiquer GPU 0 au moment du boot, ne pas rebaisser mécaniquement.

**★ Un « DOWN » du watchdog HÔTE (`Watchdog-vLLM-API`) n'est PAS une panne moteur** : mesuré 23-24/11, 74 sondes à 10 s sur 333, dont **92 % à ±2 min d'un échec de session `wsl.exe`** de la série Maintenance (`verify-qdrant-mount.log`), contre 33 % des sondes rapides — pendant que le moteur ne redémarrait pas et que le watchdog in-stack décodait. Avant tout geste : sonde indépendante `curl`, `RestartCount`/`StartedAt`, sondes de décodage in-stack. Détail et corrélation : dashboard workspace Maintenance, 24/11.

**★ Un `[DONE] [WATCHDOG] vLLM :5002 RESTAURE` n'est PAS un redémarrage moteur — c'est la sonde hôte qui répond de nouveau (mesuré 26/11).** Le watchdog hôte n'exécute rien : il constate `DOWN`, puis `RESTAURE`. Dans la nuit du 26/11 (00:36→04:46Z) il a posté **9 paires DOWN/RESTAURE, dont un épisode de 35 min avec une `[ERROR]`**, sur un moteur qui n'a **jamais redémarré** : `StartedAt` inchangé (22/11 14:16:23Z), `RestartCount=0`, et **505/505 sondes in-stack en `OK health=200 decode=200` entre 00:25 et 04:55Z, zéro trou > 90 s** ; 1 795 requêtes reçues sur la même fenêtre, **aucune tranche de 5 min sans trafic**. Les 9 épisodes tombent dans les fenêtres d'échec `wsl.exe` du journal Maintenance (`verify-qdrant-mount.log`, 61 `PROBE_ERROR` entre 00:00 et 04:59Z ; trois débuts d'épisode à 11-14 s d'un `PROBE_ERROR`). **Mesuré le 26/11 sur l'épisode de 11:26:45→11:31:35Z (10ᵉ), des DEUX côtés** : 18/18 sondes in-stack `OK health=200 decode=200` à 30 s **sans trou**, et **15 requêtes 200 sur le port publié pendant les 4 minutes pleines de l'épisode** (11:27Z 5, 11:28Z 4, 11:29Z 2, 11:30Z 4, toutes 200 ; comptage par minute dans `error_sources.jsonl`, qui reçoit par la passerelle `172.19.0.1`). **Aucun `PROBE_ERROR` `wsl.exe` dans cette fenêtre** (dernier à 06:56Z) : cet épisode n'est donc **pas attribuable** à la série Maintenance — le suspect restant est la branche `localhost`/`::1` du port publié (encadré §1), non discriminant à lui seul. La nuit du 26/11 reste **non mesurée** sur ce point : ne pas étendre rétroactivement cette mesure aux 9 épisodes de la nuit. Deux lanes ont lu le condensé « 5 restaurations watchdog » comme des redémarrages moteur. ⇒ **Avant de relayer un `RESTAURE` : `docker inspect … StartedAt`/`RestartCount`**, et ne pas écrire « restauré » pour ce que le moteur n'a pas cessé de faire.

**★ ANNONCER LA FENÊTRE SUR `global` AVANT TOUT RESTART MOTEUR (leçon 01/11, 21:11Z).** Même un restart court ou de validation : deux sous-agents `swift-reader` de CoursIA (954 s et 958 s, ~95k tokens) ont été coupés sans fichier écrit par deux redémarrages non annoncés. Le GO user autorise le geste, il ne dispense pas d'annoncer : message `global` avec **heure de début + durée attendue**, avant le geste. Non annoncé = vécu comme une panne chez le voisin, et une perte de travail réelle.

**★ Un pilote NVIDIA (ré)installé PENDANT que la VM Docker tourne tue le moteur et casse le hook GPU (mesuré 26/11).** C'est une **mise à niveau** du pilote, `32.0.16.1742` → `32.0.16.2140` (621.40), lue dans `C:\Windows\INF\setupapi.dev.log`. Séquence lue dans le journal Système (`UserPnp`, id 20003) : service `nvlddmkm` ajouté pour les 3 cartes à 15:58:09 / 15:58:23 / 15:58:38Z, `NVDisplay.ContainerLocalSystem` à 15:58:39Z, endpoints HD-audio des cartes configurés 15:58:48→15:58:53Z — et **19 s plus tard** (15:58:57Z) les deux workers TP sortent ensemble sur `torch.AcceleratorError: CUDA error: unknown error` → `EngineDeadError`, `OOMKilled=false`. **La relance (`unless-stopped`) est refusée au create** : `prestart hook #0: exit status 127, stderr: Inconsistency detected by ld.so: dl-setup_hash.c: 36 … assertion failed` (ExitCode 128), et **tout conteneur `--gpus` échoue ensuite** (3/3 sur une sonde vide ; **le message du hook change avec le temps**, pas le résultat — `exit status 127 … ld.so _dl_setup_hash`, puis dès 17:59:58Z `exit status 1 … nvidia-container-cli: WSL environment detected but no adapters were found`) : `docker run --rm --gpus device=0 --entrypoint /bin/sh vllm-openai-v0340-fsadmit:v1 -c 'echo hook-ok'`. ⇒ ce n'est ni le profil, ni l'image, ni un drapeau : **ne pas toucher au profil**. Diagnostic en trois lectures : `Get-WinEvent` (`System`, provider `UserPnp` ; `Microsoft-Windows-Kernel-PnP/Configuration`) depuis le dernier boot, `(Get-Item C:\Windows\System32\DriverStore\FileRepository).LastWriteTimeUtc`, la fin de `C:\Windows\INF\setupapi.dev.log` (versions avant/après ; heure locale), et la sonde de hook ci-dessus. ⚠️ Dans Ubuntu, `ls` affiche l'heure de Paris (+1 h) ; dans docker-desktop, l'UTC. **La panne est celle de la VM WSL entière** (mesuré 18:0xZ) : les bibliothèques GPU sont un overlay monté au boot de la VM et partagé par ses distributions (`/usr/lib/wsl/lib`, repères 15:43Z), et NVML échoue dans Ubuntu aussi — `wsl.exe -d Ubuntu -u root --exec /usr/lib/wsl/lib/nvidia-smi --query-gpu=driver_version --format=csv,noheader` → `Failed to initialize NVML: Generic operating system error`. Ce qui reste sain côté hôte et le prouve : ~52 conteneurs Up, `nvidia-smi` lit les cartes (pilote `621.40`), les 3 périphériques d'affichage `OK`, aucune clé de redémarrage en attente, `/dev/shm` propre. **Remède (corrigé à 18:06Z — « redémarrer Docker Desktop » était une inférence) : un redémarrage de Docker Desktop seul n'est PAS le remède mesuré** (il relance une distribution, pas l'overlay monté au boot de la VM). Le geste qui reconstruit cette couche est **`wsl --shutdown` puis Docker Desktop** ; le **reboot d'hôte** est le seul chemin mesuré **sur ce poste** (VM partie à 15:43Z après le reboot de 15:42:53Z, moteur servi dès 15:55:18Z). **`wsl --shutdown` SEUL a désormais un précédent mesuré sur un siège voisin** (po-2023, même soir, mêmes versions `…1742` → `…2140` : geste à 14:57:50Z, conteneurs revenus à 14:58:08Z, moteur à 14:58:09Z, **≈23 s**, sans restart de Docker Desktop ni reboot d'hôte, 6/6 sondes POST réelles en moins de 2 min — leur PR #633 ; le leur avait été installé 77 min avant le nôtre et leur Docker Desktop réinstallé 40 min plus tôt, donc la **transposition est SUPPOSÉE**, pas mesurée) ⇒ c'est le **premier geste à essayer**, le reboot d'hôte restant le repli. **Tant que le hook échoue, le watchdog in-stack retente toutes les 12 min et chaque tentative est refusée** (mesuré 22:42→23:42Z : six `RESTARTING … docker=unhealthy`, chacune suivie de `prestart hook #0`) ; **`RestartCount` reste à 0** parce que c'est `docker create` qui échoue — même angle mort structurel qu'`autoheal`, par un autre chemin. Ne pas lire `RestartCount=0` comme « rien n'a été tenté », et ne pas arrêter le watchdog pour le faire taire : ces tentatives sont inoffensives et donnent une reprise automatique dès que le hook est réparé. Le geste **coupe les ~52 conteneurs partagés et, pour `wsl --shutdown`, la distribution Ubuntu** (runners CI CoursIA, `fstier-prune.timer`) : à conséquences notables ⇒ **il s'escalade (`global` + `machine`), il ne se fait pas d'office**, même prod arrêtée. **Tant que la sonde de hook échoue, ne pas relancer le moteur**, et ne pas lire le `health=000` qui en résulte comme un wedge. Une `[DEGRADED]` postée sur trois tableaux compte pour **trois escalades** à l'organe : un seul `[REPAIRED]` sans `scope:` les ferme toutes si elles sont le même incident.

**★ 27/11 06:0xZ — l'installateur est IDENTIFIÉ ; il tournait encore et un redémarrage était en attente (mesuré). ✅ FERMÉ à 17:54:17Z par le reboot d'hôte — voir le paragraphe suivant.** La question laissée ouverte le 26/11 (« qui a lancé l'installateur ? ») est fermée **sur ce poste** : `setup.exe` **PID 51764**, démarré **15:53:05Z**, a pour **parent `NVIDIA App.exe`** (PID 20620, démarrée 15:51:58Z, 13 s avant la réinstallation de Docker Desktop) ⇒ **ce n'est pas Windows Update** ; po-2023 avait le même motif (installateur de la NVIDIA App). Il est **vivant 14 h après et immobile** — 0,02 s de CPU et **zéro octet lu en 7 s**, `Responding=True` : il attend une réponse d'interface. **Re-mesuré 27/11 12:25Z** : **0 s de CPU sur 7 s** (34,7 Mio de working set, 3 threads) mais **144,56 s cumulées** depuis 15:53:05Z — il a consommé du CPU au fil de ses phases et n'en consomme plus maintenant ; citer les deux chiffres ensemble, jamais « immobile depuis le début ». Et il a **continué à travailler après la panne** : `DrvSetupUninstallDriver` supprime l'ancien paquet `nvmdsi…71d1ad4f` (catalogue `oem24.cat`) à **19:48:54Z** — « 100 paquets vérifiés » intacts —, suppressions de périphériques (endpoint audio `MMDEVAPI`, 3 `PRINTENUM`) à **21:29:39Z**, et paquet audio **`nvhda` écrit aujourd'hui 04:59:13Z**. **25 suppressions différées** attendent un redémarrage (mesuré 27/11 12:2xZ : `PendingFileRenameOperations` porte **50 chaînes = 25 opérations**, toutes des suppressions — `SETF008.tmp`, `drivers\SET916E.tmp`, 20 `DriverStore\Temp\DEL*.tmp`, 3 chemins temporaires Edge/EdgeUpdate ; **aucun renommage**). Les chiffres de 48 et de 50 qui circulaient comptaient les **chaînes `REG_MULTI_SZ`**, pas les opérations — erreur miroir du 18:05Z, qui prenait chaque paire source/destination pour une seule entrée. **Conséquence directe pour le choix du remède** : **A** (`wsl --shutdown`) répare la couche GPU de la VM en ≈23 s (précédent po-2023) mais **laisse l'installateur en attente** — un « redémarrer maintenant » tardif peut rebooter l'hôte sans préavis ; **B** (reboot d'hôte) solde ces 25 suppressions et arrête l'installateur, mais **tue les processus Windows** : le scheduler du tapis (processus bash) **ne survit pas** et doit être relancé après, alors que le conteneur revient seul par `unless-stopped`. Dans les deux cas : ne pas toucher au profil. Mesure de contrôle : `Get-CimInstance Win32_Process -Filter "ProcessId=<pid>"` (parent, `CommandLine`) + CPU/IO à 7 s d'intervalle, `Get-ChildItem C:\Windows\System32\DriverStore\FileRepository -Directory | Sort LastWriteTimeUtc -Descending`, `PendingFileRenameOperations`.

**✅ 27/11 17:54:17Z — PANNE FERMÉE par un reboot d'hôte (voie B de Q73/Q80 ; geste du user depuis le menu Démarrer, événement 1074 ; mesuré de bout en bout).** Boot 17:55:00Z ; moteur `StartedAt` **17:56:30Z**, `health=200` en **2,9 ms** (18:05Z), première sonde de décodage in-stack **17:59:46Z** ; **KV 793 516** (identique à la référence), 0 préemption, `[shm-orphan purge]` au boot, `/dev/shm` 32/63 Go = le tier, 52 conteneurs Up, GPU 0/1 à 20 498 / 19 522 MiB, GPU 2 à 46 MiB. **Les deux sondes qui bloquaient passent** : hook `hook-ok` (rc=0) et NVML lit **621.40** dans Ubuntu (rc=0). Les 25 suppressions différées sont soldées (`PendingFileRenameOperations` absent) ; **aucun installateur NVIDIA n'est vivant après le boot** — **correction** : « setup.exe encore vivant » (17:48Z) était un artefact de réutilisation de PID (le PID 51764 porte désormais un `sk_agent.py`) ; pour affirmer « le processus X est vivant », filtrer par **nom**, jamais par PID seul. **Indispo totale 26 h 00 min 49 s** (26/11 15:58:57Z → 27/11 17:59:46Z). `[REPAIRED]` posté sans `scope:` sur workspace + global + machine à 18:08Z ; relu par l'organe : `REPAIRED myia-ai-01|vllm … a fermé 3 escalade(s)` (16:09:16Z, 16:09:26Z, 16:09:45Z la veille) — l'exit 2 qui reste est celui de la flotte, plus celui de cette lane. ⚠️ Ne plus lire cette panne comme en cours. Si le hook échoue de nouveau après une mise à niveau de pilote : `wsl --shutdown` d'abord, reboot d'hôte en repli — les deux escaladés, jamais d'office. **Tapis** : le reboot le tue (voie B). Au redémarrage, **chauffer le noyau Rust une fois avec un budget > 30 s AVANT d'appeler le lanceur** — sa garde fail-closed (30 s) rend `exit 3` sur un noyau à froid et ne lance rien (mesuré : première tentative refusée, noyau chauffé en 7,4 s, scheduler parti à 18:08:15Z, grain #27722 lancé à 18:08:16Z porte `green`).

## ⚠️ Discipline fuseaux (piège vérifié)

Hôte = Europe/Paris (UTC+2 en heure d'été, **UTC+1 depuis le passage à l'heure d'hiver le 2026-10-25**) ; conteneurs, `StartedAt`, logs RSM = UTC ; `docker logs --since/--until` prend l'heure LOCALE. Ancrer sur l'epoch, suffixer les heures citées (`12:32Z`).

**Le piège qui a fabriqué un faux signalement (08/10).** `Get-Date -Format u` rend l'heure **LOCALE** avec un suffixe **`Z`** : on obtient un horodatage qui *ressemble* à de l'UTC et ne l'est pas — décalage de +2 h, du mauvais côté. Un WARN « `:5003` injoignable depuis ~13:2xZ » était en réalité **11:2xZ**, et tombait dans une fenêtre de recréation du siège voisin : signalement faux, coût réel pour le voisin qui a dû le réfuter par la mesure. Même erreur commise sur ce siège le même jour (`Get-Date -Format "…HH:mm:ss 'Z'"`). **Récidive 24/11** : même piège en relisant le log LOCAL du watchdog hôte — « déployé 03:27Z » pour un geste fait à 02:27Z, corrigé sur PR #598 + commentaire issue + dashboard Maintenance. Ne jamais convertir de tête : prendre l'heure sur `date -u`, sur le timestamp du magasin, ou sur `[DateTimeOffset]::UtcNow`. **Toujours** `(Get-Date).ToUniversalTime()` (PowerShell) ou `datetime.now(timezone.utc)` (Python), et vérifier la conversion **avant** de poster une heure : l'offset local change aux changements d'heure (+2 en été, +1 en hiver — la règle « Z + 2 » ci-dessus historique). Un signalement horodaté faux est un signalement faux.

## ⚠️ `docker logs --since` INFIBLE depuis le 30/08 → `--tail` uniquement

Le chemin lecture-complète (`--since`, `--tail` géant) voit le segment MORT du journal ; le petit `--tail N` (≈2 500-4 000 lignes watchdog, ≤ 5 000 moteur) atteint le segment vivant. Symptôme : `--since 12h | grep -c` = 0 alors que `--tail 2` est frais → c'est CE bug, pas un service arrêté. Borner chaque segment lu et raisonner en comptes absolus.

**Un `--tail N` plus grand que le segment vivant rend 0 ligne, pas le segment entier (mesuré 30/10 18:1xZ).** Le moteur avait 8 918 lignes vivantes : `--tail 9000` en rendait 8 918, `--tail 10000` et `--tail 20000` en rendaient **0**. Le `grep -c 'out of memory'` de la spec affichait donc « 0 » sur un flux vide, depuis un nombre inconnu de cycles : **un zéro qui ne mesurait rien**. D'où le `wc -l` à côté de chaque comptage ci-dessous, et le `--tail 5000` côté moteur (environ 2 h de journal sous charge, ce qui couvre un cycle).

## (1) Check prod read-only

```bash
curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" --max-time 8 http://127.0.0.1:5002/health
docker inspect myia_vllm-medium-swift15-27b --format 'RC={{.RestartCount}} status={{.State.Status}} health={{.State.Health.Status}} StartedAt={{.State.StartedAt}}'
docker logs --tail 5000 myia_vllm-medium-swift15-27b > .tmp/eng.log 2>&1; echo "lignes=$(wc -l < .tmp/eng.log) oom=$(grep -ac 'out of memory' .tmp/eng.log)"   # lignes=0 => instrument aveugle, pas « 0 OOM »
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader
docker ps --filter name=myia_vllm --format '{{.Names}}\t{{.Status}}'
# /dev/shm hôte (ipc:host — NOUS seuls l'utilisons) : fuite à chaque boot, cf. encadré ci-dessous
docker exec myia_vllm-medium-swift15-27b df -h /dev/shm | tail -1
# wedge : le signal faisant autorité = la sonde décodage du watchdog (pas la télémétrie seule)
docker logs --tail 4000 myia_vllm-watchdog-swift15-27b 2>&1 | grep -E "WEDGE health|CRASH-LOOP|RESTARTING|BOOT-STALL" | grep -vE '^\s'
docker logs --tail 4000 myia_vllm-watchdog-swift15-27b 2>&1 | grep -c 'OK health=200 decode=200'
# élagueur du tier fs (minuterie systemd DANS WSL depuis le 20/11) : état frais + disque invité au-dessus du plancher 40 GiB + cap (0 = pression disque C:, voir ci-dessous)
python -c "import json,datetime as d;s=json.load(open('d:/vllm/myia_vllm/logs/fstier_state.json'));a=(d.datetime.now(d.UTC)-d.datetime.fromisoformat(s['ts_utc'].replace('Z','+00:00'))).total_seconds()/60;c=s['space_checks']['/mnt/c'];print('pruner age=%.0f min tier=%.1f GB cap=%.1f GB guest_free=%.1f GB c_free=%.1f%% errors=%s'%(a,s['bytes_total']/1e9,s.get('cap_bytes',-1)/1e9,s['space_checks']['guest_root']['free_bytes']/1e9,100*c['free_bytes']/c['total_bytes'],s.get('errors_count')))"
```

**⚠️ Sonder le port publié par `127.0.0.1`, JAMAIS par `localhost` (mesuré 25/11 11:50:33Z, re-mesuré en épisode à 17:52:28Z).**
La branche IPv6 du port publié **échoue par épisodes de 5 à 15 min** alors qu'IPv4 sert — `localhost`
se résout sur `::1` d'abord et la connexion ne rend jamais : `http://127.0.0.1:5002/health` = **200 en
3,3 ms** la même seconde où `localhost` et `[::1]` time-outent à 12 s. La porte de capacité du tapis
a rendu `gate-unknown` (exit 3, sa ladder de timeouts épuisée) et le watchdog hôte a vu `health=0`.
**Un `000` sur `localhost` n'est pas un moteur mort** : contre-mesure in-stack (`docker exec … curl
127.0.0.1:5002/health`), qui a rendu 200 en 1,1 ms puis 0,9 ms.

**Ce qui est mesuré, et ce qui ne l'est pas (25/11, 10 épisodes, journal du watchdog hôte qui sonde `localhost`)** : les deux voies sondées **dans la même fenêtre** dans 2 épisodes (11:50:33Z, 17:52:28Z) — IPv4 servait les deux fois ; IPv4 **par l'échantillonnage 30 s de la porte** (un verdict à chaque tick, zéro `gate-unknown`) dans les 8 épisodes postérieurs à 11:50Z ; **aucune mesure IPv4** dans les 2 premiers (00:01:47Z, 06:11→06:21Z). Sur les 8 épisodes où IPv4 a été mesuré, il servait à chaque fois. ⚠️ La **copie déployée** du watchdog (`C:\ProgramData\maint-scripts\vllm_watchdog.ps1`, propriété **Maintenance**) sonde toujours `localhost` : seule la copie du dépôt a changé (#610) — demande posée à Maintenance le 25/11 (dashboard workspace Maintenance), sans échéance. Un `LastTaskResult` `1`/`2` à cette heure-là se lit avec ce tableau sous les yeux, jamais comme un verdict moteur.

**Élagueur du tier fs — âge > 35 min ou disque invité < 40 GiB libres = organe mort, réparer dans le cycle.** Le tier n'a aucune éviction interne : sans élagueur il remplit le disque invité de 1,08 To, partagé avec le cache HF et les runners CI CoursIA (`coursia-runner.service`). Vécu le 20/11 : la tâche Windows passait par `wscript`→`pwsh`, tous deux figés par la panne G:/DriveFS ; dernier passage 07:22Z, tier 436,8 Go, **0 octet libre**, `Errno 28` côté moteur et ENOSPC sur les runners (retenue `main-red`, merges bloqués). Depuis, l'élagueur tourne par `fstier-prune.timer` dans la distribution Ubuntu, sans dépendre du shell Windows (`myia_vllm/scripts/monitoring/systemd/README.md`). La tâche Windows `fstier-prune` reste **désactivée**, pour n'avoir qu'un seul planificateur. Diagnostic : `wsl.exe -d Ubuntu -u root --exec journalctl -u fstier-prune.service -n 20`.

**`cap=0 GB` n'est pas un organe mort — c'est le signe d'une pression disque C: (mesuré 24/11).** Le plafond vaut `min(250 Gio, invité − 40 Gio, C: − 12 %)`. C: sous la réserve de 12 % (380 Gio libres le 24/11 17:51Z pour une réserve de 480 Gio) ⇒ `cap_bytes: 0` ⇒ l'élagueur ne garde que les blocs de moins de 30 min (`min_age_min`) et le tier oscille entre 0,2 et 23 Go selon les écritures. Âge frais et 0 erreur = comportement prévu (fail-safe disque), pas une panne. À remonter à Maintenance comme signal de pression C: s'il n'est pas déjà suivi ; le rétablir passe par l'espace libre sur C:, jamais par l'élagueur. **28/11 — cas symétrique, mesuré** : C: remonté à 13,66 % ⇒ le plafond **s'est rouvert seul** (96,6 → 99,2 → 111,3 GB sur quatre passes, 02:20→03:56Z) et le tier est repassé de 27,8 à 42,4 GB (≈ +5 GB par passe) avec `deleted_bytes: 0`. ⇒ un cycle ne « rouvre » rien et ne demande à personne de le faire : la formule suit C:. On surveille seulement le **dépassement de cap** et le **retour sous la réserve**.

Attendu : health 200 (<10 ms), RC stable, OOM 0, 3 conteneurs Up, sondes OK. **VRAM référence @0.70/N=48** : à froid après boot GPU 0 19 937 / GPU 1 18 930 MiB, **en charge 21 400-21 600 / 20 400-20 700** (la config 48 flux élargit les graphs sous trafic, ~1,5 GiB de plus qu'à froid). **GPU 0 > 23 000 MiB → alerter** (marge < 1,5 GiB = boot-OOM au prochain restart + pagination WDDM qui imite un wedge) — **ne pas remonter gpu-util**. **Depuis le 24/10 21:26Z : gpu-util 0,73** (mandat user « config au mieux », KV 831 723 ; profil `-fstier`, `${GPU_UTIL_SWIFT15:-0.73}`). Bande en charge attendue ~22 200 / ~21 400 MiB, à mesurer. Si GPU 0 dépasse 23 000 en charge : `GPU_UTIL_SWIFT15=0.70` au prochain restart. Pas de nouvelle hausse sans mesure en charge.

**Dérive VRAM — mesurée puis INFIRMÉE comme tendance (09/10)** : 21 408 (08/10 22:5xZ) → **21 594** (09/10 04:47Z, +186) → **21 435** (09/10 10:47Z, **−159**). Le cycle de 04:47Z avait lu une pente de +30 MiB/h et annoncé une alerte ; **la pente n'a pas tenu** — c'est un **high-water d'allocateur** (charge soutenue qui garde les graphs à leur forme max), **pas une fuite**. Leçon : **deux points ne font pas une pente** ; ne pas annoncer une extrapolation (« J+2 ») sur 6 h de données. La charge qui produit ce high-water est mesurée en §5ter. `StartedAt` stable vs cycle précédent ; un déplacement avec RC=0 = restart externe → identifier la cause (penser à `autoheal` : `docker ps | grep -i heal`, redémarreur concurrent INVISIBLE, RestartCount flat).

Comportement documenté, PAS une panne : toute requête ≥ ~100K tokens **affame les nouvelles arrivées** (dense 27B) — le watchdog tolère 90 s. Depuis le batch 8192 la fenêtre recule (prefill +21 %), mais un WEDGE `fail 1/2` (jamais 2/2) pendant une sonde prefill ou un gros prompt est le comportement attendu, **y compris déclenché par nos propres sondes de banc** (vécu 08/10 21:38 et 21:46, deux `fail 1/2` pendant les sondes 157K, zéro restart). Un WEDGE pendant un gros prefill = attendre le post-mortem avant d'agir ; le moteur est sain.

### ⚠ `/dev/shm` hôte — fuite à chaque boot (mesurée 20/10)

Le moteur est le **seul conteneur `ipc=host`** de la machine (51 conteneurs inspectés le 20/10) : **tout ce qui vit dans ce shm est à nous**. Plancher légitime = **le tier lui-même** (32 GiB en nvfp4) + les blocs `psm_*` transitoires de la génération courante (~0,5-1 GiB). **Tout le reste est orphelin** : chaque génération morte laisse ses `psm_*` (25/161/241 MB) et ses `sem.mp-*`, et **la fenêtre d'éval fs du 20/10 a laissé 2 × 8 GiB de `vllm_offload_*.mmap`** (les tiers du profil d'éval, mtime antérieurs au boot prod). État mesuré avant nettoyage : **49G/63G = 77 %**, dont **21,8 GiB d'orphelins sur 58 fichiers** ; après : **32G = 51 %, 31G libres**, moteur health 200 en 5,9 ms.

Un `/dev/shm` plein = ENOSPC pour les blocs suivants → **crash moteur** ; sous charge (fenêtre Minimax) la marge est le facteur limitant. **Seuil d'alerte : > 45G utilisés (≈ 72 %).**

**★ 2026-11-01 — l'orphelin du tier bloque désormais TOUT redémarrage, et le watchdog en était le déclencheur (91 min d'indispo).** À tier 32 GiB, la région `vllm_offload_*.mmap` (34,4 Go) survit à la mort du process : chaque boot suivant échoue `Insufficient space in /dev/shm ... 32766 MiB required, 3162x MiB free` → boucle de crash. Le 01/11 : mort 16:30Z (17 min) puis **WEDGE ~18:40Z → le watchdog redémarre 18:41:37Z (geste correct) → 91 min d'indispo** jusqu'à purge manuelle. **Correctif déployé le 01/11 21:11Z (PR #318)** : purge automatique à deux étages — (a) en tête de l'entrypoint du moteur (avant tout, no-op sur boot propre), (b) par le watchdog via `docker exec` juste avant son propre `docker restart`. **Diagnostic à jour** : si le conteneur cyclote en `BOOTING`/CRASH-LOOP, vérifier d'abord `docker logs --tail 50 <c> | grep 'shm-orphan purge'` — présent = le correctif a tourné (chercher ailleurs) ; absent = entrypoint ancien ou purge en échec → appliquer la recette manuelle ci-dessous **immédiatement** (c'est ce qui a rendu le service les deux fois).
**Mesuré 27/11 06:16Z, 14 h après l'arrêt** : un `vllm_offload_74eece56-….mmap` de **34 348 990 464 o** plus 4 `psm_*` (0,6 Go) — `df` rend **32 Go utilisés / 31 Go libres** sur 63 (le fichier est sparce : seules les pages touchées comptent). **Un tier de 32 GiB ne rentrerait donc pas sans la purge** : au prochain boot, `docker logs --tail 50 <c> | grep 'shm-orphan purge'` doit rendre une ligne `rm …` parmi les premières, et son absence est le **diagnostic**, pas une hypothèse.

**Recette manuelle (repli, si le correctif est absent ou en échec)** — ne supprime que les fichiers **antérieurs au démarrage du conteneur** :

```bash
docker inspect myia_vllm-medium-swift15-27b --format '{{.State.StartedAt}}'   # borne (UTC)
MSYS_NO_PATHCONV=1 docker exec myia_vllm-medium-swift15-27b sh -c \
  'find /dev/shm -maxdepth 1 -type f ! -newermt "2026-10-20 10:25:05" -print -delete'
```

Effet de bord mesuré : les pages tmpfs comptant dans le commit hôte, les 17 GiB rendus ont fait passer la marge commit de **86,4 % → 83,4 %** (sous le seuil §3). **Nettoyer après toute fenêtre d'éval et après tout `down/up`** — c'est là que la fuite se matérialise.

## (2) Condensation (logs roosync)

**Emplacement** : `%TEMP%\roo-state-manager-logs\`. **Il y a un fichier PAR PROCESS RSM** : `roosync-<YYYYMMDD>.log`, puis `roosync-<YYYYMMDD>-1.log`, …, `-201.log`, etc. Le 22/11, on en comptait 324 pour la journée. Le nom suit le démarrage du process, pas minuit. **Un grep sur le seul fichier du jour rend un zéro qui ne mesure rien** : il faut concaténer tous les fichiers du jour, et ceux de la veille.

```bash
L="$LOCALAPPDATA/Temp/roo-state-manager-logs"; D=$(date -u +%Y%m%d)
cat "$L"/roosync-$D*.log > .tmp/rsm_today.log; ls "$L" | grep -c "roosync-$D"   # nombre de process
grep -aiE 'condensat' .tmp/rsm_today.log | grep -avE 'LLM config:|cloud fallback condensation succeeded'
grep -aE '\[(ERROR|WARN)\]' .tmp/rsm_today.log | grep -avE 'LLM config' | tail -20
# gardien de taille du résumé : Swift d'abord (voir ci-dessous)
for p in 'Summary exceeds size limit, auto-condensing' 'Auto-condensed Summary (attempt' \
         'Auto-condense Summary attempt 1 failed' 'Auto-condense Summary: LLM did not converge'; do
  printf '%5d  %s\n' "$(grep -ac "$p" .tmp/rsm_today.log)" "$p"; done
```

Burst ≥ 12 évts/min = jest (paths `dashboard-test-*`/`__test-data__`) ; vrai échec prod = minute isolée à 1-2 évts.

**Deux chemins de condensation, deux ordres différents (code RSM lu le 22/11, `tools/roosync/dashboard.ts`).**
- **Génération du statut et du résumé : le cloud d'abord, depuis #4434 (17/11).** glm-4.7 passe par le hub, et le primaire `localhost:5002` sert de secours. Le levier est `CONDENSE_SUMMARY_CLOUD_FIRST=0`. Donc `#2719 cloud fallback condensation succeeded` est **le chemin nominal** (44 fois le 22/11), pas un signe de panne de Swift.
- **Gardien de taille du résumé** (« Summary exceeds size limit, auto-condensing », quand le résumé dépasse 5 Ko) : **Swift d'abord.** L'appel est borné par le délai de la passe, puis le cloud prend le relais, puis une troncature déterministe.
  - Mesuré le 22/11 : **10 échecs sur 12**, tous en `Request timed out` après 37 à 58 s, et 10 troncatures déterministes (« LLM did not converge »).
  - Au même moment, Swift était sain, à environ 22 tok/s par flux avec 5 requêtes longues.
  - Condenser ~1 500 tokens prend donc ~70 s, plus que le délai alloué. C'est un **désaccord de budget côté RSM**, pas un wedge (SUPPOSÉ, cohérent avec la mesure).
  - **⚠️ CORRIGÉ le 28/11 — ma première lecture (« l'appel n'est plus tenté ») était FAUSSE.** Mesure ligne à ligne (code `dashboard.ts:5511-5569` + journal du 27/11 22:22Z et 22:26Z, vintage `build-6448bbebb2b863a7` = sha `0240be28`) : **le repli cloud PART et est essayé avant le primaire** (ordre cloud-first #4872). Ce qui échoue, ce sont **les trois jambes, chacune pour un budget** : `glm-4.7` → `Request timed out` à **38,7 s** ; `deepseek-v4.1-flash` → répond en **7,4 s** mais `finishReason: max_tokens` (`contentLength 7538` < l'original de 9 506 B) ⇒ « stopped on its output budget — moving to the next model » — **la réponse est jetée** ; `claude-sonnet-5-5` → `Request timed out` à **38,7 s** ; puis le repli local (Swift) → `attempt 1 failed` à 29,4-76,6 s, `attempt 2 refused — pass deadline reached the cloud reserve (#3962)`. ⇒ troncature déterministe (9 506 → 4 964 B, 11 lignes retirées). **Trois défauts** : budget de sortie dimensionné sur le cap seul (`guardCloudMaxTokensForCap`), timeout par modèle indexé sur le prompt (30 s + 900 ms/KB ⇒ 38,4 s), et **seconde passe serrée qui n'existe que sur la jambe locale** (`MAX_ATTEMPTS`, `:5536-5566`). Comptage par vintage sur 3 087 segments : **10 déclencheurs → 10 troncatures (100 %)** sur le sha servi ⇒ critère #4872 (« ≤ 2 sur 12 ») **non atteint**. Relevé + correctifs proposés : `roo-extensions#4872`, `#issuecomment-7232003717`. **À relayer à roo-extensions (propriétaire du code), sans redémarrer quoi que ce soit ici** — et ne jamais relayer une troncature comme un état acceptable : c'est une **perte d'information** (ici le résumé du tableau `global`).
  - **Piège de lecture** : la ligne « `pass deadline reached the cloud reserve` » dit que le **primaire** est refusé, pas que le cloud a manqué. Le nuage est passé **avant**. Pour diagnostiquer, lire la séquence **complète** du `pid` (de `exceeds size limit` à `did not converge`), jamais la seule ligne de refus.
  - **28/11 05:5xZ — le défaut SURVIT au rebuild de RSM** : nouveau vintage `build-bc3b688662a1b3cc`, déclencheur **05:20:07Z** → troncature **05:22:14Z**. Décompte sur la fenêtre *hier + aujourd'hui* (2 473 330 lignes, 814 process RSM, 12 fichiers du jour + 802 d'hier) : **36 déclencheurs / 33 troncatures** ; **28/11 seul : 11 déclencheurs / 10 troncatures**, 2 succès cloud (`cloud fallback condensation succeeded` : 102 sur la fenêtre). ⇒ le correctif reste **la propriété de roo-extensions (#4872)** ; ne pas refaire la mesure ligne à ligne à chaque cycle : **citer le triplet (déclencheurs / troncatures / succès) + le vintage**, et ne pas sonner.
  - À relayer au propriétaire (roo-extensions) s'il persiste, sans redémarrer quoi que ce soit ici.

**CORRECTION (09/10) — le banner « Condensation LLM config » EST dans le log**, à `[INFO]` toutes les 5 min (`primary=qwen3.6-35b-a3b @ http://localhost:5002/v1 | cloud-fallback=… key=OK`). La spec affirmait le contraire (« jamais dans le log, stderr ») : **faux**, et cela faisait passer un battement de santé pour une absence de signal. Le banner **est le battement qui prouve que la condensation est configurée sur notre moteur** — le lire, ne pas l'exclure. Ce qu'on **filtre** (`grep -v 'LLM config:'`), ce sont les 200+ battements pour ne garder que les **événements** réels (aucun le 09/10 : condensation nominale).

**⚠️ Tout WARN `DashboardTool` se lit AVEC ±3 lignes de contexte avant d'être relayé (leçon 21/10).** Un `grep` plat a fait relayer « `Cloud condensation fallback DISABLED — FALLBACK_API_KEY not set` » comme un fait prod ; en relisant avec contexte, les trois occurrences (05:07/05:09/05:10Z) étaient **entourées de fixtures jest** (`__test-data__`, `{"fbModel": "test-fallback-model"}`) dans un worktree roo-extensions — **burst de test-suite, pas le process de prod** (roo-extensions a mesuré : `ZAI_API_KEY` présente dans les deux `.env`, code conforme). Un WARN isolé sans son voisinage n'est pas un événement. Relayé à tort = coût réel pour le voisin, comme le faux signalement horodaté du 08/10.

**Ce que le log contient aussi (et qui n'est PAS vllm)** : `[MessageManager] Error reading message file during parallel cache build: G:\…msg-…json` (messages du 02/10 illisibles) + `[MessageManager] Inbox cache rebuild hit its budget after 6200/6281 files (#3205)` + `[#3292] Explicit-id population approaching starvation threshold: 100/100`. **Périmètre RSM, pas vllm** — les relayer au propriétaire, ne pas les traiter ici.

**⚠️ Seuil de condensation 266k — RÉSOLU (10/10) : c'est l'auto-compact de Claude Code, PAS un paramètre RSM.** Réponse de roo-extensions depuis le code (web1, 09/10) : **RSM n'a aucun seuil en tokens** — ses condensations sont bornées **octets** (51 200 max) ≈ ~20k tokens. Le « 95 % de 280k = 266k » cité par le user est le seuil d'**auto-compact de Claude Code lui-même**. Le vrai risque résiduel : une session Claude Code routée vers Swift croît vers 262-266k et dépasse **notre** fenêtre (262 144) **avant** de déclencher son propre auto-compact — v0.31 répond alors 400 **sans jamais rogner** (mesuré 09/10, 3 sondes frontière, PR #110). **La parade n'est pas côté moteur** : règle déposée sur claudish #431 ([c.6091076678](https://github.com/jsboige/claudish/issues/431)) — sur 400 « maximum context length », router **cette requête** vers le cloud dans le même tour, **jamais de retry local** (l'entrée ne se rogne pas, elle se contourne). **Signature à continuer à chercher dans le census §5ter : `status 400` + `body_bytes > 100 000` ⚠️ DISCRIMINANT RESSERRÉ le 03/11** — il est **trop large** tel quel : il attrape aussi les refus **media**. Mesuré 03/11 06:37:02Z (claudish hub-side, `reqN=11222`) : 400 « at most 4 image(s) per prompt » (5 images vs notre `--limit-mm-per-prompt {"image":4}`), classé `media`, step sauté, **fallback MiniMax dans le même tour en 14,2 s = #431 fonctionne**. La conversion `body_bytes`→tokens (~4 o/token) est **invalide sur un corps multimodal** : 5 images en base64 fabriquent 1,11 Mo pour ~5-10K tokens. ⇒ ne retenir comme signature de débordement de fenêtre que `status 400` + corps **sans** `image_url`/`input_image`. Première occurrence **texte pur** = à rendre au user ET à claudish immédiatement (elle prouverait que #431 ne couvre pas ce cas). L'escalade RSM d'origine est close sans action.
  - **28/11 05:2x→05:5xZ — PREMIÈRE occurrence TEXTE PUR, et le discriminant EXACT est mesuré.** Le middleware `error_source_capture` **stocke la réponse du moteur dans le champ `error_body`** (mesuré 28/11 : `auth_prefix, body_bytes, body_head, body_tail, body_truncated_bytes, client, error_body, host, model, path, referer, status, ts, user_agent, x_claudish_*, x_forwarded_*, x_real_ip`) ⇒ **lire `error_body`, ne plus heuristiquer sur `body_bytes`**. Deux exemples relevés : `"At most 4 image(s) may be provided in one prompt"` (refus **media**, à sauter) et `"This model's maximum context length is 262144 tokens. However, your prompt contains at least 262145 input tokens, which exceeds this limit even without any output tokens. (parameter=input_tokens, value=262145)"` (**débordement de fenêtre**, `type=BadRequestError`). **3 débordements de fenêtre en texte pur** sur 14 h : **27/11 20:54:44Z, 27/11 23:19:52Z, 28/11 04:30:42Z** — corps **937-985 Ko**, `UA=Bun/1.3.14` (hub claudish), IP `90.65.170.144` (hairpin du site), clé MEDIUM. ⚠️ **Le 400 côté moteur est l'AMORCE de #431 (le hub tente le primaire), pas la preuve que #431 a échoué** : le fait que le cloud ait pris le relais se lit **côté hub** (po-2025:claudish) ⇒ le demander, ne pas l'affirmer ni le publier comme une panne. La spec du 03/11 (« ne retenir que `status 400` + corps sans `image_url`/`input_image` ») est **remplacée** par le discriminant `error_body` — mais la règle de rendu (user + claudish) reste.

## (2bis-a) Watchdog HÔTE `Watchdog-vLLM-API` — livraison des alertes (depuis #595/#598, 24/11)

```bash
L=/c/ProgramData/maint-scripts/logs
tail -4 "$L/vllm-watchdog.log" | cut -c1-170
for f in vllm-watchdog-undelivered.jsonl vllm-watchdog-undelivered.corrupt.jsonl; do
  [ -s "$L/$f" ] && echo "PENDING $f : $(wc -l < "$L/$f") ligne(s)" || true; done
pwsh -NoProfile -Command "(Get-ScheduledTaskInfo -TaskName 'Watchdog-vLLM-API').LastTaskResult"
```

**Non vide, ou `LastTaskResult=5` = alerte NON livrée** → poster son contenu à la main via `roosync_dashboard(action:"append")` (messageId de la ligne) et escalader ; la ligne n'est retirée du journal qu'après acceptation par la CLI. **Le code de sortie de la tâche ne mesure pas la santé moteur** : `1`/`2` = sonde hôte en échec à 10 s (le moteur peut être sain, voir §Prod). `0` moteur UP · `1` DOWN stack présent · `2` DOWN stack absent / docker injoignable · `5` alerte non livrée · `124` self-timeout. Depuis #598 le watchdog poste par la CLI avec un id stable par incident ; le critère de clôture de #595 est 24 h sans bloc **sans identifiant** dans les fichiers Drive `workspace-vllm.md`/`global.md` :

```powershell
$root='G:\Mon Drive\Synchronisation\RooSync\.shared-state\dashboards'
foreach($f in 'workspace-vllm.md','global.md'){
  try { $t=[IO.File]::ReadAllText((Join-Path $root $f)) }
  catch { "{0}: ILLISIBLE ({1})" -f $f,$_.Exception.Message; continue }
  $blocks=[regex]::Matches($t,'(?m)^### .*myia-ai-01\|vllm-watchdog\r?\n(?!\[msg: )')
  "{0}: blocs watchdog SANS identifiant = {1}" -f $f,$blocks.Count }
```

**Une lecture en échec n'est PAS un zéro** : le 24/11 ~03:20Z, `ReadAllText` a levé « Ressources système insuffisantes » sur `workspace-vllm.md` et la forme précédente affichait quand même « 0 ». Le `try/catch` ci-dessus rend l'échec visible (`ILLISIBLE`) — un `0` non accompagné d'erreur seulement est une mesure. Pour travailler sans G: : copier les deux fichiers en local (`.tmp/`) et pointer `$root` vers la copie.

**Un append MCP ne réécrit pas nécessairement le fichier Drive**, et `global.md` peut rester orphelin jusqu'au prochain export horodaté : ne pas conclure « la CLI ne marche pas » sur le seul fichier. Une lecture G: lente (mesuré 24/11 : 73 s) n'est pas une preuve de panne — relire avant de rapporter.

## (2ter) Tapis nb_coder — cœur du producteur

```bash
CONV=$(ls -d /d/vllm/.tmp/nbcoder/conveyor-* 2>/dev/null | sort | tail -1)   # run VIVANT = le plus récent (un chemin figé pointe sur un run mort : mesuré 25/11, `20261120` figé dans la spec alors que `20261124` tournait)
echo "conveyor vivant: $CONV"
tail -3 /d/vllm/.tmp/nbcoder/feeder/feeder.log | cut -c1-180          # dernière ligne > 1 h = feeder mort
tail -2 "$CONV/live/scheduler.jsonl" | cut -c1-220   # "held … pending=0 active=0" répété = plus rien à lancer maintenant
python -I -c "import json,sys,collections;L=[json.loads(l) for l in open(sys.argv[1],encoding='utf-8') if l.strip()];print(dict(collections.Counter((e.get('kind'),e.get('reason')) for e in L)));print('dernier tick',L[-1]['ts'])" "$CONV/live/scheduler.jsonl"   # kinds/réasons du run entier
python -I -c "import json,sys,datetime as d,collections;s=json.load(open(sys.argv[1]));g=s.get('grains',{});nb=sorted(v['not_before'] for v in g.values() if v.get('not_before'));print('grains',dict(collections.Counter(v.get('status') for v in g.values())),'prochain not_before',d.datetime.fromtimestamp(nb[0],d.UTC).isoformat() if nb else '-','state_age_min',round((d.datetime.now(d.UTC)-d.datetime.fromisoformat(s['updated'])).total_seconds()/60))" "$CONV/live/state.json"
wc -l "$CONV/queue.jsonl" /d/vllm/.tmp/nbcoder/feeder/pending.jsonl   # file du scheduler · restant à nourrir
```

**Deux files, deux rôles** (chemins mesurés 24/11) : `<conveyor-*>/queue.jsonl` = ce que le scheduler peut lancer, 1 ligne par grain — le répertoire change à chaque relance (`20261120`, `20261124`, …), d'où la ligne `CONV=` ci-dessus ; `feeder/pending.jsonl` = ce que le feeder n'a pas encore poussé, avec son `not_before`.

**Pas d'état figé ici** (retiré le 25/11) : l'instantané écrit le 24/11 03:30Z (« file de 4 lignes », « prochaine relance utile : le 26/11, à partir de 01:40Z ») était faux au cycle suivant — mesuré 25/11 06:20Z : file de 3 lignes (#27722, #28018, #28097), 3 grains `deferred` + 1 `failed`, prochain `not_before` le 27/11 22:46Z. L'état se lit par les commandes ci-dessus (`state.json`, `scheduler.jsonl`) ; cette section ne garde que ce qui reste vrai. **`held gate-unknown`** (`last_gate.error: timed out`, exit 3) = la porte de capacité, processus hôte, n'a pas atteint le moteur : un échec du chemin hôte (§Prod), pas un verdict — le scheduler retient le grain, à bon escient. Mesuré 25/11 : 19 passes en 3 épisodes, dont 10 consécutives de 06:07:49Z à 06:16:51Z, pendant que `wsl.exe` échouait côté Maintenance et que le moteur servait.

**Le journal se lit par `kind`/`reason`, pas seulement par la dernière ligne** (ajouté 25/11 ; schéma `{"ts","kind","reason","pending","active","gate"}`, les lignes `relache-probe-error` portent en plus `key` et `detail`). Répartition mesurée le 25/11 sur le run `20261124`, **instantané à 17:54:27Z** (le compteur avance de 2/min, `gate-red` sonde toutes les 30 s : citer l'heure avec le chiffre) : `held`/`gate-red` 2 112, **`held`/`gate-unknown` 31, tous jusqu'à 11:51:57Z — aucun depuis, alors que `localhost` a échoué 7 fois de plus** (preuve du correctif #610 sur le terrain), `held`/`launch-gap` 22, `held`/`capacity-target` 5, `held`/`gate-yellow` 1, `launched` 6 (dernier 24/11 23:15:04Z), `queued` 4, `qualification-deferred` 3, `deferred` 2, `queue-reloaded` 2, `queue-reload-error` 2, `withdrawn` 1, `failed` 1, `worktree-kept`/`remove-failed` 1, et **`relache-probe-error` 27** (dernier 14:51:30Z ; 24 « API rate limit exceeded for user ID 3159389 », 3 échecs réseau ; fenêtres 01:39→01:49Z, 08:46Z, 10:48Z, 11:49Z, 14:41→14:51Z). Cette dernière famille est un **moniteur gratuit de l'épuisement du seau REST** : elle monte par groupes de 3 ou 9, dans les mêmes fenêtres que §2bis — la citer au rapport avec ses heures, c'est la meilleure preuve datée du quota, et elle coûte zéro appel supplémentaire.

**★ `gate-unknown` est la signature d'une INDISPONIBILITÉ MOTEUR, pas d'un défaut de route (mesuré 27/11).** Sur le run `20261127` (démarré 05:55:44Z, moteur arrêté de la veille 15:58:57Z jusqu'à 17:59:46Z) : **1 261 `gate-unknown`, tous entre 05:55:49Z et 17:54:10Z** — donc *exactement* la fenêtre sans moteur — puis, dès que le moteur répond, **346 `gate-red` + 51 `gate-yellow` + 0 `gate-unknown`** (premier `gate-red` à 18:21:52Z, la porte laisse ~22 min de chauffe). Deux conséquences : (a) un `gate-unknown` postérieur à un boot **est** un signal, alors qu'en fenêtre d'indispo c'est le comportement attendu et il ne faut pas l'attribuer au correctif #610 ; (b) comparer deux runs exige de **séparer les ticks d'avant et d'après le boot**, sinon un run qui a traversé une panne paraît atteint d'un défaut de route qu'il n'a pas.

**Ne JAMAIS re-nourrir #28017/#28018** (faux-positifs de l'extracteur, déjà réglés hors tapis). Quarantaine `not_before` = retry une fois la date passée ; un scheduler qui n'a plus de grain n'est pas une panne. **Pas de nouveau lot Rust/std** : gel du coordinateur CoursIA — toute alimentation se fait d'abord en accord avec lui (§6). Vérifier avant de relancer : pid du scheduler, drivers détachés (un `TaskStop` tue l'arbre), révision du harnais dans `jsboige-mcp-servers` (la copie `myia_vllm/scripts/adoption/nb_coder` est gelée — user 22/11).

## (2bis) Producteur de pré-audit (nbaudit) — une ligne, à lire chaque cycle

```bash
cat "$LOCALAPPDATA/nbaudit/last-result.json"
```

`{"ts":…,"runner_rc":…,"deliver_rc":…,"ok":…,"consecutive_failures":…}` — état du **dernier** passage horaire. `ok:false` ou `consecutive_failures > 0` = **le producteur de dossiers preaudit est mort** (les consommateurs Hermes/NanoClaw retombent alors en audit *full-read*, plus coûteux pour eux). Un `consecutive_failures` qui monte = panne installée, pas un incident d'une heure.

**Couverture : le runner ne sert que les séries configurées** (`17107`, `17239`, `17357`, `17692` 02-ML-Cours, **+ `19451` = série large servie par vagues : `Audio/` (vague 1, complète 08/10) puis `Image/` (vague 2, drainée 12/11) puis `Video/` (vague 3, armée 12/11), PR #101/#113**). Un carnet **hors périmètre** n'aura jamais de dossier preaudit, panne ou pas — vérifié 08/10 : `2.8b-Theorie-PAC-Lean.ipynb` (02-ML-Cours), réclamé par Hermes, était **absent des 3 checklists** d'origine, donc son « aucun dossier preaudit » n'était **pas** l'outage. Avant d'expliquer une absence par la panne, vérifier que le carnet est **dans le périmètre** (`gh api repos/jsboige/CoursIA/issues/<n>` — REST, pas GraphQL). Le scoping par série vit dans `nb_audit_hourly.ps1` (`--subpath 19451:Video/` depuis le 12/11) ; **le runner saute de lui-même tout carnet `.ipynb` touché par une des 50 PRs ouvertes les plus récentes** (dérivé par passage — la liste statique PR #19868 de l'ordre avait pourri en 5 h, superseded par #19854) ; échec du scan = fail-open. **Vagues 2-4 autorisées** (feu vert user 08/10 soir) : basculer le préfixe (Image/, Video/, puis prose/queue selon l'ordre convergé), une vague à la fois. **Fanion vague 2 (posé 10/10)** : armer `Image/` (25 carnets, 0 cochés) quand Audio/ n'a plus de **livrables en attente** — état 10/10 05:20Z : **34/38 cochés**, 4 restants ; ne pas basculer tant qu'un carnet Audio non-coché et non-PR-skippé peut encore recevoir un dossier (sinon on l'abandonne sans pré-audit). **Vague 3 `Video/` ARMÉE le 12/11 13:50Z** : Image/ drainé (runner : 0 picked ; 3 non-cochés tous déjà audités en commentaires) alors que NanoClaw auditait déjà des carnets Video/ **en full-read sans dossier** (01-3/01-4/02-2 les 12/11 02:12-06:13Z) — exactement le coût que le producteur existe pour couper ; dry-run avant bascule : 3 carnets sélectionnés, rien écrit ; parse PS vérifié. Gel 09/10 soir levé : il avait pour motif l'armement failover, **suspendu depuis par arbitrage user**.

**⚠️ Lectures GitHub en REST, jamais en GraphQL.** `gh issue view` / `gh pr view` / `gh api graphql` dépensent le budget **GraphQL**, qui est compté **par UTILISATEUR** : toutes les lanes de toutes les machines partagent **un seul seau de 5 000/h** et le vident (35 min d'arrêt de ce producteur le 08/10). ⚠️ **`gh api rate_limit` ne voit pas cette panne** — il annonçait `.resources.graphql` = 4967/5000 pendant que *tout* appel GraphQL, même `{viewer{login}}`, était refusé : ne pas s'y fier pour diagnostiquer. **REST est par UTILISATEUR lui aussi, PAS par token** (corrigé le 25/11 ; la ligne disait « REST est par token et reste libre » — **mesuré faux**) : seau `core` de 5 000/h pour « user ID 3159389 », partagé par toutes les lanes et tous les jetons **utilisateur**, épuisé ≥5 fois le 25/11 (01:39→01:49Z, 08:46Z, 10:48Z, 11:47:36→11:51:25Z, 14:41→14:51Z). **Un jeton d'installation d'App GitHub a son PROPRE seau** (RAPPORTÉ par po-2028:claudish, mesuré à la même seconde le 25/11 18:44:04Z : `core` **4 983/5 000 restants côté installation** pendant que le seau utilisateur était à **0**) — une lane qui lit avec une installation ne puise pas dans le seau partagé, et un seau utilisateur à zéro ne dit rien de ses lectures. `gh api rate_limit` **répond même à 0** et lit ce seau REST : le sonder avant une campagne. 3 927 appels consommés en 53 min à 17:44Z pour ~15 appels de cette lane ⇒ le consommateur est ailleurs, non identifié depuis ce siège : une boucle article par article sur >20 items est le premier suspect. **Une lecture qui rend vide pendant une de ces fenêtres est une panne d'instrument, jamais « rien de neuf »** — attendre le reset et relire. Appels en **bulk** (`gh api repos/<owner>/<repo>/issues/<n>` + `/comments --paginate --jq '.[]'`, `--json`, un `search` unique), jamais item par item. Corrigé par PR #98 ; **tout outil de la flotte lisant GitHub en GraphQL est exposé au même seau**, ce qui peut expliquer des « rate limit » ailleurs.

**Pourquoi ce fichier existe et pourquoi il faut le lire ici.** Le passage a été mort **37 h** (07/10 00:05Z → 08/10 13:05Z, 32 échecs) sans que rien ne le dise : la tâche planifiée se lisait `Ready` / `LastTaskResult 0` / 0 passage manqué. **Le code de sortie ne peut pas remonter** — la tâche passe par `wscript.exe` sur `nb_audit_hourly.launcher.vbs`, dont le `Run(…, 0, False)` n'attend pas et ne rend rien (mesuré 08/10 : un VBS de cette forme lançant un enfant qui sort 7 rend **0**). Seule une trace **écrite** survit. Corollaire général : **un livrable qui sort 0 après l'échec de son producteur cache la panne** — vérifier la santé du producteur, jamais le statut du livrable.

## (2bis-c) Organe des escalades — `exit 1` est un défaut CONNU, partagé (mesuré 27/11)

**Ne pas le re-diagnostiquer à chaque cycle, et ne pas dupliquer l'escalade : elle existe.** Mesuré sur ce siège le 27/11 06:10Z : `exit 1`, `ERROR: 1 dashboard(s) illisible(s) sur 95 — mesure partielle, codes 0/2/3 non fiables` ; 908 lectures du store, 903 ok, **5 muettes** (`tools-call`, `TimeoutError after 10 s`) ; compteur **71 échéances dépassées / 12 en attente / 76 réparées**.

- **Ce n'est PAS le bearer** : `ORGAN_ENV_FILE` (portée User) est **déjà** posé sur ce siège (`D:\nanoclaw\.env`, existe) ; le remède `--env-file` ne s'applique donc pas.
- **Le défaut est le lecteur d'ARCHIVES** : `workspace-roo-extensions-2026-11-26T00-27-13.md` est déclarée par le listing et **absente du miroir local** du siège (enveloppe archive en échec). po-2028 a mesuré **4** tableaux illisibles sur 95 et l'a escaladé le 27/11 06:05:42Z (`scope: 06:05Z`) ; l'état `global` le note sur **4 sièges**. Propriétaire = dépôt **`roo-extensions`** (organe partagé), pas ce workspace.
- **Ce qu'un cycle fait** : exécuter l'organe, rapporter le triplet `overdue/waiting/repaired` du siège **comme donnée**, **ne rien conclure** sur les codes 0/2/3 (ils sont explicitement non fiables quand un tableau manque), et **ne pas poster de `[DEGRADED]` de plus** — un `[REPAIRED]` ne viendra que d'un run complet (`exit 0` ou `3`, « 0 dashboard illisible »). **28/11 — `exit 1` mesuré, et deux lectures de la même journée divergent (55 puis 5 échéances)** : le lecteur est dégradé, `myia-po-2028:CoursIA-3` l'a signalé le même jour. Citer le code et le motif, **jamais le compteur seul** ; ne pas sonner.
- **Budget de temps** : un run dure 60 à 120 s (il a dépassé 120 s une fois ici) — le lancer avec un budget, jamais au milieu d'un enchaînement chronométré.
- **28/11 05:5xZ — l'organe a RENDU cette fois (`exit 0`), triplet `overdue=50 / waiting=9 / repaired=80`** (dont 12 sur le défaut connu de l'hôte et 1 panne du lecteur). ⇒ **`exit 0` ne veut pas dire « flotte saine »** : le compteur porte **les autres sièges** (po-2024, po-2025, po-2026, po-2027, po-2028), pas le nôtre. **Notre siège est à 0 escalade ouverte** (le `[REPAIRED]` du 27/11 18:08:27Z a fermé les 3 nôtres). Ne jamais s'approprier les échéances des voisins : les signaler, ne pas les solder.

## (3) Santé G:/ DriveFS (fail-closed RSM si pathologique)

```bash
df -h /g | tail -1
timeout 30 sh -c "echo probe > '/g/Mon Drive/Synchronisation/RooSync/.vllm-probe.tmp'" && rm -f '/g/Mon Drive/Synchronisation/RooSync/.vllm-probe.tmp' && echo OK || echo KO
```

Écriture KO/timeout > 30 s = DriveFS hang → le noter au rapport, ne pas boucler sur les posts dashboard (ils échoueront), et le signaler à roo-extensions (le dossier #4131 suit la bascule PG).

**Où vit le stockage du moteur, et quoi répondre à un `[STOP][DISK]`** (mesuré 2026-11-25 23:54Z au registre `Lxss` + `docker system df`). Les deux disques qui portent la prod sont sur **C:**, pas sur D: : `Ubuntu\…\ext4.vhdx` = **1 002,1 Go** (`C:\Users\MYIA\AppData\Local\wsl\{35b80e90-…}` — tier KV disque, cache HF, runners CI) et `Docker\wsl\disk\docker_data.vhdx` = **697,0 Go** ; `DockerRootDir=/var/lib/docker`, donc **les journaux de conteneurs aussi**. ⇒ un **D: saturé ne menace pas le moteur** (mesuré le 25/11 à 0,91 % libre, moteur health 200 et RC=0) ; c'est **C:** qui compte, et le plancher de l'élagueur s'y lit déjà (`c_free`). Un `[STOP][DISK]` se traite en **trois lignes** : ce que la lane a écrit dans la fenêtre (volume + preuve), ce qu'elle peut retirer (lot **nommé**, preuve « 0 conteneur ne le monte »), et l'état **mesuré** de D:/C: — jamais un `du -sh /d/*` (scan lourd, que Maintenance écarte explicitement ; lancé le 25/11 puis arrêté). Relevé utile pour la récupération de C: : `docker system df` rend **~195 Go reclaimable toutes lanes** (images 63,1 · conteneurs 4,8 · volumes 107,5 · build cache 20,1) — **inventaire à transmettre, pas un lot à retirer** (magasin partagé, infra d'autrui). Lot propre à la lane, borné : `profiles_vllm-compile-cache-swift15-27b-v0320` (1,70 Go) + `profiles_vllm-compile-cache` (0,89 Go), caches d'images retirées du service.

**Marge commit hôte — seuil 85 %** pour tout travail lourd (prouveur, `lake build`) :

```bash
powershell -NoProfile -Command "\$m=Get-CimInstance Win32_PerfRawData_PerfOS_Memory; \$c=\$m.CommittedBytes/1GB; \$l=\$m.CommitLimit/1GB; 'Committed {0:N1}/{1:N1} GB = {2:N1}% (marge libre {3:N1} GB)' -f \$c,\$l,(100*\$c/\$l),(\$l-\$c)"
```

**⚠️ Seuil FRANCHI le 09/10 (90,1 % : 352,9/391,8 Go)** — il était à 78,1 % six heures plus tôt. **Premier consommateur : `vmmemWSL` (~93 GiB)**, pas `Code.exe` (le levier « fermer des fenêtres VS Code » ne pèse plus le premier poids — même constat que po-2025, fait converger par deux machines). Cause probable : la VM WSL2 (Docker Desktop + `tmpfs` du tier KV 24 GiB + le training CoursIA de GPU 2) qui monte par bouffées. La panne du 24/09 était à **97,8 %** ⇒ à 90,1 % **on ne lance AUCUN travail lourd** et on **signale**, on ne bricole pas (`.wslconfig`/`wsl --shutdown` = hors périmètre vllm, et `wsl --shutdown` tuerait moteur **et** hub).

**Relevé 26/11 : 99,7 % (390,5/391,8 Go, 1,2 Go libres) à 05:47Z, puis 99,5 % (396,0/397,8) à 05:55Z — `vmmemWSL` à 114,4 Go de working set**, loin devant tout autre processus (`Code` 5,9 Go au 2ᵉ rang). À ce niveau la VM WSL2 étrangle ses propres sessions : 61 échecs `wsl.exe` (« Une tentative de connexion a échoué car le parti connecté n'a pas répondu convenablement ») dans le journal Maintenance entre 00:00 et 04:59Z, coïncidant avec les épisodes de sonde hôte ci-dessus. **Le moteur, lui, servait** (505/505 in-stack, trafic du hub ininterrompu) : la sonde hôte — qui passe par `localhost` — et la session `wsl.exe` échouent alors que le réseau interne à Docker continue de servir.

**Relevé du cycle suivant, 11:47Z : 98,2 % (396,0/403,3 Go, 7,2 Go libres)** — **les octets engagés sont identiques** à ceux de 05:55Z (396,0 Go), et pourtant le pourcentage a monté de 97,6 à 98,2 % : le **plafond de commit a rétréci de 23,8 Go** (427,1 → 403,3 Go) entre 06:04Z et 11:47Z (fichier d'échange en gestion automatique — il a grandi de 35 Go dans la nuit, il a repris 24 Go ensuite). La marge libre est donc passée de 31,1 à 7,2 Go **sans qu'un octet de plus soit engagé**, et la porte de capacité rendait `red`/`reason: host-commit` (99,02 %) à 11:47Z. ⇒ citer **Go engagés + Go de plafond**, jamais un pourcentage seul, et ne pas lire une hausse de % comme une consommation nouvelle.

## (4) Prouveur Lean (#1453) — état : AUCUNE passe armée

Passe 23 close le 08/10 : **le blocage est un trou de bibliothèque, pas de harnais** — `oneStepWitnesses` retourne `[]` (`ReidemeisterCombinatorial.lean:166-172`) → `verifyMoves ≡ decide (d₁ = d₂)` réflexif seul, `verifyMoves_sound` vacuous. **Ne pas relancer de passe sur `unknotting_11n102_upper`** tant que l'énumération n'est pas implémentée (verrou = réponse coordinateur / tâche bibliothèque). Leçon consignée : vérifier l'organe AU SOURCE avant d'en faire un chemin de clôture — une docstring décrit l'intention, pas le code.

Si une NOUVELLE passe est armée un jour (lanceur `myia_vllm/scripts/adoption/prover_1453/`, pattern `run_passNN_*.sh`) : lancement **seulement** si marge < 85 % **ET** à la fenêtre **:30Z** (jamais à cheval sur le runner nbaudit **:12Z** depuis le 08/11 — décalé de :05Z parce que le seau REST GitHub bascule ~:06-:08Z et que tout passage à :05Z mourait `rate limit exceeded` ; chevauchement = ~50 tok/s/flux et le cap client 240 s tue le tour de réflexion) ; `cp` backup `.pre-passNN` avant ; **écrire la marge lue dans le post de lancement** ; compter TRUE_PLACEHOLDER avant/après ; verdict honnête sur #1453 + DM coordinateur (si la passe échoue, le dire tel quel).

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

**Carte connue (mise à jour 08/10)** : **Jamin** = `88.183.141.187` + `176.172.94.128` (RGAA, confirmé user 08/10 — PAS Candy) + IPv6 déclarée `2001:861:8ac2:e3f0:8602:b5b8:31ab:6424` (jamais observée au 08/10 ; toute apparition = Jamin, ne pas alerter) · **Candy : PAS encore observée** (annoncée plus mesurée ; attribution future par clé scopée, plus par IP) · site (hairpin) `90.65.170.144` · poste user Paris `82.66.89.184` (Q13 répondue 08/10 : « sans doute mon IP parisienne », SUPPOSÉ, Free, trafic arrêté depuis le 01/10) · po-2027 `92.150.81.115` + **`92.184.103.95` (IP sortante mobile, auto-signalée par po-2027 le 10/10 — 2ᵉ IP connue de la machine, ne pas alerter)** · web1/web2 `37.187.180.135`/`51.75.200.22` · familles mobiles Free `92.184.x`/`88.183.x`. **Nouvelle IP non réclamée avec des 200 = alerte user immédiate dans le cycle + entrée registre.** Jamais d'attribution par géoloc registre seule (leçon : l'IP « allemande » était le site lui-même). Le census complet vit en mémoire : `project_vllm_external_ip_census_20261007.md`.

### (5bis) Consommateurs externes — clé scopée `external-vllm` (Jamin / Candy)

**Empreinte `45BDC569E1E3`.** Noms autorisés : `frognano-4b`, `mini`, `swift-1.5-27b`, `qwen3.6-35b-a3b` — les deux derniers sont **le même moteur** (vérifié 08/10 : les deux rendent `200` en OpenAI **et** en Anthropic, `served_by=qwen3.6-35b-a3b`). Tout cloud (`glm-5.3`…) = **403**, sans clé = **401**. Cap **2 requêtes concurrentes** par clé.

**ACTIVE et EFFECTIVE — preuve produite le 08/10 14:02Z.** Redeploy drainé du hub (`OUTCOME success (reload config: allowlist += swift-1.5-27b)`, conteneur parti 14:02:02Z), puis **matrice vérifiée avec la clé résolue** par po-2025:claudish sur `/v1/messages/count_tokens` (route **sans inférence**) : `swift-1.5-27b` / `mini` / `frognano-4b` → **200** ; `glm-5.3` (hors allowlist) → **403 `[InboundKey] … is not permitted`**. C'est le **refus distinct et nommé** qui prouve que `inboundKeys` est chargé et mord — pas un 401 générique. Empreinte inchangée `45BDC569E1E3`. Historique : le status « INERTE » datait d'avant le redeploy ; le 401 de po-2025 n'était pas une preuve (retiré par eux) — **seule la matrice avec contre-épreuve tranche**. **Piège d'instrument** (vécu par claudish) : `config.json` porte `${EXTERNAL_VLLM_KEY}` — une *référence*, pas la valeur ; tester le littéral rend un 401 « invalid proxy authentication » qui imite une clé morte. **La remise aux externes est débloquée** (geste user).

À relever chaque cycle (mandat user 08/10 : « tu relèveras régulièrement les traces ») :

- **Delta d'IP avec 200** (script §5) — Jamin a ≥2 IPv4 mesurées + 1 IPv6 déclarée ; **Candy n'a jamais été observée**, sa première attribution se fera **par clé**, pas par IP. Toute IP hors carte avec des 200 reste une **alerte user immédiate**.
- **Volumétrie** : le census **par clé** (`inbound_key`) vit côté hub → à demander à po-2025:claudish (campagne 30 j en cours, non bloquante). Côté moteur, on ne voit que l'IP.
- **Piège de lecture** : `max_tokens < 256` ⇒ **réponse vide** (`content` null, budget entièrement consommé par le thinking) alors que le moteur est sain — ne pas le lire comme une panne de lane (leçon partagée 08/10, claudish s'y est fait prendre aussi). Idem sur `/v1/messages` : le premier bloc est `type=thinking`.
- **Levier si dérapage** : la clé se **révoque seule**, sans toucher `VLLM_API_KEY_MEDIUM` — c'est le contrôle prévu (le user soupçonne Jamin de chercher à « maxer »).

### (5ter) Census de trafic moteur — qui charge `:5002` (ajouté 09/10)

**Pourquoi.** Le 09/10, ce census a révélé **~60 req/min soutenues (≈3 600/h)** sur la prod — dont la composition n'était documentée nulle part (la baseline d'adoption était ~550 appels/**jour**). C'est aussi lui qui **explique le high-water VRAM** du §1. Le middleware `error_source_capture` journalise `user_agent`, `auth_prefix`, `body_bytes`, `model`, `path`, `status` — **tout est déjà là**, il suffit de l'agréger.

**⚠️ Le log TOURNE vite** (4 395 lignes ≈ **1,2 h** au débit mesuré) : une fenêtre demandée il y a 6 h **n'existe plus**. Toute question sur une fenêtre passée doit être posée **avant** rotation, ou couverte par une agrégation persistante.

```bash
MSYS_NO_PATHCONV=1 docker exec myia_vllm-medium-swift15-27b python3 -c "
import json,time,collections,hashlib
now=time.time()
rows=[json.loads(l) for l in open('/logs/error_sources.jsonl',errors='ignore') if l.strip()]
rec=[r for r in rows if now-(r.get('ts') or 0)<=12*3600]
span=max(1,(rec[-1]['ts']-rec[0]['ts'])/60) if rec else 1
print('lignes %d  fenetre %.1f min  ~%.1f req/min'%(len(rec),span,len(rec)/span))
print('--- UA ---')
for u,c in collections.Counter((r.get('user_agent') or '?')[:34] for r in rec).most_common(8): print('%6d %5.1f/min %s'%(c,c/span,u))
print('--- cle (empreinte SEULE, jamais de prefixe publie) ---')
for a,c in collections.Counter(r.get('auth_prefix') or 'NONE' for r in rec).most_common(4):
    print('%6d %s'%(c,'NONE' if a=='NONE' else 'fp='+hashlib.sha256(a.encode()).hexdigest()[:12]))
print('--- taille de corps ---')
b=collections.Counter()
for r in rec:
    n=r.get('body_bytes') or 0
    b['<1K' if n<1000 else '1-10K' if n<10000 else '10-100K' if n<100000 else '100K-1M' if n<1000000 else '>1M']+=1
for k in ['<1K','1-10K','10-100K','100K-1M','>1M']: print('%6d %s'%(b[k],k))
print('--- statut ---'); print(collections.Counter(r.get('status') for r in rec).most_common(4))
"
```

**Attendu / à interpréter** :
- **Sondes watchdog** `ua=curl` ~2/min, `"Reply with the single word: ok"` (max_tokens 8, finit en `stop` — depuis le 03/11 ; l'ancien `"Count to twenty."` à 24 tokens finissait en `length` et polluait les stats, mesuré 71 tokens nécessaires) : normal.
- **Condensation** `ua=Python-*` « expert en synthèse … 15 Ko » : normal, horaire.
- **Clé unique `fp=<MEDIUM>`** en tête : c'est la clé partagée des consommateurs internes (hub claudish, sk-agent, Roo, sondes). **Vérifier l'identité de la clé AVANT toute conclusion de sécurité** — comparaison côté hôte (`.env`), en n'imprimant que des `sha256[:12]`. **L'empreinte du census est celle du `auth_prefix`, pas de la clé** : le middleware écrit `authorization[:24] + "..."`, soit `"Bearer " + clé[:17] + "..."` (`error_source_capture.py`), et le census hache cette chaîne. `sha256(clé)[:12]` ne peut donc jamais égaliser un `fp=` (mesuré 25/11 : MEDIUM = `db2738ab1328` sous cette forme, `be312daf7c1c` dans le census). La forme ci-dessous recalcule l'empreinte du census pour chaque clé du `.env` — à rapprocher directement d'un `fp=`, **sans rien recopier de la clé dans la commande** (l'ancienne forme faisait coller 16 caractères de clé dans le terminal : fragment de secret dans le transcript, et deux essais sans correspondance) :
  ```bash
  python -I -c "
  import hashlib
  vals={}
  for l in open('d:/vllm/myia_vllm/.env',encoding='utf-8',errors='replace'):
      if '=' in l and not l.strip().startswith('#'):
          k,v=l.strip().split('=',1); vals[k.strip()]=v.strip().strip(chr(34)).strip(chr(39))
  for k,v in vals.items():
      if 'KEY' in k.upper() and v: print('%-28s fp=%s'%(k,hashlib.sha256(('Bearer '+v[:17]+'...').encode()).hexdigest()[:12]))
  "
  ```
- **Clé hors des connues (`MEDIUM`, `MEDIUM_VL`, `MINI`, `MICRO`, `external-vllm`) = anomalie** → §5 (alerte) + registre. **Nuance mesurée le 25/11** : une empreinte absente du `.env` et vue **uniquement en `status 401`** est une clé **refusée** — la porte tient. La signaler avec son IP et son agent, sans l'annoncer comme une utilisation non autorisée. Deux empreintes `Python-urllib` sans `X-Forwarded-For` (6 et 3 × 401) : SUPPOSÉ, un consommateur de la flotte à clé périmée.
- **⚠️ MAIS une clé connue ne dit RIEN sur le client (arbitrage po-2025, 09/10).** Le hub claudish appelle `:5002` **sous MEDIUM pour *tous* ses clients** : la clé est un **seuil de sécurité**, pas un **discriminateur d'identité**. Pour attribuer une charge, le discriminant est la **TAILLE DES CORPS** — un client à contexte long (~57 K) se distingue par `body_bytes > 100 Ko`, jamais par la clé. Ne pas conclure « c'est interne, donc c'est bénin » : un client interne qui boucle (cf. latch Zoo #4025, ~20 h) pèse autant qu'un externe.
- **`body_bytes` > 100 Ko = requêtes long-contexte** : ce sont elles qui pilotent le high-water VRAM. Un client qui boucle là-dessus (cf. latch Zoo #4025) se voit ici **avant** de se voir en VRAM.

### (5quater) Charge Minimax/failover — amortissement des préfixes (ajouté 19/10, mandat user « surveiller l'utilisation comme le feu »)

**Contexte.** Le moteur est onboardé comme marche de failover **Minimax** (mur quota ~23/10 09:00Z, reset 25/10 23:05Z — claudish #543) ; cap tandem Cand/Jamin doublé ; **maxing PERMANENT plusieurs jours attendu** = sessions récurrentes dont les préfixes sont déjà vus. Régime sain : chaque tour ne paie que son **delta** (gros prefill payé une fois, replay tier 51× moins cher). Pathologie : **re-prefill massifs récurrents** quand le working set dépasse GPU KV 429K + tier ~685K ≈ 1,11M tok → LRU jette du contexte vivant. Position lane (19/10, #543 c.6277127297) : cap progressif 2→3→5, routage-cloud avant le mur.

**À relever chaque cycle tant que la charge Minimax est active :**

1. **Hit rate prefix** (compteurs `/metrics`, reset à chaque boot — noter l'âge moteur) :
   ```bash
   curl -s http://127.0.0.1:5002/metrics | grep -E '^vllm:(prefix_cache_queries_total|prompt_tokens_cached_by_source_total)'
   ```
   **⚠ FORMULE CANONIQUE (corrigée 03/11, cycle 17:41Z)** : ratio = `Σ prompt_tokens_cached_by_source_total{device,host,disk,p2p} / prefix_cache_queries_total`. **`prefix_cache_hits_total` compte le DEVICE SEUL** — lu seul il a fabriqué une fausse panne (« 2,8 %, amortissement cassé ») alors que le vrai ratio était **86 %** : à working set > KV GPU, le tier RAM sert l'essentiel (host = 81 % du cache servi) et n'apparaît PAS dans ce compteur. En croisière longue (sessions récurrentes) le ratio doit **monter**. Vrai ratio plat ~0 avec des corps >100K en jeu = **amortissement cassé** → alerte user + registre — vérifié sur la formule complète avant de publier.
2. **Signature re-prefill (census §5ter)** : même IP/empreinte avec `body_bytes > 100K` **répétés à cadence de tour** (au lieu de delta 1-10K) = le client re-paie tout son contexte à chaque tour.
3. **Préemptions** : `vllm:num_preemptions_total` (reset au boot) qui **monte en continu** = saturation KV réelle (plus discriminant que la VRAM). `kv_offload_cpu_cache_usage_perc` reste une gauge in-flight, PAS une jauge de remplissage.
4. **Wedge watch renforcé** : les prefills géants affament les sondes (GEN_TIMEOUT 90 s) ; `WEDGE fail 1/2` pendant un gros prefill = attendu ; `2/2` → vérifier d'abord que des sessions longues sont en vol avant de conclure à une panne.
5. **Escalade = décision user, jamais auto** : si préemptions récurrentes + hit rate cassé + re-prefill massifs → (a) **marge commit d'abord** (§3 — le tier 24 GiB peut monter 32-48 GiB SI marge < 85 %), (b) **ré-éval NVFP4** (re-commande 1 var `KV_DTYPE_SWIFT15=nvfp4`, record PR #123 : KV 750K mais −13/−17 % débit). **TQ k8v4 dominé par nvfp4 sur chaque métrique mesurée — ne jamais re-tester.**

## (5quinquies) Veille amont — UN appel REST par cycle (ajouté 05/11, mandat user)

**Pourquoi cette section existe.** Le 04/11 le user a trouvé en ouvrant une issue que le fix de notre propre bug MTP ([vllm#58813](https://github.com/vllm-project/vllm/pull/58813)) attendait une validation de notre part **depuis six semaines**, et que la PR amont de notre correctif de tiering ([#63551](https://github.com/vllm-project/vllm/pull/63551)) avait une réponse d'un mainteneur **depuis dix jours**. Ce n'était pas un oubli de lecture : **la spec n'avait aucun volet de veille amont**. Un cycle de surveillance vérifie la prod, pas le monde extérieur — et nos propres commentaires créent des artefacts publics que personne ne relit.

**Règle** : une seule passe, **REST uniquement** (jamais GraphQL — seau partagé 5000/h par utilisateur), **1 requête par artefact**, en fin de cycle. Un artefact qui a bougé depuis le dernier relevé = un événement à qualifier dans le rapport ; un artefact inchangé = **une ligne, pas d'analyse**.

```bash
# 1 seul appel par artefact, sortie compacte. `updated_at` change sur commentaire/review/label.
# `issues/<n>` rend AUSSI les PR (sous-objet `pull_request`, `merged_at` dedans). Un artefact
# dont on ignore la nature se lit par `issues/`, jamais par `pulls/` : un 404 sur `pulls/` veut dire
# « c'est une issue », pas « l'artefact a disparu » (mesuré 25/11 sur #69715 et #69280).
for n in 63551 58813 58807 53414 69165 69141 69181 69715 69280 69444; do
  gh api "repos/vllm-project/vllm/issues/$n" --jq '"\(.number)\t\(if .pull_request then "PR" else "issue" end)\t\(.state)\tmerged=\(.pull_request.merged_at // "-")\tupdated=\(.updated_at)\tcomments=\(.comments)"' \
    || echo "ERREUR $n — artefact absent ou API en échec : re-mesurer, ne pas conclure"
done
```

**Liste fermée** (élargir = un commit sur ce fichier, pas une improvisation) — critère de réveil entre parenthèses :

| Artefact | Ce qu'on attend | Réveil |
|---|---|---|
| `vllm#63551` (nôtre) | review de `orozery` sur la forme révisée | review → lire le thread complet, reworker, répondre |
| `vllm#58813` | merge | **merge → planifier le retrait de l'overlay `s58813`, MTP redevient candidat** |
| `vllm#58807` (nôtre) | réponse après notre preuve du 05/11 | réponse → répondre, jamais laisser sans suite |
| `vllm#59040` / `#53414` | merge (contournements `mtp.fc`) | merge → comparer au #58813 pendant le retrait d'overlay |
| `vllm#60229` | déjà mergée 29/10 — **re-test DSpark** possible | release qui la porte + GO user = fenêtre |
| `vllm#62615` | équivalent upstream de notre correctif tiering | merge → **retirer `vllm-openai-v0320-tierpin:v1`** |
| `vllm#53180` (nôtre, TQ×spec-dec) | toute activité | activité → relire (famille CLOSE, veille seule) |
| `vllm#69165` / `#69141` | Inkling 2 Mini sur SM8x (noyaux) et experts INT4 — le chemin de notre image `inkling-sm89-test:v2` | **`#69165` FUSIONNÉE le 27/11 04:12:08Z** → plus de patch local dès qu'une release la porte ; re-mesurer le pool à MAXLEN ≥ 100 K quand les **4 leviers** (#69141, #69165, #69181, #69444) sont dans une même release, puis banc apparié dans un créneau GPU 2 |
| `vllm#69181` / `#69444` | taille du KV Inkling (historique de convolution lisible seul) | merge ou mesure nouvelle en commentaire → re-mesurer le pool à MAXLEN ≥ 100 K |
| `vllm#69715` / `#69280` | réserve des groupes conv-state, planificateur KV hybride (Inkling) | merge → la capacité Inkling peut changer d'ordre de grandeur |
| `jsboige/vllm` PR ouvertes | review humaine | review/CI rouge → traiter |

**Lignes Inkling (ajoutées 24/11, dossier rouvert par le user)** : les artefacts jumeaux (`#69444`, `#69280`) ne se lisent que si le représentant de leur ligne a bougé. Les mesures de référence sont dans le dépôt : `myia_vllm/_iteration_log/inkling_sm89_gpu2/NOTES.md` (SM89 le 22/11, banc apparié du 23/11, ce qui n'est pas établi). **Un résultat de banc s'écrit dans ce journal au cycle qui le produit** — celui du 23/11 est resté deux jours dans un brouillon de `.tmp/`, et la lane a cru le 24/11 que le banc n'avait jamais tourné.

**Ce qui n'est PAS de la veille amont** : re-tester la famille spec-dec (CLOSE 0/4, GO user requis), merger/approuver les PR d'autres lanes (hors mandat, relayer), ni relancer un test dont le critère est mort (`#40798` fermée sans merge le 2026-05-30).

**Un « zéro » doit être mesuré** : si `gh` échoue (quota, auth), l'écrire **comme une panne d'instrument**, jamais comme « rien de neuf ». Vérifier `gh api user` avant si un doute existe sur le compte (`gh` dérive entre les lanes).

## (6) Triage coordination

Inbox `roosync_messages` : lire l'adressé `myia-ai-01:vllm`, répondre/ack, `mark_read` ciblé (**`bulk_mark_read` exige un filtre `from`/`subject` — sans filtre il marque TOUT l'inbox**). Adressage machine-only = bug #3960 : ignorer les dispatchs d'autres workspaces. Dashboards : lire global + workspace-vllm ; rendre les lignes demandées (split-brain, matrices, etc.) ; relayer à l'user les réponses aux issues ouvertes par la lane.

## Clôture (OBLIGATOIRE, cet ordre)

1. **Commit + PR AVANT le rapport** — jamais annoncer du non-committé (`gh auth switch -u jsboige`, PR `--repo jsboige/vllm`, merge `--merge` ; si gh GraphQL limited → fallback REST).
2. `append` **[DONE]** sur workspace-vllm (prod, condensation, G:, watchdog hôte §2bis-a, tapis §2ter, prover, sécurité, registre restitué).
3. Ligne Active Work Log dans `MEMORY.md` (mémoire `~/.claude/projects/d--vllm/memory/`).
4. **Re-arm le cron** (6 h à :17, session-only, prompt = `/vllm-surveillance` + fallback) + `CronList` vérifié.
5. Zéro question bloquante au user : toute question va au registre `user-question-registry.md` (5 champs, dont l'attendu et le mécanisme de retrait), restitué en bloc au rapport.

Règles standing : famille spec-dec CLOSE (0/4, ne pas re-tester) · jamais de valeur de clé en clair (empreintes sha256[:12] uniquement) · infra d'un autre workspace = demander, pas appliquer.
