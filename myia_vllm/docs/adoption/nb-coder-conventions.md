# Conventions de livraison des carnets (harnais nb-coder)

Source : Epic jsboige/CoursIA#20250 (phases 2-4, verbatim « une **mention ponctuelle de
provenance** (« carnet issu de l'Epic #N »), en pied de carnet ou dans une note discrète,
jamais dans le premier paragraphe ») et Epic jsboige/CoursIA#26534 (C.1-C.3).
Ce fichier est injecté tel quel dans les prompts du driver ; il ne remplace pas la lecture
de l'issue, il fixe la forme attendue quand le corps de l'issue est long.

## Prose du carnet

- Le carnet présente son état final : aucun récit de correction, de review, de cycle ou de lane.
- Le premier paragraphe annonce le contenu à l'apprenant. Aucune référence de coordination
  (`Epic #N`, `EPIC #N`, `See #N`, `Part of #N`, `lane …`) dans la cellule d'en-tête.
- Une référence de provenance ne survit qu'en **pied de carnet**, en **note discrète** :
  `> Carnet issu de l'EPIC #N.` — jamais dans le premier paragraphe, jamais en titre `##`.
- Les numéros d'issue restent utiles en pied, dans une rubrique « pour aller plus loin »,
  quand l'issue documente une question ouverte lisible.
- Prose en français.

## Exécution et sorties

- Sorties issues d'une exécution réelle, sur le noyau canonique de la série et à sa version
  (`language_info.version` égale à celle des carnets voisins).
- Aucune sortie éditée à la main. Un geste markdown seul ne ré-exécute rien : les sorties
  existantes des cellules de code restent intactes.
- Seuls les carnets modifiés sont committés.

## Interdits (hors périmètre du harnais)

- Erreur volontaire dans un stub (C.1).
- Lean, QuantConnect, GPU lourd, renommages, catalogue, fichiers de harnais (`.claude/`,
  `CLAUDE.md`, `.github/`).