# {{ title }}

## Informations générales

- **Modèle**: {{ model_name }}
- **Date du benchmark**: {{ timestamp }}
{% if results.get("version") %}
- **Version**: {{ results.get("version") }}
{% endif %}
{% if results.get("environment") %}
- **Environnement**: {{ results.get("environment") }}
{% endif %}

## Résumé des performances

{% if metrics.get("llm_metrics") %}
### Métriques LLM

| Métrique | Valeur |
|----------|--------|
{% for key, value in metrics.get("llm_metrics", {}).items() %}
| {{ key }} | {{ value }} |
{% endfor %}
{% endif %}

{% if metrics.get("resource_metrics") %}
### Métriques de ressources

| Métrique | Valeur |
|----------|--------|
{% for key, value in metrics.get("resource_metrics", {}).items() %}
| {{ key }} | {{ value }} |
{% endfor %}
{% endif %}

## Détails des tests

{% if results.get("api_results") %}
### Résultats par API

{% for api_type, api_data in results.get("api_results", {}).items() %}
#### API {{ api_type }}

| Métrique | Valeur |
|----------|--------|
| Nombre de tests | {{ api_data|length }} |
{% if api_data and api_data|length > 0 %}
{% set exec_times_list = [] %}
{% for item in api_data %}{% do exec_times_list.append(item.get("execution_time", 0)) %}{% endfor %}
| Temps d'exécution moyen | {{ (exec_times_list|sum / exec_times_list|length)|round(2) }} s |
{% if api_type in ["completions", "chat"] %}
{% set tokens_generated_list = [] %}
{% for item in api_data %}{% do tokens_generated_list.append(item.get("tokens_generated", 0)) %}{% endfor %}
| Tokens générés moyen | {{ (tokens_generated_list|sum / tokens_generated_list|length)|round(0) }} |

{% set valid_items_api = [] %}
{% for item in api_data %}{% if item.get("execution_time", 0) > 0 %}{% do valid_items_api.append(item) %}{% endif %}{% endfor %}
| Tokens par seconde moyen | {% if valid_items_api|length > 0 %}{% set tps_num = [] %}{% for item in valid_items_api %}{% do tps_num.append(item.get("tokens_generated", 0)) %}{% endfor %}{% set tps_den = [] %}{% for item in valid_items_api %}{% do tps_den.append(item.get("execution_time", 0)) %}{% endfor %}{{ (tps_num|sum / tps_den|sum)|round(2) }}{% else %}0{% endif %} |
{% endif %}
{% else %}
| Temps d'exécution moyen | 0 s |
{% if api_type in ["completions", "chat"] %}
| Tokens générés moyen | 0 |
| Tokens par seconde moyen | 0 |
{% endif %}
{% endif %}

{% endfor %}
{% endif %}

{% if results.get("context_results") %}
### Impact de la longueur de contexte

| Longueur de contexte | Temps d'exécution moyen | Tokens générés moyen | Tokens par seconde moyen |
|----------------------|-------------------------|----------------------|--------------------------|
{% for length, items in results.get("context_results", {}).items() %}
{% if items and items|length > 0 %}
{% set ctx_exec_times = [] %}{% for item in items %}{% do ctx_exec_times.append(item.get("execution_time", 0)) %}{% endfor %}
{% set ctx_tokens_gen = [] %}{% for item in items %}{% do ctx_tokens_gen.append(item.get("tokens_generated", 0)) %}{% endfor %}
| {{ length }} | {{ (ctx_exec_times|sum / ctx_exec_times|length)|round(2) }} s | {{ (ctx_tokens_gen|sum / ctx_tokens_gen|length)|round(0) }} | {% set valid_items_ctx = [] %}{% for item in items %}{% if item.get("execution_time", 0) > 0 %}{% do valid_items_ctx.append(item) %}{% endif %}{% endfor %}{% if valid_items_ctx|length > 0 %}{% set tps_ctx_num = [] %}{% for item in valid_items_ctx %}{% do tps_ctx_num.append(item.get("tokens_generated", 0)) %}{% endfor %}{% set tps_ctx_den = [] %}{% for item in valid_items_ctx %}{% do tps_ctx_den.append(item.get("execution_time", 0)) %}{% endfor %}{{ (tps_ctx_num|sum / tps_ctx_den|sum)|round(2) }}{% else %}0{% endif %} |
{% else %}
| {{ length }} | 0 s | 0 | 0 |
{% endif %}
{% endfor %}
{% endif %}

## Visualisations

{% if visualizations.get("execution_time") %}
### Temps d'exécution

![Temps d'exécution](resources/{{ visualizations.get("execution_time") }})
{% endif %}

{% if visualizations.get("throughput") %}
### Débit (tokens par seconde)

![Débit](resources/{{ visualizations.get("throughput") }})
{% endif %}

{% if visualizations.get("context_impact") %}
### Impact de la longueur de contexte

![Impact de la longueur de contexte](resources/{{ visualizations.get("context_impact") }})
{% endif %}

## Recommandations

{% if metrics.get("llm_metrics", {}).get("recommended_batch_size") %}
- **Taille de batch recommandée**: {{ metrics.get("llm_metrics", {}).get("recommended_batch_size") }}
{% endif %}

{% if metrics.get("llm_metrics", {}).get("recommended_context_length") %}
- **Longueur de contexte recommandée**: {{ metrics.get("llm_metrics", {}).get("recommended_context_length") }}
{% endif %}

{% if metrics.get("resource_metrics", {}).get("recommended_memory") %}
- **Mémoire recommandée**: {{ metrics.get("resource_metrics", {}).get("recommended_memory") }} MB
{% endif %}

## Conclusion

Ce rapport présente les résultats des benchmarks pour le modèle {{ model_name }}. Les tests ont été effectués pour évaluer les performances du modèle dans différentes configurations et avec différentes longueurs de contexte.

{% if metrics.get("llm_metrics", {}).get("overall_performance_score") %}
Le score global de performance est de {{ metrics.get("llm_metrics", {}).get("overall_performance_score") }}/10.
{% endif %}

---

*Rapport généré automatiquement par qwen3_benchmark*