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

## 8. Addendum 01/11 19:4xZ — checkpoint swift : la frange suffit (2/2), et l'étage est tombé

**Le checkpoint swift, validé sur la question qui compte** : un arbitre de tier +1 peut-il
trancher sans relire le corpus, donc à coût négligeable ? Deux tests, prompts de ~200-300
tokens :

| Cas | Arbiteur voit | Verdict | Attendu |
|---|---|---|---|
| Claim « exactement 3 lignes WARN » + ses 4 citations | frange seule | **CONTREDIT** (« les citations contiennent à elles seules 4 lignes distinctes ») | CONTREDIT |
| G1 fusionnant `WARN RAM basse` (120) et `WARN RAM CRITIQUE` (100) + politique d'escalade | fusion + politique | **FUSION_RISQUÉE** (« noie les cas urgents dans le volume ») | FUSION_RISQUÉE |

**2/2 sur `fast-responder` (glm-5.3-flash, twin cloud)** — pas sur swift : voir ci-dessous.
Ces deux cas sont exactement la classe que les portes mécaniques ne couvrent pas (conséquence
opérationnelle d'une fusion, soutien logique d'une affirmation par ses propres citations).

**L'étage swift était indisponible pendant le test — mesuré, pas supposé** :
`classifier-local` et `summarizer-local` (swift no-thinking sur ai-01) ont échoué **3 fois sur 3**
en **502 Bad Gateway** (HTML IIS en corps d'erreur) ; `https://api.medium.text-generation-webui.myia.io/health`
= **502 sur 4/4 tentatives**, confirmé à **19:49:05Z** (~1 h après la première observation),
pendant que `models.myia.io/health` = **200** et que les presets cloud via hub répondaient
normalement. Aucune fenêtre annoncée sur le dashboard global à cette heure (ai-01 postait par
ailleurs à 16:41Z et 17:21Z) ⇒ lu comme une panne non annoncée de l'endpoint medium, owner
ai-01 ; signalé, pas touché (règle cross-workspace).

**La leçon de design qui en sort, et elle vaut plus que le 2/2** : le checkpoint est une
**dépendance distante**. Ce soir, R9/R10 ont tourné **sans lui** — les portes mécaniques ont
suffi — et le checkpoint a simplement été sauté. Règle retenue : le checkpoint est une couche
d'**amélioration**, jamais un chemin critique ; s'il est muet, le job se poursuit et le rapport
marque « checkpoint sauté ». Corollaire : conditionner un job à un étage qui peut tomber est un
défaut de conception, pas une garantie de fiabilité.

**Inventaire des presets d'arbitrage déjà provisionnés** (relevé `list_agents`) : `classifier-local`
et `summarizer-local` (swift no-thinking, les moins chers), `terminal-analyst` (swift + outils),
**`swift-delegator`** — décrit comme « le medium garde le jugement et délègue le mécanique au
mini », soit exactement cette architecture, déjà configurée ; twins cloud `analyst-glm5` /
`fast-responder` en substitut.

**Ce que l'addendum ne prouve pas** : le taux de justesse de swift lui-même sur cas ambigus
(2/2 sur un twin cloud — premier passage sur swift réel au **§10.2**), ni la dérive d'un mini
outillé en boucle (job long avec outils) — mesure à faire avant de promouvoir un job outillé de
bout en bout.

## 9. Addendum 01/11 20:0xZ — 2ᵉ passe R9/R10 par le **script** (les portes quittent le copier-coller)

**Motif** : une porte qui vit dans un snippet de doc n'est appliquée que par ceux qui ont lu la
doc. Pour un modèle mandataire — le cas d'usage visé — elle doit être **une commande à exit
code**. D'où `myia_vllm/scripts/adoption/frognano_gate.py` (zéro dépendance, `--json`, usage
documenté §12).

**`selftest` : 11/11** — les cas mesurés **et** les falsifications qui doivent échouer
(fabrication, omission, doublon, compte faux du contradicteur, champ non parsé, nombre altéré,
nombre perdu). Une porte qui ne sait pas échouer ne prouve rien : c'est la contre-preuve.

**2ᵉ passe réelle, indépendante de celle du §3** : deux `mini-summarizer` (`model_used:
frognano-4b`, **aucun repli**) sur le même corpus figé →

```text
[PORTE PASSEE] partition
  A=4 B=28 corpus=32 (somme = corpus)
  fabriquees=0 sur-comptees=0 doublons=0 manquantes=0
  COMPTE PROUVE : 4
[PORTE PASSEE] threshold
  free lt 2000.0 -> 1 ligne(s) ; parse 32/32 ; min=1128.0 max=19308.0
```

Séries : **R9 2/2, R10 2/2**. Coût de cette passe : 2 requêtes mini.

**Ce que le script durcit par rapport aux snippets** : multiplicités (2× dans la source, 3× dans
l'union = `sur-comptee`, l'ancienne porte passait) ; `threshold` **refuse** de comparer si
`partition` a échoué ; parse exhaustif obligatoire ; sortie machine.

**Ce qu'il ne change pas** : `fidelity` conserve sa limite v1 (chiffres, pas position décimale) ;
le script ne connaît aucun motif métier ; il rend le checkpoint §9 inutile là où une porte
existe, et le laisse nécessaire partout ailleurs.

## 10. Addendum 02/11 07:5xZ — contrôle discriminant (4ᵉ passe) + checkpoint **sur swift réel**

### 10.1 `partition`/`threshold` — un contrôle que les 3 passes précédentes ne faisaient pas

Corpus neuf : 32 lignes de `_logs/gpu-governor.log`, fenêtre 01/11 05:02 → 02/11 08:02. Il contient
une **paire piège** : deux lignes au **même horodatage** `2026-11-02 04:02:03`, l'une
`HEARTBEAT temp=31C free=2100MB mode=normal`, l'autre `WARN RAM basse free=2100MB temp=31C mode=normal`.

C'est le contrôle que les passes 1-3 ne faisaient pas : un extracteur qui filtre sur la **forme** de
la ligne (la présence de `temp=`/`mode=`, la position du champ) plutôt que sur le **motif** se
tromperait sur l'une des deux. Chaque extracteur n'a gardé que la sienne.

```text
[PORTE PASSEE] partition
  A=4 B=28 corpus=32 (somme = corpus)
  fabriquees=0 sur-comptees=0 doublons=0 manquantes=0
  COMPTE PROUVE : 4
[PORTE PASSEE] threshold
  free lt 4000.0 -> 5 ligne(s) ; parse 32/32 ; min=1114.0 max=19569.0
```

Séries : **R9 4/4, R10 4/4**.

**Le détail que la porte ne doit pas laisser passer dans un rapport** : le seuil rend **5 lignes
pour 4 instants distincts** — `04:02:03` figure deux fois parce que la même mesure est enregistrée
en `HEARTBEAT` et en `WARN`. C'est correct (le seuil porte sur l'union **vérifiée**, pas sur A seul),
mais un rapport qui annoncerait « 5 incidents » surestimerait. La porte prouve le **compte** ;
l'interprétation du compte reste à l'appelant.

### 10.2 Checkpoint sur swift **local** — 1/1, première fois sur la cible réelle

Le blocage du §8 est levé : `api.medium.text-generation-webui.myia.io/health` = **200** et
`models.myia.io/health` = **200** au 02/11 07:5xZ. `classifier-local` répond et la réponse porte
`model_used = swift-1.5-27b-no-thinking` — **le vrai swift, pas un twin cloud** (le contrôle de
routage reste indispensable : un preset peut servir un autre modèle sans erreur).

Cas soumis — précisément la frange qu'aucune porte ne couvre : les deux nuits de RAM CRITIQUE sont
**prouvées** par les portes (§10.1) ; la question posée est **watch ou action**. L'arbitre ne voit
que la mission, les affirmations du producteur, deux citations verbatim et la politique
opérationnelle (barre de kill 4 GB, RSM mesuré à 0.1 GB, survie des conteneurs, restart Docker
interdit sans cadre user).

```text
VERDICT: WATCH
RAISON: absorbés sans OOM ni perte de conteneur, RAM revenue à 11 GB
SEUIL_3E_NUIT: une 3e nuit consécutive <4GB déclenche l'escalade
CE_QUE_TU_NE_PEUX_PAS_JUGER: si la baisse progressive avant les pics est un cycle de vie
  normal ou une lente accumulation de fuites
```

**Ce que ça mesure vraiment** : pas une *justesse* — il n'existe pas d'oracle mécanique pour une
décision de politique. Ce qui est mesuré est plus étroit, et vaut quand même : (a) l'étage swift
**répond** sur sa cible réelle ; (b) il **ne contredit aucun fait fourni** ; (c) il **nomme
correctement sa propre frontière** — cycle de vie normal *vs* fuite lente, qui est effectivement ce
que ces données ne tranchent pas ; (d) son verdict **coïncide** avec la lecture que la politique
impose déjà.

Le point (c) est celui qui sépare un arbitre utile d'un générateur de confiance : un modèle qui
aurait répondu « tout va bien » sans nommer ce qu'il ignore n'aurait rien apporté.

**Ce que ça ne prouve pas** : 1/1, sur un cas où la politique était très cadrée. La justesse de
swift sur cas **réellement** ambigus reste non établie — il faudrait une série de cas où la
politique laisse une indétermination, et un moyen de trancher après coup. Série checkpoint :
**3/3**, dont 1 sur swift réel.
