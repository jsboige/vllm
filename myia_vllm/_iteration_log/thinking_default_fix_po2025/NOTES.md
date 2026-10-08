# Correctif « thinking par défaut » — FrogNano-4B, siège po-2025

**Date :** 2026-10-08 (après-midi)
**Déclencheur :** signalement `[WARN]` de `myia-ai-01:vllm` (`vllm-sibling-5003-down-20261008`) —
qui s'est révélé porter **deux** sujets : une coupure de fenêtre (la mienne) **et** un défaut
d'utilité que personne n'avait chiffré.
**Mandat :** user 08/10 — « il faut des agents derrière qui vérifient que ce qui est produit est
valable. Et ça peut faire partie de votre périmètre d'optimiser **l'utilité** de vos modèles en
plus des perfs de servicing. »
**Profil touché :** `configs/docker/profiles/mini-frognano-4b-po2025.yml`

---

## 1. Le défaut

FrogNano est un **raisonneur**, et le **thinking est actif par défaut**. Le siège connaissait déjà
la moitié du problème — la doctrine « Sonde de vivacité : ne JAMAIS conclure sur `content` seul »
(datait du 08/10 aussi) traitait le cas de la **sonde qui crie au loup**. Ce qui n'avait pas été
vu est le versant **consommateur** :

- un appelant qui ne passe pas `enable_thinking: false` paie plein tarif pour un raisonnement
  dont il n'a pas besoin ;
- et sous un plafond de tokens courant, il ne reçoit **rien du tout**.

C'est le pire cas possible pour la promotion du tier « mini » : le modèle d'appoint le moins cher
de la flotte se présente comme **30× plus lent, 100× plus cher, et muet**.

## 2. La mesure (même moteur, même minute, même question)

Question : « Quelle est la capitale de la France ? Réponds en un mot. »

| `max_tokens` | thinking | latence | `completion_tokens` | `content` |
|---|---|---|---|---|
| 256 | **ON** (défaut) | **2,78 s** | **200** | `Paris` |
| 256 | OFF | **0,08 s** | **2** | `Paris` |
| 1024 | **ON** (défaut) | 2,43 s | 200 | `Paris` |
| 1024 | OFF | 0,08 s | 2 | `Paris` |
| ≤ 64 | **ON** (défaut) | — | épuisé | **VIDE** (`finish_reason=length`) |

Rapport mesuré : **×34 en latence, ×100 en tokens** pour une réponse strictement identique.
Le facteur ne dépend pas du budget : à 1024 comme à 256, le raisonnement coûte ~200 tokens fixes
avant le premier token de contenu.

**Contexte qui rend le défaut grave :** la consigne de promotion de la flotte est « privilégier
FrogNano pour ce qui coûte des tokens ». Sans le kwarg, l'expérience livrée est **l'inverse exact**
de l'argument de vente.

## 3. Le correctif

```yaml
--default-chat-template-kwargs '{"enable_thinking": false}'
```

**Drapeau vérifié avant emploi** dans l'image qui tourne (v0.31.0), pour ne pas risquer un échec
au boot : `vllm serve --help=default-chat-template-kwargs` → *« Should either be a valid JSON
string or JSON keys passed individually. (default: None) »*. Le dépôt l'emploie déjà sur plusieurs
profils medium (`preserve_thinking`).

**Pourquoi c'est le bon levier, et pas une rustine côté client :** le tier mini sert du travail
mécanique — résumer, cartographier, pré-trier, corriger un fichier. Le raisonnement y est un **coût
pur**. Le défaut doit donc être « rapide et juste » ; un consommateur qui veut délibérer l'active
**par requête**. Corriger côté client aurait multiplié les occasions d'échec silencieux (le piège
#2455 de la flotte) au lieu de le supprimer.

## 4. Vérification (les 5 portes, après recréation)

| # | Porte | Résultat |
|---|---|---|
| 1 | **Sans aucun kwarg** — le cas du consommateur externe | `0,43 s` · `finish=stop` · `ctok=2` · `content='Paris'` |
| 2 | `max_tokens=16` — le plafond qui rendait vide | `finish=stop` · `ctok=2` · `content='Paris'` |
| 3 | **Opt-in explicite** `enable_thinking=true` | réfléchit toujours : `ctok=200`, `reasoning_chars=646` |
| 4 | **Tool-calling** (`qwen3_coder`) | `finish=tool_calls`, `get_weather {"city":"Paris"}` |
| 5 | Santé + capacité | `healthy`, 0 erreur, **KV 421 582 tok (12,87×)** — au-dessus des 391 748 d'avant |

**Porte 3 = la plus importante** : elle prouve que le défaut est un **défaut**, pas un retrait de
capacité. Le raisonnement reste disponible, il cesse d'être imposé.

## 5. Fenêtre et effets de bord

- **Annoncée** sur `workspace-vllm` avant le geste (`po2025-vllm-window-thinking-default-fix-20261008`),
  ainsi qu'aux deux pairs concernés (`myia-ai-01:vllm` = testeur actif, `myia-po-2025:claudish` =
  propriétaire du hub).
- **Durée réelle : 132 s** (recréation `12:51:13Z` → prêt), contre ~4 min annoncées.
- **Coupure** : route hub `frognano-4b` / `mini` uniquement. `qwen3.6-35b-a3b` (ai-01) non touché.
- **Rollback armé** en un pas : `mini-frognano-4b-po2025-kvauto-rollback.yml` (même `container_name`,
  même volume de cache → retour chaud). Le `--default-chat-template-kwargs` se retire en effaçant
  une ligne.

## 6. Ce que ça change pour l'adoption (mandat flotte)

Avant : tout consommateur externe (Jamin, Candy, sk-agent hors presets, appel direct via
`models.myia.io`) recevait une réponse dégradée ou vide. **Après :** le comportement par défaut
est le bon, sans documentation ni kwarg à transmettre.

C'est la première correction de la lane qui relève du **périmètre « utilité »** et non des
performances de servicing : aucun gain de débit, mais le débit existant devient *utilisable*.

## 7. Preuve brute

- `evidence_5003_window.txt` — log moteur horodaté capturé **avant** recréation (les logs meurent
  avec le conteneur) : 71 `POST /v1/chat/completions`, **toutes 200**, fenêtre `11:43:36Z → 12:50:24Z`.
  Sert à établir que les échecs signalés par ai-01 tombent dans la fenêtre de promotion, et que
  leur horodatage était en **heure locale étiquetée Z** (`Get-Date -Format u`).

## 8. Leçon à ne pas perdre

**Un signalement de panne peut masquer un défaut d'utilité.** ai-01 signalait une coupure ; la
coupure était réelle mais brève et la mienne. En allant mesurer le chemin exact plutôt que de
répondre « c'est sain maintenant », la même investigation a fait sortir un défaut **permanent**,
présent depuis la mise en service, qui aurait sabordé la promotion en cours. **Répondre à un
signalement par une mesure, pas par un statut.**
