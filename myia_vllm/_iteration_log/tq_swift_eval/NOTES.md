# TurboQuant k8v4 KV sur Swift-1.5-27B — évalué et REJETÉ (2026-10-09, GO user)

**Mandat** : user, crise de crédits Minimax en cours — « Tu peux le tester maintenant
avant la bascule Haiku, ça serait un vrai plus ». Contexte : le failover Haiku sur Swift
s'arme (claudish #431), la capacité KV long-contexte est le paramètre en question.

## Setup

Même profil `medium-swift15-27b.yml`, **aucune modification de fichier** — override
d'environnement compose : `KV_DTYPE_SWIFT15=turboquant_k8v4 docker compose … up -d`
(le profil rend `--kv-cache-dtype ${KV_DTYPE_SWIFT15:-fp8}`). Rollback = recreate sans
l'override. Deux moteurs frais consécutifs, même image (v0.31.0), même compile-cache
(`…-v0310`, boots chauds ~6,5 min), **même charge live** (~65 req/min mesurées §5ter,
cf. leçon PR #104 : frais-vs-frais même-heure uniquement).

- **TQ** : recreate 17:00:46Z, sain 17:07Z.
- **fp8** : recreate ~17:10Z, sain 17:16:55Z (KV 424 610 confirmé au boot).

## Résultats

**Agrégat decode (bench 48 prompts distincts, temp 0, sans thinking) :**

| N | TQ t/s | fp8 t/s | Δ TQ |
|---|---|---|---|
| 1 | 23,8 | 35,4 | **−33 %** |
| 2 | 36,3 | 46,8 | −22 % |
| 4 | 24,3 *(stall 24 s)* | 86,3 | −72 % *(faussé par le stall)* |
| 8 | 110,6 | 161,5 | −32 % |
| 16 | 233,3 | 313,9 | **−26 %** |
| 24 | 429,6 | 485,4 | −11 % |
| 32 | 547,0 | 568,1 | −4 % |
| 48 | 650,6 | 680,5 | −4 % |

**Prefill 157K** (sonde mots distincts, anti-prefix-cache) : TQ **1 307** vs fp8
**1 362** t/s (−4 %, dans le bruit — un seul passage chacun).

**Capacité & ressources :**

| | TQ k8v4 | fp8 |
|---|---|---|
| KV GPU tokens | **556 156** (+31 %) | 424 610 |
| Concurrency @262 144 | 2,12× | 1,62× |
| VRAM à froid GPU 0/1 | 20 934 / 20 018 (+~1 GiB) | 19 891 / 18 928 |

Le ratio ×1,31 extrapolé du MoE (788 417→1 030 407) tombait exactement.

## Découverte positive : TQ × offload RAM coexistent

Première combinaison jamais testée des deux mécanismes — **elle marche** :
`CPUOffloadingSpec` créée sur les deux workers, région `/dev/shm` 25,75 Go posée,
`kv_offload_store_bytes` coulant dès la première fenêtre de 10 s (1,05 Go stocké sous
trafic réel). Donc si un jour la capacité prime sur la vitesse, le chemin existe :
TQ (556K GPU) + tier (~900K à débit réduit) ≈ 1,45 M tokens.

## Canari qualité : PASS

Génération réelle avec thinking sous TQ : raisonnement propre, calcul correct
(314 km / 127 km/h → 16 h 33), fait correct (Rhône), français bien formé,
`finish=stop`. Le KV 4 bits ne dégrade pas visiblement la sortie sur cette sonde.

## Verdict : REJET

- **TQ perd à tous les N** (−4 à −33 %), le pire en basse concurrence — taxe dequant
  par token quand le batch est petit. L'écart se resserre à N≥32 (−4 %) mais ne
  s'inverse jamais.
- **La capacité n'est pas la ressource rare** : à cap 4 lanes Haiku (~800-840K tokens),
  l'occupation fp8 est ~75 % d'un total de ~1,11 M (424 610 GPU + tier ~685K). La
  ressource rare du failover est la **vitesse decode** (Swift déjà 4-6× sous Haiku).
- L'anomalie N=4 TQ (wall 24 s) : occurrence unique, possiblement un interleave de la
  charge live ; sans weight décisif mais cohérente avec un chemin TQ moins robuste.

**Décision** : fp8 conservé. Le moteur est RESTÉ en fp8 par construction (le
contre-test l'y a laissé) — aucun geste de rollback supplémentaire n'a été nécessaire.
État final vérifié : health 200/4 ms, KV 424 610, 3 conteneurs, VRAM 19 891/18 928.

## Confondants et limites

- Charge live ~65 req/min pendant TOUTE la fenêtre (benchmark sophismes FR + trafic) :
  elle déprime les deux configs d'environ −25 % vs hier soir (fp8 N=16 314 vs 412).
  La comparaison même-conditions est la seule citée dans le verdict ; les valeurs
  absolues de ce jour ne sont PAS une baseline pour demain.
- Bancs mono-passage par config (sauf structure du sweep) ; l'ordre de grandeur des
  écarts (≥11 % sur 5 N sur 8) dépasse le bruit observé sur ces instruments.
- Prefill : un passage chacun — traité comme « à égalité », pas comme une victoire fp8.

## Réutilisation

Override en une commande, sans toucher au profil :

```bash
KV_DTYPE_SWIFT15=turboquant_k8v4 docker compose -f myia_vllm/configs/docker/profiles/medium-swift15-27b.yml --env-file myia_vllm/.env up -d
# retour : même commande sans l'override
```

À re-tester seulement si le besoin inverse (capacité >> vitesse) émerge — p.ex. si le
failover Haiku montre une pression KV que le tier ne absorbe pas.
