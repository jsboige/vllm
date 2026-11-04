# FrogNano BG workflows — spécification v0 (04/11/2026, specs consommateurs en collecte)

Mandat user direct 04/11 : concevoir les **workflows agentiques conversationnels sk-agent dédiés**
(bonnes personae, bons outils) pour booster l'adoption du tier mini, en s'inscrivant dans le
principe déjà discuté : des workflows qu'un agent **lance en début de session en tâche de fond**,
qui **rendent en fin de session** un travail **facile à vérifier**, qui lui aurait coûté du temps
et des tokens conséquents — **même si la qualité n'est pas parfaite**. Anti-cible explicite :
l'agent « qui fait le travail lui-même » parce que déléguer coûte plus que faire.

Suivi : jsboige/vllm#205. Pivot d'adoption : `project-frognano-adoption-pivot` (29/10).

## 1. Le contrat BG (le produit)

| Propriété | Engagement |
| --- | --- |
| Lancement | 1 ligne en **début de session** (tâche de fond du harnais de l'agent consommateur) |
| Coût consommateur | **~0 token** pendant la session — le driver tourne hors du contexte de l'appelant |
| Livrable | En **fin de session**, sur disque, à **forme fixe**, portes mécaniques déjà passées |
| Qualité | **Imparfaite acceptée par contrat** — le critère est : coût de vérification ≪ coût de refaire soi-même |
| Vérification | Le livrable se relit d'un coup d'œil : tables, fiches, listes vérifiées mécaniquement |

## 2. Le choix d'architecture : un driver script, pas un preset interactif

- **Preset sk-agent** = délégation *interactive* : passe par le contexte de l'appelant (chaque
  appel coûte ses tokens), dépend du catalogue servi (mesuré 03/11 : `mini-fanout-extractor`
  **absent du catalogue servi**, fallback silencieux sur swift).
- **Driver script** (précédent validé : `nb_audit_driver.py`, 22-23/09, ~50 notebooks/h) :
  fan-out **HTTP direct sur `:5003`**, prompts des personas **versionnés dans ce dépôt**,
  portes exécutées dans le driver. Zéro token consommateur, indépendant du catalogue, lancable
  depuis toute machine LAN. sk-agent garde les presets pour l'interactif ; **le BG n'en dépend plus**.

## 3. Personas v0 (à figer avec les specs des consommateurs)

| Persona | Tier | Rôle | Interdits (mesurés) |
| --- | --- | --- | --- |
| `extracteur-fiche` | mini (FrogNano-4B) | copie des champs d'une source structurée vers un **JSON strict** à forme fixe | compter (recompte = machine), juger, blocs > 50 lignes/appel, verdicts |
| `normalisateur` | mini | mise en forme fixe d'un texte (markdown propre, normalisation) | changer le sens |
| `directeur` | swift-1.5-27b (local, ai-01) | reçoit les fiches **vérifiées** + la **source**, range, drapeaute | jamais en dessous du medium (proto 3 : le directeur est un tier supérieur ET reçoit la source) |

Rappels de frontière (mémoire flotte) : vote = échoue (erreurs corrélées), **liste vérifiable = gagne** ;
extraction verbatim fiable sur sources régulières (rappel 98-100 %), fragile sur markdown hétérogène ;
comptage **nulle part** sans recompte appelant.

## 4. Portes mécaniques (exécutées par le driver, jamais par un modèle)

1. **Porte schéma** — JSON parsable + clés exactes attendues.
2. **Porte verbatim** — toute valeur chaîne de la fiche doit être **sous-chaîne de la source**
   (toute valeur introuvable = fabrication ⇒ rejet + retry ciblé). C'est la porte qui rend la
   qualité « imparfaite mais sûre » : 0 fabrication prouvable mécaniquement.
3. **Porte rappel** — grep indépendant des marqueurs attendus sur la source (clore tout sweep).
4. **Recompte machine** — tous les comptes du livrable calculés par le driver, jamais par le modèle.

## 5. Candidat n°1 : triage de la file CoursIA (à valider par specs)

**Réalité mesurée 04/11 ~15:55 locale** (bulk, lecture seule) : jsboigeEPF 1 PR + 1 issue ·
jsboigeEpita 2 PRs + **24 issues** (23 dans `2025-Epita-Intelligence-Symbolique`) · jsboigeECE 0/0.
Lecture honnête : le volume du jour est petit — la valeur est dans la **récurrence par cycle**
(la file étudiante coule toute l'année) et dans le **pré-tri des 23 issues** d'un coup.

Forme (v0) :

1. **1 fetch bulk** (GraphQL : PRs ouvertes + `reviews[].state` + compteurs de commentaires en
   un seul appel — règle flotte : jamais d'appels per-item `gh`) → tranches ≤ 50 lignes par PR.
2. **Horde** `extracteur-fiche` : une fiche par PR/issue {numéro, titre, auteur, base, fichiers,
   états de review, activité}. Copie, pas d'analyse.
3. **Portes** (§4) sur chaque fiche.
4. **Directeur** range la file : oldest-first, drapeaux B.0 checkables mécaniquement
   (`CHANGES_REQUESTED` non adressé, threads inline non résolus, checks `check_run_state.py`),
   « à lire en premier ».
5. **Livrable fin de session** : un markdown — la file rangée + les fiches + ce que le
   coordinateur doit lire lui-même (la règle *Read Body Before Any Action* reste à lui : la
   horde produit l'**index**, jamais le **verdict**).

Interdits du candidat : verdict de contenu pédagogique, merge, comptage par le modèle,
appels per-item vers GitHub.

## 6. Ce qui bloque l'adoption aujourd'hui (mesuré, 04/11)

- **B1 — FrogNano est invisible des consommateurs** : pas dans le routage du hub claudish
  (le standard de consommation flotte), 0 requête externe depuis le 08/10. La seule voie =
  sk-agent direct depuis cette machine.
- **B2 — trois maillons cassés dans la chaîne** : `mini-fanout-extractor` absent du catalogue
  servi (fallback silencieux = les compteurs d'adoption mentent) ; canal fichier HS
  (`open_terminal` cassé, pas de LibreOffice — seul l'inline court marche) ; l'état de
  conversation meurt avec le processus (`self._threads = {}`).
- **B3 — aucun workflow consommateur n'existe** : les presets sont génériques ; personne n'a de
  *raison dépendable* d'appeler le mini. L'adoption est un usage, l'usage est un workflow dont
  quelqu'un dépend — c'est exactement l'objet de ce document.
- **B4 — les limites ne sont pas vendues correctement** : comptage interdit, verdicts interdits,
  > 50 lignes, rappel fragile sur markdown hétérogène. Ce sont des **contraintes de design**
  (§3-4), pas des blocages — le banc du 04/11 prouve 15/15 sur les tâches de délégation.
- **B5 — le split de propriété a parqué le sujet** : adoption → roo-extensions (« déclencheur
  chez roo-extensions ») sans traction. Le mandat user du 04/11 le relance : **conception = lane
  vllm**, câblage catalogue = roo-extensions, politique de file = CoursIA.

## 7. Répartition et rendez-vous

| Acteur | Volet |
| --- | --- |
| **roo-extensions** | **Product owner de sk-agent — la config est chez eux** : porte les personas au catalogue, répare `mini-fanout-extractor` absent, arbitre ce qui entre dans la chaîne |
| **po-2025:vllm** (cette lane) | spécification (ce document), driver BG + portes + mesure ; les personas définis ici sont **proposés** au catalogue, jamais déployés en parallèle chez nous sans empreinte commune (anti-dérive : le driver BG embarque les définitions **fingerprintées** sha256, identiques à celles du catalogue) |
| **CoursIA / CoursIA-2 / CoursIA-3** | specs (§8), fenêtre pilote, politique de file |
| RV | jsboige/vllm#205 + dashboard `global` |

## 8. Specs à prendre (demandées 04/11, échéance 05/11 12:00 locale)

Par lane consommatrice :

1. Quel travail de ton cycle coûte le plus de tokens/temps et reste **mécanique** ?
2. Quelle **forme de livrable** fin de session t'aiderait, vérifiable d'un coup d'œil ?
3. Que ne délégues-tu **pas** ?
4. Quelle source, quelle fréquence ?

## 9. Critères de succès du pilote (figés d'avance, avant toute mesure)

1. **100 %** des fiches passent la porte verbatim (0 fabrication).
2. **0** faux drapeau B.0 (précision des drapeaux = 100 % ; le rappel est mesuré et publié, pas exigé).
3. Le coordinateur relève **≥ 1 accélération actionnable** sur son cycle réel.
4. Coût consommateur mesuré : **< 1 000 tokens** par session (lancement + lecture du livrable).

## 10. Statut

v0 — squelette. **Rien n'est figé** avant retour des specs (§8). Aucun preset ni script écrit
avant les specs ; ce document est le contrat proposé, pas un livré.
