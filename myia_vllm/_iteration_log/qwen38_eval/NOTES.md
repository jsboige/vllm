# Qwen3.8-27B AWQ-INT4 + MTP-3 — évaluation d'opportunité

**Statut :** en cours (pré-téléchargement lancé 2026-08-19, fenêtre GPUs 0,1 en attente).
**Décision évaluée :** remplacer / compléter le MoE Qwen3.6-35B-A3B (prod) par le dense Qwen3.8-27B.
**PR :** [jsboige/vllm#16](https://github.com/jsboige/vllm/pull/16) — profil + batterie.

## Pourquoi

- Benchs massifs vs génération 3.6 (tier dense ≈ notre MoE) : SWE-bench Pro 61.7 vs 53.5,
  Terminal Bench 2.1 73.0 vs 63.4, QwenSWEBench 79.0 vs 49.3, OSWorld 84.3 vs 63.9,
  IFBench 79.5 vs 69.1, DeepSWE 42.2 vs 13.3. Apache-2.0.
- Feature-parité + vidéo native + `reasoning_effort` adaptatif (xhigh/medium/low).
- MTP head entraînée dans le checkpoint → spec-dec « gratuit » si la head survit au quant.
- `cyankiwi/Qwen3.8-27B-AWQ-INT4` : head MTP + vision + lm_head + GDN in_proj en BF16
  (vérifié dans config.json `ignore`) — la recette qui préserve l'acceptance en 4 bits.
- Stack : image stock v0.27.1 inchangée (transformers 5.15.0 ≥ 5.8.0 ; classes `qwen3_5`).

## Le coût attendu (à mesurer, pas supposer)

Concurrent N=16 : dense 27B estimé 200–350 tok/s vs MoE 956. MAIS concurrence réelle
mesurée (2026-08-19, fenêtre 5 j) : 15 977 req, ~8 tok/s de moyenne, 0 préemption,
0 attente-capacité → le coût dense est un coût d'échelle future, pas du présent.

## Correcteur TurboQuant (décision KV = fp8, TQ = variante B)

`turboquant_k8v4 × MTP` n'est PAS prouvé sur stock : #40831 (ngram) et #40880
(MTP × CUDA-graph, hybride) clos par l'arbre Genesis (P65/P66/P64/P68/P69), pas
upstream. Mode de défaillance = sortie dégénérée SILENCIEUSE qui passe tous les
health checks → le canary qualité de validate38.py est obligatoire pour toute
config spéculative. fp8 seul couvre ~2× la fenêtre (16/64 couches d'attention).

## Gate

Batterie : [`validate38.py`](validate38.py) (adaptée de phase 2 + mtp-acceptance +
canary + single-stream). Contre-référence A/B : le MoE 3.6 re-déployé la MÊME
soirée, même batterie (validate.py original).

## Chronologie

| heure (UTC) | événement |
|---|---|
| 2026-08-19 | GO utilisateur. Recherche (modèle/quants/recette/DFlash2/TQ-forensics). PR #16. Pré-download 21 G (conteneur CPU-only, prod intacte). |
| 08-19 10:31 | Pile 3.6 down (propre). Pile 3.8 up. |
| 08-19 10:37 | **Boot OK en 4 min 20 s** (health 200, RC=0) — dense 27B plus léger que le MoE, compile plus courte. KV : **342 691 tokens = 1,31× fenêtre** (⚠️ très en deçà de Todd 560 900 — mais lui à gpu-util 0.95 et max-num-seqs 4, nous 0.70/16). VRAM GPU0 20,0 / GPU1 19,2 GiB. `Qwen3_5MTP` résolu, drafter chargé. |
| 08-19 10:39–10:44 | **Batterie 17/17 effectif** (le seul FAIL = bug du canary v1 : `'132'` correct de 3 car échouait le seuil >30 — corrigé, re-PASS). |

## Résultats batterie (2026-08-19 10:39Z, machine même-journée)

| Gate | Résultat | Détail |
|---|---|---|
| smoke | PASS | 0,43 s → 'OK' |
| canary (v2) | PASS | 3 prompts sains, ratio 4-gram max 0,00 — **aucune dégénérescence** (fp8+MTP sain) |
| vision | PASS | 2,1 s, **4/4 couleurs** |
| tool-calling | PASS | 0,6 s → get_weather(Lyon) |
| thinking | PASS | 5,1 s, 391 trouvé, effort low |
| preserve_thinking | PASS | '7' |
| **mtp-acceptance (1ᵉʳ)** | **PASS** | **0,82** (446/543) — bande officielle FP8/NVFP4 ; head BF16 de cyankiwi drafter très bien |
| prefill-30k | PASS | 31 417 tok / 16,7 s → **1 879 tok/s** |
| prefill-95k | PASS | 101 838 tok / 60,4 s → 1 685 tok/s |
| prefill-235k | PASS | 253 503 tok / 192,6 s → **1 316 tok/s** + survie |
| single-stream | PASS | **37/36/43 t/s** (temp 0.7, no-think) — ⚠️ moitié de Todd 84 (2×3090 !) |
| concurrent-N16 (froid) | PASS | 164 tok/s |
| concurrent-N16 (chaud) | PASS | **376 tok/s** agrégé, 0 échec |
| mtp-acceptance (cumulé) | PASS | 0,48 (4 683/9 801) — retombe sous charge/temp 0.7 |

### Lecture

- **MTP fonctionne réellement** : 0,82 au premier passage, head BF16 intacte (le piège #3 est évité). Acceptance cumulée 0,48 sous charge chaude/temp 0.7.
- **Single-stream 43 t/s = décevant** : Todd mesure 84 t/s sur 2×**3090** avec le même modèle W4A16+MTP. Nos 4090 devraient faire mieux, pas 2× moins. Hypothèses à tester plus tard : (1) **AWQ group_size 32 (cyankiwi) vs 128 (Todd)** — surcoût de déquant Marlin 4× ; (2) le warning `max_num_scheduled_tokens=4096` du spec-dec ; (3) harness différent.
- **Concurrent N=16 376 t/s** : dans l'estimation 200–350 (légèrement au-dessus) — le coût dense attendu, à confronter au 3.6 même-journée.
- **KV 342 691 = 1,31× fenêtre** : UNE requête 262K à la fois. Pour le scénario « traces agentiques longues concurrentes », fp8@0.70 ne suffit pas → soit gpu-util ↑ (marge VRAM GPU0 ≈ 4,5 GiB), soit **TurboQuant** (variante B + canary obligatoire), soit les deux.

### A/B même-journée (08-19, 3.6 restauré 11:04Z, batterie validate.py 11:08Z, 13/13 PASS)

| Métrique | Qwen3.8-27B AWQ+MTP-3 fp8 | Qwen3.6-35B-A3B TQ (prod) | Référence 3.6 du 08-14 |
|---|---|---|---|
| Boot (chaud/vierge) | **4 min 20 s** (volume compile vierge !) | 8 min 20 s (chaud) | ~8 min |
| Vision | 2,1 s, 4/4 | 4,3 s, 4/4 | — |
| Tool calling | **0,6 s** | 1,9 s | 0,47 s |
| Thinking (17×23) | **5,1 s** (effort low) | 15,1 s (défaut) | — |
| Single-stream (no-think, 300 tok) | 43 t/s max | 47 t/s max | **~120 t/s** |
| **Concurrent N=16 (chaud)** | **376 t/s** | 213 t/s | **956 t/s** |
| Prefill 30K | 1 879 tok/s | 3 957 tok/s | 5 346–8 177 |
| Prefill 253K | 1 316 tok/s | 3 375 tok/s | ~4 300 |
| KV tokens | 342 691 (**1,31× fenêtre**) | 1 030 407 (3,93×) | idem |

### ⚠️ Le biais qui domine la lecture : la machine, encore

Les DEUX modèles sont aujourd'hui à ~1/3 de leurs références du 08-14 (3.6 : 47 vs ~120 single, 213 vs 956 N=16 ; 3.8 : 43 vs 84 Todd-sur-3090). suspect initial = training CoursIA sur GPU 2 (9,1 GiB, absent le 08-14)… **mais à la capture post-batterie le job est IDLE (210 MHz, 2 %, 32 W)** — contention affaiblie, pas exclue (état pendant la batterie inconnu). Nouveau point pour l'enquête machine ouverte : le 08-19 les deux stacks dégradent ENSEMBLE.

Ce que l'A/B d'aujourd'hui prouve quand même (mêmes conditions pour les deux) :
- **N=16 chaud : le dense 3.8+MTP a battu le MoE (376 vs 213)** — inimaginable à machine saine, mais c'est la mesure du jour. Le MTP aide le dense sous charge là où le MoE est étranglé par la machine.
- **Prefill : le MoE gagne nettement (×2,3–2,6)** — 3B actifs vs 27B, structurel. Pour les charges 253K, 193 s vs 75 s.
- **Latences fonctionnelles : le 3.8 gagne partout** (vision 2×, tools 3×, boot 2×).

### Verdict de fenêtre (provisoire — A/B contaminé par l'état machine)

1. **Remplacement immédiat : NON.** On ne remplace pas le MoE sur la base d'un jour où il est à 22 % de sa mesure de la semaine dernière ; ses chiffres sains (956 N=16, 120 single) restent la référence de capacité.
2. **Le 3.8 est un excellent candidat** — fonctionnellement supérieur (reasoning_effort, vidéo, latences), MTP validé (0,82), stable 17/17. À re-mesurer à machine saine (GPU 2 libre) pour des chiffres propres : single-stream vrai, N=16 vrai, et l'hypothèse group_size 32 vs 128 (43 vs 84 t/s Todd) mérite un quant GS-128.
3. **Le chemin qualité**: GSM8K/IFEval/MMStar sur le harness local — non exécutés ce jour (fenêtre), à programmer au prochain run.
4. **KV 1,31× est le vrai goulot structurel** pour « traces agentiques longues » : gpu-util ↑ (≈4,5 GiB libres/GPU) et/ou variante TQ (canary obligatoire).

## A/B relatif 4 variantes (2026-08-20, fenêtre ~18:30Z→, image overlay v0.27.1+#51812)

Méthode : verdict RELATIF sous bruit accepté (zoo/desktop/training = fond permanent,
décision user). Baseline 3.6-A sur la prod telle quelle avant le premier swap ;
bracket 3.6-B à la restauration pour mesurer la dérive du bruit pendant la fenêtre.
Banc : `ab_bench.py` (canary 3 prompts + acceptance + single 3×300 + N=16×200,
temp 0.7 no-think). ⚠️ noms de métriques v0.27.1 : `vllm:spec_decode_num_draft_tokens_total`
(pas "drafted") — corrigé dans le script, acceptance v1 relevée post-hoc.

| Variante | Image | KV dtype | MTP | Quant | single t/s | N=16 t/s | acceptance | canary |
|---|---|---|---|---|---|---|---|---|
| **3.6-A** (prod) | stock v0.27.1 | TQ k8v4 | — | 3.6 MoE GS-32 | 66/78/79 | **462** | — | PASS |
| **v1** | overlay #51812 | fp8 | 3 | cyankiwi GS-32 | 43/41/41 | 151 | 0,474 (2623/5532) | PASS |
| **v2** | overlay #51812 | fp8 | 8 | cyankiwi GS-32 | 21/24/24 | 124 | 0,22 (2970/13456) | PASS |
- v2 : l'avertissement vLLM se vérifie (« num_speculative_tokens > 1 → multiple forwards on same MTP layer → lower acceptance ») : MTP-8 divise l'acceptance par 2 (0,47→0,22) ET le single-stream par 2 (41→22). **Perte nette, éliminé.**
| **v3** | overlay #51812 | **turboquant_k8v4** | 3 | cyankiwi GS-32 | 30/68/36 | 93 | 0,89→0,10 | **FAIL (DEGENERATE)** |
- **v3 = dégénérescence CONFIRMÉE** : canary fr/code r4g 0,94-0,96 (répétition quasi totale). Échantillon temp-0 : « la diffusion de la diffusion de la diffusion » puis mur de « !!!! » — exactement le mode silencieux #40831/#40880 (TQ×MTP), **qui passe tous les health checks**. KV TQ 438 154 tok (+27 % vs fp8). **Verdict : TQ+MTP sur stock v0.27.1+#51812 = CASSÉ silencieusement — même avec le fix GDN gates #51812. Le canary qualité est le SEUL détecteur.** À remonter upstream (issue avec échantillon) une fois confirmé sur config pure stock.
| **v4** | overlay #51812 | fp8 | 3 | **philbert440 GS-128** | 33/23/38 | 138 | 0,79→0,47 | PASS |
- v4 : GS-128 ≈ GS-32 en single (23-38 vs 41-43), N=16 légèrement inférieur (138 vs 151), acceptance 1ᵉʳ passage meilleure (0,79 vs 0,47) mais cumulée identique. **L'hypothèse group_size (43 vs 84 t/s Todd-sur-3090) est ÉLIMINÉE** — le gap single-stream n'est pas la taille de groupe Marlin.
| **3.6-B** (prod) | stock v0.27.1 | TQ k8v4 | — | 3.6 MoE GS-32 | 98/94/91 | **844** | — | PASS |

## Verdict de la fenêtre (2026-08-20 ~18:33→19:27 locales)

1. **LE BRUIT DOMINE TOUT** : le bracket 3.6-A→3.6-B (même pile, même script, 1 h d'écart)
   montre **462 → 844 t/s N=16 (+83 %)** et 66-79 → 91-98 single. Toute comparaison
   3.8-vs-3.6 dans cette fenêtre est INVALIDE : les variantes 3.8 ont tourné dans le
   creux, le 3.6-B dans la remontée. **Leçon de méthode : à bruit fluctuant, seul un
   A-B-A-B intercalé (ou des moyennes longues) compare deux modèles ; un A/B
   séquentiel mesure le bruit.**
2. **DONNÉE MACHINE MAJEURE** : 844 t/s à 19:26 = ~88 % de la référence 08-14 (956).
   La régression machine n'est PAS permanente — elle est **fluctuante** (creux 18:33,
   sommet 19:26). L'enquête pivote : chercher ce qui charge l'hôte ~18:00-19:00
   (zoo ? training burst ? desktop ?) plutôt qu'une dégradation continue.
3. **TQ + MTP = DÉGÉNÉRÉ sur stock v0.27.1+#51812** (correct, indépendant du bruit) :
   canary FAIL r4g 0,94-0,96, échantillon temp-0 « la diffusion de la diffusion… » + mur
   de « ! ». Famille #40831/#40880 TOUJOURS vivante malgré le fix GDN gates. Passe
   tous les health checks → canary obligatoire. Pour l'issue upstream : reproduire
   d'abord sur stock PUR (sans l'overlay) pour écarter toute ambiguïté.
4. **MTP-8 ÉLIMINÉ** : acceptance 0,22 vs 0,47, single-stream divisé par 2 (v1/v2 à
   10 min d'écart, même conditions — cette comparaison intra-fenêtre tient).
5. **GS-128 ≈ GS-32** (v1/v4, acceptance cumulée 0,47 tous deux) : l'hypothèse
   group_size pour l'écart vs Todd (84 t/s sur 3090) est éliminée.
6. **Décision bascule : AUCUNE ce soir** — il faudra re-mesurer le 3.8 en intercalé
   avec le 3.6, ou à un moment de bruit stable. Le 3.6 reste en prod (restauré,
   watchdog relancé).

## Repro stock-pur (2026-08-20 21:14 locales) — TQ×MTP-3, image officielle v0.27.1 SANS overlay

**REPRODUIT** : canary code DEGENERATE r4g 0,92 (fr OK 513 ch cette fois — la dégénérescence
est intermittente par prompt, pas totale). Échantillon temp-0 (scratchpad
tq_mtp_degenerate_sample.txt) : `sum(range(1, 1, 1, 1, 1, ...` puis mur de « 1 ».
Acceptance 0,34-0,38, single 59-67, N=16 95. KV 440 027.

→ Le bug TQ×spec-dec est **upstream v0.27.1**, indépendant de #51812 (repro sans l'overlay).
Datapoint prêt pour issue : config exacte, échantillon, métriques, variabilité par prompt.

## A-B-A-B interleaved — B1 (3.8 fp8+MTP-3, overlay #51812) bench 2026-08-20 21:31Z
```
RESULT|B1-3.8|acceptance=0.787|acceptance_after_load=0.493|canary=PASS|single=27/23/25|n16=119
canary: fr OK (r4g 0.02), code OK (r4g 0.01), math OK
```
- Leg B1 between A1 (3.6: single 49/54/72, N=16 683) and pending A2.
- NB single 3.8 très bas (27 vs 43 la veille, ~90-110 attendus) → la machine fluctue encore (échantillonneur 2h actif). Seule l'intercalation compare.

## Incident fenêtre A-B-A-B — A2 boot raté 2× (2026-08-20 19:35Z→20:35Z), récupéré
- Symptôme : `up -d` 3.6 → RC=16 crash-loop, guard HF refuse (« largest blob 0 bytes »).
- **Cause racine = MA faute d'opérateur** : le swap a omis `--env-file myia_vllm/.env`.
  Sans lui `HF_CACHE_PATH` retombe sur le défaut `~/.cache/huggingface` (cache local
  CoursIA — datasets gsm8k/IFEval/sudoku visibles dans le conteneur), où le modèle 3.6
  n'existe pas. Le bind WSL n'était PAS en cause : l'UNC est resté joignable tout du long.
- **Le guard a fait exactement son travail** : sans lui, vLLM aurait re-téléchargé 19 GB
  dans le mauvais cache (le scénario phantom-download, déclenché par env manquant plutôt
  que par WSL). Fail-loud en ~3 min par tentative au lieu d'une heure de faux « boot patient ».
- Récupération : `compose down && compose up -d --env-file myia_vllm/.env` → guard PASS
  (blob 5,37 G), poids en chargement 20:37Z. A1 (3.6, lancé avant la fenêtre avec env
  correct) reste valide ; B1 valide ; A2 reprend à froid après ce délai.
- **Leçon** : tout swap de profil DOIT porter `--env-file myia_vllm/.env` — l'oubli ne
  fait pas échouer `up -d`, il substitue silencieusement le mauvais cache + efface les
  clés API. Le guard transforme ce piège en échec bruyant.

## A-B-A-B — A2 (3.6 prod) bench 2026-08-20 22:37Z (après incident récupéré)
```
RESULT|A2-3.6|canary=PASS|single=101/101/103|n16=872
```
- La machine a CHAUFFÉ entre les jambes : A1 N=16 683 (21:1xZ) → A2 872 (22:37Z), single 49-72 → 101-103.
  Confirme la fluctuation lente dominante — seule l'intercalation compare.
- État : A1 683 · B1 119 · A2 872 · B2 en boot.

## A-B-A-B — B2 (3.8 fp8+MTP-3) + bracket 3.6-B + SYNTHÈSE (2026-08-20 soir)
```
RESULT|B2-3.8|acceptance=0.748|acceptance_after_load=0.484|canary=PASS|single=48/45/33|n16=138   22:44 locales
RESULT|B-bracket-3.6|canary=PASS|single=103/102/100|n16=870                                   22:49 locales
```
⚠️ **Correction horodatages** : les entrées B1/A2 ci-dessus étiquetées « 21:31Z » / « 22:37Z »
sont en fait des heures LOCALES (le script `ab_bench.py` affiche datetime.now()).
Vrais instants : A1 ~19:14Z · B1 19:31Z · A2 20:37Z · B2 20:44Z · bracket 20:49Z (21:14→22:49 locales).

### Tableau intercalé (t/s, bruit identique par paire)
| Jambe | Pile | single (moy) | N=16 | acceptance |
|---|---|---|---|---|
| A1 (21:14 loc.) | 3.6 MoE TQ | 58,3 | **683** | — |
| B1 (21:31) | 3.8 fp8+MTP-3 | 25,0 | **119** | 0,79→0,49 |
| A2 (22:37) | 3.6 MoE TQ | 101,7 | **872** | — |
| B2 (22:44) | 3.8 fp8+MTP-3 | 42,0 | **138** | 0,75→0,48 |
| bracket (22:49) | 3.6 MoE TQ | 101,7 | **870** | — |

**Ratios appariés (le cœur de la méthode)** : N=16 → A1/B1 = **5,7×**, A2/B2 = **6,3×**.
Single → 2,33× / 2,42×. Le bruit a déplacé les deux modèles DANS LE MÊME SENS entre les
jambes (+28 % 3.6, +16 % 3.8) — le ratio ~6× tient partout. Verdict ROBUSTE au bruit.

### Verdict : PAS DE BASCULE
- 3.6-35B-A3B MoE reste prod, ~6× devant à N=16, ~2,4× en single, ×2,3–2,6 en prefill (08-19).
- 3.8-27B AWQ+MTP-3 = candidat **tier qualité** (SWE-bench Pro +8,2, Terminal Bench +9,6,
  DeepSWE +28,9 vs 3.6) PAS un candidat débit. Son créneau : complément GPU 2 (TP=1) si un
  jour on veut un tier qualité — mais KV TP=1 sur 24 Go serait très serré (poids ~14 Go) : non exploré.
- MTP acceptance **divise par ~1,6 sous charge** (0,75–0,79 → 0,48–0,49) — attendu (drafts
  rejetés en batch), à retenir pour toute projection de gain MTP multi-utilisateur.
- Machine : A1 683 → A2 872 (+28 %) entre les jambes — l'échantillonneur hôte (96 min,
  85 k lignes) montre GPU 2 à 0 % toute la fenêtre, et AUCUNE corrélation stable
  util/clocks/power ↔ débit (A2 a fait 872 t/s à ~70 W là où le bracket a fait 870 à ~110 W).
  La fluctuation n'est PAS visible dans la télémétrie GPU → côté hôte (CPU/PCIe/WDDM),
  capturée par aucun compteur de ce sampler. L'enquête machine reste ouverte là-dessus.

## Issue upstream postée (2026-08-21)
**[vllm#53180](https://github.com/vllm-project/vllm/issues/53180)** — « TurboQuant k8v4 + MTP silently produces degenerate output on hybrid GDN models (v0.27.1, stock) ». Repro stock-pur + discriminants (TQ seul OK / fp8+MTP OK / TQ+MTP FAIL / #51812 ne fixe pas) + échantillon tronqué. Vérifs pré-post : #40807 (open) = crash CUDA-graph, autre symptôme ; #40831/#40880 fermées SANS fix upstream — le SHA de fermeture de #40880 (`fc9a62534`) **n'existe pas dans vllm-project/vllm** (commit du repo aval Genesis), confirmant le statut « famille vivante en release ».
