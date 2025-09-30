# Tests des Services vLLM

Ce répertoire contient des scripts pour tester les services vLLM avant et après la migration vers les modèles Qwen3. Ces tests permettent de vérifier que les services fonctionnent correctement et de mesurer leurs performances.

## Prérequis

- Python 3.8 ou supérieur
- pip (pour installer les dépendances Python)
- Accès aux services vLLM à tester

## Installation

Les dépendances Python nécessaires seront automatiquement installées lors de la première exécution du script `run_tests.sh`. Si vous préférez les installer manuellement, exécutez:

```bash
pip install requests python-dotenv aiohttp openai
```

## Configuration

Les tests utilisent un fichier `.env` situé à la racine du projet pour configurer les endpoints à tester. Si ce fichier n'existe pas, un fichier par défaut sera créé avec les configurations suivantes:

```
# Configuration des endpoints pour les tests vLLM
OPENAI_ENDPOINT_NAME_2="Local Model - Micro"
OPENAI_API_KEY_2=32885271D7845A3839F1AE0274676D87
OPENAI_BASE_URL_2="https://api.micro.text-generation-webui.myia.io/v1"
OPENAI_CHAT_MODEL_ID_2="Qwen/Qwen3-4B-AWQ"

OPENAI_ENDPOINT_NAME_3="Local Model - Mini"
OPENAI_API_KEY_3=0EO6JAQITAL2Q0LW0ZUVA55W3YNCX4W9
OPENAI_BASE_URL_3="https://api.mini.text-generation-webui.myia.io/v1"
OPENAI_CHAT_MODEL_ID_3="Qwen/Qwen3-8B-AWQ"

OPENAI_ENDPOINT_NAME_4="Local Model - Medium"
OPENAI_API_KEY_4=X0EC4YYP068CPD5TGARP9VQB5U4MAGHY
OPENAI_BASE_URL_4="https://api.medium.text-generation-webui.myia.io/v1"
OPENAI_CHAT_MODEL_ID_4="Qwen/Qwen3-30B-A3B"
```

Vous pouvez modifier ce fichier pour ajouter ou modifier des endpoints. Le format est le suivant:

```
OPENAI_ENDPOINT_NAME_X="Nom de l'endpoint"
OPENAI_API_KEY_X=clé_api
OPENAI_BASE_URL_X="url_de_base"
OPENAI_CHAT_MODEL_ID_X="nom_du_modèle"
```

Où `X` est un nombre (1, 2, 3, etc.). Les endpoints sont chargés dans l'ordre croissant de `X`.

## Utilisation

### Scripts d'exécution

#### Pour Linux/macOS (Script Shell)

Le script `run_tests.sh` est un wrapper autour du script Python qui facilite l'exécution des tests. Pour l'utiliser:

```bash
./run_tests.sh [options]
```

#### Pour Windows (Script Batch)

Le script `run_tests.bat` est l'équivalent Windows du script shell. Pour l'utiliser:

```cmd
run_tests.bat [options]
```

Options disponibles:

- `-h, --help`: Affiche l'aide
- `-a, --all`: Exécute tous les tests
- `-c, --connection`: Teste la connexion aux services
- `-g, --generation`: Teste la génération de texte
- `-t, --tools`: Teste l'utilisation d'outils
- `-r, --reasoning`: Teste le raisonnement
- `-b, --benchmark`: Effectue un benchmark de performance
- `-p, --parallel`: Teste le traitement parallèle
- `--repeats N`: Nombre de répétitions pour le benchmark (défaut: 3)
- `--parallel-requests N`: Nombre de requêtes parallèles (défaut: 5)

Exemples:

```bash
# Exécuter tous les tests
./run_tests.sh --all

# Tester uniquement la connexion et la génération de texte
./run_tests.sh -c -g

# Effectuer un benchmark avec 5 répétitions
./run_tests.sh -b --repeats 5
```

### Script Python

Vous pouvez également exécuter directement le script Python:

```bash
python3 test_vllm_services.py [options]
```

Les options sont les mêmes que pour le script shell.

## Types de Tests

### Test de Connexion

Ce test vérifie que les services sont accessibles en récupérant la liste des modèles disponibles.

### Test de Génération de Texte

Ce test vérifie que les services peuvent générer du texte en réponse à un prompt simple.

### Test d'Utilisation d'Outils

Ce test vérifie que les services peuvent utiliser des outils (function calling) en réponse à un prompt qui nécessite l'utilisation d'un outil.

### Test de Raisonnement

Ce test vérifie que les services peuvent effectuer un raisonnement étape par étape pour résoudre un problème simple.

### Benchmark de Performance

Ce test mesure les performances des services en termes de temps de réponse et de tokens par seconde.

### Test de Traitement Parallèle

Ce test vérifie que les services peuvent traiter plusieurs requêtes en parallèle et mesure leurs performances dans ce contexte.

## Interprétation des Résultats

Les résultats des tests sont affichés dans la console avec des codes couleur pour faciliter la lecture:
- ✅ Vert: Test réussi
- ⚠️ Jaune: Avertissement
- ❌ Rouge: Test échoué

À la fin des tests, un résumé est affiché pour chaque endpoint testé, indiquant les résultats de chaque type de test.

## Dépannage

### Les tests échouent avec une erreur de connexion

Vérifiez que:
1. Les services vLLM sont en cours d'exécution
2. Les URLs dans le fichier `.env` sont correctes
3. Les clés API dans le fichier `.env` sont correctes

### Les tests échouent avec une erreur d'importation Python

Vérifiez que toutes les dépendances Python sont installées:

```bash
pip install requests python-dotenv aiohttp openai
```

### Les tests de raisonnement ou d'outils échouent

Ces tests dépendent des capacités du modèle. Si un modèle n'est pas capable de raisonnement ou d'utilisation d'outils, ces tests échoueront. Cela ne signifie pas nécessairement que le service ne fonctionne pas correctement.