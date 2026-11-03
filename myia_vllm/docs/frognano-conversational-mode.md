# FrogNano-4B en mode conversationnel (sk-agent) — ce qui marche, mesuré le 03/11/2026

Mandat user du 02/11 soir : « continue à te battre pour doper l'adoption via sk-agent en
conversationnel ». Ce document est la preuve servie : une capacité **nouvelle** (le
`conversation_id` persistant de sk-agent) mesurée sur le moteur réel, avec sa frontière exacte.

**Pour qui** : les lanes qui délèguent du travail au tier mini. Le product owner de la chaîne
sk-agent est `roo-extensions` (décision user 02/11) ; ce document est l'input *serving* qui lui
manquait pour décider **quoi déléguer en conversationnel** — il ne duplique pas son mandat.

## Le résultat en une table

Conversation `conv-adoption-fidelite-001` (mémoire de faits) et `conv-adoption-increment-001`
(journal croissant sur 2 tours, 6 lignes, 3 WARN) :

| Classe de tâche en conversationnel | Mesure | Verdict |
|---|---|---|
| Mémoire de faits entre tours | « Je m'appelle Hubert » → T2 : « Votre prénom est Hubert » | **MARCHE** |
| Rappel ordonné de 3 faits sur 4 tours | `ALPHA\nBETA\nGAMMA` exact, dans l'ordre | **MARCHE** |
| **Extraction incrémentale** (partie 2 ajoutée au tour suivant) | 3/3 lignes WARN **verbatim** sur les 2 parties | **MARCHE** |
| Comparaison inter-tours (min de `free=`) | `2900MB` — la bonne valeur, tirée de la partie 2 | **MARCHE** |
| **Comptage à travers les tours** | demandé le total (attendu 3) → a répondu **`2`** | **ÉCHEC** |

Le comptage échoue **alors même qu'au tour suivant le modèle a listé les 3 lignes correctement** :
ce n'est pas une perte de contexte, c'est la **frontière de comptage du modèle** (déjà documentée
en one-shot : échecs à 6, 7, 8, 12 lignes, et le mot `DONE` sous-compté). La conversation ne la
déplace pas. **Règle inchangée : toute sortie comptable est recomptée par l'appelant.**

## Ce que le conversationnel apporte *en plus* du one-shot

Un seul cas, mais il est structurel : **le corpus peut GRANDIR sans être renvoyé**.

- **One-shot** (le mode mesuré jusqu'ici) : chaque cycle renvoie tout le journal (60 lignes
  ≈ 6-8 K tokens). Sur 12 cycles/jour, c'est 12 × le même contenu re-payé.
- **Conversationnel** : chaque tour n'envoie que **le delta** (3-6 nouvelles lignes ≈ 300 tokens) ;
  le serveur garde l'historique et le cache de préfixe. Le modèle répond sur l'ensemble.

Forme d'usage : *« voici les lignes depuis ton dernier tour — qu'est-ce qui est nouveau ? »*
C'est **exactement la forme du cycle vigie**, en délégable.

## Coût mesuré

Au **tour 6** d'une conversation (6 tours d'historique), le delta moteur d'un tour = **+1 118
tokens de prompt, +6 de génération** (compteurs `vllm:prompt_tokens_total` avant/après).
Croissance **linéaire** (~180 tok/tour de contenu accumulé) ⇒ 20 tours ≈ 3,5-4 K tokens de prompt :
négligeable face au contexte 32 K et au pool KV de 426 K (13 contextes pleins).

## Fragilité à connaître (avant de déléguer)

- **L'état vit dans le processus sk-agent** : un restart du serveur sk-agent **tue les
  conversations**. Une conversation n'est pas un journal durable — le corpus de référence reste
  le fichier, pas l'historique du modèle.
- **Le mode conversationnel ne rend pas le modèle meilleur** : il rend le *transport* incrémental.
  Les classes refusées (comptage, jugement, verdict) le restent.
- **`model_used` se contrôle à chaque réponse** : un preset mal nommé retombe silencieusement sur
  un autre modèle (mesuré 26/10 : `agent:"frognano-4b"` → servi par `analyst`/swift sans erreur).

## Recette de reproduction (7 appels, ~2 min)

Via le MCP sk-agent (`mcp__sk-agent__call_agent`), preset `mini-summarizer`, même
`conversation_id` à chaque tour :

1. « Je m appelle Hubert. Retiens ce prenom et reponds seulement: note. » → attendu `note`
2. « Quel est mon prenom ? » → attendu `Hubert`
3. « Retiens ce mot-cle : ALPHA. Reponds seulement: ok. » (idem BETA, GAMMA)
4. « Liste, dans l ordre, les trois mots-cles. » → attendu `ALPHA\nBETA\nGAMMA`
5. « Voici la PARTIE 1 … (3 lignes, 1 WARN). Combien de lignes WARN ? » → attendu `1`
6. « Ajoute la PARTIE 2 … (3 lignes, 2 WARN). Combien au TOTAL ? » → **rendu `2`, attendu `3`
   — l'échec est le résultat attendu de la frontière de comptage**
7. « Sans compter : liste VERBATIM toutes les lignes WARN du journal complet. » → attendu
   **les 3 lignes, verbatim**

Contrôles : `model_used=frognano-4b` à chaque tour ; delta `vllm:prompt_tokens_total` par tour.

## Où ça sert concrètement (propositions ouvertes au product owner)

| Usage | Pourquoi le conversationnel | Garde |
|---|---|---|
| Veille de journal (delta par cycle) | seul le delta est envoyé | extraction verbatim uniquement, jamais de compte |
| Tri au fil de l'eau (nouvelles issues/PRs) | le corpus grandit sans re-paiement | liste citée, jugement par l'appelant |
| Suivi de dossier multi-cycles | l'historique porte les faits déjà établis | état = fichier, pas conversation |

Voir aussi : `myia_vllm/docs/frognano-team-solve.md` (l'assemblée et les portes exécutables),
`myia_vllm/docs/frognano-capacity-sheet.md` (capacité one-shot du moteur).
