# Espace de travail vllm — flotte myia (workers siblings po-2025 / po-2026)

**Rôle.** Ce clone est le poste de travail des **workers siblings** sur le fork
`jsboige/vllm` : po-2025 (FrogNano) et po-2026 (Embeddings). Les siblings se
coordonnent sur le **dashboard workspace-vllm**, avec `ai-01:vllm` (siège prod :5002).

**Périmètre assigné**

| Volet | Issue | Machine | État |
|---|---|---|---|
| FrogNano-4B | `myia-ai-01/vllm#70` | po-2025 | P0 inventaire GPU livré 05/10 ; workspace créé 06/10 |
| Embeddings | `myia-ai-01/vllm#71` | po-2026 | instruction livrée 05/10 ; workspace créé 06/10 (PR profil + scripts + runbook) |

**Matériel (mesuré 05/10, ne pas réétablir)**

- GPU : **RTX 3080 Ti Laptop, 16 Go VRAM** (pas 24) — driver 616.92. BF16 tient, mais le
  plafond de concurrence reste à mesurer.
- Le hub claudish (conteneur, même machine) **n'a aucun accès GPU** (`DeviceRequests=null`) :
  la coexistence se joue sur CPU / RAM / thermique, pas sur la VRAM.
- Échantillonneur thermique mort depuis le 31/08 ; max constaté 83 °C en banc d'essai,
  ≤ 57 °C sinon. Croiser température × charge, jamais l'un seul.

**Dépôts**

- `origin` = `jsboige/vllm` (fork, branche `main`).
- `upstream` = `vllm-project/vllm` — pour les rebases, jamais pour pousser.
- Les fichiers `CLAUDE.md` / `AGENTS.md` de la racine appartiennent à vLLM upstream :
  **ne pas les modifier ici** (friction à chaque sync). Les notes flotte vivent dans ce
  fichier.

**Conventions flotte** (héritées, non négociables)

- Commits conventionnels, PR vers `jsboige/vllm`, `Closes #NN` dans le corps.
- Un chiffre cité est **mesuré**, avec sa source ; qualifier VERIFIE / RAPPORTE / SUPPOSE.
- Jamais de secret dans un commit ; jamais de suppression sans preuve de préservation.
- Point d'entrée **sk-agent** (`:8100`, streamable-http, container `mcp-tools` sur ai-01 —
  **RAPPORTE** par ai-01, annonces 06/10 11:39Z puis 18:48Z post-redémarrage ; le `:8010`
  de la note initiale du matin précédait l'annonce du catalogue). À câbler dans l'init
  du workspace. Télémétrie d'usage **en place** depuis ms#1387 (`SK_AGENT_USAGE_LOG`,
  bumps parents #4080/#4089, volume mesuré #4085) ; conteneur redémarré le 06/10 18:47Z,
  catalogue à jour (**Swift-1.5-27B**, remplace Qwen3.6 35B MoE retiré le 25/09).
- Le harnais partagé (règles, skills) vit dans `jsboige/roo-extensions` — s'y référer plutôt
  que dupliquer.

**Siège po-2026 (volet Embeddings, mesuré 05-06/10)**

- GPU : **RTX 3080 Ti Laptop, 16 Go VRAM** (jumelle de po-2025) — driver 616.92.
  Service d'embeddings flotte : Qwen3-Embedding-4B W4A16-AWQ, vLLM v0.23.0,
  `--runner pooling`, gpu-mem 0.75, derating -12,5 % + undervolt 1800 MHz.
- Mémoire : 64 Go RAM, **cap vmmem WSL 16 Go** depuis 05/10 (GO user — gels SPOF n°4/5
  par pagefile-thrash ; détail `myia_vllm/docs/embeddings-po2026-runbook.md`).
- Runtime de service : reste au dépôt local `C:\Production\Embeddings` (prod vivante) ;
  ce workspace porte le profil canonique, les scripts mutualisables et la doc.
  La bascule éventuelle de la gestion = fenêtre arbitrée par le user (#71).
- Profils/scripts apportés : `embeddings-qwen3-4b-awq-po2026.yml`,
  `scripts/embedding-proxy-logger.py`, `scripts/gpu-thermal-governor.ps1`,
  `docs/embeddings-po2026-runbook.md`.

**Journal**

- 2026-10-06 — workspace créé sur po-2025 (clone du fork `72e2dfcc95`, `upstream` ajouté,
  140 Mo) par la lane `po-2025:claudish`, sur demande user relayée par `ai-01:vllm`.
- 2026-10-06 — workspace créé sur po-2026 (`D:\Dev\vllm`, clone depth-5 du fork
  `b2cc30bbce`, `upstream` ajouté par gh ; initialement posé sous `C:\Production\vllm`
  puis déplacé sur D: le même jour — équilibre disque, D: 1 To libres vs C: 341 Go)
  par la lane `po-2026:Embeddings`, sur instruction user directe. Apport : profil
  compose embeddings + sidecar capture + gouverneur thermique + runbook v0.23
  (PR #78 vers main, refs #71). **Siège de passation** : la vigie embeddings
  (surveillance 12h) migre vers `myia_vllm/` (CLAUDE.md + skill + mémoire lane) —
  le runtime de service reste au dépôt prod `C:\Production\Embeddings`.
- 2026-10-06 PM — **siège po-2026 OPÉRATIONNEL (worker sibling #2)** : session
  démarrée par le user dans `D:\Dev\vllm` ; validation passation passée (1er cycle
  `/surveillance-embeddings`, rapport workspace-Embeddings 13:35 locale) ;
  embeddings-99 a retiré son cron 12h (clôture postée). Cron siège : **5 h à :17**
  (`f10b0717`, surveillance + coordination siblings, mandat user). Heads-up posé
  sur workspace-vllm : **le démarrage d'un siège génère une vague d'indexation
  one-shot de son clone** (~150 k pts/h mesuré, latence co-tenants dégradée
  temporairement) — valable pour le siège po-2025 à venir.
- 2026-10-06 soir — PR doc (lane `po-2025:roo-extensions`, mandat user 06/10) :
  endpoint sk-agent corrigé `:8100` (qualifié RAPPORTE, source ai-01) et télémétrie
  d'usage marquée en place — le volet « à porter par roo-extensions » est couvert par
  ms#1387 + bumps #4080/#4089. Prochaine étape volet C : preset mini FrogNano +
  gardes récursion (#70, #4085).
