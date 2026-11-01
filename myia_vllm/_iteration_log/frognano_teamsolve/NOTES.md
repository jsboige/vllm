# FrogNano team-solve : assemblée de spécialistes + portes mécaniques (01/11 2026)

**Question posée par le user** (01/11 soir) : sk-agent a été conçu avec un mode conversationnel
pour du test-time scaling par assemblée de spécialistes capables de se contredire (cf. harnais
CoursIA) ; du bruit Reddit court sur
[memdoor/examples/workflows/team-solve](https://github.com/guregodevo/memdoor/tree/main/examples/workflows/team-solve).
Peut-on concevoir un workflow agentique qui **augmente la fiabilité** du modèle et **augmente la
couverture** de ce qu'il peut servir ?

Recette durable : `myia_vllm/docs/frognano-team-solve.md`. Ce fichier est le record de la
mesure. Tout s'est passé sur le siège po-2025 (:5003, FrogNano-4B-2609 NVFP4 + KV fp8, v0.32.0),
via `mcp__sk-agent__call_agent`, preset `mini-summarizer`, `model_used: frognano-4b` contrôlé
sur CHAQUE réponse (aucun `fallback_from`).

## 0. Ce que memdoor/team-solve apporte comme grain

Le workflow (méthode GVS5H, Lee 2026) : 5 petits modèles — planificateur, 2 idéateurs en
parallèle (familles algorithmiques distinctes), solveur, manager + réparateur. Chaque agent
part d'un **contexte frais** et ne communique **que par fichiers** ; « un script qui exécute les
samples décide du succès, pas un modèle ». Résultat affiché : 9,8/10 vs 8,0 pour le même modèle
en un appel (LiveCodeBench Hard, 10 problèmes × 5 passes), avec une honnêteté rare (parité avec
le harnais des auteurs, contamination non exclue, n petit).

Deux points nous concernent directement :

1. **Le gain ne vient pas du débat, mais de la décomposition** : chaque étape reste dans la
   compétence du modèle, et le verdict appartient à une **commande mécanique**.
2. Les auteurs créditent la **discipline de registre** (contextes frais, passage par fichiers)
   plutôt que le chat — c'est le contre-pied exact du « mode conversationnel » intuitif, et il
   recoupe notre règle flotte « le mini ne verdict jamais ».

## 1. Protocole

Corpus **figé** (règle des 24e/31e mesures : l'oracle porte sur le corpus transmis, jamais sur
une source vivante) : `.tmp/ts_corpus.txt`, `tail -32` de `_logs/gpu-governor.log`, fenêtre
31/10 16:02 → 01/11 19:02 locale. Composition vérifiée : **28 HEARTBEAT + 4 WARN = 32**, toutes
les lignes portent `free=<N>MB`.

Oracles (calculés AVANT tout appel, par l'appelant) :

| Question | Oracle |
|---|---|
| E1 — nombre de lignes `WARN` | **4** |
| E2 — lignes avec `free` < 2000 Mo | **1** (06:22:03, `free=1128MB`) ; min du corpus 1128 |
| E3 — nombres d'un paragraphe technique FR | 20 nombres (multiset) |

Trois classes choisies parce qu'elles sont **refusées en mono-appel** (§1 de
`frognano-fanout-delegation.md`) : comptage (échecs dès 6 lignes), seuil sur valeur de champ
(1/4 + 19 FP, 20e mesure), réécriture/traduction (non calibrée).

## 2. Baselines mono-appel (les classes refusées échouent comme prédit)

| Exp | Question posée telle quelle | Réponse du mini | Oracle | Verdict |
|---|---|---|---|---|
| E1a | « combien de lignes contiennent WARN ? (nombre seul) » | **3** | 4 | ÉCHEC (sous-comptage, conforme à la frontière) |
| E2a | « free est-il descendu sous 2000 Mo ? OUI/NON puis cite » | **NON** … en citant la ligne `free=1128MB` | OUI, 1 ligne | ÉCHEC **le verdict contredit sa propre preuve** — reproduit le mode de la 20e mesure : il trouve la ligne, il ne compare pas le nombre |

## 3. L'assemblée — deux extracteurs à personas distinctes + portes mécaniques

Deux appels parallèles, personas par `system_prompt` (Contrôleur d'alertes : spécialiste WARN ;
Régistraire des mesures : spécialiste HEARTBEAT, « ton collègue s'occupe des WARN »), mission =
recette R1 verbatim mono-motif. Les motifs {WARN, HEARTBEAT} **partitionnent** le corpus — c'est
le cœur du design.

**Portes mécaniques (exécutées par l'appelant, jamais par le mini)** :

| Porte | Contrôle | Résultat |
|---|---|---|
| P1 précision | chaque ligne rendue ∈ source | **0/0 fabrication** (A et B) |
| P2a disjoint | A ∩ B = ∅ | **0** |
| P2b partition | \|A\| + \|B\| = 32 = \|corpus\|, union unique 32 | **4 + 28 = 32 ✓** |
| P2c couverture | lignes du corpus absentes de l'union | **0** |

**Verdicts dérivés (par l'appelant, sur lignes vérifiées)** :

- **E1 : WARN = 4 — PROUVÉ, pas deviné.** La partition exacte + la précision exacte ferment le
  rappel : aucune ligne n'a pu être ni ajoutée ni perdue ni comptée deux fois. Le compte n'est
  plus une statistique, c'est un théorème.
- **E2 : OUI, 1 ligne (`free=1128MB`), min = 1128 — PROUVÉ, scan exhaustif 32/32** (tous les
  `free=` parsés depuis l'union vérifiée). La comparaison numérique, refusée au modèle, est une
  regex côté appelant.

## 4. E3 — réécriture (traduction FR→EN) derrière une porte de fidélité

Producteur : persona Traducteur technique (« chaque nombre doit se retrouver exactement »).
Porte de fidélité **mécanique pure** (regex appelant — pourquoi déléguer une vérification qu'une
regex fait exactement ?) : extraction des nombres des deux côtés, normalisation des séparateurs
(espace/virgule FR ↔ virgule/point EN), diff multiset.

**Résultat : 20/20 nombres identiques** — traduction SERVIE. Limite notée de la porte v1 : la
normalisation retire tous les séparateurs, donc elle prouve la conservation des chiffres, pas
des magnitudes décimales (74,9 vs 7,49 ne seraient pas distingués) — suffisant pour la classe
« traduction technique fidèle », à durcir si le cas d'usage exige les décimales.

## 5. Le contradicteur — la mesure la plus instructive de la session

Persona Avocat du diable (« ta seule arme est la preuve par extraction »), à qui on donne
l'affirmation fausse « exactement 3 lignes WARN » et la consigne de réfuter par citations.

**Ce qu'il a rendu** : les 4 lignes WARN verbatim correctes, et la réfutation finale correcte
(la 4e ligne contredit « 3 »). **Mais en racontant son propre verdict faux en route** : « Le
compte réel est de 5 lignes », puis une spirale d'auto-correction visible (« je ne vois que 4…
mon premier compte était erroné… c'est 4 lignes ») jusqu'à la bonne réponse.

**Lecture (1 essai, mais convergente avec le reste du corpus de mesures)** : dans une même
réponse, la **citation est juste et le compte est faux**. Le mécanisme de contradiction ne
marche à 4B que s'il s'exprime **en preuves** ; en opinions il produit du bruit visible. La
porte mécanique n'a pas filtré son « 5 » par chance : elle ne lit JAMAIS ses affirmations, elle
recompte elle-même les citations vérifiées. C'est la formalisation mesurée de la règle flotte
« producteur ≠ vérificateur ».

Corollaire design : **les personas à 4B divergent sur le ton, pas sur les erreurs** (mêmes
poids). La diversité qui décorrèle est **structurelle** : partition des motifs, sens de lecture,
découpage en shards — pas la personnalité.

## 6. Coût (compteurs moteur, delta 18:19Z → 18:4xZ)

| | Valeur |
|---|---|
| Requêtes | **6** (2 baselines + 2 extracteurs + 1 traducteur + 1 contradicteur), toutes `finished_reason=stop`, 0 erreur |
| Prompt tokens | +10 071 |
| Generation tokens | +2 483 |

L'assemblée proprement dite (E1+E2 ensemble) = **2 appels / ~3 K tokens de prompt**, puisque les
mêmes deux extractions servent le compte ET le seuil.

## 7. Ce que ça n'est pas

- **Pas un débat d'opinions** : le chemin critique ne contient aucun échange libre entre mini —
  chaque spécialiste a un contexte frais et une classe validée, à la memdoor. Le mode
  conversationnel sk-agent reste pertinent pour l'étage de **triage** (quand une porte échoue,
  décider du retry vs repli grep) — non testé ici, piste ouverte.
- **Pas une raison de déléguer son grep** : compter `WARN` dans un fichier local = `grep -c`,
  zéro token (§ « Où le fan-out ne bat PAS grep »). La niche de l'assemblée est : corpus
  **déjà dans le contexte** de l'appelant (dashboard, DM, page distante) ou jugement exigeant
  de toute façon une partition.
- **Pas une généralisation à n=1 essai par condition** : les baselines s'appuient sur des
  séries antérieures (comptage : échecs mesurés dès 6 lignes ; seuil : 20e mesure 1/4 + 19 FP) ;
  les passes de l'assemblée sont nouvelles et deviennent les 1res d'une série à tenir.
