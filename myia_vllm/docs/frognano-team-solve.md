# FrogNano team-solve — assemblée de spécialistes + portes mécaniques (R9-R11)

**Question** (user, 01/11 2026) : un workflow agentique peut-il augmenter la **fiabilité** du
modèle et la **couverture** de ce qu'il sert — dans l'esprit des harnais conversationnels
(sk-agent) et du bruit Reddit autour de
[memdoor team-solve](https://github.com/guregodevo/memdoor/tree/main/examples/workflows/team-solve) ?

**Réponse courte, mesurée le jour même sur le siège po-2025** : oui — mais pas en faisant
discuter le modèle. L'assemblée gagne en **décomposant** la tâche refusée en étapes de la classe
validée (extraction verbatim mono-motif), et en rendant le verdict à des **portes mécaniques**
côté appelant. Trois classes refusées en mono-appel deviennent servables avec preuve :
**comptage, seuil sur valeur de champ, réécriture/traduction**. Record complet de la mesure :
`_iteration_log/frognano_teamsolve/NOTES.md`.

Ce document étend `frognano-fanout-delegation.md` (R1-R8) — il en hérite les règles : corpus
figé, oracle calculé avant l'appel, `model_used` contrôlé sur chaque réponse, jamais de verdict
au mini.

## 1. Le principe (et ce que memdoor nous a appris)

team-solve (méthode GVS5H) fait gagner 9,8/10 contre 8,0/10 au même modèle — par décomposition
en étapes compétentes, contextes frais, communication par fichiers, et **verdict mécanique**
(« a script decides success, not a model »). Les auteurs créditent la discipline de registre,
pas le débat. Nos mesures convergent :

- **Baseline mono-appel** (classes refusées, redites ici pour l'occasion) : « combien de WARN ? »
  → **3** (oracle 4) ; « free < 2000 Mo ? » → **NON** en citant la ligne `free=1128MB` —
  *le verdict contredit sa propre preuve*.
- **Contradicteur** (persona avocat du diable, 1 essai) : dans la même réponse, les citations
  sont exactes (4/4 lignes verbatim) et le compte annoncé est faux (« le compte réel est de 5 »)
  avant auto-correction visible. **La citation traverse, le jugement non.**

Donc : à 4B, la persona change le ton, pas les erreurs (mêmes poids ⇒ erreurs corrélées). La
diversité utile est **structurelle** (partition, sens, shards). Et l'assemblée ne « rend pas le
modèle plus intelligent » : elle fait en sorte qu'on ne lui demande **jamais** ce qu'il sait mal
faire.

## 2. Le workflow

```text
             ┌─ Extracteur A (motif M, persona alertes) ──┐
ORDONNANCEUR ┤                                             ├─ PORTES ── VERDICT
(appelant)   └─ Extracteur B (motif ¬M, persona mesures) ─┘  (mécaniques)  (appelant)
   découpe, choisit M tel que {M, ¬M} partitionne le corpus
```

| Rôle | Qui | Droit | Interdit |
|---|---|---|---|
| Ordonnanceur | appelant (agent, jamais mini) | découper, choisir les motifs, exécuter les portes, calculer, juger | déléguer un verdict |
| Extracteurs | mini, personas distinctes, **contextes frais** (1 appel chacun, parallèles) | recopier verbatim les lignes d'UN motif | compter, commenter, transformer |
| Portes | appelant, déterministes | précision (∈ source), disjoint (A∩B=∅), partition (\|A\|+\|B\|=\|corpus\|), couverture | faire confiance à une affirmation du mini |
| Contradicteur | mini, persona « preuve par extraction » | citer les lignes qui réfutent une affirmation | voir son compte retenu (seules ses citations franchissent la porte) |
| Producteur + porte de fidélité | mini (réécriture) + appelant (regex multiset) | traduire/réécrire court | livrer sans la porte |

**L'invariant central** : *toute sortie du mini franchit une porte mécanique avant tout usage
aval — et une porte ne lit jamais les affirmations, elle recompte les citations vérifiées.*

## 3. R9 — Comptage prouvé (partition + recompte)

*Fastidieux/refusé* : « combien de lignes X dans ce corpus ? » (échecs mesurés dès 6 lignes).

1. Choisir M tel que {M, ¬M} partitionne le corpus (ex. `WARN` / `HEARTBEAT` ; sinon
   `M` / « le reste », en énumérant les autres valeurs du champ).
2. Deux appels R1 parallèles (persona distincte chacun, prompt de la recette R1 de
   `frognano-fanout-delegation.md`, motif unique).
3. Portes : chaque ligne ∈ source ; A∩B = ∅ ; \|A\|+\|B\| = \|corpus\|.
4. **Le compte est |A| — prouvé** : partition + précision exactes ⇒ rappel fermé.

```powershell
$A = @(Get-Content $outA | ? { $_.Trim() } | % Trim); $B = @(Get-Content $outB | ? { $_.Trim() } | % Trim)
$C = @(Get-Content $corpus | ? { $_.Trim() } | % Trim)
$fab = @($A + $B | ? { $C -notcontains $_ }).Count          # precision : attendu 0
$inter = @($A | ? { $B -contains $_ }).Count                # disjoint   : attendu 0
$union = @($A + $B | Sort-Object -Unique)
$cov = @($C | ? { $union -notcontains $_ }).Count           # couverture : attendu 0
if ($fab -eq 0 -and $inter -eq 0 -and $cov -eq 0 -and $A.Count + $B.Count -eq $C.Count) {
  "compte prouve : $($A.Count)" } else { "porte ECHOUEE : retry shard / repli grep" }
```

**Mesuré (01/11)** : WARN = 4 prouvé (4+28=32, 0 fabrication, 0 omission) ; baseline disait 3.

## 4. R10 — Seuil/jugement sur valeur de champ, prouvé

*Refusé en mono-appel* (20e mesure : 1/4, 19 FP — le modèle trouve la ligne, ne compare pas le
nombre ; baseline du jour : NON en citant `free=1128MB`).

Même assemblée que R9 (les deux extractions se **réutilisent**) : l'appelant parse le champ sur
l'union vérifiée et compare lui-même.

```powershell
$frees = $union | % { if ($_ -match 'free=(\d+)MB') { [pscustomobject]@{l=$_;v=[int]$Matches[1]} } }
"$($frees.Count)/$($union.Count) parses"                    # exhaustif attendu
$frees | ? { $_.v -lt 2000 } | % l                          # verdict : lignes, min, tout est mecanique
```

**Mesuré** : OUI, 1 ligne (`free=1128MB`), min 1128, scan 32/32 exhaustif — le même assemblage
sert R9 ET R10 pour 2 appels.

## 5. R11 — Réécriture courte derrière porte de fidélité

*Non calibré jusqu'ici*. Le mini produit (traduction FR→EN, reformulation, reformatage court)
sous persona « chaque nombre/unité doit se retrouver exactement » ; la porte est **mécanique
pure** : extraction regex des nombres des deux côtés, normalisation des séparateurs
(espace/virgule FR ↔ virgule/point EN), diff multiset. Toute divergence → repair (renvoyer au
producteur le nombre manquant/altéré) ou refus.

```powershell
function Get-Nums([string]$t) { [regex]::Matches($t, '\d+(?:[ .,]\d+)*') | % { $_.Value -replace '[ ,.]','' } }
$d = @(Compare-Object @(Get-Nums $src) @(Get-Nums $tr))
if ($d.Count -eq 0) { "fidelite OK — servie" } else { $d }   # chaque ecart = nombre perdu/altere
```

**Mesuré** : 20/20 nombres préservés sur un paragraphe technique dense. Limite v1 : la
normalisation prouve les chiffres, pas la position décimale (74,9 ≡ 749 ≡ 74.9) — durcir si le
cas l'exige.

## 6. Quand NE PAS utiliser l'assemblée

- **Critère littéral + corpus local** : `grep -c` gagne toujours (zéro token, millisecondes).
  La niche : corpus **déjà dans le contexte** de l'appelant (dashboard, DM, page distante — pas
  de grep local possible), ou jugement qui exigeait de toute façon une partition.
- **Aucune porte n'existe pour la sortie visée** (synthèse multi-sources, goût, pertinence) :
  l'assemblée n'a rien à fermer — tier medium avec oracle distinct.
- **Corpus > ~50 lignes par appel** : découper en shards d'abord (R1), l'assemblée opère par
  shard, la partition se vérifie sur l'union des shards.

## 7. Ce qui reste interdit, même assemblé

Le mini ne compte pas, ne compare pas, n'agrège pas, ne verdict pas — **il cite** ; le
contraedicteur n'est cru que sur ses citations, jamais sur son compte (mesuré : « 5 » annoncé,
4 cités, verdict final correct par la citation). Aucun verdict ne sort d'un vote de personas :
à poids identiques, les votes sont corrélés.

## 8. Pistes ouvertes (non testées)

- **Triage conversationnel** (`run_conversation` sk-agent) quand une porte échoue : décider
  retry ciblé vs repli grep vs shard plus petit — la seule place où le mode conversationnel
  a un rôle plausible, car la décision est reversible et peu coûteuse.
- **Presets sk-agent dédiés** aux personas (Contrôleur/Régistraire/Traducteur/Avocat du diable)
  pour éviter de recoller les `system_prompt`.
- Driver pour crons dédiés (pattern `nb_audit_driver.py`).
- Série à tenir : les passes du 01/11 sont les premières de chaque classe (R9 : 1/1, R10 : 1/1,
  R11 : 1/1) — la verbatimité inter-appels étant variable (cf. 22e-25e mesures), la porte reste
  le juge à chaque usage.

## 9. Checkpoint swift — l'arbitre de la frange (mesuré 01/11, 2/2)

**Le problème qu'il résout** : les portes mécaniques n'existent que là où un oracle existe
(grep local, partition, regex). Sur un job **long** et une source **distante ou hétérogène**
(dashboard, web, PDF, prose), il n'y a pas d'oracle — et l'appelant ne peut pas lire 2 000
lignes pour trancher. C'est exactement la classe où le mini produit de l'utile et où la
vérification coûte plus cher que le travail.

**Protocole** : un arbitre de tier supérieur, appelé **au checkpoint**, qui ne voit QUE :

1. la mission ;
2. les **affirmations** du producteur ;
3. ses **citations** verbatim ;
4. la **politique opérationnelle** (ce que l'humain fait de la sortie).

Il **ne relit jamais le corpus** — c'est toute l'économie du dispositif, et c'est ce qui a été
validé :

| Cas testé (01/11) | Arbiteur voit | Verdict rendu | Attendu |
|---|---|---|---|
| Claim « exactement 3 lignes WARN » + 4 citations | la frange seule (~200 tokens) | **CONTREDIT** (« les citations contiennent à elles seules 4 lignes distinctes ») | CONTREDIT |
| Taxonomie G1 fusionnant `WARN RAM basse` (120) et `WARN RAM CRITIQUE` (100) | la fusion + la politique (CRITIQUE escalade) | **FUSION_RISQUÉE** (« noie les cas urgents dans le volume ») | FUSION_RISQUÉE |

2/2 sur `fast-responder` (glm-5.3-flash, twin cloud — **substitut explicite** : le swift local
était indisponible, cf. ci-dessous). La décision logique « les citations contredisent le
compte » ne dépend pas du modèle arbitre ; ce qui reste à mesurer sur swift local, c'est le
taux sur des cas ambigus.

**Règles** :

- **Quand** : seulement quand une porte mécanique ne peut pas décider — fusion sémantique,
  conséquence opérationnelle, pertinence. Jamais sur chaque étape : 1 à 3 checkpoints par job
  typique. Coût : quelques centaines de tokens par checkpoint, contre des milliers pour faire
  relire le corpus.
- **Le verdict de l'arbitre est une recommandation, pas un fait** : l'appelant l'applique
  mécaniquement (scinder le groupe, relancer l'extraction sur la frange signalée). Un arbitre
  non plus ne « verdict » pas — il oriente une décision que l'appelant exécute.
- **Dépendance distante — mesuré à nos frais** : le 01/11, `api.medium…/health` a rendu **502
  sur 4/4 tentatives** (19:49:05Z confirmé, ~1 h d'indisponibilité) pendant que `models.myia.io`
  répondait 200. Le workflow R9/R10 a continué **sans le checkpoint** (portes mécaniques
  seules) : le checkpoint est une **couche d'amélioration, jamais un chemin critique** ; s'il
  est muet, le job se poursuit et le rapport marque « checkpoint sauté ».
- **Presets disponibles aujourd'hui** (ne pas en inventer) : `classifier-local` et
  `summarizer-local` (swift no-thinking, le moins cher), `terminal-analyst` (swift + outils),
  **`swift-delegator`** — déjà provisionné pour exactement cette architecture (« le medium
  garde le jugement et délègue le mécanique au mini ») ; twins cloud `analyst-glm5` /
  `fast-responder` en substitut, toujours étiquetés comme tels dans le rapport.

## 10. Outils et jobs longs — le vrai levier d'adoption

Le risque d'adoption est nommé par le user : *« il est plus rapide de faire soi-même »* — vrai
sur les jobs courts à critère littéral (`grep` gagne, cf. §6), faux sur les jobs **fastidieux et
chronophages** que personne ne fait jamais. C'est là que se joue l'utilité, et c'est là que les
outils changent la classe :

| Preset mini | Outil(s) déjà branchés | Ce que ça autorise |
|---|---|---|
| `mini-coder-fix` | `open_terminal` | diagnostic mono-fichier bouclé (lire → éditer → tester) |
| `mini-repo-scan` | `open_terminal` (lecture) | inventaire/cartographie d'un sous-arbre |
| `mini-summarizer` | `markitdown` | documents (PDF/DOCX/XLSX) → Markdown → extraction |
| `mini-web-research` | `searxng` | collecte de sources sur une question précise |

**Architecture pour un job long** (à mesurer avant d'être promue) : le mini travaille par
tranches courtes (≤50 lignes, ≤10 étapes), chaque tranche franchie par une porte mécanique ;
un checkpoint d'arbitrage tous les N items sur la seule frange ; l'appelant ne lit à la fin que
la liste consolidée et une commande de contrôle. La préservation du **contexte de l'appelant**
reste l'incitation qui marche (`frognano-fanout-delegation.md` §4).

**Non mesuré, à faire** : la dérive d'un mini **outillé en boucle** (combien de tours avant que
la qualité tombe), et le coût réel d'un job de bout en bout avec outils + checkpoints. Tant que
ce n'est pas mesuré, un job outillé long se conduit avec un point de contrôle humain en fin de
chaîne.

## 11. Ce que ça change pour le modèle **mandataire** (le vrai gain d'usage)

L'argument d'adoption ne se joue pas seulement en tokens ni en latence : il se joue en
**précaution**. Un modèle mandataire qui délègue au mini doit aujourd'hui se poser une question
à chaque appel — *« cette tâche est-elle dans sa classe validée ? »* — parce que la frontière
mesurée (comptage interdit, seuil sur valeur de champ 1/4, pas de verdict) est une liste de
pièges qu'il doit connaître par cœur. C'est un coût cognitif invisible et permanent : la
délégation paraît risquée, donc elle n'a pas lieu.

L'assemblée déplace ce coût **du mandataire vers la machine** :

| Sans portes | Avec portes |
|---|---|
| le mandataire doit choisir une tâche **déjà** dans la classe validée | il peut soumettre la tâche **telle quelle** : c'est la porte qui refuse ou répare |
| une sortie fausse est indétectable à la lecture (le compte faux arrive au même format que le juste) | une sortie fausse **échoue à la porte** — 0 fabrication / 0 omission / 32 parses, ou porte échouée |
| la confiance est une propriété du **modèle** (« que sait-il faire ? ») | la confiance est une propriété du **montage** (« quelles portes ai-je posées ? ») |
| chaque nouveau cas d'usage exige une calibration préalable | l'extensibilité vient d'ajouter un **motif**, pas de re-calibrer un modèle |

Conséquences pour l'orchestrateur :

- **Le mandataire n'a plus besoin d'être prudent sur le contenu, seulement sur l'usage** :
  ce qui sort d'une porte peut être consommé sans relecture ; ce qui échoue est un signal
  explicite, pas une erreur silencieuse. C'est ce qui rend la délégation **routinière** plutôt
  qu'exceptionnelle — et une délégation routinière est la seule qui produise un changement de
  comportement.
- **R3 (producteur ≠ vérificateur) devient mécanisable** : la règle flotte n'est plus une
  discipline que le mandataire doit s'imposer, c'est un script qui tourne après chaque appel.
- **La porte garde le mandataire honnête** : `grep -c` reste imbattable sur un fichier local
  (§6) — la porte ne pousse pas à déléguer ce qui ne doit pas l'être ; elle rend simplement
  déléguable ce qui ne l'était pas.
- **Le checkpoint §9 est ce qui rend le montage tenable sur la durée** : sans lui, un job long
  finit par produire une frange que plus aucune porte ne couvre ; avec lui, la frange est
  arbitrée pour quelques centaines de tokens, sans relire la source.

**Limite à ne pas franchie** : ce tableau dit que le montage rend le mini **utilisable sans
précaution sur des classes couvertes par une porte**. Il ne dit pas qu'il rend le mini apte à
tout — les classes sans oracle restent au tier medium (§6), et la dérive d'un mini outillé en
boucle reste non mesurée (§10).

## 12. Les portes en une commande — `frognano_gate.py`

Un mandataire ne doit **pas** avoir à recopier les snippets des §3-§5 : tant que la porte est un
copier-coller, elle n'est appliquée que par ceux qui ont lu la doc — c'est-à-dire presque jamais.
Le mécanisme est donc livré comme script : `myia_vllm/scripts/adoption/frognano_gate.py`
(aucune dépendance, sortie humaine par défaut, `--json` pour un appelant automatisé, **exit code
0 = porte passée / 1 = échouée / 2 = erreur d'usage**).

```bash
python myia_vllm/scripts/adoption/frognano_gate.py partition --corpus C --a A --b B
python myia_vllm/scripts/adoption/frognano_gate.py threshold --corpus C --a A --b B \
        --field free --op lt --value 2000
python myia_vllm/scripts/adoption/frognano_gate.py fidelity  --src S --dst D
python myia_vllm/scripts/adoption/frognano_gate.py selftest
```

Ce que la porte fait, et que la version PowerShell ne faisait pas :

- **multiplicités**, pas seulement l'appartenance : une ligne présente 2× dans la source et 3×
  dans l'union est signalée `sur-comptee` (l'ancienne porte passait) ;
- **`threshold` exige que `partition` passe** : on ne compare jamais des nombres issus de lignes
  non prouvées ;
- **parse exhaustif obligatoire** : un seul champ non parsé = porte échouée, jamais ignoré ;
- **`--json`** : un mandataire consomme `{passed, hits, hit_lines}` sans lire de prose.

**`selftest`** rejoue les cas mesurés **et les falsifications qui doivent échouer** (fabrication,
omission, doublon, compte faux du contradicteur, champ non parsé, nombre altéré, nombre perdu) :
**11/11 contrôles OK**. C'est la contre-preuve de la porte — une porte qui ne sait pas échouer ne
prouve rien.

**Mesuré le 01/11 (2ᵉ passe indépendante, par le script)** : deux extracteurs `mini-summarizer`
(`model_used: frognano-4b`, aucun repli) sur le corpus figé → **partition 4 + 28 = 32, 0
fabrication, 0 doublon, 0 manquante, COMPTE PROUVÉ : 4** ; seuil `free < 2000` → **1 ligne,
`min=1128`, parse 32/32**. Séries : R9 2/2, R10 2/2.

**Limites assumées** : `fidelity` retire les séparateurs (prouve les chiffres, pas la position
décimale — cf. §5) ; le script ne connaît **aucun** motif ni champ métier, il reçoit tout en
argument ; et il ne remplace pas le checkpoint §9 — il le rend inutile là où une porte existe, et
le laisse nécessaire partout ailleurs.

---

Mesures : `_iteration_log/frognano_teamsolve/NOTES.md`. Classes de base et recettes R1-R8 :
`frognano-fanout-delegation.md`. Frontières du mini : mémoires
`reference-mini-counting-frontier`, `reference-mini-verbatim-prefix-instability`.
