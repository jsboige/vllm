# Espace de travail vllm — flotte myia (po-2025, worker sibling)

**Rôle.** Ce clone est le poste de travail du **worker sibling po-2025** sur le fork
`jsboige/vllm`. Un second sibling tourne sur **po-2026** (volet Embeddings) ; les deux se
coordonnent sur le **dashboard workspace-vllm**.

**Périmètre assigné**

| Volet | Issue | Machine | État |
|---|---|---|---|
| FrogNano-4B | `myia-ai-01/vllm#70` | po-2025 (ce workspace) | P1 en cours — siège vllm inauguré 06/10 (profil + garde thermique posés, 1er serve en préparation) |
| Embeddings | `myia-ai-01/vllm#71` | po-2026 | sibling #2 |

**Matériel (mesuré 05/10, ne pas réétablir)**

- GPU : **RTX 3080 Ti Laptop, 16 Go VRAM** (pas 24) — driver 616.92. BF16 tient, mais le
  plafond de concurrence reste à mesurer.
- Le hub claudish (conteneur, même machine) **n'a aucun accès GPU** (`DeviceRequests=null`) :
  la coexistence se joue sur CPU / RAM / thermique, pas sur la VRAM.
- Échantillonneur thermique mort depuis le 31/08 ; max constaté 83 °C en banc d'essai,
  ≤ 57 °C sinon. Croiser température × charge, jamais l'un seul.
  **Revivé 06/10** par le siège vllm : logger user-level /5 min (45 °C à vide au 1er
  heartbeat) ; gouverneur SYSTEM (recette twin po-2026) en attente de fenêtre UAC.

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
- Point d'entrée **sk-agent** (`:8010`, streamable-http, container `mcp-tools` sur ai-01) :
  à câbler dans l'init du workspace — télémétrie d'usage encore absente (à porter par
  roo-extensions).
- Le harnais partagé (règles, skills) vit dans `jsboige/roo-extensions` — s'y référer plutôt
  que dupliquer.

**Journal**

- 2026-10-06 — workspace créé sur po-2025 (clone du fork `72e2dfcc95`, `upstream` ajouté,
  140 Mo) par la lane `po-2025:claudish`, sur demande user relayée par `ai-01:vllm`.
- 2026-10-06 — **siège `po-2025:vllm` inauguré** (session user) : onboarding + P1 engagée —
  profil `mini-frognano-4b-po2025.yml`, logger thermique posé (sans UAC), gouverneur prêt
  (fenêtre UAC en attente), config modèle décodée, cron vigie 4 h. Faits marquants : aucun
  quant communautaire exploitable vLLM/GPU (17 = GGUF/MLX/ONNX/EXL3/NVFP4) → AWQ W4A16
  maison planifié ; BF16 primaire (9,3 Go). Détail : #70 + dashboard workspace-vllm.
