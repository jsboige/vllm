# Ornith-1.5-35B-A3B — éval consolidation (2026-08-22)

**Hypothèse** : Ornith-1.5 = fine-tune de notre châssis exact (Qwen3_5MoeForConditionalGeneration,
30 GDN + 10 attn, 256 experts/8, vocab 248 320, 262K, vision 27 couches, MIT) → candidat
« consolidation » : qualité ≈ 3.8-27B (SWE Pro 59,6 vs 61,7, TB 68,5 vs 73,0) AU débit 3.6 (même MoE).
Benchs vendor vs notre 3.6 exact : SWE-V 79/73,4 · SWE Pro 59,6/49,5 · TB-CC 68,5/49,2 · NL2Repo 46,2/29,4 · GPQA +3,2.

**Quant** : `ulkaa/Ornith-1.5-35B-A3B-AWQ-INT4` (08-21) — compressed-tensors pack-quantized W4A16
GS-32 **asym**, experts quantisés (0 ignorés → Marlin MoE), 120 in_proj GDN + 110 visual en BF16.
Même famille de recette que cyankiwi 3.6 prod. Le bloqueur Ornith-1.0 (asym rejeté par le loader)
n'existe plus : sur v0.27.1 le chemin Marlin WNA16 supporte asym (`may_have_zp=not symmetric`,
registres zp alloués) — vérifié dans le code, à confirmer au boot réel.

## Leçons Ornith-1.0 (2026-07-02, rejet après ~7 h prod) — gates obligatoires
1. `/no_think` IGNORÉ (3.6 l'honore) → canary. 2. Sur-pensée 3-5K chars sur trivial → canary
trivial_think_len. 3. IFEval −3,3 / MMStar −4,7 (base 3.5) → le 1.5 est sur châssis 3.6, à re-mesurer.
4. Template sans preserve_thinking → flag DROPPÉ du profil ; audit template si adoption.

## Calibration des niveaux de pensée (décision user 08-22)
Post-adoption si validée : itérations empiriques pour un réglage « pense juste ce qu'il faut » —
longueur de raisonnement sur tâches triviales/standard, défaut enable_thinking par créneau d'usage,
éventuellement reasoning_effort si le template l'expose. Objectif : efficacité sans sur-pensée.

## Méthode burst (contrainte user : ne pas perturber l'usage)
Chaque burst ≤ ~90 s, gaps ≥ 2 min entre bursts — le trafic réel s'écoule entre eux. Unité de
comparaison = le burst individuel, bracketé par des bursts 3.6 avant/après (méthode A-B-A-B
validée 08-20 : seule l'intercalation compare à machine fluctuante). Noter l'uptime hôte à chaque
jambe (enquête machine : débit corrélé à l'uptime, réf 894/941 t/s à ~75 min post-reboot).

## Séquence fenêtre (GO user 08-22 « dès que tu peux »)
1. [pré] Pré-download ulkaa (~21 GB, cache HF WSL, imbriqué hub/hub comme le reste).
2. [pré] Baseline 3.6 : canary + 2×single + 2×n16 bursts.
3. Swap 3.6 down → Ornith up (TOUJOURS --env-file myia_vllm/.env — incident 08-20).
   Boot ~8-15 min (compile vierge probable : nouveau vocab 248 320 → nouveau volume compile cache).
4. Ornith : canary comportemental d'abord (gate go/no-go), puis 2×single, 2×n16, 2×think.
5. Restore 3.6 + watchdog → bracket 3.6 (1×n16, 1×single).
6. Verdict aux seuils 1.0 : IFEval/MMStar pas de régression >1 pt (batterie qualité séparée si
   les gates comportementales passent), /no_think propre, débit ±5 % vs bursts 3.6 appariés.

## Résultats

(baseline 3.6 + jambes Ornith à consigner ci-dessous)

## Fenêtre 08-22 (démarrage)
- **Leçon predownload** : le cache HF WSL est monté en HF_HOME (`\wsl...\huggingface\hub` → `/root/.cache/huggingface`), donc les modèles vivent dans `hub/hub/models--*` (imbriqué). Le predownload docker run doit monter l'UNC sur `/root/.cache/huggingface/hub` PUIS le dossier résultant doit être déplacé dans `hub/hub/` (UNC rename refusé → `wsl -d Ubuntu -u root -- mv`, fichiers détenus par root). Le guard a validé le déplacement au vol (blob 20,0 Go détecté à l'itération suivante).
- Baseline 3.6 (machine LENTE, ~8h uptime — cf enquête) : canary 4/5 (no_think échoue aussi sur 3.6 → gate relative), single 64/47, n16 424/237.

## Fenêtre 08-22 — RÉSULTATS Ornith-1.5 (ulkaa AWQ-INT4, stock v0.27.1 + TQ k8v4)
**Boot : PARFAIT.** MarlinExperts actif, TQ hybrid détecté (couches full-attn [3,7,...,39] = pattern 3.6 exact), poids 11,52 GiB/GPU, **KV 1 009 643 tok** (3.6 : 1 030 407, −2 %), boot ~12 min. La théorie Marlin-asym confirmée au réel.

| Gate | Ornith-1.5 | 3.6 baseline | Verdict |
|---|---|---|---|
| fr-prose | r4g 0,00, 540 ch | r4g 0,00, 641 ch | OK |
| enable_thinking:false | reason=0 | reason=0 | OK |
| **trivial_think_len** | **219 ch** | 683 ch | **OK — tueur 1.0 GUÉRI** |
| /no_think | 347 ch | 932 ch | même comportement des 2 — gate relative OK |
| tool_call (qwen3_coder) | 0,42 s | 0,57 s | OK |
| single t/s | **83/96/93 · 69/70/71** | 64/… · 47/… | **Ornith devant** |
| n16 t/s | 159 (warm-up) · 552 · **763** | 424 · 237 (phase lente) | paire à l'état rapide : 763 vs bracket 3.6 à venir |
| think | 889ch@78 · 445ch@77 t/s | — | raisonnement court, débit sain |

- Machine fluctuante pendant toute la fenêtre (3.6 424/237 en phase lente → Ornith 763 quand elle est remontée) : le bracket 3.6 post-restore donnera la paire à l'état courant.

## Fenêtre 08-22 — BRACKET + VERDICT + dataclé enquête machine
```
RESULT|bracket-3.6|n16|621/652 t/s|single|88/97/97    (état machine rapide)
```
**Verdict Ornith-1.5 (phase 1, comportement + débit) : DÉGAGEMENT TOUT VERT.**
- Paire à état machine comparable : Ornith n16 552/763 vs 3.6 621/652 → **ratio ~1:1** (mêmes MoE/châssis, comme prédit). Single : Ornith 83-96/69-71 vs 3.6 88-97/64-47 → parité à léger avantage Ornith.
- Les 3 tueurs du 1.0 sont guéris : trivial_think 219 ch (vs 3-5K), enable_thinking:false reason=0, tool call 0,42 s.
- KV 1 009 643 (−2 % vs 3.6), boot 12 min, MarlinExperts + TQ k8v4 hybrid OK.
- Reste avant adoption : batterie qualité (IFEval/MMStar/GSM8K — les vrais motifs du rejet 1.0), audit template preserve_thinking, calibration pensée (itérations empiriques, décision user).

## Phase 2 (08-22 soir) — BATTERIE QUALITÉ : VERDICT REJET

Méthode : harness `lmms_quality.py`, 300 premiers échantillons (déterministe, `enable_thinking:False`),
scoring **apparié par index** contre le full-run 3.6 sur les mêmes 300 index + test exact de McNemar
sur les paires discordantes (script scratchpad `paired_score.py`).

| Bench (n=300 apparié) | Ornith-1.5 | 3.6 (mêmes index) | Δ | McNemar |
|---|---|---|---|---|
| GSM8K | 80,3 % | 88,0 % | **−7,7 pts** | chi2=13,1 **SIGNIF** |
| IFEval strict | 80,7 % | 88,7 % | **−8,0 pts** | chi2=12,6 **SIGNIF** |
| MMStar | 61,0 % | 63,7 % | −2,7 pts | chi2=1,3 ns |

(Brut vs full-run 3.6 : 80,3/87,6 · 80,7/87,6 · 61,0/55,7 — le 61 vs 55,7 brut est un artefact
de sous-ensemble ; l'apparié dit −2,7 ns, vision préservée.)

**VERDICT : PAS D'ADOPTION.** GSM8K et IFEval régressent de ~8 points, significativement —
le seuil 1.0 (« pas de régression > 1 pt ») est pulvérisé sur 2 des 3 batteries. Ornith-1.5
répète le profil du 1.0 : un fine-tune coding/agentic (SWE/TB/NL2Repo en hausse côté vendor)
qui paie la qualité générale math + instruction-following. Le débit ~1:1 et les tueurs guéris
(phase 1) ne compensent pas. **Ce n'est pas le lot de consolidation.**

Prod 3.6 restaurée dans la foulée (même fenêtre).

## Audit template (phase 2, sans swap)
- `preserve_thinking` : **0 occurrence** — mais **équivalent natif** : le template ré-injecte
  `message.reasoning_content` (champ standard que vLLM remplit via le parser qwen3) dans le bloc
  `<think>` de l'historique (lignes 91-100). Rétention multi-tours OK pour tout client qui renvoie
  le champ. Le flag droppé du profil était la bonne décision (il aurait été ignoré).
- `enable_thinking` : standard Qwen3 (`false` pré-remplit `<think>\n\n</think>`), validé phase 1.
- `reasoning_effort` : absent — la calibration pensée aurait été binaire + prompt. Sans objet
  (rejet).

## DATACLÉ ENQUÊTE MACHINE (collecteur hôte pendant la fenêtre)
| Phase (locales) | Débit N=16 | CPU hôte | Note |
|---|---|---|---|
| 20:10-20:22 3.6 baseline | 424 / 237 | **91 % (29,1/32)** | LENTE |
| 20:25-20:48 Ornith | 552 → 763 | **66 % (21,0/32)** | RAPIDE |
| 20:50+ 3.6 bracket | 621 / 652 | (fin de capture) | RAPIDE |
→ **CORRÉLATION DIRECTE CPU hôte ↔ débit**. `NCCL_P2P_DISABLE=1` ⇒ allreduce TP par mémoire hôte ⇒ CPU saturé = steps affamés = débit écroulé SANS signature GPU (toutes les mesures nvidia-smi restaient normales). La corrélation uptime s'explique : la charge de fond (docker.backend 2,3 cœurs visibles, node, desktop) s'accumule avec l'uptime jusqu'à saturation. **Fix à évaluer : ré-armer P2P (le désactiver datait de contraintes PCIe/précédents), ou borner la charge de fond, ou reboot programmé.**
