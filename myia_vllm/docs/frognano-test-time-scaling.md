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

## Deuxième protocole (03/11, mandat user) — critique à persona vs directeur

Le user a proposé deux architectures : **(A)** un FrogNano au prompt système crafté pour
critiquer le travail des autres, **(B)** un agent tiers (Haiku/Minimax/Swift) qui **dirige**
une équipe de FrogNano en pointant leurs erreurs, dépense peu et leur fait dépenser beaucoup.

**Corpus durci d'abord** (sinon il n'y a rien à réparer : la liste était parfaite 3/3 sur
22 lignes). Journal gouverneur, **120 lignes**, motif `temp=31C`, **oracle `grep` = 42**, dont
**3 `WARN`** = piège motif-vs-forme.

### Producteur seul (référence) — FrogNano, liste verbatim

**40/42, 0 fabrication.** Les **2 seules lignes manquées sont les 2 `WARN RAM basse`**
(02/11 04:02 et 03/11 02:12) — et la première **partage son horodatage avec un `HEARTBEAT`
qu'il a bien listé**. Le mode d'échec est le piège motif-vs-forme, pas du bruit : il perd la
ligne quand la forme attendue (`HEARTBEAT`) est satisfaite par une voisine.

### A. Critique à persona — FrogNano + system prompt « CRITIQUE SÉVÈRE »

Mission : rendre les lignes du journal absentes de la liste. **10 lignes rendues :**

| Catégorie | Nombre | Détail |
|---|---|---|
| **Fabrications** (absentes du journal) | **7** | ex. `2026-10-30 09:02:02 HEARTBEAT temp=31C free=15037MB` — dans le journal cette ligne est `temp=54C` |
| Faux positifs (déjà dans la liste) | 2 | `23:02:02 …14808MB`, `09:02:02 …7371MB` |
| **Vrais positifs** | **1** | la `WARN` du 04:02 |

**Recall 1/2, précision 10 %.** Le persona n'aide pas : il **complète le motif de tête**. Un
critique qui ne peut pas exécuter la vérification **invente** au lieu de vérifier — et il
l'invente avec une confiance parfaite, ce qui est pire que l'omission du producteur.

### B. Directeur — `swift-delegator` (Swift-1.5-27B, garde le jugement, délègue au mini)

Le preset existe déjà côté sk-agent et correspond exactement à l'architecture user. Mission
donnée : produire les 2 lignes manquantes **avec preuve mécanique**, par un agent mini outillé
(`open_terminal`). **Résultat : `call_agent` a timeout à 300 s** sur cette mission (journal 120
lignes + liste 40 lignes). **Aucun résultat exploitable ⇒ NON CONCLUANT, pas concluant à
l'échec.** Signal opérationnel en soi : la boucle de délégation dépasse 5 min sur une tâche
d'audit de cette taille — à réinstrumenter (mission plus courte, ou budget de tours explicite)
avant d'en tirer quoi que ce soit.

### Ce que ça change pour l'architecture

1. **Le persona n'est pas le levier ; l'outil l'est.** La différence entre A et un critique
   fiable n'est pas la sévérité du prompt mais le fait de pouvoir **exécuter** `grep`/`comm`.
   Sans exécution, le critique fabrique — 7 inventions mesurées.
2. **Le producteur reste fiable sur la liste** (40/42, 0 fabrication) : la réparation utile
   n'est pas « un avis sur la réponse » mais **un diff contre l'oracle**. C'est une opération
   mécanique, donc du ressort de l'appelant, pas d'un agent.
3. **Forme à retenir pour B** : le directeur doit ordonner une **exécution** (« fais tourner
   `grep -c`, rends la sortie »), jamais une **relecture** (« regarde ces deux listes ») — la
   relecture est exactement ce que A a raté.

Voir aussi : `frognano-team-solve.md` (l'assemblée à personas et les portes mécaniques),
`frognano-conversational-mode.md` (le transport conversationnel et ses limites),
`frognano-capacity-sheet.md` (le moteur).

---

## Troisième protocole (03/11, mandat user) — directeur **non-swift** : RÉUSSITE, et il corrige ma doctrine

Le user a demandé de reprendre l'architecture B avec **un autre modèle que Swift** (« explicitement
saturé par des contextes longs, prévoir au moins 400 s »), via Minimax ou Haiku PAYG. Test exécuté
avec `critic` (preset sk-agent, hub, **`timeout=420`**), sur le corpus-piège de 22 lignes — celui qui
contient la ligne `WARN` que **tous** les producteurs ratent.

### Montage

Un seul appel, trois blocs dans le contexte du directeur : le journal source (22 lignes), la
production de **LFM3-1.7B** (41 lignes, dont 27 de délibération), la production de **FrogNano-4B**
(13 lignes propres). Consigne : auditer chaque production, désigner la plus fiable, **rendre la
liste correcte**.

### Résultat — le premier 14/14 du siège

| Architecture | Corpus-piège 22 lignes | Bruit |
|---|---|---|
| FrogNano seul | 13/14 | 0 |
| LFM3 seul | 13/14 | **27 lignes de délibération** |
| Critique à persona sur FrogNano (matin 03/11) | rappel 1/2 | **7 fabrications / 10 lignes** |
| **Directeur fort (cloud, 420 s)** | **14/14, correspondance exacte d'ensemble** | **0** |

Vérifié **mécaniquement** après coup, pas sur parole : `set(rendu) == set(oracle)`, 0 manquante,
0 en trop, toutes les lignes issues du corpus. **C'est la première fois qu'une configuration de ce
siège résout intégralement le piège motif-vs-forme.**

L'audit qu'il a rendu est lui aussi juste, y compris le point que personne n'avait vu :

> « Total attendu : 14 lignes — 13 HEARTBEAT + 1 ligne WARN `2026-11-03 02:12:03 WARN RAM basse
> free=3824MB temp=31C mode=normal`, où `temp=31C` n'est pas en 3e champ — **c'est le piège**. »
> « Sous un contrat "verbatim, rien d'autre", **la contamination est plus grave que l'omission** :
> P1 est inexploitable en l'état, P2 est incomplète mais utilisable après ajout d'une ligne. »

### ⚠ Correction de ma propre doctrine (point 3 du protocole précédent)

J'avais écrit : *« le directeur doit ordonner une **exécution** (`grep`/`comm`), jamais une
**relecture** — la relecture est exactement ce que A a raté. »* **Ce test la falsifie en partie.**
Le directeur a réussi en **pure relecture, sans exécuter un seul outil** : les trois blocs étaient
dans son contexte, il a scanné. La règle correcte est plus étroite :

> **Le levier n'est pas l'outil, c'est la capacité de vérifier.** Un modèle **faible** à qui on
> demande de relire fabrique (mesuré : 7 inventions sur 10 lignes) — il lui faut une exécution
> déléguée. Un modèle **fort** disposant du corpus entier dans son contexte relit correctement,
> sans outil. C'est la **force du modèle** qui rend la relecture fiable, pas la forme de la
> consigne.

Corollaire opérationnel : **le directeur doit être d'un tier supérieur au producteur**, et il doit
**recevoir la source**, pas seulement les productions à comparer. Les deux conditions sont
nécessaires ; l'outillage n'est qu'un substitut quand l'une des deux manque.

### Caveat honnête sur le modèle réellement servi

`model_used` renvoie `glm-5.3`, mais le directeur **s'est identifié lui-même comme DeepSeek Flash
(`ds@deepseek-flash`)** dans sa réponse — cohérent avec la cascade de failover active ce jour
(le rôle `sonnet` était précisément servi par DeepSeek Flash). **RAPPORTÉ par le modèle, pas
VERIFIÉ indépendamment.** Ce qui est VERIFIÉ, c'est le résultat (14/14 mécanique). Pour la
décision d'architecture, la distinction est secondaire : dans les deux cas c'est un **modèle
cloud d'un tier supérieur au producteur**, ce que le user demandait (« autre chose que Swift »).

### Non testé, et pourquoi

**L'échelle.** Le corpus de 120 lignes n'a pas été passé au directeur : cela exigeait de
re-transcrire 7,4 K caractères de journal dans l'appel, avec un risque réel d'erreur de
transcription qui aurait faussé la mesure. **Non mesuré ≠ mesuré négatif** — c'est le prochain
test à faire, et il demande un canal fichier vers sk-agent (les attachments refusent le texte).

### Ce que ça change dans la pratique du siège

1. **La délégation à deux étages devient défendable** : FrogNano produit vite et proprement
   (13/14, 0 bruit), un directeur cloud relit et rend 14/14. Coût : ~5,5 K caractères de prompt
   pour le directeur, quelques centaines de tokens de sortie — FrogNano fait le gros du travail.
2. **La porte mécanique reste obligatoire**, mais elle change de rôle : elle n'est plus le seul
   filet, elle devient le **juge final** qui vérifie le directeur lui-même. Un directeur fort
   n'est pas infaillible — il est simplement bien meilleur sur le motif-vs-forme.
3. **Ne jamais accepter le 14/14 sur parole** : je l'ai recompté contre l'oracle. C'est la règle
   du siège appliquée au directeur aussi.

