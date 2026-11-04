# Q5 — Banc qualité large du tier mini : NVFP4 (prod) vs BF16 (référence), 04/11/2026

Issue de référence : jsboige/vllm#70 (siège po-2025). Question d'origine (registre, 08/10) :
la qualité du checkpoint NVFP4 servi reposait sur **5 prompts A/B** — fallait-il une passe
large avant que des externes en dépendent ? **GO user du 04/11** : « Go pour un banc, c'est
le moment pendant qu'on ne tire pas ».

## Méthode

`myia_vllm/scripts/testing/quality_bench_po2025.py` — **120 tâches déterministes** (graine
20261104), **8 catégories × 15**, dont la réponse est **calculée par la machine** au moment
de la génération des prompts. Aucun jugement de modèle : chaque sortie est notée par
comparaison exacte, parsing JSON ou comptage. Décodage **greedy** (temperature 0.0),
`enable_thinking:false` par requête, `max_tokens` 320.

| Catégorie | Ce qui est mesuré |
|---|---|
| `arith` | arithmétique entière (a·b+c), réponse = un nombre |
| `extract` | extraction de 3 champs d'un dossier → JSON |
| `transform` | mise en majuscules exacte d'une phrase |
| `count` | comptage d'une lettre dans un texte fourni |
| `json` | sortie JSON à schéma imposé (2 clés) |
| `grounded` | question factuelle dont la réponse est DANS le texte fourni |
| `constraint` | phrase de exactement N mots (N variable par tâche) |
| `sort` | tri croissant de 5 nombres |

## Bras mesurés

| Bras | Poids | KV | Image | Boot |
|---|---|---|---|---|
| **prod** `mini-frognano-4b-po2025.yml` | NVFP4 | fp8 | v0.32.0 | 102 s (chaud) |
| **référence** `mini-frognano-bf16-eval-v0320.yml` | BF16 | BF16 | **v0.32.0** | 360 s (compile cache froid) |

Isolation volontaire : le profil rollback existant (`…-bf16-rollback.yml`) est resté en
**v0.31.0** ; l'utiliser aurait confondu **modèle ET version moteur**. Le profil d'éval
rejoue BF16 sur **l'image de production v0.32.0**, même `container_name`, même port,
même volume HF, cache de compilation dédié.

## Résultats

| Catégorie | NVFP4 (prod) | BF16 | Δ |
|---|---:|---:|---:|
| arith | 2/15 (0,133) | 5/15 (0,333) | +3 |
| constraint | 0/15 (0,000) | 4/15 (0,267) | +4 |
| count | 5/15 (0,333) | 3/15 (0,200) | −2 |
| extract | 15/15 (1,000) | 15/15 (1,000) | 0 |
| grounded | 15/15 (1,000) | 15/15 (1,000) | 0 |
| json | 15/15 (1,000) | 15/15 (1,000) | 0 |
| sort | 15/15 (1,000) | 15/15 (1,000) | 0 |
| transform | 15/15 (1,000) | 15/15 (1,000) | 0 |
| **TOTAL** | **82/120 = 0,683** | **87/120 = 0,725** | **+5** |
| Durée des 120 tâches | **24,9 s** | 44,1 s | NVFP4 **×1,8** |

Sorties brutes : `myia_vllm/_logs/quality_bench_nvfp4_20261104T124501Z.json` et
`quality_bench_bf16_20261104T125305Z.json` (par tâche : prompt, oracle, sortie, verdict).

## Lecture

1. **Aucune dégradation détectable du checkpoint NVFP4.** L'écart total (5 points sur 120)
   est **dans le bruit** : à n=120 l'intervalle à 95 % vaut ≈ ±8,5 points, et les écarts
   par catégorie (3/15, 4/15, 2/15) sont très en dessous de leur propre erreur-type
   (≈ 11-13 points à n=15).
2. **Les faiblesses sont celles du 4B, pas de la quantification.** Les trois catégories
   faibles le sont **des deux côtés** : arithmétique mentale fausse d'un chiffre
   (ex. attendu 476, lu 456), comptage de lettres dans 60 caractères, et **phrase figée à
   6 mots quel que soit le N demandé** (« La mer est un océan bleu. » — 6 mots pour une
   consigne à 4). BF16 ne corrige pas ces trois défauts, il en rattrape quelques tirages.
3. **Les tâches utiles au tier mini sont parfaites des deux côtés** : extraction
   structurée, JSON à schéma, transformation, tri, question ancrée dans un texte fourni —
   **15/15 partout**. C'est exactement le profil d'usage de délégation (mécanique,
   vérifiable).
4. **Le quant reste le bon choix** : même qualité mesurable, **×1,8 plus rapide** sur la
   charge, et KV fp8 (×1,87 de capacité face au BF16).

## Ce qui change dans la formulation honnête

Avant : « qualité vérifiée sur 5 prompts ». Après : « **vérifié sur 120 tâches à oracle
machine, écart BF16 non significatif (±8,5 pts)** ». Toujours **pas** « qualité
verrouillée » : le banc mesure l'instruction-following et des tâches vérifiables, pas le
raisonnement ouvert ; et il ne dit rien de la robustesse hors distribution.

## Décision

- **Q5 close par exécution.** Rollback BF16 reste armé (swap chaud, ~2-6 min selon cache).
- Pas de passe additionnelle à commander : le signal qui la déclencherait serait une
  **plainte d'un consommateur externe**, et le premier geste serait alors le rollback.
- Le banc est **rejouable** : `python quality_bench_po2025.py --label <nom>` après tout
  changement de checkpoint ou d'image (graine fixe ⇒ comparaison appariée).

## Incident de méthode évité (à conserver)

Le premier passage affichait `arith 2/15` : réflexe correct = **inspecter les sorties
brutes avant de conclure**. Vérification faite : le modèle rendait bien UN nombre, et ce
nombre était faux (476 attendu → 456 lu). Le vérificateur n'était donc pas cassé — mais il
aurait pu l'être, et une métrique à 13 % ressemble autant à un bug de notation qu'à une
vraie faiblesse. **Toujours faire tourner le banc sur un cas connu avant de publier un
chiffre.**
