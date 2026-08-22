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
