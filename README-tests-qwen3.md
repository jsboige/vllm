# Tests Qwen3 - Documentation

Ce document décrit les tests récupérés des branches qwen3-integration, qwen3-parser et qwen3-parser-improvements.

## Structure des tests

Les tests sont organisés en trois catégories principales:

1. **tests/performance** - Tests de performance pour les modèles Qwen3
2. **tests/reasoning** - Tests de raisonnement pour les modèles Qwen3
3. **tests/tool_calling** - Tests d'appel d'outils pour les modèles Qwen3

## Tests de performance

Le répertoire `tests/performance` contient:

- `tests/performance_comparison.py` - Script pour mesurer et comparer les performances des API des modèles Qwen3 entre l'accès local et l'accès externe.

Ce script effectue des tests sur différentes API (models, completions, chat/completions, tool_calling) et compare les résultats entre l'accès local et l'accès externe.

## Tests de raisonnement

Le répertoire `tests/reasoning` contient:

- `tests/reasoning_parser.py` - Script pour vérifier la fonctionnalité du parser de raisonnement avec les modèles Qwen3.
- `tests/reasoning_optimized.py` - Version optimisée du script de test de raisonnement.
- `test_qwen3_reasoning_parser.py` - Script spécifique pour tester le parser de raisonnement de Qwen3.

Ces scripts envoient des requêtes avec raisonnement activé à différents serveurs API vLLM et vérifient les réponses.

## Tests d'appel d'outils (Tool Calling)

Le répertoire `tests/tool_calling` contient:

- `tests/tool_calling.py` - Script de base pour vérifier la fonctionnalité d'appel d'outils avec les modèles Qwen3.
- `tests/tool_calling_optimized.py` - Version optimisée du script de test d'appel d'outils.
- `test_qwen3_tool_parser.py` - Script pour tester le parser d'outils de Qwen3.
- `test_qwen3_tool_calling.py` - Script spécifique pour tester l'appel d'outils de Qwen3.
- `test_qwen3_tool_calling_custom.py` - Script pour tester l'appel d'outils personnalisés de Qwen3.
- `test_qwen3_tool_calling_custom_fixed.py` - Version corrigée du script de test d'appel d'outils personnalisés.
- `test_qwen3_tool_calling_fixed.py` - Version corrigée du script de test d'appel d'outils.

Ces scripts envoient des requêtes avec outils activés à différents serveurs API vLLM et vérifient les réponses.

## Configuration

Chaque répertoire de test contient un fichier `.env` qui doit être configuré avec les clés API et les URL de base appropriées pour les différents modèles (micro, mini, medium).

Exemple de configuration `.env`:
```
OPENAI_API_KEY_MICRO="votre_clé_api_micro"
OPENAI_BASE_URL_MICRO="http://localhost:5003/v1"

OPENAI_API_KEY_MINI="votre_clé_api_mini"
OPENAI_BASE_URL_MINI="http://localhost:5002/v1"

OPENAI_API_KEY_MEDIUM="votre_clé_api_medium"
OPENAI_BASE_URL_MEDIUM="http://localhost:5001/v1"
```

## Exécution des tests

Pour exécuter un test, utilisez la commande suivante:

```bash
# Test de raisonnement avec le modèle mini
python -m tests/reasoning.tests/reasoning_parser mini

# Test d'appel d'outils avec le modèle medium
python -m tests/tool_calling.tests/tool_calling medium

# Test de performance avec tous les modèles
python -m tests/performance.tests/performance_comparison --model all
```

## Notes importantes

- Ces tests nécessitent des serveurs API vLLM actifs avec les modèles Qwen3 chargés.
- Les tests peuvent être adaptés pour différentes configurations en modifiant les fichiers `.env`.
- Les tests d'appel d'outils simulent des appels à des fonctions externes, mais ne les exécutent pas réellement.

## Versions propres des scripts

En raison de problèmes d'encodage dans les fichiers originaux, des versions propres des scripts ont été créées:

- `tests/tool_calling_clean.py` - Version propre du script de test d'appel d'outils
- `tests/reasoning_parser_clean.py` - Version propre du script de test de raisonnement
- `tests/performance_clean.py` - Version propre du script de test de performance

Ces versions propres sont fonctionnelles et peuvent être utilisées pour exécuter les tests.

## Exécution des tests avec les versions propres

Pour exécuter un test avec une version propre, utilisez la commande suivante:

```bash
# Test de raisonnement avec le modèle mini
python -m tests/reasoning.tests/reasoning_parser_clean mini

# Test d'appel d'outils avec le modèle medium
python -m tests/tool_calling.tests/tool_calling_clean medium

# Test de performance avec le modèle mini et l'API models
python -m tests/performance.tests/performance_clean --model mini --api models
```