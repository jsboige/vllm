# Swift sur v0.34.0 — overlay tierpin et cache KV non extensible (18-20/11/2026)

Production depuis le 19/11 00:07Z : `vllm-openai-v0340-tierpin:v1`, profil
`medium-swift15-27b-fstier.yml`, `--disable-extensible-kv-cache`, **KV 793 516 tokens**.
Cette fiche versionne une bascule qui, jusqu'au 20/11, ne tournait que depuis des fichiers
de brouillon (`.tmp/swift-v0340-overlay/`, ignoré par git).

## Chronologie

Les points 1 à 4 sont RAPPORTÉS : ce sont les mesures de cette lane, consignées dans sa mémoire
au moment des faits. Le point 5 est MESURÉ le 20/11.

1. **Préflight (18/11 ~23:17Z).** Le stock v0.34.0 épinglé (`vllm/vllm-openai@sha256:cf5b2fdd…`)
   garde la course de tiering qui avait fait tomber le moteur 5 fois le 24/10 (`AssertionError:
   Chunk … not found in cache`, `cpu/manager.py`). Le correctif local des deux modules a été
   porté sur les sources du tag. Résultats : 3/3 tests de régression dans l'image, 219/219 tests
   amont, import `TouchOnHitFsTier` OK. La bascule a été retenue ce soir-là : commit hôte à
   87,47 %, au-dessus du seuil de 85 % des tâches lourdes.
2. **Bascule (18/11 23:51Z).** GO user, avec un seuil explicite (« seuil à 89% également pour
   redémarrage stp »). Fenêtre annoncée sur `global`. Recréation du moteur seul, à 87,19 % de
   commit. Génération watchdog OK à 23:55:20Z, RC=0. **KV annoncé 412 345 tokens** contre
   776 824 en v0.32.
3. **Diagnostic (19/11 00:01Z).** Le dtype reste NVFP4 (métrique et backend FlashInfer,
   `torch.uint8` empaqueté). La perte vient du **cache KV extensible**, actif par défaut en
   v0.34 : il redimensionne le cache après le warmup, soit
   17,03 − (22,21 − 10,90 − 0,03) − 2,06 = 3,69 GiB/rang, 291 blocs. La formule de capacité en
   tokens est inchangée entre les deux tags.
4. **A/B (19/11 00:03→00:07Z, GO user, fenêtre annoncée).** Une seule différence Compose :
   `--disable-extensible-kv-cache`. NVFP4, gpu-util 0,71, offload 32 GiB et volume de
   compilation sont inchangés. Variante B : **793 516 tokens / 560 blocs**, contre A 412 345 / 291
   et v0.32 776 824. Génération watchdog OK à 00:07:36Z, RC=0. 16 tokens relus depuis le disque
   après le boot : c'est une preuve de lecture fs, pas une mesure de débit. Confirmé après le
   reboot hôte du 19/11 : 793 516.
5. **Versionnement (20/11 ~05:30Z, MESURÉ).**
   - Hash de configuration Compose **identique** entre le profil versionné et chacun des trois
     conteneurs en service :
     - moteur `0663c09a8229…` ;
     - watchdog `c0a2bf9506cd…` ;
     - télémétrie `6904335d898d…`.

     Avant ce commit, le profil versionné donnait `e8eb71e4…` pour le moteur : un
     `compose up -d` lancé depuis le dépôt aurait recréé la production en v0.32.
   - Fichiers de l'overlay identiques octet pour octet à ceux de l'image en service :
     - `cpu/manager.py` `93110d5f…` ;
     - `tiering/manager.py` `fba881f0…`.
   - Base du port (`port.py`, objet tag `0c57b419…` du fork) identique octet pour octet aux
     fichiers du stock `cf5b2fdd…`.
   - Régression rejouée dans des conteneurs jetables sans GPU (`overlay_v0320_tierpin/tests/
     test_step_hit_protection.py`) :
     - stock v0.34.0 : **3 échecs**, dont le premier reproduit l'assertion de production
       `Chunk … not found in cache` ;
     - overlay : **3 réussites**.

     ⇒ la course n'est toujours pas corrigée dans la release amont.

## Contenu de `configs/docker/overlay_v0340_tierpin/`

- `Dockerfile` : `FROM` stock v0.34.0 par digest, plus les deux modules et `py_compile`.
- `vllm/v1/kv_offload/{cpu,tiering}/manager.py` : les fichiers servis.
- `PATCH.diff` : diff contre le stock, 17 lignes changées. Même correctif que
  `overlay_v0320_tierpin` : les HIT du pas courant sont protégés de l'éviction par une promotion
  fs→RAM (`_step_hit_keys` → `extra_protected`), et la protection est vidée à
  `on_schedule_end`, à `reset_cache` et autour des sondages hors fil.
- `port.py` : le script de port, conservé tel quel pour la provenance (empreinte
  `91305f6c…`). Il pose une ancre unique par changement et compile le résultat. Il écrit sous
  `swift-v0340-overlay/` relatif à son dossier, donc il se lance depuis une copie sous `.tmp/`.
- `regression.sh` : le lanceur de régression d'origine (`/regression` monté).

Construction : `docker build -t vllm-openai-v0340-tierpin:v1 myia_vllm/configs/docker/overlay_v0340_tierpin`.

## Retour arrière vers v0.32

Le flag `--disable-extensible-kv-cache` n'existe qu'à partir de v0.34 : changer l'image ne
suffit pas. Il faut restaurer le profil d'avant ce commit, ce qui ramène l'image, le volume de
compilation et la ligne de commande :

```bash
git show 8bb6d9f5b9:myia_vllm/configs/docker/profiles/medium-swift15-27b-fstier.yml > .tmp/rollback-v0320.yml
docker compose -p profiles --project-directory myia_vllm/configs/docker/profiles \
  -f .tmp/rollback-v0320.yml --env-file myia_vllm/.env up -d --no-deps vllm-medium-swift15-27b
```

L'image `vllm-openai-v0320-tierpin:v1` et le volume `vllm-compile-cache-swift15-27b-v0320`
sont conservés. Tout restart s'annonce sur `global` avant le geste.

## Retirer l'overlay

Dès qu'une release amont porte un correctif équivalent (suivi : notre PR amont #63551, design
demandé par `orozery`), on rejoue `regression.sh` sur la nouvelle release stock. Si les 3 tests
passent sans overlay, on revient à l'image stock.
