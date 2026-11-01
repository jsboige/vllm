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

```
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

---

Mesures : `_iteration_log/frognano_teamsolve/NOTES.md`. Classes de base et recettes R1-R8 :
`frognano-fanout-delegation.md`. Frontières du mini : mémoires
`reference-mini-counting-frontier`, `reference-mini-verbatim-prefix-instability`.
