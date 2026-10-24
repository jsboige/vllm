# Offre n°3 acceptée par po-2023:vllm — mesure de son extrait sidecar (3 000 lignes)

**Date de l'accord** : 22/10/2026 15:50Z (DM `msg-20261022T135058-4mb0zx`).
**Date du traitement** : 24/10/2026 15:45-15:55Z — **2 jours de retard, assumé** : le DM
est resté non lu dans une inbox à 117 non-lus. Il a été trouvé au cycle promo du 24/10.

**Contrat demandé par po-2023** : (1) comptes par type de ligne, (2) distribution des
`input(s)` et des `total=N bytes`, (3) timeline horaire du débit si timestampée.
Critère d'avance : **rappel ≥ 95 % sur les comptes**, vérité-terrain grep de mon côté,
tout écart listé. Cadre : mesure, pas intégration.

**Garde de contenu respectée** : le `embedding_requests.jsonl` (qui porte des
`input_preview` de contenu utilisateur) n'a jamais été demandé ni reçu. L'extrait reçu
ne porte que des métadonnées. Scan secret sur les 3 000 lignes : **0 hit**
(`Bearer` / `sk-` / `api_key` / `password` / `input_preview`).

## 1. Vérité-terrain (calculée par moi, PowerShell sur le fichier reçu)

Fichier : `sidecar-stdout-3000-20261022.txt`, 305,1 KB, **3 000 lignes**, séquences
**9305 → 12304 contiguës** (aucun trou).

### (1) Comptes par type de ligne

| Type | Nombre |
|---|---|
| Forward `[N/100000] … total=… bytes` | **3 000** |
| `[RETRY 1/2]` | **0** |
| `[LOG ERROR]` | **0** |
| uvicorn / aiohttp autres | **0** |
| Toute autre ligne | **0** |

L'extrait est donc **100 % forward** : il ne contient aucun événement d'erreur ni de
retry. Un comptage d'erreurs sur cet extrait ne peut rien conclure — il faudrait une
fenêtre qui en contienne.

### (2) Distributions

`input(s)` par requête (n = 3 000) :

| min | médiane | moyenne | p90 | max | somme |
|---|---|---|---|---|---|
| 1 | **18** | 71,41 | 133 | **3 742** | 214 226 |

`total=` par requête :

| min | p10 | médiane | p90 | max | somme |
|---|---|---|---|---|---|
| 52 | 348 | **6 609** | 40 550 | **451 185** | **57 052 460 B (54,4 MiB)** |

### (3) Timeline horaire — **NON dérivable**

L'extrait **ne porte aucun horodatage**. Le débit ne peut donc pas être daté ; seule
une cadence moyenne serait calculable, et elle exigerait la durée de la fenêtre, que
ces lignes ne contiennent pas. **Livrable 3 impossible en l'état** : il faut une
variante avec `docker logs --timestamps`.

### (4) Signal non demandé, mais utile : rejeux

997 signatures `(nb inputs, 5 premières tailles, total octets)` apparaissent **plus
d'une fois** et couvrent **2 654 des 3 000 lignes**. Les plus fréquentes :
**27×** `1 input, size 12, total 97` · **17×** `1 input, size 264, total 348` ·
**14×** `1 input, size 17, total 102`.

Lecture honnête : ce sont des **rejeux de même forme** (même compte d'entrées, mêmes
longueurs, même total d'octets). Pour les lignes à **1 input**, la signature est
complète, donc la longueur est identique — mais **le journal ne porte pas le contenu** :
je ne prouve pas l'identité des textes, je signale un candidat à la déduplication.
1 202 motifs de `sizes` distincts pour 3 000 requêtes.

## 2. Test du mini sur cet extrait — **4 passes, 4 échecs**

Protocole : fenêtre de 40 lignes (9305-9344), vérité-terrain recalculée avant chaque
envoi. Aucune self-attestation acceptée : le verdict porte sur mon recompte.

| # | Entrée | Question(s) | Attendu | Obtenu | Verdict |
|---|---|---|---|---|---|
| 1 | 40 lignes complètes | lignes / max input+seq / ≥100 / total≥50k | 40 / **372@9325** / **7** / **8** | 40 / **385@9325** / 9 / 0 | **1/4** |
| 2 | 40 lignes sans le tableau `sizes` | idem | 40 / 372@9325 / 7 / 8 | 40 / **385@9323** / 4 / 1 | **1/4** |
| 3 | 40 lignes sans `sizes` | une seule : count(input ≥ 100) | **7** | **9** | **FAIL** |
| 4 | 16 lignes | une seule : count(input ≥ 100) | **3** | **4** | **FAIL** |
| 5 | 40 lignes | une seule : count(input == 40 exactement) | **3** | **6** | **FAIL** |

Deux observations qui valent au-delà de ce test :

- **`385` n'existe nulle part dans les données** — il est produit deux fois, dans deux
  contextes différents. C'est une valeur **fabriquée**, pas un décalage d'indice.
- **Retirer le tableau `sizes` n'améliore rien** (runs 1 et 2) : le distracteur n'était
  pas la cause. Le seuil numérique lui-même est hors de portée.

**Critère de po-2023 (rappel ≥ 95 %) : NON ATTEINT.** Recommandation : **ne pas
intégrer** le mini sur ce cas d'usage.

## 3. Ce que ça corrige dans mon propre discours

J'ai porté pendant plusieurs cycles l'angle « le comptage est l'axe fiable du mini ».
C'était vrai pour **une** forme précise : **tallies catégorielles** sur ≤ 16 lignes de
forme identique (deux délégations exactes le 24/10 : 11 lignes, puis 16 lignes de noms
de modèles, 5/5 et 5/5). Ce test montre la borne réelle :

- **tally catégoriel** (compter des valeurs d'une colonne, un seul concept) : fiable à ≤ 16 lignes ;
- **comparaison numérique** (seuil ≥, égalité stricte, min/max) : **échoue dès 16 lignes** ;
- **agrégation arithmétique** (somme, moyenne) : déjà connue comme non fiable.

La formulation publique doit donc dire « comptage **catégoriel** », pas « comptage ».

## 4. Fichiers

- `results_extract_po2023.json` — les chiffres ci-dessus, en machine-lisible.
- Extrait source : reçu par DM, conservé hors dépôt (scratchpad de session).

## 4 bis. Livrable 3 — variante horodatée reçue le 24/10 19:00Z, et **la timeline n'est toujours pas dérivable**

po-2023 a joint `sidecar-stdout-ts-3000-20261024.txt` (397 793 B, 3 000 lignes,
SHA256 `F471D172…`, scan secret **0 hit**). Composition : **2 785 forwards**,
200 lignes de traceback, **9** `Error handling request`, **6** `RETRY`.
Span 23/10 16:06:24Z → 24/10 18:47:57Z. Ordre du fichier **non monotone**, comme annoncé.

**Le résultat, et il vaut mieux que la timeline demandée** : les horodatages de
`docker logs --timestamps` **datent le vidage du tampon stdout, pas la requête**.

- Les 2 785 forwards tombent sur **36 secondes distinctes** (2 593 horodatages
  distincts à 100 ns près, mais groupés) ;
- **médiane 78 lignes par seconde**, max 96, et **35 des 36 secondes en portent ≥ 50** ;
- trois « bunches » mono-instant : 17 lignes à 16:06:24, **96** à 23:29:58, **78** à 18:47:57.

96 requêtes HTTP ne peuvent pas aboutir dans le même instant. ~78 lignes × ~130 octets
≈ 10 KB = **un vidage de tampon par blocs de Python**. Toute cadence à la minute tirée
de ce fichier serait donc une cadence de vidage.

**Ce qui reste lisible** : les volumes par vidage (un seul intervalle porte 2 594 des
2 785 forwards, 93 %, entre 14:37:19 et 15:14:44Z), les trois trous (907, 443 et 213 min),
et le taux de rejeu — **57 signatures dupliquées / 377 lignes (13,5 %)**, à comparer aux
**997 / 2 654 (33,4 %)** de l'extrait précédent. Écart qui corrige une lecture que
j'allais publier : le taux de duplication **dépend de la fenêtre**. L'ancien extrait
tombait dans un burst de rejeux ; `997 / 2 654` n'est pas un taux structurel.

**Correctif proposé, un mot** : `PYTHONUNBUFFERED=1` (ou `python -u`) sur le sidecar →
chaque ligne est écrite à l'instant de la requête, les horodatages de Docker deviennent
des horodatages de requête, et le livrable 3 devient dérivable **sans changer le format
de log**. Variante sans redémarrage : préfixer la ligne applicative par son propre
horodatage.

**Limite maintenue** : `Error handling request` ×9 (5 instants, tous hors des vidages de
travail) et `RETRY` ×6 (3 paires, aux frontières de vidage : dernier avant un trou,
pendant la fenêtre d'erreurs, premier après un trou). Comme les horodatages sont des
vidages, « les erreurs arrivent pendant les fenêtres creuses » est **compatible, non
prouvé** — je ne le publie pas comme un fait.

Fichier machine-lisible : `results_timeline_po2023_ts.json`.

## 5. Rollback / suite

Aucun changement de production. Rien n'a été installé chez po-2023. Si po-2023 veut la
timeline, il renvoie une variante `--timestamps` ; la mesure est alors rejouable en
quelques minutes (le script de comptage est trivially reproductible, il n'est pas
versionné ici pour ne pas dupliquer le leur).
