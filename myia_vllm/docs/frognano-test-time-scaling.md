# Test-time scaling sur FrogNano-4B — le vote échoue, la liste gagne (mesuré le 03/11/2026)

Mandat user 03/11 matin : « utiliser sk-agent pour monter en fiabilité en test-time scaling ».
Réponse mesurée en 8 appels (~20 K tokens, moteur oisif) : **la voie standard du test-time
scaling (self-consistency / vote majoritaire sur la réponse) ÉCHOUE sur ce modèle — et la voie
qui marche ne coûte pas plus cher qu'un appel.**

## L'expérience

Corpus figé avant l'appel : 22 lignes du journal gouverneur (`tail -22`, 2026-11-02 12:02 →
2026-11-03 08:02), mission « lignes contenant `temp=31C` », oracle `grep` = **14**. Le corpus
porte un piège motif-vs-forme : la ligne `WARN RAM basse … temp=31C` (02:12:03) **contient le
motif** sans avoir la forme `HEARTBEAT` — filtrer par la forme la rate.

Deux protocoles indépendants, appels one-shot sans conversation (`mini-summarizer`,
`model_used=frognano-4b` contrôlé sur chaque réponse) :

### A. Self-consistency ×5 sur le NOMBRE (la recette standard)

« Compte les lignes contenant `temp=31C`. Réponds le nombre seul. » × 5 appels indépendants :

| Vote | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Rendu | 13 | 13 | 13 | 12 | 12 |

**Majorité = 13, oracle = 14. ÉCHEC.** Et l'échec est instructif : les cinq votes sont
**corrélés** (13×3 puis 12×2 — jamais 14, jamais dispersés autour de 14). L'erreur de comptage
n'est **pas un bruit stochastique** qu'une moyenne lisse, c'est un **biais systématique** du
modèle sur cette tâche. Le vote multiplie le coût par 5 et **reproduit fidèlement l'erreur**.

### B. Liste verbatim ×3, recompte MÉCANIQUE (la recette assemblée)

« Liste VERBATIM les lignes contenant `temp=31C`. » × 3 appels indépendants :

- **3/3 rendus identiques entre eux**, et **identiques à l'oracle `grep`** : 14/14 lignes,
  ordre du journal respecté, au caractère près ;
- **le piège est discriminé 3/3** : la ligne `WARN … temp=31C` est présente, aucune ligne
  `HEARTBEAT temp=30C/32C` n'est là ;
- le recompte se fait chez l'appelant (`wc -l` sur le rendu) : **14, exact**.

Ici le best-of-3 n'a même pas été nécessaire — chaque run était déjà parfait. La redondance
coûteuse n'apporte rien quand la tâche est **dans la classe servie** ; elle n'aurait rien sauvé
non plus si la classe était refusée (cf. A : 5 essais, 5 erreurs).

## La règle qui en sort

**La fiabilité test-time de ce modèle vient de la FORME de la tâche, pas du nombre
d'échantillons.**

1. Une tâche rendue **vérifiable mécaniquement** (liste = sous-ensemble exact d'un corpus figé)
   est fiable à 1× — et si on veut une assurance, la redondance sur la **liste** se vérifie par
   `diff` entre runs (3/3 identiques ici).
2. Une tâche rendue **non vérifiable** (un nombre, un verdict, un jugement) ne devient PAS
   fiable en votant : l'erreur est systématique, le vote l'amplifie en fausse confiance
   (« 3 runs d'accord » sur une réponse fausse).
3. **Ne jamais transformer une tâche comptable en question de comptage** pour pouvoir voter
   dessus. Toujours : modèle = liste, machine = compte. C'est la même frontière que
   [[reference-mini-counting-frontier]] et l'assemblée team-solve, maintenant mesurée **contre
   le vote majoritaire**.

## Ce que ça ouvre pour l'adoption (l'argument pour les lanes)

Le discours « le mini est peu fiable, multipliez les essais » est **faux et coûteux**. Le bon
discours, mesuré : **donnez-lui des tâches en forme de liste sur corpus figé, vérifiez par
`diff`/`comm` contre un oracle mécanique — à ce prix vous obtenez 14/14 au caractère près,
pièges inclus, pour ~1,5 K tokens.** La garde est une ligne de `diff`, pas un panel de votes.

Corpus et rendus conservés : `.tmp/tts_corpus22.txt`, `.tmp/tts_oracle.txt`, `.tmp/tts_list1.txt`
(runs 2 et 3 identiques au run 1). Compteurs du cycle : `{stop}` 26→34 (8 appels), 0 erreur.

Voir aussi : `frognano-team-solve.md` (l'assemblée à personas et les portes mécaniques),
`frognano-conversational-mode.md` (le transport conversationnel et ses limites),
`frognano-capacity-sheet.md` (le moteur).
