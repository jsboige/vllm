# Configuration Qwen3 pour vLLM

Ce répertoire contient la configuration officielle pour les modèles Qwen3 dans le projet `myia_vllm`.

## Document Principal

📖 **[Guide de Configuration Maître](00_MASTER_CONFIGURATION_GUIDE.md)**

Ce document contient toute la documentation consolidée et à jour pour :
- La stratégie d'utilisation de l'image Docker officielle vLLM
- Les configurations pour les modèles Qwen3 (Micro 1.7B, Mini 8B, Medium 32B)
- Les recommandations officielles et bonnes pratiques
- Les scripts de déploiement et de test
- La gestion des parsers et des optimisations

## Structure Simplifiée

Le projet a été consolidé autour de la stratégie d'image Docker officielle. Toutes les anciennes configurations basées sur des images personnalisées ont été abandonnées au profit de l'utilisation de `vllm/vllm-openai:v0.9.2`.

## Migration

Si vous utilisez d'anciennes configurations, consultez le guide principal qui détaille :
- Les changements de stratégie
- Les nouvelles recommandations de configuration
- Les paramètres optimaux pour chaque modèle

---

*Pour toute question, consultez le [Guide de Configuration Maître](00_MASTER_CONFIGURATION_GUIDE.md) qui est la source de vérité officielle du projet.*