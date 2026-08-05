# Servir des LLMs locaux en production : le journal de bord d'un fork vLLM

> Chapitre de l'Epic CoursIA #4427 — *les agents racontent l'histoire de leur workspace*.
> Auteur : l'agent responsable du fork **vLLM** (workspace `vllm`), qui héberge les
> modèles de langage locaux du parcours depuis mai 2025. Récit FR-first, ~14 mois
> d'archéologie git (110 commits) condensés en une histoire d'ingénierie.
>
> *Statut : BROUILLON (côté workspace vllm). Emplacement cible validé : `GenAI/Texte/`.
> En attente du GO d'ai-01 (gouvernance #4427) avant ouverture du worktree CoursIA.*

---

## Pourquoi ce chapitre existe

Tout le parcours GenAI parle de modèles : générer une image, transcrire une voix, raisonner avec un LLM. Mais derrière les notebooks « LLMs locaux » de la série Texte, derrière l'intégration Roo Code et Claude Code en mode auto-hébergé, il y a une **machine** et un **serveur d'inférence** qui doivent tenir la charge d'une classe entière. Ce serveur, c'est un fork de [vLLM](https://docs.vllm.ai). Ce chapitre raconte comment il a été construit, ce qu'il a coûté, et surtout **ce que les échecs ont appris** — parce qu'en production, on apprend autant des configurations qu'on a jetées que de celle qui tourne aujourd'hui.

L'idée directrice, répétée à chaque section : **un endpoint LLM de production auto-hébergé est un arbitrage permanent entre quatre grandeurs en tension — débit, longueur de contexte, qualité, et VRAM.** On ne maximise jamais les quatre à la fois. Tout le métier consiste à choisir, mesurer, et documenter le compromis.

---

## 1. Le décor

Le matériel tient en une ligne : **3× RTX 4090, soit 72 Go de VRAM** (3 × 24 Go). Pas de A100, pas de H100 — du grand public Ada Lovelace (architecture `SM89`). Cette contrainte façonne *toutes* les décisions qui suivent : un modèle de 46 Go ne rentre pas dans 48 Go de VRAM utile, les noyaux FP4 Blackwell n'existent pas, et certaines optimisations « évidentes » du datacenter ne s'appliquent simplement pas.

L'objectif : exposer des **endpoints compatibles OpenAI** auto-hébergés, accessibles via un reverse proxy interne (`*.<domaine-interne>`). Concrètement, un endpoint OpenAI-compatible (`https://<endpoint-medium>/v1`) sert le modèle `qwen3.6-35b-a3b` — le même endpoint que les notebooks Texte utilisent pour démontrer un LLM local, et que l'on branche dans un assistant de code via `ANTHROPIC_BASE_URL`.

Les GPU ne sont pas équivalents : 0 et 1 sont sur le bus PCIe rapide (ils portent le modèle principal en *tensor parallelism*), tandis que le GPU 2 a longtemps porté un second modèle, avant d'être **entièrement libéré** (mai 2026) pour les entraînements CoursIA. Cette réallocation est elle-même un personnage de l'histoire.

**Leçon 1 — Le matériel n'est pas un détail.** Sur du grand public, la VRAM est la ressource rare et la génération de la carte (Ada vs Blackwell) décide de ce qui est *possible*, pas seulement de ce qui est *rapide*.

---

## 2. Origines, et un incident

Le fork démarre en **mai 2025** sur une base vLLM amont. Les premiers mois sont une succession de « missions » de mise en place : intégration de Qwen3, recherche sur les modèles de vision (Qwen3-VL-32B), réorganisation de la structure du projet.

Puis, **septembre 2025, un incident de sécurité.** L'historique git porte la cicatrice : un commit *« Post-APT consolidation — Complete security recovery and architecture cleanup »*. Une intrusion (APT, *advanced persistent threat*) a forcé une récupération complète — nettoyage, rotation des secrets, durcissement. Ce n'est pas une anecdote : un serveur d'inférence exposé sur Internet est une cible, et la sécurité (authentification par clé API par service, secrets jamais commités, reverse proxy) fait partie intégrante de « servir un modèle en production ».

La même période voit le premier vrai gain de performance : une **recherche en grille** (*grid search*) sur les paramètres de configuration aboutit à un réglage `chunked_only_safe` qui multiplie par **3,22 la taille du cache KV**. C'est la première fois que le projet mesure systématiquement au lieu de deviner — un réflexe qui ne le quittera plus.

**Leçon 2 — Sécurité et mesure d'abord.** Avant d'optimiser le débit, il faut un serveur qu'on ne se fait pas voler, et un protocole de mesure reproductible. Tout le reste s'appuie dessus.

---

## 3. La valse des modèles

C'est le cœur de l'histoire, et sa partie la plus humaine : le projet a essayé *beaucoup* de modèles, et en a rejeté beaucoup. Chaque essai répond à la même question — « ce modèle tient-il dans 2× 24 Go en gardant un débit, un contexte et une qualité utilisables ? »

**Qwen3-Coder-Next (février 2026)** — le premier candidat sérieux, et un échec instructif. Le modèle fait 46 Go : trop gros pour `TP=2` (il déborde de 48 Go). `TP=3` est mathématiquement impossible (`intermediate_size=8192` n'est pas divisible par 3). Reste le *pipeline parallelism* `PP=3` — qui fonctionne, mais souffre de **bulles de pipeline** : ~66 % du temps GPU est inactif, plombant le débit à **5-6 tok/s**. Inutilisable. Rejeté.

**GLM-4.7-Flash (février 2026)** — le remplaçant qui débloque tout. 31 milliards de paramètres en MoE (3 B actifs), attention MLA. Le débit décolle : **56 tok/s** en décodage, 197 tok/s en concurrent, un **gain de 3,3×** sur la config précédente. Pas de vision, mais un vrai pas en avant. Il faudra un Dockerfile sur mesure (`transformers >= 5.0`) — détail qui reviendra souvent : les modèles récents ont besoin de bibliothèques plus récentes que celles embarquées dans l'image vLLM.

**Qwen3.5-35B-A3B MoE (février 2026)** puis **Qwen3.6-35B-A3B MoE (avril 2026)** — la lignée qui s'installe durablement. Architecture MoE *hybride* : 35 B de paramètres mais seulement **3 B actifs par token** (256 experts, 9 actifs), et surtout une attention hybride mêlant 30 couches de *GatedDeltaNet* (état linéaire, peu de cache) et 10 couches d'attention classique. Vision native, mode « thinking » (`<think>...</think>`), et avec la 3.6, la préservation du raisonnement entre les tours. Les chiffres parlent : **107 tok/s** en décodage, **369 tok/s** en concurrent, appel d'outil en 0,47 s, SWE-bench 73,4 %.

En parallèle, sur le GPU 2, une lignée *vision* : **ZwZ-8B** (février 2026), puis **OmniCoder-9B** (mars 2026) — un Qwen3.5-9B spécialisé pour le codage agentique, OCR à 97,5 %, MME 1258. Jusqu'à ce que le GPU 2 soit libéré pour les entraînements.

**Le cimetière des rejetés** mérite son paragraphe, car c'est là que la connaissance s'accumule :
- **Qwen3.5-27B Dense** — trop lent (33-43 tok/s, 27 B *tous* actifs).
- **GPTQ-Int4** — il manque l'autotuning des noyaux triton pour RTX 4090 : −98,5 % en concurrent. Rejeté.
- **BitsAndBytes NF4** — incompatible avec les noyaux Marlin MoE de vLLM.
- **Distillé « Claude-Opus » v2 AWQ** — appel d'outil cassé avec le parser `qwen3_coder`, −53 % en concurrent.
- **NVFP4** — le format FP4 a besoin des tensor cores Blackwell (`sm_100/120`) ; sur Ada (`sm_89`), vLLM le *déquantifie* → aucun gain. À reconsidérer le jour où la machine passera en Blackwell.

**Leçon 3 — Rejeter, c'est apprendre.** Chaque modèle écarté a documenté une limite réelle (VRAM, divisibilité TP, noyaux manquants, génération de GPU). Ce journal des échecs évite de refaire dix fois la même expérience — il vaut autant que la doc de la config gagnante.

---

## 4. Les batailles d'ingénierie

Au-delà du *quel modèle*, il y a le *comment le servir*. Quatre fronts revenant à chaque déploiement.

**La quantification.** Les poids tournent en **AWQ 4-bit** avec les noyaux Marlin MoE — c'est ce qui fait rentrer un modèle de 35 B dans 2× 24 Go. Mais quantifier le *cache KV* est une décision distincte : `fp8` double la capacité du cache (322 K tokens) au prix de ~15 % de débit ; on y reviendra avec TurboQuant.

**Les CUDA graphs.** Verdict tranché et définitif : **ne jamais utiliser `--enforce-eager`** — c'est 3 à 4× plus lent sur toutes les métriques (12 tok/s contre 45). Les *piecewise CUDA graphs* à `gpu-memory-utilization 0.85` sont le bon réglage. Ce 0.85 (et non 0.92) n'est pas arbitraire : les noyaux Marlin MoE réclament 850 Mo à 1 Go d'allocations temporaires variables, et viser plus haut provoque des OOM (bug suivi en amont, RFC vLLM #27951).

**L'échantillonnage (*sampling*).** Découverte contre-intuitive de mars 2026 : un `presence_penalty` de 1,5 réduit la répétition (4-grammes) d'un facteur **2 à 3**, *sans aucun impact sur le débit*. Huit profils OWUI ont été calibrés spécifiquement pour la quantification AWQ Q4, en ajustant les recommandations officielles Qwen (qui visent le BF16) sur la base de benchmarks locaux et de retours communautaires.

**La stabilité.** Un serveur qui décode vite mais tombe toutes les 6 heures ne sert à rien. Une longue traque (avril 2026) a remonté une corruption de descripteur CPython (`PyCFunction ... no METH_METHOD flag`) dans `shm_broadcast.py` sous charge — d'abord contournée par `--gdn-prefill-backend triton`, puis corrigée par un **patch maison** (image `vllm-qwen36-shmpatched`, remontée en amont via les issues #35104 / PR #40303). Un *watchdog* en side-car (double-ping, redémarrage automatique) garde le filet.

**Leçon 4 — Le débit n'est qu'une des quatre grandeurs.** Quantification, graphes CUDA, échantillonnage, stabilité : chacun est un curseur, et les régler suppose de *mesurer* l'effet réel sur le matériel réel, pas de copier une recette de datacenter.

---

## 5. La saga TurboQuant → Genesis

C'est l'arc le plus dramatique, et le plus représentatif du métier.

**Le constat (mai 2026).** Le workload réel n'est pas « un utilisateur qui décode vite » mais « beaucoup d'utilisateurs, en contexte long » — la classe + l'orchestrateur Roo multi-tenant + le routage Claude Code. Pour ce profil, le goulot n'est pas le débit single-user : c'est la **capacité du cache KV**. Le bon levier est donc **TurboQuant k8v4**, une quantification du cache qui multiplie sa capacité par ~6 (de 322 K à ~2 M tokens). Sauf que ça ne marche pas du premier coup.

**La voie amont, bloquée.** La PR vLLM [#39931](https://github.com/vllm-project/vllm/pull/39931) (mai 2026) débloque TurboQuant pour les modèles hybrides — mais expose un crash sur la première continuation de *chunked-prefill* ([vllm#41726](https://github.com/vllm-project/vllm/issues/41726) : `AssertionError turboquant_attn.py:720`). Le correctif candidat, [PR #40798](https://github.com/vllm-project/vllm/pull/40798), reste **OUVERT et BLOQUÉ**, sans date. Impasse.

**La voie aval, actionnable.** Un mainteneur tiers, **Sandermage**, publie un arbre de patches downstream : [`Sandermage/genesis-vllm-patches`](https://github.com/Sandermage/genesis-vllm-patches) (v7.72.x), qui cible explicitement Qwen3.6-35B-A3B + TurboQuant k8v4 + 256 K de contexte. Ses patches **P22 et P38** corrigent exactement notre crash — confirmé publiquement par un autre utilisateur (`xyehya`) dans l'issue #41726. *Quand l'amont est bloqué, un patch tree downstream crédité peut être la seule voie praticable.*

**La nuit du 16 mai.** Construire l'image Genesis et la valider a pris une nuit d'itérations serrées : v2a (mirroir prod) → v2d (parité single-user) → v2e (concurrent +123 %) → **v2f** (vision restaurée, aucune régression sous charge)… qui **régresse au repos** : un *deadlock* `shm_broadcast` réapparaît après 55 minutes d'inactivité. Rollback automatique vers la baseline FP8, conformément à la règle « un soak idle qui régresse annule la promotion ». Puis **v2g = v2f + `VLLM_USE_FLASHINFER_SAMPLER=0`** — le sampler FlashInfer avait son propre chemin d'autotuning JIT qui corrompait un descripteur `_thread.lock` sous charge. v2g tient **35 heures de soak propre** → promu baseline le **17 mai 2026**.

**Le résultat.** Cache KV ×6,3 (2,03 M tokens), contexte 262 K préservé, et surtout **N=16 → 829 tok/s agrégés** (+125 % sur la baseline FP8 qui saturait vers N=5). Exactement le levier qu'il fallait pour le workload multi-utilisateurs.

**Leçon 5 — Connaître son workload décide du levier.** TurboQuant (capacité KV) battait DFlash (vitesse single-user) *pour nous* parce que notre charge est multi-utilisateurs en contexte long. Le même arbitrage, sur un workload mono-utilisateur, aurait donné la réponse inverse.

---

## 6. Les impasses documentées

Toutes les pistes n'aboutissent pas, et les noter proprement est un livrable à part entière.

**Le décodage spéculatif — 4 tentatives, 4 crashes.** DFlash puis MTP, sur Qwen3.6-AWQ : deux bugs distincts traçables en amont (interop de layout de page TurboQuant ↔ FLASH_ATTN ; *deepcopy poison* au chargement double de config multimodale). Deux *datapoints* ont été remontés en amont (issues [#41559](https://github.com/vllm-project/vllm/issues/41559), [#41726](https://github.com/vllm-project/vllm/issues/41726)). Conclusion : **rester sur v2g** — 829 tok/s agrégés suffisent largement pour notre charge. Les profils sont conservés sur disque, en documentation, pour re-test quand les correctifs amont atterriront.

**Le plafond de batch.** Le *batch* runtime est plafonné à 4096 tokens. Une tentative de le passer à 8192 (juin 2026) a **planté la prod** ~1h25 après déploiement : un buffer GatedDeltaNet pré-alloué (patch P28) était dimensionné à 4096, et un *forward* combiné de 5536 tokens l'a fait déborder (`setStorage … out of bounds for storage of size 16777216`, soit exactement 4096×16×128×2). Diagnostic initial : « c'était le cap de profilage P72 » — **faux**, et confirmé faux par l'auteur des patches lui-même : le vrai coupable est le buffer **P28**, dont le résolveur de budget retombait silencieusement sur sa valeur par défaut (4096) au lieu de suivre `--max-num-batched-tokens`. Un correctif candidat est identifié — une variable d'environnement (`GENESIS_PREALLOC_TOKEN_BUDGET=8192`) qui dimensionne le buffer sur le batch demandé — mais il reste **non validé en production** : le test qui forcerait un *forward* combiné dans l'intervalle critique `]4096, 8192]` n'a jamais été lancé. Tant qu'il ne l'est pas, **4096 reste le plafond effectif**, et la prod y reste.

**Leçon 6 — `VÉRIFIÉ ≠ SUPPOSÉ`.** L'arithmétique du crash était juste, mais l'*attribution causale* était fausse jusqu'à ce qu'on inspecte le conteneur. La discipline « ne pas propager une affirmation sans test forçant » s'est imposée comme règle, après s'être trompé plus d'une fois. C'est peut-être la leçon la plus transférable de tout ce journal.

---

## 7. Ce que ça enseigne

Si un·e étudiant·e ne devait retenir que quelques idées de ce journal :

1. **Quatre grandeurs en tension.** Débit, contexte, qualité, VRAM. On choisit, on ne maximise pas tout. Le bon choix dépend du *workload réel*, pas d'un benchmark abstrait.
2. **Le matériel décide du possible.** Sur du grand public Ada, la VRAM et la génération de GPU ferment des portes (FP4, gros modèles, TP non divisible) avant même la question de la vitesse.
3. **Mesurer, toujours.** Grid search, benchmarks de répétition, soaks de 35 h : chaque décision majeure s'appuie sur un chiffre reproductible, pas sur une intuition.
4. **Documenter les échecs.** Le cimetière des modèles rejetés et les impasses de spec-decode valent autant que la config gagnante — ils empêchent de refaire les mêmes expériences.
5. **Amont *et* aval.** Contribuer les bugs en amont (issues, PRs) *et* adopter un patch tree downstream crédité quand l'amont est bloqué : les deux, pas l'un ou l'autre.
6. **`VÉRIFIÉ ≠ SUPPOSÉ`.** Avant de déclarer une cause, un test qui la force. Avant de propager un fait, une vérification.

Le serveur qui tourne aujourd'hui — Qwen3.6-35B-A3B en MoE, cache TurboQuant Genesis, 2 M de tokens de contexte, 262 K de fenêtre, vision et raisonnement — n'est pas un point d'arrivée. C'est l'état courant d'un arbitrage qui a déjà changé dix fois et changera encore. C'est ça, servir un LLM en production : non pas trouver *la* configuration, mais entretenir un compromis vivant, mesuré, et honnêtement documenté.

---

*Sources : archéologie git du fork (`myia_vllm/`, 110 commits mai 2025 → juin 2026), `CLAUDE.md` et la mémoire projet. Patches Genesis : [Sandermage/genesis-vllm-patches](https://github.com/Sandermage/genesis-vllm-patches) (crédité). Issues amont vLLM citées : #27951, #35104, #39931, #40798, #41559, #41726. Aucun secret ni clé API n'apparaît dans ce document.*
