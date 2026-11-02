# Fenêtre de charge swift N=2/4/6 — 02/11/2026 20:00Z (GO user + claudish, thread Q-73)

Question : swift peut-il absorber la marge ~245/h (le levier po-2028 de Q-73) ?
Réponse mesurée : **NON dans le régime du 02/11 soir — le garde a aborté au premier
palier, 90 s après le départ** : 2 requêtes synthétiques concurrentes par-dessus le
trafic réel suffisent à casser le seuil client 240 s. C'est une donnée, pas un échec
de fenêtre : les paliers N=4/N=6 sont inatteignables dans ce régime, et la
saturation est **la file**, pas l'admission GPU (`preempt_delta = 0`).

## Chronologie (UTC)

| Heure | Événement |
|---|---|
| 19:59:38 | Palier N=2 démarré. **Préflight : KV déjà 89,4 %, preempt total 20, waiting 0** |
| ~20:01 | Garde `waiting>0 en continu > 60 s` DÉCLENCHÉ (max_waiting=3) |
| 20:02 | Abort du palier — N=4/N=6 jamais tentés |
| 20:05:19 | **Récupération VÉRIFIÉE** : waiting=0.0 toutes raisons, KV 63,8 %, preempt 20 (inchangé) |

## Les 2 requêtes du palier N=2 (les seules de la fenêtre)

| # | ptok | ctok | TTFT | e2e |
|---|---|---|---|---|
| 1 | 101 877 | 1 200 | 263,7 s | 285,6 s |
| 2 | 129 635 | 954 | 266,9 s | 286,2 s |

Palier : p50/p95/p99 e2e = 285,6/286,2/286,2 s · KV max 89,75 % · `preempt_delta` **0**.

## Trois lectures

1. **Le moteur était presque plein avant moi.** KV 89,4 % au préflight = trafic réel
   déjà au plafond de son working set (la prédiction « trafic minimal à 20:00Z,
   MiniMax ouvert » est contredite par la mesure — le flip 15:38Z a rendu po-2028
   éligible et la charge swift mesurée montait : 224→327/h dans la journée).
2. **Une requête ~100-130 K dans un régime chargé coûte > 4 min de TTFT à tout le
   monde** (max_waiting=3 = mes 2 + au moins 1 requête réelle mise en file).
   Le seuil client 240 s du hub est cassé par DEUX requêtes — pas par six.
3. **Effet latéral observé en direct** : pendant la fenêtre, le condenseur RSM a
   timé-out à 90 s sur swift (dashboard auto-condensation, repli cloud) — le motif
   « trois instruments, une même file » de claudish, mesuré depuis l'extérieur.

## Miss de design consignée (honnêteté de la mesure)

L'estimation de tokens du driver visait 40/55/70/85 K ; **réel 101 877/129 635**
(≈ 0,4 token/mot sur ce corpus, pas 0,74). Les requêtes étaient ~2× plus lourdes
que visé — soit ~1,25× le profil moyen réel (88,8 K) et ~0,8× le profil pic
(142 K SUPPOSÉ). Le verdict « N=2 casse le seuil » vaut donc **pour le profil
pic**, pas pour le profil moyen. Une re-fenêtre à prompt moyen (~60-80 K vérifiés
ptok) reste à faire pour borner le régime moyen — mais dans un régime de KV 89 %,
la conclusion directionnelle ne changera probablement pas.

## Politique d'admission — PROPOSITION sur les données

Mesures d'appui : KV 831 723 tokens ; un 262 K = 31 % du pool ; TTFT 264 s pour 2
requêtes ~115 K en régime KV ~89 % ; préemptions 0 pendant l'épisode.

1. **Seuil d'admission par taille de prompt, dynamique** : refuser (HTTP 413/429,
   pas mettre en file) toute requête dont `prompt_tokens > seuil` où
   `seuil = (1 − KV_usage) × 831 723 − 2 × décodage_moyen` — concrètement à 89 %
   de KV, le seuil tombe à ~50 K ; à 60 %, ~250 K (tout passe). Implémentation :
   middleware OWUI ou hub, pas vLLM natif.
2. **Priorité courte-ctx en file** : à parité de KV, admettre les petits prompts
   d'abord (l'attente infligée par un 130 K à trois 20 K est de 4 min contre 40 s).
3. **Le dé-fleeting de MiniMax n'ouvre PAS tout seul** : la marge 245/h de Q-73
   n'existe que si la politique (1) est en place — sinon les paliers N=4/N=6 sont
   des murs, mesurés.
4. **À borner ensuite** : re-fenêtre à profil moyen, un jour de KV < 70 % au
   préflight, pour mesurer où le seuil 240 s tient réellement (N estimé ≥ 4).

## Artefacts

- Driver : `myia_vllm/scripts/adoption/bench_load_swift.py` (PR #332)
- JSONL : 2 requêtes, `.tmp/swift_load_window.jsonl` (re-générable)
- Garde déclenché : `num_requests_waiting > 0` en continu 61 s — critère claudish
  respecté à la lettre, abort automatique sans intervention.
