#!/usr/bin/env python3
"""
Test d'audit rapide pour vérifier l'état des services Qwen3
"""

import requests
import json
import sys

def test_service(port, api_key, service_name):
    """Test un service Qwen3"""
    print(f"\n=== TEST {service_name.upper()} (Port {port}) ===")
    
    # Test 1: Vérifier les modèles
    try:
        response = requests.get(
            f"http://localhost:{port}/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10
        )
        if response.status_code == 200:
            models = response.json()
            model_id = models['data'][0]['id']
            print(f"[OK] Modele charge: {model_id}")
        else:
            print(f"[ERREUR] Erreur modeles: {response.status_code}")
            return False
    except Exception as e:
        print(f"[ERREUR] Erreur connexion: {e}")
        return False
    
    # Test 2: Test simple de génération
    try:
        response = requests.post(
            f"http://localhost:{port}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": "Dis juste 'OK'"}],
                "max_tokens": 10
            },
            timeout=30
        )
        if response.status_code == 200:
            result = response.json()
            print(f"[DEBUG] Response: {json.dumps(result, indent=2)}")
            content = result['choices'][0]['message']['content']
            if content:
                print(f"[OK] Generation: {content.strip()}")
            else:
                print(f"[WARN] Generation vide")
        else:
            print(f"[ERREUR] Erreur generation: {response.status_code}")
            print(f"[DEBUG] Response: {response.text}")
            return False
    except Exception as e:
        print(f"[ERREUR] Erreur generation: {e}")
        return False
    
    # Test 3: Test tool calling simple
    try:
        response = requests.post(
            f"http://localhost:{port}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": "Utilise la fonction test_function pour dire bonjour"}],
                "tools": [{
                    "type": "function",
                    "function": {
                        "name": "test_function",
                        "description": "Une fonction de test",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "message": {"type": "string", "description": "Message à afficher"}
                            },
                            "required": ["message"]
                        }
                    }
                }],
                "tool_choice": "auto",
                "max_tokens": 100
            },
            timeout=30
        )
        if response.status_code == 200:
            result = response.json()
            message = result['choices'][0]['message']
            if 'tool_calls' in message and message['tool_calls']:
                print(f"[OK] Tool calling: Fonction appelee")
            else:
                print(f"[WARN] Tool calling: Pas d'appel de fonction detecte")
        else:
            print(f"[ERREUR] Erreur tool calling: {response.status_code}")
    except Exception as e:
        print(f"[ERREUR] Erreur tool calling: {e}")
    
    return True

def main():
    """Test principal"""
    print("AUDIT COMPLET DES SERVICES QWEN3")
    print("=" * 50)
    
    services = [
        (5000, "test-key-micro", "MICRO (Qwen3-1.7B-FP8)"),
        (5001, "test-key-mini", "MINI (Qwen3-8B-AWQ)"),
        (5002, "test-key-medium", "MEDIUM (Qwen3-32B-AWQ)")
    ]
    
    results = []
    for port, api_key, name in services:
        success = test_service(port, api_key, name)
        results.append((name, success))
    
    print("\n" + "=" * 50)
    print("RESUME DE L'AUDIT")
    print("=" * 50)
    
    all_ok = True
    for name, success in results:
        status = "FONCTIONNEL" if success else "DEFAILLANT"
        print(f"{name}: {status}")
        if not success:
            all_ok = False
    
    if all_ok:
        print("\nTOUS LES SERVICES SONT FONCTIONNELS !")
    else:
        print("\nCERTAINS SERVICES ONT DES PROBLEMES")
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())