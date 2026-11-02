# Fiche de capacité servie — FrogNano-4B (po-2025:5003)

**Mesuré le 02/11/2026** sur le siège `myia-po-2025:vllm`, moteur en service depuis le
31/10 05:35:57Z (`RestartCount=0`, aucune interruption). Toutes les valeurs de cette fiche sont
**mesurées**, pas estimées : la commande de reproduction est en §8. Ce qui n'est pas mesuré est
listé en §9.

Destinataires : les lanes qui délèguent au tier mini (product owner du canal : `roo-extensions`).
Le but est qu'une décision de délégation devienne mécanique au lieu de demander une lecture.

## 1. Capacité

| Paramètre | Valeur mesurée | Source |
|---|---|---|
| Contexte servi (`max_model_len`) | **32 768 tokens** | `/v1/models` |
| Cache KV total | **426 473 tokens** | `vllm:cache_config_info{kv_cache_size_tokens}` |
| Type de KV | `fp8` | idem |
| `block_size` | 544 | idem |
| Concurrence max au contexte plein | **13,0** | `kv_cache_max_concurrency` |
| Préfixe partagé | activé, hash `sha256` | idem |
| Empreinte moteur | **4,288 GiB** RAM / 16 GiB | `docker stats` |
| VRAM | **14 548 / 16 384 MiB** | `nvidia-smi` |

**À retenir** : 426 473 tokens de cache pour un contexte de 32 768, soit **13 contextes pleins
simultanés**. La capacité n'est pas la contrainte à l'échelle d'une horde : 16 requêtes
simultanées sur une délégation de 1 341 tokens n'occupent que **5 %** du cache.

## 2. Débit et latence (mesurés)

Corpus de mesure : 32 lignes de la forme du journal du gouverneur, instruction d'extraction
verbatim des lignes `WARN` — c'est-à-dire **une délégation réelle**, pas un prompt synthétique.
Décodage glouton (`temperature=0`), `max_tokens=192`, streaming.

| Concurrence | Débit agrégé | Débit par requête | TTFT médian | TTFT max | Latence médiane | Latence max | Erreurs |
|---|---|---|---|---|---|---|---|
| **N=1** | **115,2 tok/s** | 115,2 tok/s | **0,09 s** | 0,09 s | **1,32 s** | 1,32 s | 0/1 |
| **N=8** | **532,2 tok/s** | 68,4 tok/s | 0,55 s | 0,83 s | 2,22 s | 2,28 s | 0/8 |
| **N=16** | **829,1 tok/s** | 54,4 tok/s | 0,70 s | 1,30 s | 2,79 s | 2,92 s | 0/16 |

Lecture : le débit agrégé **×7,2 entre N=1 et N=16**, alors que le débit par requête ne perd que
53 %. C'est le profil attendu d'un petit modèle sur une seule carte — **la horde est le bon usage,
la requête unique est le mauvais**.

## 3. Qualité sous charge (vérifiée, pas supposée)

La vitesse ne vaut rien si la sortie se dégrade. Chaque échantillon a été recompté contre le
corpus **attendu** (4 lignes `WARN` sur 32) :

| Concurrence | Lignes rendues | Attendu | Verbatim | Fabriquées | Manquantes |
|---|---|---|---|---|---|
| N=1 | 4 | 4 | **OUI** | 0 | 0 |
| N=8 | 4 | 4 | **OUI** | 0 | 0 |
| N=16 | 4 | 4 | **OUI** | 0 | 0 |

**La qualité tient à N=16**, sur cette classe. C'est le point qui autorise une horde : à cette
charge, ce n'est pas le modèle qui se dégrade.

## 4. Coût d'une délégation

| Poste | Valeur mesurée |
|---|---|
| Prompt par appel | **1 341 tokens** |
| Génération par appel | **152 tokens** |
| Total moteur par appel | **≈ 1 493 tokens** |

**Attention au contresens** : ce coût-là est celui **du moteur**. Le coût d'orchestration côté
appelant est d'un autre ordre — mesuré le 27/10 sur une horde de 30 shards : **57 369 tokens de
prompt moteur + 164 787 tokens de sous-agent**. La délégation n'économise des tokens que si elle
remplace une lecture que l'appelant aurait faite dans sa **propre** fenêtre de contexte. Sur un
fichier local et un critère littéral, `grep` reste gratuit — la délégation ne se justifie pas.

## 5. Modes d'échec connus (mesurés, à ne pas redécouvrir)

| Classe | Ce qui casse | Parade |
|---|---|---|
| Comptage | faux à 6, 7, 8 et 12 lignes ; sous-compte le mot `DONE` | **porte `partition`** — le compte devient un théorème |
| Seuil sur valeur de champ | trouve la ligne et **ne compare pas** le nombre | **porte `threshold`** — parse exhaustif obligatoire |
| Tableau quasi identique | filtre par pertinence au lieu de la colonne (2/4) | `grep` sur la colonne, ou grep de rappel systématique |
| Verbatimité | préfixe horodaté supprimé par intermittence (0/17 à 14/14 selon l'appel) | **vérifier à chaque appel**, jamais supposer |
| Agrégation | échecs dès 6 lignes | recompte par l'appelant, jamais d'agrégat délégué |
| Routage | un preset peut servir **un autre modèle** sans erreur | contrôler `model_used` dans chaque réponse |

## 6. Quand l'utiliser — et quand pas

**Bon usage** : extraction verbatim sur logs (98,6-100 % mesuré, robuste jusqu'à N=16), tri
mécanique, pré-filtrage d'un corpus volumineux, appels parallèles indépendants dont la sortie est
**vérifiable**.

**Mauvais usage** : tout comptage, seuil ou agrégat sans porte ; prose libre ; tableau dense ;
verdict, jugement, goût ; et tout critère littéral sur un fichier **local** (où `grep` gagne à
coût nul).

## 7. Ce que cette fiche garantit — et ce qu'elle ne garantit pas

Elle garantit la **capacité et la vitesse** à un instant donné, et que la classe verbatim tient à
N=16. Elle ne garantit **pas** que votre tâche appartient à cette classe : c'est à la **porte** de
le dire, pas à cette fiche.

## 8. Reproduire la mesure

```bash
python myia_vllm/scripts/adoption/bench_capacity.py --concurrency 1,8,16
```

Le script lit la clé depuis `myia_vllm/.env` (jamais en argument), construit le corpus à la forme du
journal du gouverneur, mesure TTFT et latence en streaming, et écrit `bench_capacity_out.json`.
La vérification de qualité recompte les échantillons contre le corpus attendu.

## 9. Ce que cette fiche ne dit pas

- Le comportement **au-delà de N=16** n'est pas mesuré.
- Le comportement **au contexte long** (32 K rempli) n'est pas mesuré : les chiffres ci-dessus sont
  obtenus avec un prompt de 1 341 tokens.
- Le débit **avec des prompts hétérogènes** n'est pas mesuré : ici les 16 requêtes partagent un
  prompt identique, ce qui avantage le cache de préfixe.
- Les modes d'échec du §5 sont ceux des classes **testées** ; l'absence d'une ligne ne prouve pas
  l'absence du mode d'échec.
