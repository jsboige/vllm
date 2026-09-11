# Traffic Identity

`traffic_identity.py` turns the privileged vLLM request capture into a small, reviewable traffic map. It is a diagnostic tool, not an access-control list.

## Why this exists

A public IP rarely identifies a person. Shared NAT, roaming connections, VPN exits, reverse proxies, and containers all reuse addresses. Conversational and application signatures are often more useful: client family, endpoint, model, time window, and a short request clue.

The tool therefore uses a human-in-the-loop cycle:

1. scan the live JSONL and all rotated gzip archives;
2. group requests by address and coarse signature;
3. apply only the small set of reviewed rules in the registry;
4. present recent public unknown groups locally with redacted conversation clues;
5. add a rule only after a person validates the attribution.

It does not learn identities, modify the network, rotate credentials, or change the leaked-key monitor.

## Files

- `scripts/monitoring/traffic_identity.py` — scanner, classifier, local review queue, and reports.
- `configs/monitoring/traffic_identity_registry.json` — reviewed evidence and conditional entries.
- `logs/traffic_identity.review.json` — operator-only report; may contain short redacted clues.
- `logs/traffic_identity.summary.json` and `.md` — shareable reports; never contain conversation text.

Everything under `logs/` remains gitignored.

## Commands

From `myia_vllm`:

```powershell
python scripts/monitoring/traffic_identity.py validate-registry
python scripts/monitoring/traffic_identity.py inventory
python scripts/monitoring/traffic_identity.py review --since 2026-09-01T00:00:00Z --limit 30
python scripts/monitoring/traffic_identity.py explain --group <group-id>
python scripts/monitoring/traffic_identity.py migrate-state --dry-run
```

`inventory` reads, in order, every `logs/archive/error_sources-*.jsonl.gz`, transitional `.jsonl` archives, and the current `logs/error_sources.jsonl`. Exact raw-line hashes prevent double counting when the current file is later found in an archive. No hash is published. The first syntactically valid `X-Forwarded-For` hop is trusted only because the front proxy is expected to overwrite client-supplied forwarding headers; deployments that append untrusted values must fix that boundary before using network matches as evidence.

A missing corpus produces `NO_CORPUS` and exit code 4. An unreadable archive or malformed complete line produces `INCOMPLETE` and exit code 3. Neither is reported as “no traffic.” An incomplete final line is retried on the next scan.

## Privacy boundary

The source log is privileged: request fragments can contain prompts and occasionally embedded credentials.

The local review file may contain at most three short clues per group. Before storage, the tool:

- prefers the last user message when a captured body is valid JSON;
- collapses whitespace and truncates to 240 characters;
- redacts credential-like assignments, long hexadecimal/token-like strings, and email addresses.

It is still operator-only and must not be posted to dashboards or committed.

The shared JSON and Markdown are constructed from an allowlist of fields. They omit clues, authorization prefixes, raw bodies, arbitrary user agents, and referrers. Unknown groups are reduced to aggregate counters; their exact and masked addresses are both omitted. Known addresses remain visible because the requested operator inventory needs them.

## Registry semantics

Subjects are typed as machine, service, team, person, location, or network. Rules combine reviewed evidence such as an IP/CIDR, coarse UA category, conversational category, endpoint, and validity interval.

States are deliberately simple:

- `ACTIVE` — reviewed current fact;
- `HISTORICAL` — useful attribution for a past period;
- `PENDING_DEPLOYMENT` — expected signature, but deployment has not been observed;
- `CONDITIONAL` — never activate from traffic alone;
- `DISPUTED` — contradictory evidence remains visible.

Every person rule requires explicit confirmation. If it also matches a network, it must include application evidence; a network-only person rule is invalid. Shared ranges can identify a location or network, not everyone behind it. Conditional and pending subjects cannot auto-activate. Person labels are omitted from the shared pending-subject list.

## Initial interpretation rules

- **web1:** the historical OVH address is retained; the documented migration target requires firsthand cutover evidence.
- **La Bretonnière:** known LAN addresses identify infrastructure roles. A proxy or NAT address does not identify the end user.
- **po-2027:** roaming addresses become time-bounded observations; traffic alone does not bind them to the machine.
- **SAFARI:** this is a business conversational signature, not the Safari browser UA. It identifies the cohort only. Stéphane or another team member needs external validation.
- **LivresAgités:** the historical `AI Engine` signature is useful, but the service stays `PENDING_DEPLOYMENT` until new post-deployment traffic is observed and reviewed.
- **Jamin:** no pre-registration. A future request produces evidence to review, not automatic attribution.
- **Vanessa:** no active rule. A future Claude Desktop-like signature remains an unknown candidate until validated; Claude Code through Claudish is a different path.
- **Conflicting egress:** contradictory po-2023/po-2025 evidence remains `DISPUTED` until a new firsthand measurement settles it.

## Human qualification workflow

Run `inventory`, then `review`. The review queue defaults to public `UNKNOWN` and `DISPUTED` groups, newest first. The shared report contains only their aggregate group/event counts; detailed unknowns stay in this bounded local queue. Use the group ID to discuss the traffic without copying the raw request. Once the user identifies it, add the narrowest time-bounded rule with a dated evidence statement and rerun `validate-registry` plus the tests.

Do not add an address merely because it appears plausible. Prefer application/conversation evidence, and keep unknown when the evidence does not separate multiple people.

## Maintenance and Claudish consumption

Maintenance and Claudish should consume `traffic_identity.summary.json` or invoke the reporting command. They must not parse the raw log or maintain another identity table. They must check `schema_version`, `generated_at`, and `coverage.verdict`; a stale, unsupported, or incomplete artifact is `UNKNOWN`.

The existing `claudish_traffic` tool remains authoritative for Claude Code proxy traffic. It is not a replacement for this vLLM-side organ.

## Shadow rollout

The first release is intentionally not scheduled and does not publish automatically. Validate it against the real corpus into an isolated operator directory, review all recognized and disputed groups, and scan the shared artifact for leaks. Scheduler/dashboard wiring is a later operational change after that shadow output is accepted.

Rollback is simply to stop invoking this script. No service, proxy, credential, or runtime monitor state is changed.
