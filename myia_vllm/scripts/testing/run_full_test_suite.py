#!/usr/bin/env python3
"""
Full Test Suite Runner for Qwen3-Coder-Next Deployment.

This script runs a comprehensive validation suite after deployment:
1. Pre-flight checks (model files, Docker container, GPU memory)
2. API health and connectivity tests
3. Inference benchmarks (latency, throughput)
4. Tool calling validation (single, multi-tool, result cycle)
5. Reasoning quality tests
6. Code generation quality
7. Concurrent load testing
8. Memory stress test

Usage:
    python run_full_test_suite.py [--quick] [--api-url URL]
    python run_full_test_suite.py --preflight-only  # Only check prerequisites
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def check_model_files(model_path: str = "./models/Qwen3-Coder-Next-W4A16") -> dict:
    """Check if quantized model files exist and are valid."""
    model_dir = Path(model_path)
    result = {
        "exists": model_dir.exists(),
        "path": str(model_dir.absolute()),
        "files": [],
        "total_size_gb": 0,
    }

    if model_dir.exists():
        files = list(model_dir.glob("*"))
        result["files"] = [f.name for f in files]

        # Check for required files
        required_patterns = ["config.json", "tokenizer", "*.safetensors"]
        has_config = any(f.name == "config.json" for f in files)
        has_tokenizer = any("tokenizer" in f.name for f in files)
        has_weights = any(f.suffix == ".safetensors" for f in files)

        result["has_config"] = has_config
        result["has_tokenizer"] = has_tokenizer
        result["has_weights"] = has_weights
        result["valid"] = has_config and has_tokenizer and has_weights

        # Calculate total size
        total_size = sum(f.stat().st_size for f in files if f.is_file())
        result["total_size_gb"] = round(total_size / (1024**3), 2)

    return result


def check_docker_container(container_name: str = "myia_vllm-medium-coder") -> dict:
    """Check Docker container status."""
    result = {
        "running": False,
        "healthy": False,
        "status": "not found",
        "error": None,
    }

    try:
        # Check if container exists and its status
        output = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}} {{.State.Health.Status}}", container_name],
            capture_output=True,
            text=True,
        )

        if output.returncode == 0:
            parts = output.stdout.strip().split()
            status = parts[0] if parts else "unknown"
            health = parts[1] if len(parts) > 1 else "no healthcheck"

            result["status"] = status
            result["running"] = status == "running"
            result["healthy"] = health == "healthy"
            result["health_status"] = health
        else:
            result["error"] = output.stderr.strip()

    except FileNotFoundError:
        result["error"] = "Docker not found"
    except Exception as e:
        result["error"] = str(e)

    return result


def check_gpu_memory() -> dict:
    """Check GPU memory availability."""
    result = {
        "gpus": [],
        "total_vram_gb": 0,
        "available_vram_gb": 0,
        "error": None,
    }

    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
        )

        if output.returncode == 0:
            for line in output.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 5:
                    gpu = {
                        "index": int(parts[0]),
                        "name": parts[1],
                        "total_mb": int(parts[2]),
                        "used_mb": int(parts[3]),
                        "free_mb": int(parts[4]),
                    }
                    result["gpus"].append(gpu)
                    result["total_vram_gb"] += gpu["total_mb"] / 1024
                    result["available_vram_gb"] += gpu["free_mb"] / 1024

            result["total_vram_gb"] = round(result["total_vram_gb"], 1)
            result["available_vram_gb"] = round(result["available_vram_gb"], 1)
        else:
            result["error"] = output.stderr.strip()

    except FileNotFoundError:
        result["error"] = "nvidia-smi not found"
    except Exception as e:
        result["error"] = str(e)

    return result


def run_preflight_checks() -> bool:
    """Run all pre-flight checks and report status."""
    print("=" * 60)
    print("PRE-FLIGHT CHECKS")
    print("=" * 60)

    all_passed = True

    # Check 1: Model files
    print("\n[1/3] Checking model files...")
    model_check = check_model_files()
    if model_check["exists"] and model_check.get("valid", False):
        print(f"  ✓ Model found: {model_check['path']}")
        print(f"    Size: {model_check['total_size_gb']} GB")
        print(f"    Files: {len(model_check['files'])} files")
    else:
        print(f"  ✗ Model NOT found or invalid at: {model_check['path']}")
        if model_check["exists"]:
            print(f"    Missing: config={not model_check.get('has_config')}, "
                  f"tokenizer={not model_check.get('has_tokenizer')}, "
                  f"weights={not model_check.get('has_weights')}")
        all_passed = False

    # Check 2: Docker container
    print("\n[2/3] Checking Docker container...")
    docker_check = check_docker_container()
    if docker_check["running"]:
        status_icon = "✓" if docker_check["healthy"] else "⚠"
        print(f"  {status_icon} Container running: {docker_check['status']}")
        print(f"    Health: {docker_check.get('health_status', 'unknown')}")
    else:
        print(f"  ○ Container not running: {docker_check['status']}")
        if docker_check["error"]:
            print(f"    Error: {docker_check['error']}")
        # Not a failure - container can be started later

    # Check 3: GPU memory
    print("\n[3/3] Checking GPU availability...")
    gpu_check = check_gpu_memory()
    if gpu_check["gpus"]:
        print(f"  ✓ Found {len(gpu_check['gpus'])} GPU(s):")
        for gpu in gpu_check["gpus"]:
            print(f"    GPU {gpu['index']}: {gpu['name']} "
                  f"({gpu['free_mb']/1024:.1f}GB free / {gpu['total_mb']/1024:.1f}GB total)")
        print(f"  Total VRAM: {gpu_check['total_vram_gb']} GB")
        print(f"  Available: {gpu_check['available_vram_gb']} GB")

        # Check if we have enough for the model (~46GB needed)
        if gpu_check["total_vram_gb"] < 70:
            print("  ⚠ Warning: Total VRAM may be insufficient (need ~46GB for model + KV cache)")
    else:
        print(f"  ✗ No GPUs detected: {gpu_check['error']}")
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("PRE-FLIGHT: ALL CHECKS PASSED")
    else:
        print("PRE-FLIGHT: SOME CHECKS FAILED")
    print("=" * 60)

    return all_passed


async def run_benchmarks(api_url: str, quick_mode: bool = False):
    """Run the benchmark suite."""
    # Import the benchmark module
    from benchmark_coder_next import CoderNextBenchmark

    benchmark = CoderNextBenchmark(
        api_url=api_url,
        model_name="qwen3-coder-next",
        timeout=180.0,  # Longer timeout for 80B model
    )

    await benchmark.run_all(
        include_concurrent=True,
        concurrent_users=5 if not quick_mode else 3,
        requests_per_user=3 if not quick_mode else 2,
        quick_mode=quick_mode,
    )

    return benchmark.results


def generate_report(results: list, output_file: str = None):
    """Generate a test report."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_tests": len(results),
            "passed": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
        },
        "results": [
            {
                "test": r.test_name,
                "success": r.success,
                "latency_ms": r.latency_ms,
                "tokens_per_second": r.tokens_per_second,
                "error": r.error,
                "details": r.details,
            }
            for r in results
        ],
    }

    report["summary"]["pass_rate"] = f"{report['summary']['passed']}/{report['summary']['total_tests']}"

    if output_file:
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReport saved to: {output_file}")

    return report


async def main():
    parser = argparse.ArgumentParser(
        description="Full test suite for Qwen3-Coder-Next deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:5002",
        help="vLLM API URL (default: http://localhost:5002)",
    )

    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: fewer tests, lower concurrency",
    )

    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Only run pre-flight checks, skip benchmarks",
    )

    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip pre-flight checks, run benchmarks directly",
    )

    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Save report to JSON file",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("QWEN3-CODER-NEXT FULL TEST SUITE")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API URL: {args.api_url}")
    print()

    # Pre-flight checks
    if not args.skip_preflight:
        preflight_ok = run_preflight_checks()

        if args.preflight_only:
            sys.exit(0 if preflight_ok else 1)

        if not preflight_ok:
            print("\n⚠ Pre-flight checks had issues. Continue anyway? (y/N)")
            response = input().strip().lower()
            if response != "y":
                print("Aborting.")
                sys.exit(1)

    # Run benchmarks
    print("\n")
    results = await run_benchmarks(args.api_url, args.quick)

    # Generate report
    if args.report:
        generate_report(results, args.report)

    # Exit with appropriate code
    passed = sum(1 for r in results if r.success)
    total = len(results)

    if passed == total:
        print("\n✓ ALL TESTS PASSED - Deployment is ready for production!")
        sys.exit(0)
    else:
        print(f"\n✗ {total - passed}/{total} tests failed - Review issues above")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
