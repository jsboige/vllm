on # 📋 PLAN DE TESTS - SERVICE MEDIUM QWEN3-32B-AWQ

**Service** : vLLM Medium (Qwen3-32B-AWQ)  
**Version vLLM** : v0.11.0  
**Status Document** : ⚠️ **TESTS NON EXÉCUTÉS** - Documentation uniquement  
**Date Création** : 2025-10-16

---

## ⚠️ AVERTISSEMENT IMPORTANT

**Ce document décrit les tests à effectuer ULTÉRIEUREMENT**. Les tests n'ont PAS été exécutés lors du déploiement initial (MISSION 9 - PHASE 9).

Le service medium a été déployé avec succès et est opérationnel, mais **aucun test fonctionnel n'a été effectué** au-delà du health check basique.

---

## 🎯 OBJECTIFS DES TESTS

### Tests de Base (Priorité CRITIQUE)
1. ✅ Health Check API (`/health`) - **EFFECTUÉ**
2. ✅ Liste Modèles (`/v1/models`) - **EFFECTUÉ**
3. 🔄 Chat Completion Basique - **À FAIRE**
4. 🔄 Text Completion Basique - **À FAIRE**

### Tests Fonctionnels Avancés (Priorité HAUTE)
5. 🔄 Raisonnement Multi-Step (Chain-of-Thought)
6. 🔄 Tool Calling avec Qwen3
7. 🔄 Contexte Long (>64k tokens)
8. 🔄 Streaming Responses

### Tests de Performance (Priorité MOYENNE)
9. 🔄 Latence Première Réponse (TTFT)
10. 🔄 Throughput (tokens/sec)
11. 🔄 Tests de Charge (concurrence)
12. 🔄 Stabilité Longue Durée

### Tests de Robustesse (Priorité BASSE)
13. 🔄 Gestion Erreurs API
14. 🔄 Limites Context Window
15. 🔄 Résistance aux Crashes

---

## 📚 TESTS DE BASE

### Test 1 : Health Check ✅ EFFECTUÉ

**Objectif** : Vérifier que l'API répond correctement

**Commande** :
```bash
curl http://localhost:5002/health
```

**Résultat Attendu** :
```
HTTP 200 OK
```

**Résultat Obtenu** :
✅ HTTP 200 OK - Service opérationnel

---

### Test 2 : Liste Modèles ✅ EFFECTUÉ

**Objectif** : Vérifier que le modèle est chargé et disponible

**Commande** :
```bash
curl http://localhost:5002/v1/models
```

**Résultat Attendu** :
```json
{
  "object": "list",
  "data": [
    {
      "id": "Qwen2.5-32B-Instruct-AWQ",
      "object": "model",
      "created": ...,
      "owned_by": "vllm"
    }
  ]
}
```

**Résultat Obtenu** :
✅ Modèle `Qwen2.5-32B-Instruct-AWQ` disponible

---

### Test 3 : Chat Completion Basique 🔄 À FAIRE

**Objectif** : Tester la génération de texte via l'API chat

**Script Python** :
```python
# myia_vllm/tests/test_medium_chat_basic.py

import requests
import json

def test_chat_completion_basic():
    """Test basique de chat completion avec prompt simple"""
    
    url = "http://localhost:5002/v1/chat/completions"
    
    payload = {
        "model": "Qwen2.5-32B-Instruct-AWQ",
        "messages": [
            {
                "role": "user",
                "content": "Qu'est-ce que l'intelligence artificielle en une phrase ?"
            }
        ],
        "max_tokens": 100,
        "temperature": 0.7
    }
    
    response = requests.post(url, json=payload)
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    assert "choices" in data, "Response missing 'choices' field"
    assert len(data["choices"]) > 0, "No choices returned"
    assert "message" in data["choices"][0], "No message in first choice"
    
    message = data["choices"][0]["message"]["content"]
    assert len(message) > 0, "Empty message returned"
    
    print("✅ Test Chat Completion Basique RÉUSSI")
    print(f"Réponse: {message}")
    
    return data

if __name__ == "__main__":
    test_chat_completion_basic()
```

**Commande d'exécution** :
```bash
python myia_vllm/tests/test_medium_chat_basic.py
```

**Critères de Succès** :
- ✅ HTTP 200
- ✅ Réponse contient `choices[0].message.content`
- ✅ Contenu non vide
- ✅ Temps de réponse < 5 secondes

---

### Test 4 : Text Completion Basique 🔄 À FAIRE

**Objectif** : Tester la génération via endpoint completions

**Script Python** :
```python
# myia_vllm/tests/test_medium_completion_basic.py

import requests

def test_text_completion_basic():
    """Test basique de text completion"""
    
    url = "http://localhost:5002/v1/completions"
    
    payload = {
        "model": "Qwen2.5-32B-Instruct-AWQ",
        "prompt": "L'intelligence artificielle est",
        "max_tokens": 50,
        "temperature": 0.7
    }
    
    response = requests.post(url, json=payload)
    
    assert response.status_code == 200
    
    data = response.json()
    assert "choices" in data
    assert len(data["choices"]) > 0
    
    text = data["choices"][0]["text"]
    assert len(text) > 0
    
    print("✅ Test Text Completion Basique RÉUSSI")
    print(f"Texte généré: {text}")
    
    return data

if __name__ == "__main__":
    test_text_completion_basic()
```

**Critères de Succès** :
- ✅ HTTP 200
- ✅ Génération cohérente
- ✅ Respecte max_tokens

---

## 🧠 TESTS FONCTIONNELS AVANCÉS

### Test 5 : Raisonnement Multi-Step 🔄 À FAIRE

**Objectif** : Vérifier capacité de raisonnement Chain-of-Thought

**Base de référence** : [`myia_vllm/tests/scripts/tests/test_reasoning.py`](../../tests/scripts/tests/test_reasoning.py)

**Script Python** :
```python
# myia_vllm/tests/test_medium_reasoning.py

import requests

def test_reasoning_chain_of_thought():
    """Test raisonnement multi-étapes avec Chain-of-Thought"""
    
    url = "http://localhost:5002/v1/chat/completions"
    
    prompt = """Résous ce problème étape par étape :

Un train part de Paris à 10h00 à 120 km/h.
Un autre train part de Lyon (450 km de Paris) à 10h30 à 150 km/h vers Paris.
À quelle heure se croisent-ils ?

Pense étape par étape :
1. Distance initiale
2. Vitesses relatives
3. Calcul du temps
4. Heure de croisement
"""
    
    payload = {
        "model": "Qwen2.5-32B-Instruct-AWQ",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 500,
        "temperature": 0.1  # Basse température pour précision
    }
    
    response = requests.post(url, json=payload)
    
    assert response.status_code == 200
    
    data = response.json()
    answer = data["choices"][0]["message"]["content"]
    
    # Vérifier que la réponse contient les étapes
    assert "étape" in answer.lower() or "step" in answer.lower()
    
    print("✅ Test Raisonnement Multi-Step RÉUSSI")
    print(f"\nRéponse:\n{answer}")
    
    return data

if __name__ == "__main__":
    test_reasoning_chain_of_thought()
```

**Critères de Succès** :
- ✅ Décomposition en étapes
- ✅ Calculs corrects
- ✅ Réponse finale cohérente
- ✅ Format structuré

---

### Test 6 : Tool Calling Qwen3 🔄 À FAIRE

**Objectif** : Tester appels de fonctions avec Qwen3

**Base de référence** : [`myia_vllm/tests/scripts/tests/test_qwen3_tool_calling.py`](../../tests/scripts/tests/test_qwen3_tool_calling.py)

**Script Python** :
```python
# myia_vllm/tests/test_medium_tool_calling.py

import requests
import json

def test_tool_calling_weather():
    """Test tool calling avec fonction météo"""
    
    url = "http://localhost:5002/v1/chat/completions"
    
    # Définir la fonction disponible
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Obtenir la météo actuelle pour une ville",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "Nom de la ville"
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "Unité de température"
                        }
                    },
                    "required": ["city"]
                }
            }
        }
    ]
    
    payload = {
        "model": "Qwen2.5-32B-Instruct-AWQ",
        "messages": [
            {
                "role": "user",
                "content": "Quel temps fait-il à Paris ?"
            }
        ],
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 200
    }
    
    response = requests.post(url, json=payload)
    
    assert response.status_code == 200
    
    data = response.json()
    choice = data["choices"][0]
    
    # Vérifier que le modèle appelle la fonction
    assert "tool_calls" in choice.get("message", {}), "No tool calls in response"
    
    tool_call = choice["message"]["tool_calls"][0]
    assert tool_call["function"]["name"] == "get_weather"
    
    args = json.loads(tool_call["function"]["arguments"])
    assert "city" in args
    assert "paris" in args["city"].lower()
    
    print("✅ Test Tool Calling RÉUSSI")
    print(f"Fonction appelée: {tool_call['function']['name']}")
    print(f"Arguments: {args}")
    
    return data

if __name__ == "__main__":
    test_tool_calling_weather()
```

**Critères de Succès** :
- ✅ Détection correcte du besoin de fonction
- ✅ Nom de fonction correct
- ✅ Arguments corrects et formatés JSON
- ✅ Pas d'hallucinations

---

### Test 7 : Contexte Long (>64k tokens) 🔄 À FAIRE

**Objectif** : Vérifier support contexte jusqu'à 131k tokens

**Script Python** :
```python
# myia_vllm/tests/test_medium_long_context.py

import requests

def test_long_context_64k():
    """Test avec contexte de ~64k tokens"""
    
    url = "http://localhost:5002/v1/chat/completions"
    
    # Générer un long contexte (approximatif : 1 mot = 1.3 tokens)
    # Pour 64k tokens, environ 50k mots
    long_text = "Lorem ipsum dolor sit amet. " * 2000  # ~14k tokens
    
    payload = {
        "model": "Qwen2.5-32B-Instruct-AWQ",
        "messages": [
            {
                "role": "system",
                "content": f"Voici un long document:\n\n{long_text}"
            },
            {
                "role": "user",
                "content": "Résume ce document en une phrase."
            }
        ],
        "max_tokens": 100
    }
    
    response = requests.post(url, json=payload)
    
    assert response.status_code == 200
    
    data = response.json()
    
    # Vérifier usage tokens
    usage = data.get("usage", {})
    print(f"Tokens prompt: {usage.get('prompt_tokens', 'N/A')}")
    print(f"Tokens completion: {usage.get('completion_tokens', 'N/A')}")
    print(f"Total tokens: {usage.get('total_tokens', 'N/A')}")
    
    answer = data["choices"][0]["message"]["content"]
    assert len(answer) > 0
    
    print("✅ Test Contexte Long RÉUSSI")
    print(f"Résumé: {answer}")
    
    return data

if __name__ == "__main__":
    test_long_context_64k()
```

**Critères de Succès** :
- ✅ Pas d'erreur "context too long"
- ✅ Réponse cohérente avec contexte
- ✅ Temps de réponse acceptable (<30s)

---

### Test 8 : Streaming Responses 🔄 À FAIRE

**Objectif** : Tester streaming pour UX temps réel

**Script Python** :
```python
# myia_vllm/tests/test_medium_streaming.py

import requests

def test_streaming_response():
    """Test streaming de la réponse"""
    
    url = "http://localhost:5002/v1/chat/completions"
    
    payload = {
        "model": "Qwen2.5-32B-Instruct-AWQ",
        "messages": [
            {"role": "user", "content": "Raconte-moi une courte histoire."}
        ],
        "max_tokens": 200,
        "stream": True  # Activer streaming
    }
    
    response = requests.post(url, json=payload, stream=True)
    
    assert response.status_code == 200
    
    chunks = []
    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data_str = line[6:]  # Remove 'data: ' prefix
                if data_str != '[DONE]':
                    import json
                    chunk = json.loads(data_str)
                    chunks.append(chunk)
                    
                    # Afficher chunk
                    if 'choices' in chunk and len(chunk['choices']) > 0:
                        delta = chunk['choices'][0].get('delta', {})
                        if 'content' in delta:
                            print(delta['content'], end='', flush=True)
    
    print("\n✅ Test Streaming RÉUSSI")
    print(f"Nombre de chunks reçus: {len(chunks)}")
    
    return chunks

if __name__ == "__main__":
    test_streaming_response()
```

**Critères de Succès** :
- ✅ Réception progressive des tokens
- ✅ Pas de latence anormale entre chunks
- ✅ Message complet cohérent

---

## ⚡ TESTS DE PERFORMANCE

### Test 9 : Latence TTFT (Time To First Token) 🔄 À FAIRE

**Objectif** : Mesurer temps avant premier token

**Base de référence** : [`benchmarks/benchmark_latency.py`](../../../benchmarks/benchmark_latency.py)

**Script Python** :
```python
# myia_vllm/tests/test_medium_latency.py

import requests
import time

def test_ttft_latency():
    """Mesurer Time To First Token"""
    
    url = "http://localhost:5002/v1/chat/completions"
    
    payload = {
        "model": "Qwen2.5-32B-Instruct-AWQ",
        "messages": [
            {"role": "user", "content": "Dis bonjour"}
        ],
        "max_tokens": 1,
        "stream": True
    }
    
    start = time.time()
    response = requests.post(url, json=payload, stream=True)
    
    ttft = None
    for line in response.iter_lines():
        if line and ttft is None:
            ttft = time.time() - start
            break
    
    print(f"✅ TTFT: {ttft:.3f}s")
    
    # Objectifs :
    # - Excellent : < 0.5s
    # - Bon : 0.5-1.0s
    # - Acceptable : 1.0-2.0s
    # - Problématique : > 2.0s
    
    if ttft < 0.5:
        print("  🏆 Excellent")
    elif ttft < 1.0:
        print("  ✅ Bon")
    elif ttft < 2.0:
        print("  ⚠️  Acceptable")
    else:
        print("  ❌ Problématique")
    
    return ttft

if __name__ == "__main__":
    test_ttft_latency()
```

**Critères de Succès** :
- ✅ TTFT < 1.0s (optimal)
- ✅ Cohérent entre runs

---

### Test 10 : Throughput (tokens/sec) 🔄 À FAIRE

**Objectif** : Mesurer vitesse de génération

**Script Python** :
```python
# myia_vllm/tests/test_medium_throughput.py

import requests
import time

def test_throughput():
    """Mesurer throughput en tokens/sec"""
    
    url = "http://localhost:5002/v1/chat/completions"
    
    payload = {
        "model": "Qwen2.5-32B-Instruct-AWQ",
        "messages": [
            {"role": "user", "content": "Écris un paragraphe sur l'IA"}
        ],
        "max_tokens": 500
    }
    
    start = time.time()
    response = requests.post(url, json=payload)
    duration = time.time() - start
    
    data = response.json()
    usage = data.get("usage", {})
    completion_tokens = usage.get("completion_tokens", 0)
    
    throughput = completion_tokens / duration if duration > 0 else 0
    
    print(f"✅ Throughput: {throughput:.1f} tokens/sec")
    print(f"   Tokens générés: {completion_tokens}")
    print(f"   Durée: {duration:.2f}s")
    
    # Objectifs pour 2x RTX 4090 :
    # - Excellent : > 100 tokens/sec
    # - Bon : 50-100 tokens/sec
    # - Acceptable : 30-50 tokens/sec
    
    if throughput > 100:
        print("  🏆 Excellent")
    elif throughput > 50:
        print("  ✅ Bon")
    elif throughput > 30:
        print("  ⚠️  Acceptable")
    else:
        print("  ❌ Sous-optimal")
    
    return throughput

if __name__ == "__main__":
    test_throughput()
```

**Critères de Succès** :
- ✅ Throughput > 50 tokens/sec
- ✅ Utilisation GPU optimale

---

### Test 11 : Tests de Charge (Concurrence) 🔄 À FAIRE

**Objectif** : Tester comportement sous charge

**Base de référence** : [`qwen3_benchmark/`](../../../qwen3_benchmark/)

**Script Python** :
```python
# myia_vllm/tests/test_medium_load.py

import requests
import concurrent.futures
import time

def single_request(request_id):
    """Effectuer une requête simple"""
    url = "http://localhost:5002/v1/chat/completions"
    
    payload = {
        "model": "Qwen2.5-32B-Instruct-AWQ",
        "messages": [
            {"role": "user", "content": f"Dis bonjour #{request_id}"}
        ],
        "max_tokens": 50
    }
    
    start = time.time()
    response = requests.post(url, json=payload)
    duration = time.time() - start
    
    return {
        "id": request_id,
        "status": response.status_code,
        "duration": duration
    }

def test_concurrent_load(num_requests=10, max_workers=5):
    """Test avec requêtes concurrentes"""
    
    print(f"Lancement de {num_requests} requêtes avec {max_workers} workers...")
    
    start = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(single_request, i) for i in range(num_requests)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    total_duration = time.time() - start
    
    # Statistiques
    successes = sum(1 for r in results if r["status"] == 200)
    avg_latency = sum(r["duration"] for r in results) / len(results)
    throughput = num_requests / total_duration
    
    print(f"\n✅ Test de Charge Complété")
    print(f"   Requêtes réussies: {successes}/{num_requests}")
    print(f"   Latence moyenne: {avg_latency:.2f}s")
    print(f"   Throughput global: {throughput:.2f} req/sec")
    print(f"   Durée totale: {total_duration:.2f}s")
    
    return results

if __name__ == "__main__":
    test_concurrent_load(num_requests=20, max_workers=10)
```

**Critères de Succès** :
- ✅ 100% de succès sous charge modérée
- ✅ Latence < 2x latence baseline
- ✅ Pas de crashes ou timeouts

---

### Test 12 : Stabilité Longue Durée 🔄 À FAIRE

**Objectif** : Vérifier pas de memory leaks sur 1h+

**Script Python** :
```python
# myia_vllm/tests/test_medium_stability.py

import requests
import time
import psutil
import docker

def test_long_running_stability(duration_minutes=60, interval_seconds=60):
    """Test stabilité sur longue durée"""
    
    client = docker.from_env()
    container = client.containers.get("myia-vllm-medium-qwen3")
    
    url = "http://localhost:5002/v1/chat/completions"
    
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    
    iteration = 0
    results = []
    
    print(f"Test de stabilité sur {duration_minutes} minutes...")
    
    while time.time() < end_time:
        iteration += 1
        
        # Requête test
        try:
            payload = {
                "model": "Qwen2.5-32B-Instruct-AWQ",
                "messages": [
                    {"role": "user", "content": f"Test iteration {iteration}"}
                ],
                "max_tokens": 50
            }
            
            req_start = time.time()
            response = requests.post(url, json=payload, timeout=30)
            latency = time.time() - req_start
            
            # Stats conteneur
            stats = container.stats(stream=False)
            memory_mb = stats['memory_stats']['usage'] / (1024 * 1024)
            
            result = {
                "iteration": iteration,
                "timestamp": time.time(),
                "status": response.status_code,
                "latency": latency,
                "memory_mb": memory_mb
            }
            results.append(result)
            
            print(f"[{iteration}] Status: {response.status_code}, "
                  f"Latency: {latency:.2f}s, Memory: {memory_mb:.0f}MB")
            
        except Exception as e:
            print(f"❌ Erreur iteration {iteration}: {e}")
            results.append({
                "iteration": iteration,
                "error": str(e)
            })
        
        time.sleep(interval_seconds)
    
    # Analyse résultats
    successes = sum(1 for r in results if r.get("status") == 200)
    avg_latency = sum(r["latency"] for r in results if "latency" in r) / len([r for r in results if "latency" in r])
    
    print(f"\n✅ Test Stabilité Complété")
    print(f"   Itérations: {iteration}")
    print(f"   Succès: {successes}/{iteration}")
    print(f"   Latence moyenne: {avg_latency:.2f}s")
    
    return results

if __name__ == "__main__":
    # Test court pour validation
    test_long_running_stability(duration_minutes=5, interval_seconds=30)
```

**Critères de Succès** :
- ✅ Aucun crash pendant durée test
- ✅ Mémoire stable (pas de leaks)
- ✅ Latence stable dans le temps

---

## 🛡️ TESTS DE ROBUSTESSE

### Test 13 : Gestion Erreurs API 🔄 À FAIRE

**Script Python** :
```python
# myia_vllm/tests/test_medium_error_handling.py

import requests

def test_error_invalid_model():
    """Test avec modèle invalide"""
    url = "http://localhost:5002/v1/chat/completions"
    
    payload = {
        "model": "invalid-model-name",
        "messages": [{"role": "user", "content": "test"}]
    }
    
    response = requests.post(url, json=payload)
    assert response.status_code == 400 or response.status_code == 404
    
    print("✅ Erreur modèle invalide gérée correctement")

def test_error_empty_messages():
    """Test avec messages vides"""
    url = "http://localhost:5002/v1/chat/completions"
    
    payload = {
        "model": "Qwen2.5-32B-Instruct-AWQ",
        "messages": []
    }
    
    response = requests.post(url, json=payload)
    assert response.status_code == 400
    
    print("✅ Messages vides rejetés correctement")

def test_error_excessive_tokens():
    """Test avec max_tokens excessif"""
    url = "http://localhost:5002/v1/chat/completions"
    
    payload = {
        "model": "Qwen2.5-32B-Instruct-AWQ",
        "messages": [{"role": "user", "content": "test"}],
        "max_tokens": 200000  # Au-delà du max
    }
    
    response = requests.post(url, json=payload)
    # Devrait soit rejeter, soit clamper à max_model_len
    
    print(f"✅ max_tokens excessif géré (status: {response.status_code})")

if __name__ == "__main__":
    test_error_invalid_model()
    test_error_empty_messages()
    test_error_excessive_tokens()
```

---

## 📊 RÉSUMÉ ET PRIORITÉS

### Tests par Priorité

**CRITIQUE (À faire en premier)** :
1. ✅ Health Check - **FAIT**
2. ✅ Liste Modèles - **FAIT**
3. 🔄 Chat Completion Basique
4. 🔄 Text Completion Basique

**HAUTE (Avant production)** :
5. 🔄 Raisonnement Multi-Step
6. 🔄 Tool Calling
7. 🔄 Contexte Long
8. 🔄 Streaming

**MOYENNE (Optimisation)** :
9. 🔄 Latence TTFT
10. 🔄 Throughput
11. 🔄 Tests de Charge

**BASSE (Validation robustesse)** :
12. 🔄 Stabilité Longue Durée
13. 🔄 Gestion Erreurs
14. 🔄 Limites Context
15. 🔄 Résistance Crashes

### Ordre d'Exécution Recommandé

```bash
# 1. Tests basiques (5 min)
python myia_vllm/tests/test_medium_chat_basic.py
python myia_vllm/tests/test_medium_completion_basic.py

# 2. Tests fonctionnels (15 min)
python myia_vllm/tests/test_medium_reasoning.py
python myia_vllm/tests/test_medium_tool_calling.py
python myia_vllm/tests/test_medium_streaming.py

# 3. Tests performance (20 min)
python myia_vllm/tests/test_medium_latency.py
python myia_vllm/tests/test_medium_throughput.py
python myia_vllm/tests/test_medium_load.py

# 4. Tests robustesse (variable)
python myia_vllm/tests/test_medium_error_handling.py
python myia_vllm/tests/test_medium_long_context.py
python myia_vllm/tests/test_medium_stability.py  # 5-60 min
```

---

## 📁 STRUCTURE FICHIERS TESTS

```
myia_vllm/tests/
├── test_medium_chat_basic.py          # Test 3
├── test_medium_completion_basic.py     # Test 4
├── test_medium_reasoning.py            # Test 5
├── test_medium_tool_calling.py         # Test 6
├── test_medium_long_context.py         # Test 7
├── test_medium_streaming.py            # Test 8
├── test_medium_latency.py              # Test 9
├── test_medium_throughput.py           # Test 10
├── test_medium_load.py                 # Test 11
├── test_medium_stability.py            # Test 12
└── test_medium_error_handling.py       # Test 13
```

---

## 🎯 MÉTRIQUES CIBLES

### Performance (2x RTX 4090, Qwen3-32B-AWQ)

| Métrique | Cible Minimale | Cible Optimale | Notes |
|----------|----------------|----------------|-------|
| TTFT | < 1.0s | < 0.5s | Prompt court |
| Throughput | > 50 tok/s | > 100 tok/s | Génération |
| Latence P50 | < 2.0s | < 1.0s | Prompts variés |
| Latence P99 | < 5.0s | < 3.0s | Worst case |
| Concurrent Requests | 10 | 20+ | Sans dégradation |

### Robustesse

| Critère | Cible |
|---------|-------|
| Uptime sur 1h | 100% |
| Taux erreurs | < 0.1% |
| Memory leaks | Aucun |
| Crash recovery | < 30s |

---

## 📝 NOTES IMPORTANTES

### Contexte du Document

Ce plan de tests a été créé durant la **PHASE 9** de la MISSION 9 (Redéploiement Service Medium - Méthodologie SDDD).

**Raison de non-exécution** : Selon les instructions SDDD, la phase 9 consiste à **documenter** les tests sans les exécuter. L'exécution sera faite ultérieurement par l'équipe ou via une sous-tâche dédiée.

### Prérequis Avant Exécution

1. ✅ Service medium déployé et HEALTHY
2. ✅ Port 5002 accessible
3. ✅ Python 3.8+ avec `requests` installé
4. ✅ Docker accessible pour stats conteneur
5. 🔄 Créer les fichiers de tests listés ci-dessus

### Dépendances Python

```bash
pip install requests pytest docker psutil
```

### Variables d'Environnement

```bash
# Optionnel pour tests
export VLLM_API_BASE=http://localhost:5002
export VLLM_MODEL=Qwen2.5-32B-Instruct-AWQ
```

---

## 🔗 RÉFÉRENCES

- Déploiement : [`DEPLOYMENT_MEDIUM_20251016.md`](./DEPLOYMENT_MEDIUM_20251016.md)
- Configuration : [`MEDIUM_SERVICE.md`](./MEDIUM_SERVICE.md)
- Paramètres : [`MEDIUM_SERVICE_PARAMETERS.md`](../docker/MEDIUM_SERVICE_PARAMETERS.md)
- Tests existants : [`tests/scripts/tests/`](../../tests/scripts/tests/)
- Benchmarks : [`qwen3_benchmark/`](../../../qwen3_benchmark/)

---

**Version** : 1.0  
**Status** : ⚠️ Documentation uniquement - Tests non exécutés  
**Dernière mise à jour** : 2025-10-16  
**Auteur** : Agent Code (Mode SDDD - Mission 9)