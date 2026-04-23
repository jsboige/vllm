# Rapport de benchmark Qwen3 QWEN3-32B-AWQ

Date: 2025-07-03 23:14:25

## Informations sur le modèle

- **Modèle**: qwen3-32b-awq
- **Taille**: N/A
- **Quantization**: N/A
- **Description**: N/A

## Configuration du test

- **Nombre d'itérations**: 5
- **Timeout**: 120 secondes

## Résultats

- **Temps d'exécution total**: 27.75 s

### Métriques

| Métrique | Valeur |
|----------|--------|
| total_api_calls | 15 |
| avg_execution_time | 1.8470672766367595 |
| min_execution_time | 0.0029997825622558594 |
| max_execution_time | 3.0518500804901123 |

### Analyse

#### summary

- **total_api_calls**: 15
- **avg_execution_time**: 1.8470672766367595
- **min_execution_time**: 0.0029997825622558594
- **max_execution_time**: 3.0518500804901123

#### api_performance

- **completions**: {'avg_execution_time': 2.787312936782837, 'min_execution_time': 2.7067313194274902, 'max_execution_time': 3.0518500804901123, 'avg_execution_time_formatted': '2.79 s', 'min_execution_time_formatted': '2.71 s', 'max_execution_time_formatted': '3.05 s', 'num_iterations': 5, 'avg_tokens_generated': 150.0, 'avg_tokens_total': 163.0, 'tokens_per_second': 53.81527062158026}
- **chat**: {'avg_execution_time': 2.7456573009490968, 'min_execution_time': 2.7205915451049805, 'max_execution_time': 2.7832906246185303, 'avg_execution_time_formatted': '2.75 s', 'min_execution_time_formatted': '2.72 s', 'max_execution_time_formatted': '2.78 s', 'num_iterations': 5, 'avg_tokens_generated': 150.0, 'avg_tokens_total': 187.0, 'tokens_per_second': 54.63172696321176}
- **embeddings**: {'avg_execution_time': 0.008231592178344727, 'min_execution_time': 0.0029997825622558594, 'max_execution_time': 0.02752399444580078, 'avg_execution_time_formatted': '8.23 ms', 'min_execution_time_formatted': '3.00 ms', 'max_execution_time_formatted': '27.52 ms', 'num_iterations': 5}

## Erreurs

- **Phase**: tool_calling_api
- **Erreur**: Erreur HTTP 400: 400 Client Error: Bad Request for url: http://localhost:8092/v1/chat/completions
- **Timestamp**: 2025-07-03T23:14:25.856588

- **Phase**: tool_calling_api
- **Erreur**: Erreur HTTP 400: 400 Client Error: Bad Request for url: http://localhost:8092/v1/chat/completions
- **Timestamp**: 2025-07-03T23:14:25.860592

- **Phase**: tool_calling_api
- **Erreur**: Erreur HTTP 400: 400 Client Error: Bad Request for url: http://localhost:8092/v1/chat/completions
- **Timestamp**: 2025-07-03T23:14:25.873587

- **Phase**: tool_calling_api
- **Erreur**: Erreur HTTP 400: 400 Client Error: Bad Request for url: http://localhost:8092/v1/chat/completions
- **Timestamp**: 2025-07-03T23:14:25.876592

- **Phase**: tool_calling_api
- **Erreur**: Erreur HTTP 400: 400 Client Error: Bad Request for url: http://localhost:8092/v1/chat/completions
- **Timestamp**: 2025-07-03T23:14:25.879593

