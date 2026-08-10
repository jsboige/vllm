#!/usr/bin/env python3
"""Sonde phase 1 : force un prefill de continuation (~30 K tokens, chunke) puis
verifie que le moteur survit.

Le crash vllm#41726 (`turboquant_attn.py:720:_continuation_prefill`) se declenchait
au PREMIER chunk de continuation, c.-a-d. des qu'un prompt depasse
--max-num-batched-tokens. On envoie donc un prompt tres au-dessus de 4096, puis une
requete courte pour verifier que l'EngineCore n'est pas mort/wedge derriere.

Usage: python probe.py [--port 5003] [--tokens 30000]
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request

BASE_WORDS = (
    "the quick brown fox jumps over a lazy dog while parsing tensor shapes and "
    "allocating workspace buffers for continuation prefill across attention layers "
    "in a hybrid gated delta network with quantized key value cache entries "
).split()


def build_prompt(approx_tokens: int) -> str:
    """~4 chars/token. Texte varie (pas une seule phrase repetee) pour rester
    realiste sans dependre d'un tokenizer local."""
    out, i = [], 0
    # ~0.75 mot/token en anglais
    target_words = int(approx_tokens * 0.75)
    while len(out) < target_words:
        w = BASE_WORDS[i % len(BASE_WORDS)]
        if i % 17 == 0:
            out.append(f"[segment-{i // 17}]")
        out.append(w)
        i += 1
    return " ".join(out)


def post(port: int, payload: dict, timeout: int):
    req = urllib.request.Request(
        f"http://localhost:{port}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read())
    return body, time.time() - t0


def wait_health(port: int, max_wait: int) -> bool:
    t0 = time.time()
    while time.time() - t0 < max_wait:
        try:
            with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=5) as r:
                if r.status == 200:
                    print(f"[health] 200 apres {time.time() - t0:.0f}s")
                    return True
        except Exception:
            pass
        time.sleep(5)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5003)
    ap.add_argument("--tokens", type=int, default=30000)
    ap.add_argument("--model", default=None, help="defaut: 1er modele servi")
    ap.add_argument("--boot-wait", type=int, default=900)
    a = ap.parse_args()

    if not wait_health(a.port, a.boot_wait):
        print(f"ECHEC: /health pas 200 apres {a.boot_wait}s -- le moteur n'a pas boote")
        return 2

    model = a.model
    if model is None:
        with urllib.request.urlopen(f"http://localhost:{a.port}/v1/models", timeout=10) as r:
            model = json.loads(r.read())["data"][0]["id"]
    print(f"[modele] {model}")

    prompt = build_prompt(a.tokens)
    print(f"[prompt] {len(prompt)} chars (~{a.tokens} tokens vises)")

    # 1. LE test : prefill long -> chunke -> chemin _continuation_prefill
    print("\n=== 1/2 prefill long (continuation) ===")
    try:
        body, dt = post(
            a.port,
            {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt + "\n\nEn un mot, quel animal est cite ?"}
                ],
                "max_tokens": 32,
                "temperature": 0.0,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=600,
        )
    except Exception as e:  # noqa: BLE001
        print(f"ECHEC prefill long: {type(e).__name__}: {e}")
        print(">>> verifier `docker logs` : turboquant_attn.py / Workspace is locked / EngineDeadError")
        return 1

    u = body.get("usage", {})
    print(f"OK en {dt:.1f}s | prompt_tokens={u.get('prompt_tokens')} "
          f"completion_tokens={u.get('completion_tokens')}")
    print(f"reponse: {body['choices'][0]['message'].get('content', '')[:120]!r}")

    # 2. le moteur survit-il ? (un wedge se voit ici, pas au-dessus)
    print("\n=== 2/2 requete courte apres coup (test de survie) ===")
    try:
        body2, dt2 = post(
            a.port,
            {
                "model": model,
                "messages": [{"role": "user", "content": "Dis simplement: OK"}],
                "max_tokens": 16,
                "temperature": 0.0,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=120,
        )
    except Exception as e:  # noqa: BLE001
        print(f"ECHEC survie: {type(e).__name__}: {e}")
        print(">>> le prefill long a passe mais le moteur est mort/wedge derriere")
        return 1

    print(f"OK en {dt2:.1f}s | reponse: "
          f"{body2['choices'][0]['message'].get('content', '')[:80]!r}")
    print("\n=== VERDICT: les 2 requetes ont abouti ===")
    print("Confirmer l'absence de trace dans les logs avant de conclure.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
