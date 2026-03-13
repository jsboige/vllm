#!/usr/bin/env python3
"""
Test script for vLLM /v1/models endpoint.

This script queries the OpenAI-compatible /v1/models endpoint to list
all available models and display their status.

Usage:
    python test_models_endpoint.py [--host HOST] [--port PORT] [--api-key KEY]

Environment variables:
    VLLM_HOST: Default host (default: localhost)
    VLLM_PORT: Default port (default: 5002)
    VLLM_API_KEY: API key for authentication
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

try:
    import requests
except ImportError:
    print("Error: 'requests' library required. Install with: pip install requests")
    sys.exit(1)


@dataclass
class ModelInfo:
    """Represents a model from the /v1/models endpoint."""
    id: str
    owned_by: str
    created: Optional[int] = None
    object_type: str = "model"
    
    @property
    def created_date(self) -> Optional[str]:
        """Convert Unix timestamp to human-readable date."""
        if self.created is None:
            return None
        return datetime.fromtimestamp(self.created).strftime("%Y-%m-%d %H:%M:%S")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Test vLLM /v1/models endpoint and display available models"
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("VLLM_HOST", "localhost"),
        help="vLLM server host (default: localhost or VLLM_HOST env var)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("VLLM_PORT", "5002")),
        help="vLLM server port (default: 5002 or VLLM_PORT env var)"
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("VLLM_API_KEY"),
        help="API key for authentication (default: VLLM_API_KEY env var)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON response"
    )
    return parser.parse_args()


def build_url(host: str, port: int) -> str:
    """Build the full endpoint URL."""
    return f"http://{host}:{port}/v1/models"


def get_models(host: str, port: int, api_key: Optional[str]) -> dict:
    """
    Query the /v1/models endpoint.
    
    Args:
        host: Server hostname
        port: Server port
        api_key: Optional API key for authentication
        
    Returns:
        JSON response as dictionary
        
    Raises:
        requests.RequestException: On connection or HTTP errors
    """
    url = build_url(host, port)
    headers = {"Content-Type": "application/json"}
    
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    
    return response.json()


def parse_models(response: dict) -> list[ModelInfo]:
    """
    Parse the API response into ModelInfo objects.
    
    Args:
        response: JSON response from /v1/models endpoint
        
    Returns:
        List of ModelInfo objects
    """
    models = []
    for model_data in response.get("data", []):
        models.append(ModelInfo(
            id=model_data.get("id", "unknown"),
            owned_by=model_data.get("owned_by", "unknown"),
            created=model_data.get("created"),
            object_type=model_data.get("object", "model")
        ))
    return models


def print_models(models: list[ModelInfo], host: str, port: str) -> None:
    """
    Display models in a formatted table.
    
    Args:
        models: List of ModelInfo objects
        host: Server hostname (for display)
        port: Server port (for display)
    """
    print(f"\n{'='*70}")
    print(f" vLLM Models Endpoint - {host}:{port}")
    print(f"{'='*70}\n")
    
    if not models:
        print("  ⚠ No models available")
        return
    
    # Determine column widths
    id_width = max(len(m.id) for m in models)
    owner_width = max(len(m.owned_by) for m in models)
    
    # Header
    print(f"  {'Model ID':<{id_width}}  {'Owner':<{owner_width}}  {'Created'}")
    print(f"  {'-'*id_width}  {'-'*owner_width}  {'-'*19}")
    
    # Rows
    for model in models:
        created = model.created_date or "N/A"
        status_icon = "✓" if model.id else "✗"
        print(f"  {status_icon} {model.id:<{id_width}}  {model.owned_by:<{owner_width}}  {created}")
    
    print(f"\n  Total: {len(models)} model(s) available")
    print(f"{'='*70}\n")


def main() -> int:
    """
    Main entry point.
    
    Returns:
        Exit code (0 for success, 1 for error)
    """
    args = parse_args()
    
    try:
        # Query endpoint
        response = get_models(args.host, args.port, args.api_key)
        
        # Output format
        if args.json:
            print(json.dumps(response, indent=2))
            return 0
        
        # Parse and display
        models = parse_models(response)
        print_models(models, args.host, args.port)
        
        return 0
        
    except requests.exceptions.ConnectionError:
        print(f"\n✗ Connection failed: Cannot reach {args.host}:{args.port}")
        print("  Ensure the vLLM server is running and accessible.")
        return 1
        
    except requests.exceptions.Timeout:
        print(f"\n✗ Request timed out: {args.host}:{args.port}")
        return 1
        
    except requests.exceptions.HTTPError as e:
        print(f"\n✗ HTTP error: {e.response.status_code} - {e.response.text}")
        return 1
        
    except json.JSONDecodeError:
        print("\n✗ Invalid JSON response from server")
        return 1
        
    except Exception as e:
        print(f"\n✗ Unexpected error: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
