import json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://localhost:5002"
KEY = os.environ["VLLM_API_KEY_MEDIUM"]
MODEL = os.environ.get("AB_MODEL", "qwen3.8-27b")
TAG = sys.argv[1] if len(sys.argv) > 1 else "run"


def post(payload, timeout=300):
    req = urllib.request.Request(
        BASE + "/v1/chat/completions", data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = json.load(r)
    return b, time.time() - t0


def metrics():
    req = urllib.request.Request(BASE + "/metrics",
                                 headers={"Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode()


def mtp_acceptance():
    try:
        m = metrics()
        acc = float(re.search(r'vllm:spec_decode_num_accepted_tokens_total\{[^}]*\} (\S+)', m).group(1))
        drf = float(re.search(r'vllm:spec_decode_num_draft_tokens_total\{[^}]*\} (\S+)', m).group(1))
        return acc / drf if drf > 0 else 0.0
    except Exception:
        return None


def fourgram_ratio(txt):
    toks = txt.split()
    if len(toks) < 8:
        return 0.0
    grams = [tuple(toks[i:i + 4]) for i in range(len(toks) - 3)]
    return 1 - len(set(grams)) / len(grams)


CANARIES = [
    ("fr", "Explique en deux phrases pourquoi le ciel est bleu."),
    ("code", "Ecris une fonction Python qui calcule la somme des carres des n premiers entiers, avec un exemple."),
    ("math", "Combien font 11 fois 12 ? Reponds par le nombre seul."),
]


def canary():
    ok, det = True, []
    for tag, prompt in CANARIES:
        b, dt = post({"model": MODEL, "max_tokens": 300, "temperature": 0.7,
                      "messages": [{"role": "user", "content": prompt}],
                      "chat_template_kwargs": {"enable_thinking": False}}, 300)
        txt = b["choices"][0]["message"].get("content") or ""
        ratio = fourgram_ratio(txt)
        sane = ratio < 0.5 and len(txt.strip()) > 0
        if tag == "math":
            sane = sane and "132" in txt
        else:
            sane = sane and len(txt.strip()) > 30
        ok = ok and sane
        det.append(f"{tag}:{'OK' if sane else 'DEGENERATE'}(r4g={ratio:.2f},{len(txt.strip())}ch,{dt:.1f}s)")
    return ok, det


def single_stream(rounds=3, max_tokens=300):
    rates = []
    for r in range(rounds):
        b, dt = post({"model": MODEL, "max_tokens": max_tokens, "temperature": 0.7,
                      "messages": [{"role": "user", "content":
                                    f"Describe in detail how PagedAttention works (pass {r})."}],
                      "chat_template_kwargs": {"enable_thinking": False}}, 300)
        rates.append(b["usage"]["completion_tokens"] / dt)
    return rates


def concurrent(n=16, max_tokens=200):
    payloads = [{"model": MODEL, "max_tokens": max_tokens, "temperature": 0.7,
                 "messages": [{"role": "user", "content":
                               f"Ecris un paragraphe detaille sur l'histoire du train a grande vitesse, variante {i}."}],
                 "chat_template_kwargs": {"enable_thinking": False}} for i in range(n)]

    def run(p):
        b, dt = post(p, 600)
        return b["usage"]["completion_tokens"]

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=n) as ex:
        total = sum(ex.map(run, payloads))
    wall = time.time() - t0
    return total / wall


if __name__ == "__main__":
    print(f"=== AB BENCH {TAG} model={MODEL} t={time.strftime('%H:%M:%S')} ===", flush=True)
    ok, det = canary()
    acc = mtp_acceptance()
    single = single_stream()
    agg = concurrent()
    acc2 = mtp_acceptance()
    print(f"RESULT|{TAG}|acceptance={acc}|acceptance_after_load={acc2}"
          f"|canary={'PASS' if ok else 'FAIL:' + ';'.join(det)}"
          f"|single={'/'.join(f'{r:.0f}' for r in single)}|n16={agg:.0f}", flush=True)
    print("canary detail:", "; ".join(det), flush=True)
