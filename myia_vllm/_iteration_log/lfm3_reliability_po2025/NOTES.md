# LFM3-1.7B — fiabilité comparée à FrogNano (po-2025, 03/11/2026)

**Question du user** : « S'il hallucine moins que FrogNano, on l'onboarde. »
**Réponse mesurée : NON. Il hallucine davantage.** FrogNano reste en production.

Fenêtre annoncée sur `global` avant le geste, `lfm3-eval` sur `:5023`
(overlay `vllm-openai-v0320-lfm3:v1`, `--trust-remote-code`, thinking OFF par
défaut), FrogNano restauré et **prouvé par génération réelle** (`frognano-4b` → `Paris`).

---

## 1. Le contrôle apparié qui tranche

Même corpus (22 lignes de `gpu-governor.log`), même prompt, même `temperature:0`,
même session. Oracle = `grep 'temp=31C'` sur le corpus → **14 lignes**.

| | `finish` | rendues | réelles | couverture | délibération dans `content` | fabrication |
|---|---|---|---|---|---|---|
| **FrogNano-4B** (prod) | `stop` | **13** | 13 | 13/14 | **0** | 0 |
| **LFM3-1.7B** (mt=1024) | `length` | 39 | 13 | 13/14 | **25** | 1 |
| **LFM3-1.7B** (consigne stricte, mt=1024) | `length` | 41 | 13 | 13/14 | **27** | 1 + 14 abrégées |

**Rappel identique** (13/14), **même ligne manquée** des deux côtés — la
`2026-11-03 02:12:03 WARN RAM basse free=3824MB temp=31C`, c'est-à-dire le
piège motif-vs-forme déjà documenté (`reference-mini-verbatim-prefix-instability`).
**La différence n'est pas le rappel, c'est la propreté de la sortie.**

FrogNano rend 13 lignes et s'arrête. LFM3 rend 41 lignes dont 27 qui ne sont
pas de la donnée :

```
Wait, let's list exactly from the given text:
Lines with "temp=31C" verbatim:
- 2026-11-02 13:02:02 ... temp=31C ...        <- ABREGEE, non verbatim
Let's extract each full line containing "temp=31C". I'll go through the original block:
1. 2026-11-02 12:02:02 HEARTBEAT temp=30C ... -> include    <- corpus re-dumpe annote
```

## 2. `enable_thinking:false` est COSMÉTIQUE sur ce checkpoint

C'est le fait le plus important de la fenêtre, et il contredit l'attente créée
par la correction du 03/11 matin (« le template expose bien `enable_thinking` »).

Le template fait bien ce qu'il annonce — il émet `<think></think>` pré-fermé —
mais **le modèle ne cesse pas de raisonner pour autant : sa délibération sort
en clair dans `content`**. Le flag supprime l'enveloppe, pas le comportement.
Sous difficulté (corpus court, filtre ambigu), le raisonnement fuit.

Secondaire mais réel : combiné à `--reasoning-parser deepseek_r1`, la sortie
partait **entièrement** dans `reasoning` avec `content` vide
(le parser cherche un `</think>` qui n'arrive jamais). Premier lancement de la
fenêtre : 5/5 tests à `content_chars=0`. Le parser a donc été retiré.

## 3. L'autre régime, et pourquoi il ne sauve pas le modèle

Sur le corpus **120 lignes avec budget suffisant** (`mt=4096`), LFM3 est bon :

| | `finish` | rendues | réelles | couverture oracle (42) | hors-motif | fabrication |
|---|---|---|---|---|---|---|
| LFM3 mt=4096 | `stop` | 115 | **115** | **42/42, 0 manquante** | 73 | **0** |
| LFM3 mt=2048 | `length` | 69 | 67 | 28/42 | 39 | 2 |
| FrogNano (référence) | `stop` | 40 | 40 | 40/42 | 0 | 0 |

LFM3 atteint une **couverture parfaite** que FrogNano n'atteint pas (42/42 vs
40/42, la différence étant justement les 2 lignes `WARN`). Mais il y arrive en
**recopiant 73 lignes hors-motif** : précision 42/115 = **37 %**, contre 100 %
pour FrogNano. Et le comportement **varie d'un run à l'autre** — même tâche,
même modèle, budget différent : propre sur 120 lignes, délibérant sur 22.

**Ce que ça donne en production** : un producteur dont la sortie contient
parfois la réponse, parfois la réponse + son raisonnement. Aucun consommateur
ne peut distinguer les deux sans une porte mécanique — ce qui est exactement
l'architecture qu'on a déjà.

## 4. Ce qui marche chez LFM3

À créditer, ce ne sont pas des échecs :

- **Piège d'hallucination** (« quelle ligne indique GPU > 90 % ? ») → `AUCUNE`.
  **Correct**, aucune ligne inventée sur une information absente du corpus.
- **Appel d'outil** → `finish=tool_calls`, `get_weather({"city":"Paris"})`
  bien formé, `qwen3_coder`. **La voie outil est fonctionnelle.**
- **Sanity** → `Paris.`, 3 tokens.
- **Comptage** → `31` pour un oracle de 42. Échec, mais **de la même famille
  que FrogNano** (frontière du comptage documentée) : aucun des deux ne compte.

## 5. Verdict

**On n'onboarde pas LFM3 comme remplaçant de FrogNano.**

Le critère du user était explicite — « s'il hallucine moins, on l'onboarde ».
Il hallucine **plus** : 27 lignes de délibération contre 0, et 14 formes
abrégées non-verbatim (`... temp=31C ...`) qui sont des fabrications de forme.
Sur la précision il perd aussi largement (37 % vs 100 %).

**Ce que LFM3 a de meilleur — 1,50× FrogNano à N=16 — ne s'achète qu'en
acceptant un producteur moins fiable.** Or le siège a **zéro trafic externe** :
payer en fiabilité pour un débit que personne n'utilise serait le mauvais échange.

**Statut retenu** : candidat documenté, non promu. Ré-ouvrable si (a) un
`chat_template` LFM3 ultérieur rende `enable_thinking:false` réellement
silencieux, ou (b) le siège reçoive du trafic où le débit de LFM3 serait le
facteur limitant — et dans ce cas **avec la porte mécanique devant**, jamais en
producteur direct.

**Le fait transférable** : sur ce siège, aucun modèle ne tient seul. FrogNano
manque des lignes silencieusement, LFM3 raisonne à voix haute. La fiabilité
vient de l'**oracle mécanique**, pas du choix du modèle — c'est la conclusion
du protocole test-time scaling, confirmée une fois de plus par un modèle
différent.

---

## Artefacts

| Fichier | Contenu |
|---|---|
| `.tmp/tts_corpus22.txt` | corpus 22 lignes |
| `.tmp/tts_oracle22.txt` | oracle `grep temp=31C` = 14 lignes |
| `.tmp/frog_22_ctrl.txt` | contrôle FrogNano (13 lignes, 0 délibération) |
| `.tmp/lfm3_22_strict.txt` | LFM3 consigne stricte (41 lignes, 27 délibération) |
| `.tmp/lfm3_22_mt1024.txt` | LFM3 consigne normale (39 lignes, 25 délibération) |
| `.tmp/lfm3_120_mt4096.txt` | LFM3 120 lignes (115 réelles, 42/42, 0 fabrication) |
| `.tmp/arch_corpus120.txt` | corpus 120 lignes |

## Piège de mesure rencontré (à ne pas répéter)

Premier jugement rendu avec `arch_oracle31.txt` — l'oracle du **corpus 120** —
appliqué au **corpus 22**. Résultat : « 13/42, 29 manquantes », c'est-à-dire un
verdict catastrophe entièrement fabriqué par le juge. Reconstruit l'oracle sur
le bon corpus (`grep` sur `tts_corpus22.txt`), le vrai chiffre est 13/14.
**Le juge peut fausser avant le producteur** — déjà consigné, refait ici.
