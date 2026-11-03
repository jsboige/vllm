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
| **Veille de journal par delta** (T1 = 6 lignes, T2 = 24 lignes ajoutées seulement) | 2/2 lignes `WARN` **verbatim**, `diff` byte-identique à l'oracle `grep` sur le corpus figé | **MARCHE** |

Le comptage échoue **alors même qu'au tour suivant le modèle a listé les 3 lignes correctement** :
ce n'est pas une perte de contexte, c'est la **frontière de comptage du modèle** (déjà documentée
en one-shot : échecs à 6, 7, 8, 12 lignes, et le mot `DONE` sous-compté). La conversation ne la
déplace pas. **Règle inchangée : toute sortie comptable est recomptée par l'appelant.**

## Ce que le conversationnel apporte *en plus* du one-shot

Un seul cas, mais il est structurel : **le corpus peut GRANDIR sans que l'appelant ait à le
détentir ni à le re-sérialiser**.

- **One-shot** (le mode mesuré jusqu'ici) : l'appelant doit reconstituer le journal entier
  (60 lignes ≈ 6-8 K tokens) et le renvoyer à chaque cycle.
- **Conversationnel** : l'appelant n'envoie que **le delta** (3-6 nouvelles lignes ≈ 300 tokens)
  et ne garde aucun état ; le serveur porte l'historique.

⚠ **Correction mesurée le 03/11 (ce que ce n'est PAS)** : l'historique est **re-lu par le moteur
à chaque tour**. Le prompt côté moteur ne reste donc pas au delta — il croît avec l'historique
accumulé. Test delta dédié (T1 = 6 lignes, T2 = 24 lignes ajoutées) : **+2 410 tokens de prompt
pour les 2 tours**, soit ~1 500 au T2 (historique + delta), pas ~300. L'économie réelle porte sur
**le payload que l'appelant construit**, pas sur les tokens que le moteur lit. Ce que le serveur
économise en calcul vient du **cache de préfixe** (le préfixe déjà vu n'est pas recalculé) — et
c'est maintenant mesuré **par tour**, pas seulement sur la vie du compteur (voir la table plus bas).

Forme d'usage : *« voici les lignes depuis ton dernier tour — qu'est-ce qui est nouveau ? »*
C'est **exactement la forme du cycle vigie**, en délégable. Mesuré : T1 (6 lignes, 0 `WARN`) →
`ok` ; T2 (24 lignes ajoutées, 2 `WARN` dont une de 155 caractères avec `<`) → **les 2 lignes,
verbatim, `diff` byte-identique** à l'oracle `grep` sur le corpus figé (`conv-vigie-delta-001`).

### Le cache de préfixe, chiffré par tour (l'instrument qui manquait)

Instantané `vllm:prompt_tokens_total` / `prefix_cache_hits_total` avant et après **un tour** de la
même conversation (T3, historique de 2 tours) :

| Compteur | Delta du tour |
|---|---|
| `prompt_tokens_total` | **+1 872** |
| `prefix_cache_hits_total` | **+1 632** |
| ⇒ tokens réellement préfilés | **240** |

**87,2 % du prompt est servi par le cache** : le moteur relit 1 872 tokens et n'en calcule que
240. C'est ce qui rend l'historique re-lu peu coûteux **en calcul**.

⚠ **Ce que le cache ne départage PAS** : un appelant one-shot qui renvoie le même journal d'un
cycle à l'autre bénéficie du même préfixe stable et des mêmes hits. **L'avantage du conversationnel
n'est donc pas économique — il est d'orchestration** (aucun état ni corpus à porter côté appelant).
À dire tel quel plutôt que de vendre une économie de tokens qui n'existe pas.

## Coût mesuré

Au **tour 6** d'une conversation (6 tours d'historique), le coût moteur de ce tour = **+1 118
tokens de prompt, +6 de génération** (compteurs `vllm:prompt_tokens_total` avant/après). C'est
bien le **prompt complet relu** (système + historique + nouveau tour), pas le seul delta.
Croissance linéaire dans l'historique accumulé : 20 tours de petits messages ≈ 3,5-4 K tokens de
prompt, négligeable face au contexte 32 K et au pool KV de 426 K (13 contextes pleins).

Comparaison honnête avec le one-shot, à contenu égal : **le prompt moteur est du même ordre**
(les deux renvoient tout le contenu), mais le conversationnel **délègue la reconstitution du
corpus au serveur** — c'est un gain de code appelant et de robustesse (pas de re-sérialisation,
pas d'état client), pas une division de la facture. Le gain de **temps**, lui, vient du cache de
préfixe : le préfixe déjà calculé n'est pas refait.

## Deux limites structurelles du `conversation_id` (mesurées le 03/11)

Le serveur sk-agent vivant sur ce siège est celui de `roo-extensions`
(`D:\dev\roo-extensions\mcps\internal\servers\sk-agent\sk_agent.py`) — lu en lecture seule.

1. **Les conversations vivent en mémoire du processus.** `self._threads: dict[str,
   ChatHistoryAgentThread] = {}` (`sk_agent.py:597`). Le serveur MCP est lancé **par session**
   (transport stdio) : un redémarrage de session tue toutes les conversations. Conséquence
   directe pour l'usage que ce doc propose : **la veille de journal par delta fonctionne DANS un
   cycle, pas ENTRE deux cycles** — un `conversation_id` réutilisé au cycle suivant repart vierge.
2. **Un `conversation_id` inconnu ne produit pas d'erreur : il crée un fil neuf, silencieusement**
   (`_get_or_create_thread`, `sk_agent.py:1368-1374`). Mesuré : `conv-adoption-hubert-001` →
   « Hubert » (la conversation existe) ; `conv-id-inexistant-999` → « inconnu » (fil neuf, aucune
   erreur, `model_used=frognano-4b` dans les deux cas). **Un appelant qui réutilise un id périmé
   croit avoir repris une conversation et en a ouvert une vide.** Garde : placer une **sonde de
   rappel** (« quel fait t'ai-je donné au premier tour ? ») en tête de tout tour repris, et la
   traiter comme un échec si la réponse ne restitue pas le fait.

**Ce que ça demande côté chaîne** (product owner `roo-extensions`, pas cette lane) : soit un
sk-agent **long-vivant** (transport HTTP plutôt que stdio-par-session), soit l'historique porté
par l'appelant. Sans l'un des deux, le mode conversationnel reste un outil **intra-cycle**.

## Fragilité à connaître (avant de déléguer)

- **L'état vit dans le processus sk-agent** (voir la limite 1 ci-dessus) : une conversation n'est
  pas un journal durable — le corpus de référence reste le fichier, pas l'historique du modèle.
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

**Variante veille par delta** (`conv-vigie-delta-001`, 2 appels, ~30 s) — corpus **figé sur
disque avant l'appel**, c'est le point qui rend l'oracle fiable :

- T1 : « Je te donne le début d'un journal. Lis-le et réponds seulement `ok` » + les 6 premières
  lignes (0 `WARN`).
- T2 : « Voici les NOUVELLES lignes du même journal, depuis ton dernier tour. Liste VERBATIM
  toutes les lignes `WARN` » + **uniquement** les 24 lignes ajoutées (2 `WARN`).
  → attendu **2/2 verbatim** ; contrôle `grep WARN corpus_B | diff - rendu` = **0 écart**.

Contrôles : `model_used=frognano-4b` à chaque tour ; delta `vllm:prompt_tokens_total` par tour.

## Où ça sert concrètement (propositions ouvertes au product owner)

| Usage | Pourquoi le conversationnel | Garde |
|---|---|---|
| Veille de journal (delta par cycle) | seul le delta est envoyé | extraction verbatim uniquement, jamais de compte |
| Tri au fil de l'eau (nouvelles issues/PRs) | le corpus grandit sans re-paiement | liste citée, jugement par l'appelant |
| Suivi de dossier multi-cycles | l'historique porte les faits déjà établis | état = fichier, pas conversation |

Voir aussi : `myia_vllm/docs/frognano-team-solve.md` (l'assemblée et les portes exécutables),
`myia_vllm/docs/frognano-capacity-sheet.md` (capacité one-shot du moteur).
