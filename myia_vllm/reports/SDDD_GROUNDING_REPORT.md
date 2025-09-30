# Rapport d'Activité d'Investigation - Restauration du Projet "Qwen3 Deployment"

**Date:** 2025-08-11
**Auteur:** Roo, Assistant IA d'Investigation
**Mission:** "Semantic Grounding" - Identifier la configuration la plus stable et la mieux documentée du projet pour guider sa restauration.
**Méthodologie:** SDDD (Semantic-Documentation-Driven-Design)

---

## 1. Objectif de la Mission

L'objectif principal de cette investigation était de surmonter la corruption de l'historique des commits du projet en localisant un état de référence fiable datant de la période "fin juillet / début août". La méthodologie SDDD a été employée, postulant que la documentation la plus complète et la plus cohérente sert de "source de vérité" pour reconstituer l'architecture technique et les configurations de déploiement.

## 2. Déroulement de l'Investigation

L'investigation s'est déroulée en plusieurs étapes séquentielles, en s'appuyant sur les capacités de recherche sémantique pour explorer la base de connaissances documentaire du projet.

### Étape 2.1: Recherche Sémantique Initiale

Deux requêtes de recherche sémantique ont été exécutées pour couvrir les aspects de configuration et d'optimisation :

1.  **Requête 1:** `"configuration stable et documentation complète des modèles Qwen3"`
    *   **Objectif:** Identifier les documents décrivant l'état final et validé des configurations.
    *   **Résultat clé:** Le fichier `myia_vllm/docs/qwen3/QWEN3-CONFIGURATIONS-DEFINITIVES.md` a été identifié avec un score de pertinence très élevé (0.913).

2.  **Requête 2:** `"stratégie d'optimisation et déploiement des profils medium, micro, mini"`
    *   **Objectif:** Trouver des informations sur les paramètres d'optimisation spécifiques et les rapports de déploiement pour les différents profils de modèles.
    *   **Résultat clé:** Le fichier `myia_vllm/docs/qwen3/QWEN3-FINAL-DEPLOYMENT-REPORT.md` a émergé comme le document le plus pertinent (score de 0.899), corroborant les informations de la première recherche.

### Étape 2.2: Analyse des Artefacts Documentaires

Une lecture et une analyse croisée des deux documents clés ont été effectuées.

*   **`QWEN3-CONFIGURATIONS-DEFINITIVES.md`**: Ce document a été rapidement identifié comme la **Référence Absolue**. Il contient une description exhaustive et normative de l'architecture cible, incluant :
    *   Les noms de modèles précis.
    *   L'allocation des ressources GPU (`CUDA_VISIBLE_DEVICES`).
    *   Les paramètres vLLM communs pour l'optimisation (cache KV en FP8, `rope-scaling`, `chunked-prefill`, etc.).
    *   Les parsers spécifiques pour le `tool-calling` (`qwen3`) et le `reasoning` (`deepseek_r1`).
    *   Les extraits de code YAML pour les fichiers `docker-compose.yml` de chaque profil.

*   **`QWEN3-FINAL-DEPLOYMENT-REPORT.md`**: Ce rapport sert de validation pratique et de "Procès-Verbal de Recette" pour la configuration décrite ci-dessus. Il confirme que l'architecture a été déployée avec succès, testée et jugée "Prête pour la production". Il apporte des preuves concrètes :
    *   Des métriques de performance (Tokens/sec, latence, utilisation mémoire GPU).
    *   Des résultats de tests validant le fonctionnement des `tool-calls` et du `reasoning`.
    *   Les commandes `docker ps` et `docker-compose` exactes utilisées pour la gestion des services.

## 3. Conclusions de l'Investigation

1.  **Source de Vérité Identifiée:** La combinaison des deux documents `QWEN3-CONFIGURATIONS-DEFINITIVES.md` et `QWEN3-FINAL-DEPLOYMENT-REPORT.md` constitue une "source de vérité" fiable et complète pour la restauration du projet. Le premier définit "quoi" faire, le second confirme "que ça a été fait et que ça marche".

2.  **Configuration Stable Reconstituée:** L'état le plus stable et fonctionnel du projet s'articule autour de trois services `docker-compose`, un pour chaque profil de modèle (Medium, Micro, Mini), utilisant des optimisations vLLM spécifiques et une configuration GPU claire.

3.  **Prochaines Étapes Recommandées:** La phase d'investigation est terminée. La prochaine étape consiste à synthétiser ces informations dans un plan d'action clair pour l'orchestrateur de restauration.

---
---

# Annexe A: Synthèse de Grounding pour l'Orchestrateur

**Objectif:** Fournir un plan d'action directement exploitable pour la restauration du projet sur la base de la configuration stable identifiée.

## A.1. Source de Vérité Absolue

*   **Document de Configuration:** [`myia_vllm/docs/qwen3/QWEN3-CONFIGURATIONS-DEFINITIVES.md`](myia_vllm/docs/qwen3/QWEN3-CONFIGURATIONS-DEFINITIVES.md)
*   **Document de Validation:** [`myia_vllm/docs/qwen3/QWEN3-FINAL-DEPLOYMENT-REPORT.md`](myia_vllm/docs/qwen3/QWEN3-FINAL-DEPLOYMENT-REPORT.md)

Toute action de restauration doit se conformer strictement aux spécifications contenues dans ces deux fichiers.

## A.2. Plan d'Action Suggéré

### Étape 1: Restauration des Fichiers de Configuration `docker-compose`

Créer/restaurer les trois fichiers `docker-compose` suivants, en copiant-collant le contenu YAML directement depuis le document `QWEN3-CONFIGURATIONS-DEFINITIVES.md`.

1.  **Fichier:** `myia_vllm/deployments/qwen3/docker-compose.medium.yml`
    *   **Modèle:** `Qwen/Qwen2-32B-Instruct-AWQ`
    *   **GPU:** 2x (e.g., `CUDA_VISIBLE_DEVICES=0,1`)
    *   **Port:** `8001`

2.  **Fichier:** `myia_vllm/deployments/qwen3/docker-compose.micro.yml`
    *   **Modèle:** `Qwen/Qwen2-1.7B-Instruct-fp8`
    *   **GPU:** 1x (e.g., `CUDA_VISIBLE_DEVICES=2`)
    *   **Port:** `8002`

3.  **Fichier:** `myia_vllm/deployments/qwen3/docker-compose.mini.yml`
    *   **Modèle:** `Qwen/Qwen1.5-0.5B-Chat`
    *   **GPU:** 1x (e.g., `CUDA_VISIBLE_DEVICES=3`)
    *   **Port:** `8003`

### Étape 2: Configuration de l'Environnement

Assurer la présence d'un fichier `.env` à la racine (`myia_vllm/.env`) contenant les clés d'API requises, qui sont référencées dans les fichiers `docker-compose`.
Exemple de structure:
```env
# Fichier .env
QWEN_API_KEY_MEDIUM=VOTRE_CLE_ICI
QWEN_API_KEY_MICRO=VOTRE_CLE_ICI
QWEN_API_KEY_MINI=VOTRE_CLE_ICI
HF_TOKEN=VOTRE_TOKEN_HUGGINGFACE_ICI
```

### Étape 3: Déploiement et Validation

1.  **Lancer les services** en utilisant les commandes `docker-compose` spécifiées dans le rapport de déploiement final.
    ```bash
    # Exemple pour le modèle Medium
    docker-compose -f myia_vllm/deployments/qwen3/docker-compose.medium.yml up -d
    ```

2.  **Valider le déploiement** en utilisant la commande `docker ps` et en vérifiant les logs de chaque conteneur.

3.  **Effectuer des tests de santé** en envoyant des requêtes de test aux points de terminaison de l'API de chaque modèle pour valider le `tool-calling` et le `reasoning`, comme décrit dans le rapport de déploiement.

## A.3. Résumé des Paramètres Clés (Pour Référence Rapide)

*   **Optimisations communes vLLM:**
    *   `--enable-chunked-prefill`
    *   `--enable-prefix-caching`
    *   `--kv_cache_dtype fp8`
    *   `--rope-scaling yarn` (factor 4.0)
    *   `--gpu-memory-utilization 0.9999`
*   **Parsers:**
    *   `--tool-call-parser qwen3`
    *   `--reasoning-parser deepseek_r1`
*   **Parallélisme Tensoriel:**
    *   `tensor-parallel-size=2` pour `Medium`
    *   `tensor-parallel-size=1` pour `Micro` et `Mini`
