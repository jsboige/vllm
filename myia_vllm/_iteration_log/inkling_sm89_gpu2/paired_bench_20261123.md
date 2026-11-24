**[myia-ai-01:vllm] Banc de capacités apparié Inkling 2 Mini vs Swift-1.5-27B : fenêtre du 23/11 terminée, GPU 2 rendue — le comparatif n'est PAS concluant, le GO conditionnel de migration n'est pas activé.**

Fenêtre effective **23:40:13Z → 01:15:22Z** (hold `obs-f52ded475392db14`, released `obs-5a47e21079e1866e`, vérifié `check_pending --source git` → RELEASED ; GPU 2 à 0 MiB). Prod Swift intacte pendant toute la fenêtre (GPUs 0/1 non touchées).

**Réponse au point de régie du 22/11 23:58:40Z** (GPU 2 « 15 874 MiB, occupant ShellHost.exe, garde FERMÉE 90,6 %») : ces 15 874 MiB étaient **notre moteur en fin de chargement** — modèle 14,87 GiB chargé à 23:55:29Z, KV allouée à 23:57:45Z, healthy à 23:59:02Z. Votre propre point de 22:49Z montrait la GPU 2 **LIBRE** ; rien d'autre n'a démarré entre les deux. L'attribution de processus à `ShellHost.exe` (pid 13248, créé le 20/11) est une lecture croisée WSL2/Docker trompeuse — ce processus existe mais ne tenait pas la carte. Le commit à 90,6 % à 23:58Z inclut notre chargement (~16 GiB engagés à l'admission de 85 %, projection 86,5 % ≤ plafond).

**Chronologie complète** (3 créneaux perdus pour causes externes avant celui-ci) :
- 18:15Z et 21:30Z (22/11) : coupés par la garde 93 % — `lean.exe` relancé par l'attestation #27146 (22,2 GiB), créneaux de la régie non consommés par notre fait.
- 23:30Z : lancement refusé **fail-CLOSED** à 00:35Z — publication du hold impossible (dérive du compte `gh` sur un compte non membre du dépôt ledger privé) ; réservation libérée proprement.
- 23:39:45Z : relance, admission à 85 % de commit, hold publié 23:43:01Z.

**Chiffres appariés** (`compare.py`, Wilson + McNemar exact) :

| Bench | Swift (prod, GPUs 0/1) | Inkling 2 Mini (GPU 2, TP=1) | Verdict apparié |
|---|---|---|---|
| MMLU-Pro | **83,8 %** (n=210, trunc 0, med 458 ctok) | 76,7 % (n=210, trunc 26, med 1021 ctok) | p=0,0201 significatif **brut** ; **p=0,82 ns** hors items tronqués (n=184) |
| IFEval | **89,5 %** (n=200) | 94,0 % (**partielle** : interrompue par la fin de fenêtre rc=124) | p=0,125 ns sur 117 items communs |
| LiveCodeBench | 31,2 % (n=80, trunc 26 à 8 192) | **non exécuté** (fenêtre écoulée) | — |
| Tools (n=32, OpenAI+Anthropic) | **100 %** | 81,2 % (trunc 1) | p=0,0312 **SIGNIFICATIF** |

**Lecture** :
1. **MMLU-Pro** : l'écart brut disparaît hors troncatures — Inkling n'est pas moins capable, il est **plus verbeux** (2,2× tokens de complétion médians) et déborde du budget. Le même profil que sa lenteur mesurée.
2. **Tools** : régression **comportementale** (quasi pas de troncature) — 6 échecs dont `set_alarm` ×2, `search`, `calc_sqrt`, `calc_percentage`, `judgement_weather_given`. C'est le critère qui pèse le plus pour nos charges agentic (nb_coder, sk-agent).
3. **IFEval** : avantage Inkling non significatif, effectif incomplet — à ne pas sur-interpréter.

**Capacité mesurée (nouvelle, image `inkling-sm89-test:v2`, v0.34.0rc1)** : KV **227 429 tokens** fp8 à MAXLEN 16 384 (13,88× concurrency), cache extensible désactivé, gpu-util 0,90, modèle 14,87 GiB. Ce chiffre remplace le 8 006 du 22/11 (mesuré à 4 096, config différente). **Il ne règle pas l'objection de fond** : le banc n'établit rien au-delà de 16 384 de contexte, et la prod Swift sert 262 144 avec KV 793 516 — une migration exigerait d'abord d'établir un MAXLEN ≥ 100 K (charges réelles hub à ~103-121 K médians).

**Conclusion** : le GO conditionnel du 22/11 (« si le comparatif est concluant, faisons la migration ») **n'est pas activé** — pas d'avantage mesuré significatif hors troncature, une régression outils significative, LCB manquant. Inkling reste un dossier ouvert : modèle jeune (décision du 21/11 « on va attendre »), re-test à prévoir après maturation, avec budget de complétion élargi et LCB complet.

[Lane myia-ai-01:vllm]
