"""
Script de test basique pour Qwen3-VL-32B-Instruct-FP8
Mission 17 : Validation du support vision vLLM

Ce script teste les capacités de base du modèle multimodal:
- Chargement d'une image de test
- Requête vision simple (image captioning)
- Validation du preprocessing multimodal
"""

import base64
import sys
from pathlib import Path

import openai
import requests


def encode_image_to_base64(image_path: Path) -> str:
    """Encode une image en base64 pour l'API OpenAI."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def download_test_image(image_path: Path) -> None:
    """Télécharge une image de test officielle Qwen si elle n'existe pas."""
    if image_path.exists():
        print(f"✅ Image de test déjà présente : {image_path}")
        return
    
    # Image de démo officielle Qwen
    url = "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen-VL/assets/demo.jpeg"
    print(f"📥 Téléchargement de l'image de test depuis {url}...")
    
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    
    # Créer le répertoire parent si nécessaire
    image_path.parent.mkdir(parents=True, exist_ok=True)
    
    image_path.write_bytes(response.content)
    print(f"✅ Image téléchargée : {image_path}")


def test_qwen3_vl_basic():
    """Test de base du modèle Qwen3-VL avec une requête vision simple."""
    
    # Configuration du client OpenAI pointant vers vLLM local
    client = openai.OpenAI(
        base_url="http://localhost:5002/v1",  # Port du service medium-vl
        api_key="vllm",  # Clé par défaut vLLM
    )
    
    # Chemin de l'image de test
    image_path = Path(__file__).parent / "test_image.jpg"
    
    # Télécharger l'image si nécessaire
    try:
        download_test_image(image_path)
    except Exception as e:
        print(f"❌ Erreur lors du téléchargement de l'image : {e}")
        return False
    
    # Encoder l'image en base64
    print("\n🔄 Encodage de l'image en base64...")
    base64_image = encode_image_to_base64(image_path)
    print(f"✅ Image encodée ({len(base64_image)} caractères)")
    
    # Requête à l'API vLLM
    print("\n🚀 Envoi de la requête vision à vLLM...")
    try:
        response = client.chat.completions.create(
            model="Qwen/Qwen3-VL-32B-Instruct-FP8",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is in this image? Describe it in detail."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            max_tokens=200,
            temperature=0.7,
        )
        
        # Afficher la réponse
        print("\n" + "=" * 60)
        print("RÉPONSE DU MODÈLE :")
        print("=" * 60)
        print(response.choices[0].message.content)
        print("=" * 60)
        
        # Vérifications basiques
        assert response.choices[0].message.content, "❌ Réponse vide du modèle"
        assert len(response.choices[0].message.content) > 10, "❌ Réponse trop courte"
        
        print("\n✅ Test de base réussi !")
        return True
        
    except openai.OpenAIError as e:
        print(f"\n❌ Erreur API OpenAI : {e}")
        return False
    except Exception as e:
        print(f"\n❌ Erreur inattendue : {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("TEST BASIQUE QWEN3-VL-32B-INSTRUCT-FP8")
    print("Mission 17 - Validation Support Vision")
    print("=" * 60)
    
    success = test_qwen3_vl_basic()
    
    if success:
        print("\n✅ TOUS LES TESTS SONT PASSÉS")
        sys.exit(0)
    else:
        print("\n❌ ÉCHEC DES TESTS")
        sys.exit(1)