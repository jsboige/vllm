"""Teacher-forced passage NLL through /v1/completions prompt_logprobs (our own probe, stdlib only).

Same passage, same server flags except the KV dtype -> the bf16 vs fp8 KV delta is the number
that matters; the absolute value only has to look like natural text (~1.5-2.5 nats/token).
usage: python -I probe_nll.py <base_url> <model> <out.json> [label]
"""
import json
import math
import os
import sys
import time
import urllib.request

PASSAGE = (
    "The river rises in the hills to the north, where the snow lingers until late spring, and it "
    "runs south through a long valley of farms before it reaches the sea. For most of the year it "
    "is shallow and slow, and children wade across it in summer to reach the orchards on the far "
    "bank. In April, however, the melt arrives all at once. The water turns brown, the current "
    "carries whole branches past the mill, and the old stone bridge, built two centuries ago by "
    "the parish, becomes the only way to cross for several weeks. The farmers keep records of the "
    "highest floods by cutting marks into the bridge's eastern pillar, and the oldest mark is now "
    "so worn that only a careful eye can read the year beside it. Engineers who surveyed the "
    "valley last decade proposed a dam upstream, arguing that it would protect the lower fields "
    "and supply electricity to the nearby town. The proposal divided the community: some welcomed "
    "the promise of steady water for irrigation, while others feared that the reservoir would "
    "drown the meadows where their families had grazed sheep for generations. After two years of "
    "meetings, the council decided to build a series of small retention ponds instead, which slow "
    "the spring flood without blocking the river entirely."
)


def post(url, body, timeout=300):
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("PROBE_API_KEY")  # only for the known-positive check on prod; the test server is keyless
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main():
    base, model, out = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
    label = sys.argv[4] if len(sys.argv) > 4 else ""
    t0 = time.time()
    r = post(f"{base}/completions", {"model": model, "prompt": PASSAGE, "max_tokens": 1,
                                       "temperature": 0, "prompt_logprobs": 0})
    pl = r["choices"][0].get("prompt_logprobs")
    # prompt_logprobs=0 -> each position holds ONLY the actual prompt token's logprob (no top-k),
    # so a multi-entry position means the server did not honour k=0: counted, never guessed.
    lps, multi = [], 0
    for entry in (pl or [])[1:]:  # first token has no context
        if not entry:
            continue
        if len(entry) != 1:
            multi += 1
            continue
        lps.append(next(iter(entry.values()))["logprob"])
    nll = -sum(lps) / len(lps) if lps else float("nan")
    res = {"label": label, "model": model, "tokens_scored": len(lps), "multi_entry_skipped": multi, "mean_nll": nll,
           "ppl": math.exp(nll) if lps else float("nan"), "prompt_tokens": r.get("usage", {}).get("prompt_tokens"),
           "elapsed_s": round(time.time() - t0, 2)}
    json.dump(res, open(out, "w", encoding="utf-8"), indent=2)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
