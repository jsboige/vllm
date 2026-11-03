# LFM3-1.7B overlay v0.32.0 — fenêtre d'éval 02/11/2026 (GO user)

Question fondatrice : « la fiche HF mentionne vLLM, qu'est-ce qui bloque ? »
Réponse vérifiée le 02/11 : **LFM3 n'existe pas dans vLLM** (upstream main : `lfm3.py`
404, registry 5 entrées Lfm2 / 0 Lfm3). La carte HF liste « BF16 → vLLM » mais le
lien pointe vers une page de doc **LFM2.5** — doc en avance sur le code. Le support
arrive par PR **vllm-project/vllm#64959** (ouverte le 01/11, autonome : elle embarque
le kernel width-7 de #64647).

## Le greffe (image `vllm-openai-v0320-lfm3:v1`)

Recette nanbeige : stock v0.32.0 **pinné par digest**
(`sha256:befccf0e…`) + 3 fichiers runtime copiés dans dist-packages :
`models/lfm3.py` (391 l., NOUVEAU), `models/registry.py` (+1 ligne),
`layers/mamba/ops/causal_conv1d.py` (kernel width-7). Preuves au build :
apply 3-way PROPRE (préimage v0.32.0 vs main driftée), préimage **byte-identique**
(sha256 cb16cc92… / 16ed7ca9…), asserts registry+imports dans le RUN, LABELs.
Source : `myia_vllm/configs/docker/overlay_v0320_lfm3/` (PR jsboige/vllm#330).

Poids : 3,3 GB via `hf download` — **gotcha Xet confirmé une 3e fois** (stub 5 KB
silencieux, exit 0) : `HF_HUB_DISABLE_XET=1` + vérif `du -sh`.

## Fenêtre exécutée (annoncée sur `global` AVANT le geste, règle du jour)

| Heure (UTC) | Événement |
|---|---|
| 15:24:31 | FrogNano `docker stop` — VRAM 0 MiB, 16 s de settle |
| ~15:25 | `lfm3-eval` up sur :5023 (`--max-model-len 32768 --gpu-memory-utilization 0.80 --trust-remote-code`) |
| ~15:27:35 | **HEALTH 200 en ~150 s** ; arch résolue `Lfm3ForCausalLM` |
| ~15:28-15:30 | Génération réelle ×2, bench N=1/8/16, sonde thinking-off |
| 15:30:58 | `docker rm -f lfm3-eval` |
| 15:31:17 | FrogNano `docker start` (16 s de settle respectés) |
| ~15:33 | FrogNano health 200 (~90 s, boot chaud) + **génération réelle** : réponse directe 27/9 tokens |

**Durée totale ~8,5 min** (annoncée ~20). Aucun incident.

## Faits moteur (VERIFIÉ)

- **KV 408 734 tokens** à gpu-util 0,80 / ctx 32 768 → **12,47× concurrence**
  (FrogNano même carte : 426 473 → 13,0× — parité de capacité, KV `auto` bf16)
- Modèle **3,36 GiB**, chargé en 42 s ; conteneur 3,1 GiB RAM
- `--trust-remote-code` requis (config custom_code)
- Warning serveur : template **system-first** (les system messages inline des
  clients Claude-style cassent le prefix cache) — sans importance pour l'éval

## Le point bloquant : LFM3-1.7B est un modèle THINKING

La génération inline `…raisonnement…</think>réponse` dans `content`, sans
séparateur (pas de reasoning parser configuré). Conséquence mesurée au bench :
`ctok = max_tokens × N` **exactement** (192/1536/3072) — le budget part entier
en `<think>`, la réponse ne sort jamais sous plafond court. `verbatim=NON` aux
3 niveaux. **Sonde thinking-off par system-prompt : NE COUPE PAS** (le `</think>`
reste) — le bloc est ouvert par le template lui-même. Couper exigerait un
`--chat-template` custom ou un `--reasoning-parser` adapté (NON TESTÉ, hors
fenêtre). Même classe de pathologie que FrogNano avant le correctif du 08/10.

## Bench (bench_capacity.py, corpus gouverneur 32 lignes, même protocole que la fiche FrogNano)

| N | LFM3-1.7B agg tok/s | FrogNano agg tok/s | ratio | TTFT med |
|---|---|---|---|---|
| 1 | 110,8 | 115,2 | 0,96× | 0,04 s |
| 8 | 615,1 | 532,2 | 1,16× | 0,43 s |
| 16 | **1 245,9** | 829,1 | **1,50×** | 0,22 s |

0 erreur sur 25 requêtes. **Mécaniquement supérieur en charge** (1,50× à N=16,
TTFT bas), mais le débit compte des tokens de pur raisonnement — pour la classe
d'usage délégation/verbatim, le score utile est nul tant que thinking n'est pas
coupé ou séparé.

## Verdict

**FrogNano reste en prod.** Le greffe prouve que LFM3-1.7B est **servable dès
aujourd'hui** (boot propre, KV parité, débit 1,5×) — mais pas **utilisable** pour
nos charges sans travail de template. Parké : overlay + image + poids conservés ;
à rouvrir quand (a) template/reasoning-parser testé, ou (b) upstream #64959
mergé → re-test sur stock pur, overlay retiré.

---

## ⚠ CORRECTION 03/11/2026 — le « point bloquant » ci-dessus est FAUX

Le verdict du 02/11 affirmait « thinking inline non séparable, couper exigerait un
`--chat-template` custom ou un reasoning-parser ». **Vérification faite dans le
checkpoint lui-même** (`~/.cache/huggingface/hub/models--LiquidAI--LFM3-1.7B/
snapshots/ac2586a34f1a1c03329dbdcdefabd8b6478ddaa7/chat_template.jinja`, 12 129 c) :

| Fait | Preuve |
|---|---|
| **`enable_thinking` est natif** | l. 3 `{%- set enable_thinking = enable_thinking \| default(true) -%}` |
| `false` ⇒ bloc think **vide** | l. 273-280 `{%- if enable_thinking -%}{{- "<think>" -}}{%- else -%}{{- "<think></think>" -}}` |
| `preserve_thinking` existe aussi | l. 2 |
| **le template rend les outils** | 22 occurrences de `tools`, format `<tool_call>\n<function=NAME>\n<parameter=k>` (famille qwen3-coder) |
| **un parser générique existe déjà** | `vllm/reasoning/deepseek_r1_reasoning_parser.py` : `start_token="<think>"`, `end_token="</think>"` |

**Erreur méthodologique** : la « sonde thinking-off » du 02/11 était un **system
prompt** (« réponds sans raisonner »). Ce n'est pas le mécanisme du template : le
bloc `<think>` est émis parce que `enable_thinking` vaut `true` **par défaut**, pas
parce qu'il serait inconditionnel. J'ai conclu sur un test qui ne pouvait pas
marcher, sans passer `chat_template_kwargs`.

**Ce qui reste vrai** (et n'est pas une propriété du modèle) : sans
`--reasoning-parser`, l'API rend le raisonnement **dans `content`** et
`ctok = max_tokens` sous plafond court. C'est une configuration, pas une limite.

**Ce qui reste NON MESURÉ** et conditionne toute bascule :

1. comportement avec `enable_thinking: false` (répond-il vraiment, sans délayer ?) ;
2. **verbatim** aux 3 niveaux dans ce mode (la classe servie) ;
3. **fiabilité des appels d'outils** (jamais testée sur ce modèle).

Re-test court (~6-8 min, même fenêtre que le 02/11) : `chat_template_kwargs
{"enable_thinking": false}` + gates verbatim + une sonde d'appel d'outil. À faire
**avant** de trancher entre LFM3 et FrogNano. Voir aussi
`myia_vllm/docs/frognano-seat-watchlist.md`.

**Leçon à garder** : une sonde qui échoue ne prouve pas que le mécanisme est
impossible — elle peut prouver qu'on a sondé le mauvais levier. Lire le template
avant de conclure sur le template.

## Gotchas pour successeurs

- `bench_capacity.py --base` attend l'URL **complète** de l'endpoint
  (`http://host:port/v1/chat/completions`), pas la racine — sinon 404 sec.
- `grep -P` sur cette machine/Git Bash échoue sur les locales
  (« supports only unibyte and UTF-8 locales ») pour extraire une clé de `.env` :
  utiliser `LC_ALL=C grep '^VAR=' | cut -d= -f2 | tr -d '\r'`.
- Xet stub (3e occurrence) : voir ci-dessus.
