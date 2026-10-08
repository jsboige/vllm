# myia_vllm — poste de travail des sièges vLLM (index)

Ce dossier est partagé par les **sièges** de la flotte vLLM : chacun travaille dans son
propre clone du fork, mais ce dossier porte leurs artefacts communs (profils, scripts,
docs). **Lire d'abord** [`../FLEET-WORKSPACE.md`](../FLEET-WORKSPACE.md) — il porte les
conventions de la flotte (sièges, dashboards, canaux, doctrine de mesure).

## Ce fichier est un index, pas un document de siège

`CLAUDE.md` est **auto-chargé par Claude Code** dans toute session travaillant sous
`myia_vllm/`. Y écrire le document d'un siège injecterait son contexte chez tous les
autres — et un chemin unique ne peut de toute façon pas porter N sièges (collision
`add/add`, rencontrée le 2026-10-08 entre po-2026 et po-2025).

**Convention** : un document par siège, dans [`docs/seats/`](docs/seats/).

- [`docs/seats/po2026-embeddings.md`](docs/seats/po2026-embeddings.md) — siège `myia-po-2026`, lane **embeddings** (identité, mission de vigie, non-négociables, chemins de service).
- `docs/seats/po2025-frognano.md` — siège `myia-po-2025`, lane **FrogNano** *(à créer par ce siège)*.

## Docs de lane (contenu, hors index)

- [`docs/embeddings-po2026-runbook.md`](docs/embeddings-po2026-runbook.md) — runbook du service embeddings (pièges, recovery, signature « pilote NVIDIA → pont CDI »).
- [`docs/po2026-embeddings-lane-memory.md`](docs/po2026-embeddings-lane-memory.md) — mémoire opérationnelle condensée de la lane.
- [`.claude/skills/surveillance-embeddings/`](.claude/skills/surveillance-embeddings/SKILL.md) — skill de vigie (invocable `/surveillance-embeddings`).
