# FrogNano BG workflows — spécification v1 (FIGÉE 05/11/2026, 06:00 locale)

Mandat user direct 04/11 : concevoir les **workflows agentiques conversationnels sk-agent dédiés**
(bonnes personae, bons outils) pour booster l'adoption du tier mini, en s'inscrivant dans le
principe déjà discuté : des workflows qu'un agent **lance en début de session en tâche de fond**,
qui **rendent en fin de session** un travail **facile à vérifier**, qui lui aurait coûté du temps
et des tokens conséquents — **même si la qualité n'est pas parfaite**. Anti-cible explicite :
l'agent « qui fait le travail lui-même » parce que déléguer coûte plus que faire.

Suivi : jsboige/vllm#205. Pivot d'adoption : `project-frognano-adoption-pivot` (29/10).

**v1 = specs consommateurs reçues et intégrées** (6 réponses, 05/11 00:56→01:49Z, échéance 12:00
tenue) : coordinateur `myia-ai-01:CoursIA` · adjoint `myia-po-2023:CoursIA-2` (2 messages) ·
adjoint `myia-po-2025:CoursIA-2` · secrétaire `myia-po-2028:CoursIA-3` (direct + relais) ·
PO sk-agent `myia-po-2025:roo-extensions`. Le PO a validé le figage : « vous pouvez figer la
spécification sur ces bases ».

## 1. Le contrat BG (le produit) — inchangé, validé par les specs

| Propriété | Engagement |
| --- | --- |
| Lancement | 1 ligne en **début de session** (tâche de fond du harnais de l'agent consommateur) |
| Coût consommateur | **~0 token** pendant la session — le driver tourne hors du contexte de l'appelant |
| Livrable | En **fin de session**, sur disque, à **forme fixe**, portes mécaniques déjà passées |
| Qualité | **Imparfaite acceptée par contrat** — le critère est : coût de vérification ≪ coût de refaire soi-même |
| Vérification | Le livrable se relit d'un coup d'œil : tables, fiches, listes vérifiées mécaniquement |

Forme de livrable **convergente across les 4 consommateurs** : index à champs fixes, une ligne
par item, **citation verbatim + provenance** (auteur, date, URL), **zéro statut déduit, zéro
verdict**. Rejet net du rapport narratif (« relu trois fois pour en extraire quatre faits » —
po-2023:CoursIA-2). Règle d'or du coordinateur : **« une ligne vide vaut mieux qu'une ligne
devinée »**.

## 2. Le choix d'architecture : un driver script, pas un preset interactif — confirmé par le PO

- **Preset sk-agent** = délégation *interactive* : passe par le contexte de l'appelant, dépend du
  catalogue servi.
- **Driver script** : fan-out **HTTP direct sur `:5003`**, prompts des personas versionnés dans ce
  dépôt, portes exécutées dans le driver. Zéro token consommateur, indépendant du catalogue.
- **Confirmation PO (05/11)** : le driver HTTP direct « ne consulte pas le catalogue — il n'a
  besoin ni de l'un ni de l'autre ». Les empreintes sha256 des définitions restent la référence
  anti-dérive ; **l'id de preset n'est qu'une étiquette locale, jamais la référence**.

## 3. Personas v1 (figées)

| Persona | Tier | Rôle | Interdits (mesurés) |
| --- | --- | --- | --- |
| `extracteur-fiche` | mini (FrogNano-4B) | copie des champs d'une source structurée vers un **JSON strict** à forme fixe | compter (recompte = machine), juger, blocs > 50 lignes/appel, verdicts, statuts déduits |
| `normalisateur` | mini | mise en forme fixe d'un texte (markdown propre, normalisation) | changer le sens |
| `directeur` | swift-1.5-27b (local, ai-01) | **range et priorise seulement** (oldest-first, « à lire en premier ») sur fiches déjà passées par les portes | tout verdict de fond, toute décision déléguée (liste §5-interdits) |

Conditions PO acceptées pour le directeur : (a) producteur (mini) ≠ vérificateur (swift) — jamais
swift jugeant swift ; (b) les portes mécaniques tranchent avant lui, il ne tranche que ce qu'elles
n'ont pas tranché ; (c) **chaque rapport de run trace `model_used` + empreinte sha256 de la
définition**.

Rappels de frontière (mémoire flotte) : vote = échoue (erreurs corrélées), **liste vérifiable =
gagne** ; extraction verbatim fiable sur sources régulières (rappel 98-100 %), fragile sur
markdown hétérogène ; comptage **nulle part** sans recompte appelant ; **critère littéral + corpus
local → grep, jamais la horde** (adjoint po-2025 : « ne pas fan-out ce grep »).

## 4. Portes mécaniques (exécutées par le driver, jamais par un modèle) — inchangées

1. **Porte schéma** — JSON parsable + clés exactes attendues.
2. **Porte verbatim** — toute valeur chaîne de la fiche doit être **sous-chaîne de la source**
   (introuvable = fabrication ⇒ rejet + retry ciblé). 0 fabrication prouvable mécaniquement.
3. **Porte rappel** — grep indépendant des marqueurs attendus sur la source ; **les absents sont
   mesurés contre le corpus source complet** (précision de l'adjoint po-2025 : « une précision
   prouvée ne vaut pas rappel »).
4. **Recompte machine** — tous les comptes calculés par le driver, jamais par le modèle.

Contrôle consommateur associé (coordinateur) : chaque extrait cité doit être **retrouvé byte pour
byte par `git show <tête>:<fichier>`** — c'est la porte verbatim côté livrable.

## 5. Les trois workflows v1 (dérivés des specs, un squelette commun)

Squelette commun : **snapshot bulk** (REST paginé / GraphQL une requête / git blobs — jamais
d'appels per-item) → **horde `extracteur-fiche`** (tranches ≤ 50 lignes) → **portes §4** →
**directeur range** → livrable markdown/JSONL à champs fixes. Fréquence : **1× par cycle**
(2-4 h), snapshot unique, seuls les champs volatiles sont re-extraits entre cycles.

### W1 — Réserves par PR (consommateur : coordinateur ai-01:CoursIA) — **PILOTE**

Son coût mesuré : 13 PRs en attente de levée de réserve, **2 swift-reader × 70 min au cycle
précédent**. Le travail : énumérer les réserves non levées (reviews `CHANGES_REQUESTED`,
`[Hermes] COMMENT_WITH_CONCERNS`, glyphes 🟡/🔴, commentaires humains après le dernier
`[OVERRIDE]`), retrouver la réponse écrite de la lane, montrer où la tête traite le point.

Livrable par PR : `| point (verbatim + id) | auteur (login) | réponse lane (id, date) | preuve à
la tête (fichier:ligne ou id cellule + extrait) | TRAITÉ / NON TRAITÉ / RENVOI(cible) |`. La
colonne TRAITÉ est **mécanique** : preuve trouvée byte pour byte à la tête ou non. Livré sur
`workspace-CoursIA` en fin de session — « consommé au cycle suivant » (coordinateur).

Sources : `jsboige/CoursIA`, PRs nommées par l'inbox RooSync, REST en lots (quota `jsboige`
partagé, jamais GraphQL en boucle par élément). 5-15 PRs/cycle, cron 4 h du coordinateur.

### W2 — Comparaison de têtes sur même fichier + fiche de cycle (adjoints CoursIA-2)

Cas mesuré (po-2023, 05/11) : 2 PRs sur le MÊME carnet, 12 cellules code × 2 têtes — comparer
`execution_count`, clés de `metadata`, texte des sorties. Livrable :
`| cellule | base | head | écart | preuve |`, aucune prose. Plus la **fiche de cycle** (en FIN de
cycle, après livraison) : `| item | mécanique/substantiel | où (chemin+ligne) | commande de
re-vérification | écart mesuré |` + en-tête 3 chiffres (items, items mécaniques, tokens
économisés).

Sources : blobs git + organes locaux existants (`scripts/notebook_tools/*`, `check_run_state.py`,
exec-ratchet, output-collapse) — **aucun réseau, aucun `gh`** (contrainte : état `gh auth` global
au process de la lane, une écriture concurrente le mute). Offre du consommateur : **2-3 cas réels
de la semaine (paires de têtes + résultat attendu) pour valider l'extracteur avant le pilote**.

### W3 — Pli d'attributs global des PRs (secrétaire po-2028:CoursIA-3)

~200 PRs ouvertes. Livrable 1 (une ligne par PR, jamais un statut déduit) :
`pr | head_sha | lane | ai01_approver | ai01_state | ai01_commit_id | dossier_count |
dossier_last_author | dossier_last_created_at`. Livrable 2 (tête seulement) : pli des check-runs
`| check_name | latest_status | latest_started_at |` avec pli **GLOBAL** latest-wins par
`started_at` (jamais page par page). Champs volatils (`head_sha`, check-runs) seuls re-extraits
entre cycles ; une extraction par cycle suffit (cycle 30 min).

Anti-dérives mesurées à encoder dans le driver : `--jq` s'applique page par page (6 rouges
fabriqués sur 113 runs) ; `comments(last:1)` rend 265 candidates pour 206 réelles ; un `APPROVED`
ne vaut rien sans `commit_id` comparé à la tête. Pool par GraphQL en UNE requête paginée.

### Interdits unanimes (tous consommateurs) — le BG ne fait jamais

Verdict READY/BLOCKED, levée B.0 (glyphe du corps, auteur ou `[OVERRIDE]` nommant le login),
jugement de fond (pédagogie, preuve Lean, honnêteté d'une sortie, labeling exercice/exemple),
Read-Body avant geste, **toute écriture GitHub** (commentaire, body, issue, merge, APPROVE),
ré-exécution de preuve (papermill/nbconvert — un intermédiaire qui refabrique une sortie la
détruit), le choix d'arbitrage de convergence.

## 6. Ce qui bloquait l'adoption (revu au 05/11 — 3 blocages sur 5 levés ou requalifiés)

- **B1 — invisibilité consommatrice : PARTIELLEMENT LEVÉ.** Première complétion **routée hub**
  le 05/11 01:16Z (log claudish `model=frognano-4b src=direct`, 14 015 car. générés, consommateur
  sans tag machine) : la voie de consommation standard existe sur demande explicite. Reste 0
  consommateur externe routine.
- **B2 — chaîne cassée : REQUALIFIÉ (n'était pas cassé).** `mini-fanout-extractor` **n'a jamais
  existé au catalogue** (PO mesuré : 4 presets mini exactement ; les définitions `mini-*.md` sont
  des agents Claude Code, pas des presets sk-agent — deux mécanismes, une famille de noms, d'où
  le fallback silencieux). **Rien à réparer** ; le driver BG ne dépend du catalogue pour rien.
- **B3 — aucun workflow : LEVÉ par ce document** (3 workflows spécifiés par leurs consommateurs).
- **B4 — limites mal vendues : LEVÉ** — les consommateurs les reprennent eux-mêmes comme
  contraintes de design dans leurs specs (§3, §5-interdits).
- **B5 — split de propriété sans traction : LEVÉ** — le PO a répondu en 17 h et validé le figage.

## 7. Répartition et rendez-vous (confirmée par le PO)

| Acteur | Volet |
| --- | --- |
| **roo-extensions** (PO sk-agent) | Rien à faire **tant que les personas restent internes au driver** (arbitrage (a) du PO). Si un jour elles doivent être servies aux autres lanes : envoi des 3 définitions → PR template + sync (arbitrage (b)). |
| **po-2025:vllm** (cette lane) | spécification (ce document, figée), driver BG + portes + mesure ; empreintes sha256 des définitions embarquées |
| **CoursIA / CoursIA-2 / CoursIA-3** | fenêtre pilote (W1 chez le coordinateur), corpus de validation (2-3 cas réels offerts par po-2023:CoursIA-2), politique de file |
| RV | jsboige/vllm#205 + dashboard `global` |

## 8. Specs — REÇUES (section close)

Les 4 questions (travail coûteux mécanique, forme de livrable, non-délégeable, source/fréquence)
ont reçu 5 réponses consommatrices + 1 PO, intégrées aux §3/§5/§6/§7. Réponses complètes dans les
DM `msg-20261105T00*` (threads `spec-bgwf-*-20261104`), résumées ici.

## 9. Critères de succès du pilote (figés d'avance — inchangés)

1. **100 %** des fiches passent la porte verbatim (0 fabrication).
2. **0** faux drapeau (précision des colonnes mécaniques = 100 % ; le rappel est mesuré et
   publié, pas exigé).
3. Le consommateur relève **≥ 1 accélération actionnable** sur son cycle réel (cible mesurable :
   les 70 min de swift-readers du coordinateur).
4. Coût consommateur mesuré : **< 1 000 tokens** par session (lancement + lecture du livrable).

## 10. Statut et suite

**v1 FIGÉE le 05/11 06:00 locale** — sous l'échéance user de 12:00. Étape suivante : **driver W1**
(snapshot REST bulk → horde extracteur-fiche → portes → directeur → markdown sur
`workspace-CoursIA`), validation d'abord sur les 2-3 cas réels offerts par po-2023:CoursIA-2,
puis fenêtre pilote avec le coordinateur (lecture seule GitHub, charge horde ≈ négligeable,
aucune fenêtre moteur à annoncer).

### 10.1 Driver W1 — premier livrable mesuré (05/11 11:07 locale) et sa correction de conception

`myia_vllm/scripts/adoption/bg_workflows/w1_reserves.py` sur `jsboige/CoursIA`
(#24457, #24640, #24599) : **13/14 fiches PASS** la porte verbatim, **34 s** pour 14 points
contre 471 s / ~160 k tokens pour 7 PRs côté coordinateur. La fiche écartée est **signalée dans
la table** (`⚠️ PORTE ÉCHUE 4/5 champ ['extrait']`), plus seulement dans le compte d'en-tête.

**Défaut de conception trouvé et corrigé avant livraison — la colonne de statut était fausse.**
La v1 prévoyait `TRAITÉ / NON TRAITÉ` calculé sur « le texte cité par la réserve est-il encore
présent à la tête ? ». Mesure sur les 3 PRs : **9 alertes produites, 9 fausses**, pour une raison
structurelle et non réglable — **la polarité d'une réserve varie d'un point à l'autre du même
lot**. #24640 p1 cite `csharp_sha` comme *preuve que c'est bon* (« reproduits byte-exact »), p2
cite `HttpPort 86660` comme *le défaut*. Un jeton présent à la tête ne prouve donc rien dans un
sens ni dans l'autre ; en tirer un statut fabrique des faux drapeaux symétriques.

Correction (soustraction, pas inversion) : la colonne devient un **fait** — `n/m jetons cités
encore présents à la tête`, avec l'exemple **le plus long** (le plus discriminant) et les
fichiers `@sha`. Aucun statut, aucune alerte. C'est cohérent avec le footer du livrable (« le BG
ne juge pas la levée ») et avec §5-interdits (jugement de fond). **La spec §5 est corrigée par
la mesure** : `TRAITÉ / NON TRAITÉ` n'est pas mécanisable sur ce corpus ; la ligne de statut
revient à la lane, le BG livre le fait et son emplacement.

Reste à mesurer : le directeur (rangement oldest-first) et la livraison sur `workspace-CoursIA`.

### 10.2 Directeur W1 — construit et mesuré en mode mock le 06/11 (oracle 2 cas po-2023:CoursIA-2)

Trois pièces, la polarité reste nulle part (§10.1) :

1. **« Balle » mécanique par point** (driver, dates/auteurs seulement) : levée posée →
   `FERMÉ` ; réponse lane postérieure → `COORDINATEUR` (arbitrage/levée formels attendus) ;
   sinon → `LANE` (réponse attendue). Par PR : la pire balle l'emporte.
2. **Directeur LLM** (hub claudish, clé proxy `CLAUDISH_PROXY_KEY` — swift alias
   `qwen3.6-35b-a3b` par défaut, `DIRECTEUR_MODEL` remplaçable : le user a suggéré Minimax
   le 03/11, swift étant saturé par les contextes longs) : il rend **une permutation complète
   des PRs + une raison qui cite un fait** — rien d'autre. **Ses portes, portées par le
   driver** (producteur ≠ directeur ≠ portes) : G1 JSON strict ; G2 permutation exacte
   (rien inventé, rien oublié) ; G3 chaque raison est sous-chaîne de la table de faits ;
   G4 zéro mot de décision (levable/ready/blocked/traité…). Toute échec → **fallback
   mécanique** (balle bloquante puis oldest-first), signalé dans le livrable. Chaque run
   trace `model_used` + `def_sha256` + latence + tokens (condition PO §3c).
3. **Mode `mock`** (aucun modèle) : l'ordre mécanique seul — pipeline complet validable
   sans clé.

**Mesuré (self-test 9/9 + oracle réel 06/11 08:06 locale, `--directeur mock`)** :
PR #24755 → `FERMÉ` (levée 17:02Z du 05/11 — livré comme fait, aucune levée faite par le BG) ;
PR #24442 → `COORDINATEUR` — l'oracle d'hier attendait `LANE`, mais la lane a posé sa réponse
`[ACTION]` 6658517981 (05/11 12:55Z) *entre-temps* : le routage suit les dates, le cas a
évolué, le routage LANE est couvert par le self-test. Le classement mock respecte
balle-bloquante-puis-oldest (#24442 avant #24755).

**En attente** : clé proxy claudish (demandée à po-2025:claudish) pour la première passe
LLM du directeur ; puis livraison sur `workspace-CoursIA` et fenêtre pilote coordinateur.
