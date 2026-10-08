# Swift-1.5-27B — batch 8192 + seqs 48 (2026-10-08 soir, feu vert user)

**Mandat** : user parti dormir — « tu as mon feu vert pour faire des tests et adopter les
paramètres qui améliorent nos perfs ». Deux paramètres, méthode A/B même-soirée, adoption
sur mesure, tout reverté si perdant. **Les deux ADOPTÉS ; en prod depuis 21:50Z (8192) et
22:14Z (48).**

## Leviers choisis (et ce qu'on n'a pas touché)

- `--max-num-batched-tokens 4096 → 8192` : levier **prefill** — la douleur documentée du
  27B dense est la starvation des nouvelles requêtes pendant un prefill géant
  (130-170 s pour ≥100K). 8192 validé sur le MoE (PR #24), 16K rejeté (−17 % KV),
  jamais tranché sur Swift.
- `--max-num-seqs 32 → 48` : levier **capacité** — la lignée PR #74 (16→32 = +70 % de
  plafond d'agrégat).
- **Non touché** : gpu-util 0.70 (règle : jamais remonter sans re-mesure ; risque
  boot-OOM pendant la nuit = crash-loop de 6 h sans user).

## Le piège de fraîcheur (éliminé par contre-test)

La baseline initiale (21:22Z) courait sur le moteur âgé de 3 jours ; chaque config de
test sur moteur frais. Or **ce soir, tout moteur frais mesure ~8 % sous le moteur âgé**
(4096 : 577,7 âgé vs 530-532 frais ; cf. investigation débit machine). Comparer
« 8192-frais vs 4096-âgé » fabrique un faux recul prefill (−5 %) ET un faux plafond de
gain decode. **Contre-test mené : recreate 4096 frais + double sweep** → la comparaison
valide est frais-vs-frais, entrelacée dans la même heure.

## Résultats (frais vs frais, moyennes des passages)

| N | 4096/32 | 8192/32 | 8192/48 |
|---|---|---|---|
| 16 | 333 | 412 | 412-414 |
| 24 | 464 | 569 | 564-572 |
| 32 | 531 | **718** | 698-723 |
| 48 | — | — | **907,5** |
| prefill 157K (t/s) | 1 316 | 1 595 | 1 608 |
| per-stream @max N | 22,9 | 29,0 | 23,1 |
| KV tokens | 456 004 | 429 319 | 424 610 |
| VRAM GPU0/1 (MiB) | 20 159/19 158 | 19 781/18 780 | 19 937/18 930 |

**8192** : decode +23-35 % à N≥16, prefill +21 %, KV −5,9 % (1,64× la fenêtre —
immatériel à 2-7 % d'occupation), VRAM inchangée. **48** : plafond +26 % de plus
(N=48 : 907 t/s, stable sur 2 passages), per-stream 23 t/s, zéro coût mesurable
(KV −1,3 %, VRAM +150 MiB, préfill identique).

## Instruments

- `bench_concurrent_scaling.py` étendu à 48 prompts distincts (même règle
  anti-inflation que PR #74 : jamais de prompts partagés, sinon le prefix-cache fausse
  les nombres).
- Sonde prefill (scratchpad, non versionnée) : filler à mots distincts tirés avec
  seed aléatoire → 157K tokens, impossible à servir depuis le prefix-cache ; métrique
  = prompt_tokens/wall.

## Validation en trafic réel

Le passage nbaudit de **22:05Z a tourné sur la config 8192** (`ok:true`, vague 1
complète `19451:Audio/` incluse) — les audits sk-agent passent. Watchdog v5 et
wedge-telemetry non recréés (Up 3 jours), moteur healthy, 0 OOM sur les 3 boots.

## Reste ouvert

- La référence VRAM de la spec surveillance (`GPU 0 ≈ 20 700-21 400`) date de
  4096/32 ; à 8192/48 la mesure est **19 937/18 930** — la fourchette mérite une
  actualisation au prochain cycle (elle est prudente, pas fausse).
- La dérive machine (moteur âgé ~8 % plus rapide que tout frais ce soir) reste
  inexpliquée — voir `project_machine_throughput_investigation`.
