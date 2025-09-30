import argparse
import json
import sys

from ..client import VLLMClient
from ..test_data import REASONING_MESSAGES
from ..utils import log

def test_reasoning(client: VLLMClient, model_name: str) -> bool:
    """Teste la capacité de raisonnement d'un modèle."""
    log("INFO", f"Testing reasoning for {model_name}...")
    
    data = {
        "model": model_name,
        "messages": REASONING_MESSAGES,
        "max_tokens": 500
    }
    
    try:
        result = client.chat_completion(**data)
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            log("ERROR", "La réponse ne contient pas de contenu.")
            return False
            
        log("INFO", "✅ Reasoning test successful!")
        log("INFO", f"Response: {content}")
        return True
    except Exception as e:
        log("ERROR", f"❌ Exception: {str(e)}")
        return False

def main():
    """Fonction principale."""
    parser = argparse.ArgumentParser(description="Test de raisonnement pour un service vLLM.")
    parser.add_argument("--model", default="vllm-qwen3-32b-awq", help="Nom du modèle à tester.")
    parser.add_argument("--endpoint", default="http://localhost:5001/v1", help="URL de l'API vLLM.")
    parser.add_argument("--api-key", default="X0EC4YYP068CPD5TGARP9VQB5U4MAGHY", help="Clé API.")
    
    args = parser.parse_args()
    
    client = VLLMClient(endpoint=args.endpoint, api_key=args.api_key)
    
    if test_reasoning(client, args.model):
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main())