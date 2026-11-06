# sk-agent — lots d'outils, presets vitrines et paramètres de service

**Objet** : rendre l'usage du modèle local (broker sk-agent) trivial pour toute lane.
**Porteur doc** : ai-01:vllm (expertise service). **Porteur config** : roo-extensions (`d:\roo-extensions\mcps\internal\servers\sk-agent\sk_agent_config.json`).
**Date** : 2026-10-01. Modèle servi : Swift-1.5-Qwen3.8-27B W4A16 + FP8 KV (alias `qwen3.6-35b-a3b`), 262K ctx, vision+thinking+`preserve_thinking`, KV 465K tokens.

## 1. Pourquoi passer par sk-agent (le standard de consommation)

- **La clé API ne quitte jamais le broker** : les lanes appellent sk-agent, jamais `:5002` directement. Zéro rotation à propager, zéro secret dans les configs des lanes (règle secrets n°5, incident #3958).
- **Capacité dispo** : running=0 sur 78-92 % des minutes, KV <1 % — déléguer une charge récurrente ne coûte rien en QoS.
- **Qualité** : 262K contexte natif, vision, thinking persistant multi-tours, préfixe cache chaud.

## 2. Mécanique vérifiée (schéma `call_agent`, vérifié 01/10)

| Besoin | Mécanisme |
|---|---|
| Choisir les plugins **par appel** | `mcp_overrides: {"add":["mcp_id"],"remove":[...]}` (delta) ou `{"replace":[...]}` (plein) |
| Composer un agent à la carte | `agent_spec: {"extends":"analyst","model":"...","mcps":{"replace":[...]},"sampling":{...}}` |
| Rester sur un preset documenté | `agent: "<preset-id>"` (liste : `list_agents`) |
| Multi-tours | `conversation_id` (rendu par le 1ᵉʳ appel) |
| Vision / PDF / docs | `attachment` (chemin local, URL, ou tableau JSON multi-images) |
| Tour long (>300 s défaut) | entrée modèle dédiée avec budget client (précédent : `qwen3.6-35b-a3b-audit` 600 s, #3797) |

**Réponse à la question « les agents maîtres peuvent-ils choisir ? »** : oui, deux niveaux —
`mcp_overrides` par appel (léger, sans config) et `agent_spec` (composition complète).
Les **presets restent la voie documentée** : ils portent la description, le système-prompt et le
sampling calibrés — un preset = un chemin balisé, un override = l'écart de circonstance.

## 3. Lots d'outils (à prescrire)

| Lot | MCP | Usage type | Classe de risque |
|---|---|---|---|
| **A — terminal+repo** | `desktop_commander` | shell, python, `git`/`gh` (lecture), exploration fichiers | **exec** — la lane maîtresse répond de ce qui tourne |
| **B — notebook** | `jupyter_papermill` | exécution kernels, re-derivation, plots | exec (kernel dédié) |
| **C — recherche** | `searxng` (+ `playwright` si web interactif) | veille, doc, citations web | lecture |
| **D — vision** | aucun MCP (attachments natifs) | OCR, figures, PDF, screenshots | lecture |
| **E — coordination** | `roo-state-manager` (à ajouter au config, voir §4) | lire/poster dashboards, inbox | écriture partagée — démonialement utile, à cadrer |

**Combos présrits** :
- `auditeur` = A+B+C (pattern éprouvé : `notebook-auditor`, ~50 notebooks/h à C=6)
- `analyste` = C(+D)
- `ops-léger` = A (drift config, lecture logs, `gh pr view`…)
- `coordonné` = E+C (veille + restitution dashboard)

## 4. Presets vitrines (JSON prêt pour le config roo-extensions)

```jsonc
// mcps[] — LOT E à ajouter (commande stdio du RSM, à ajuster au vrai chemin roo-extensions) :
{ "id": "roo_state_manager", "description": "Dashboards/inbox RooSync (read + append)",
  "command": "node", "args": ["<chemin roo-state-manager MCP>"],
  "risk_class": "write_shared", "allowed_capabilities": ["coordination"] }

// agents[] — vitrines :
{ "id": "terminal-analyst",
  "description": "Local analyst with terminal+repo access (desktop-commander): log analysis, config drift, gh read-only. Output French, evidence-cited.",
  "model": "qwen3.6-35b-a3b",
  "system_prompt": "<voir §6>",
  "mcps": ["desktop_commander", "searxng"],
  "capabilities": ["shell", "repo_read", "web"],
  "memory": { "enabled": false },
  "sampling": { "temperature": 0.6, "top_p": 0.95, "top_k": 20, "presence_penalty": 0.0, "max_tokens": 4096 } }

{ "id": "coordination-agent",
  "description": "Local agent that reads/posts RooSync dashboards and drafts lane reports.",
  "model": "qwen3.6-35b-a3b",
  "system_prompt": "<voir §6>",
  "mcps": ["roo_state_manager", "searxng"],
  "capabilities": ["coordination", "web"],
  "memory": { "enabled": false },
  "sampling": { "temperature": 0.7, "top_p": 0.95, "top_k": 20, "presence_penalty": 1.5, "max_tokens": 2048 } }
```

## 5. Expertise service (contribution vllm) — paramètres par usage

Calibration transférée de la famille Qwen AWQ (mesures locales 2026-03/04, [[sampling-optimization]]) —
mêmes quant/serving ; à re-mesurer si dérive qualitative sur Swift.

| Usage | temp | top_p | top_k | presence_penalty | repetition_penalty | min_p |
|---|---|---|---|---|---|---|
| Raisonnement général (thinking) | 0.7 | 0.95 | 20 | **1.5** | 1.0 | — |
| Coding / agentique outillé | **0.6** | 0.95 | 20 | **0.0** | 1.0 | — |
| Chat / instruct (sans thinking) | 0.7 | 0.8 | 20 | 1.5 | 1.1 | 0.01 |
| Audit / analyse critique | 0.6 | 0.95 | 20 | 0.5 | 1.0 | — |

Faits mesurés derrière ce tableau : `presence_penalty` 1.5-2.0 divise la répétition 4-gram par 2-3×
sans coût débit ; pp=0 en coding évite la casse de code ; min_p 0.01 filtre les artefacts de quant.

**Discipline de charge** (registre d'usage Swift) :
- Créneaux occupés : nbaudit **:05Z** (4-8 min), prouveur **:30Z**. Éviter de lancer une campagne outillée dessus.
- **Fenêtre backup 03:00 locale (~40 min)** : le moteur est DOWN — ne pas programmer de jobs 01:00-01:45Z.
- Toute charge lourde récurrente se déclare sur `global` AVANT (règle en place).

**Budgets de tour** : défaut client 300 s/appel LLM. Une boucle outillée dense (audit, forensique)
→ demander une entrée modèle à budget 600 s (précédent #3797, 1 ligne de config).

**Hygiène contexte** : joindre des extraits, pas des fichiers entiers (262K ctx ≠ raison de le remplir) ;
`preserve_thinking` actif côté serveur — les raisonnements survivent aux tours, inutile de les rejouer.

## 6. Prompt guidance (squelette système recommandé)

Leçons du pilote audit ([[project-vllm-adoption-mandate]]) : le modèle local **ne vérifie pas
spontanément** — la consigne doit l'y forcer.

```text
Tu es <rôle> sur la machine ai-01. Règles :
1. Tu ne conclus JAMAIS sans preuve exécutée : toute affirmation quantitative passe par un outil
   (shell/kernel/recherche) dont tu cites la commande et le résultat.
2. Un outil par étape ; attends le résultat avant l'étape suivante.
3. Réponds en français ; chiffres et citations avec leur source ; « non vérifié » est une réponse valable.
4. Reste dans le périmètre demandé ; si une action est destructrice ou sort du périmètre, arrête-toi et rapporte.
5. Format final : constats (avec preuves) → diagnostic → recommandation. Concis.
```

## 7. Anti-patterns

- Passer la clé vLLM à une lane ou dans un prompt — le broker est là pour ça.
- `desktop-commander` sans périmètre : c'est du shell sur ai-01 — la lane maîtresse définit ce que
  l'agent a le droit de toucher et le dit dans le système-prompt (règle 4 du squelette).
- Compter sur le modèle pour « vérifier en tête » : mesuré faux (pilote 1 du 22/09 — 1 tool-call
  sur 9 sans l'étape B du harnais).
- Ignorer les créneaux (§5) : une campagne qui chevauche le runner :05Z dégrade les deux.
