import gzip
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[2] / "scripts" / "monitoring" / "traffic_identity.py"
)
SPEC = importlib.util.spec_from_file_location("traffic_identity", MODULE_PATH)
ti = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(ti)
REGISTRY_PATH = (
    Path(__file__).parents[2]
    / "configs"
    / "monitoring"
    / "traffic_identity_registry.json"
)


def event(ts, ip, ua="", text="hello", path="/v1/chat/completions", status=200):
    return {
        "ts": ts,
        "status": status,
        "path": path,
        "client": "172.19.0.1:1234",
        "model": "qwen3.6-35b-a3b",
        "user_agent": ua,
        "x_forwarded_for": ip,
        "x_real_ip": "",
        "referer": "https://private.example/user",
        "auth_prefix": "Bearer DO-NOT-LEAK-THIS...",
        "body_head": json.dumps({"messages": [{"role": "user", "content": text}]}),
        "body_tail": "",
    }


class TrafficIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.live = self.root / "error_sources.jsonl"
        self.archives = self.root / "archive"
        self.archives.mkdir()
        self.registry = ti.load_registry(REGISTRY_PATH)

    def tearDown(self):
        self.temp.cleanup()

    def write_lines(self, path, records, gzip_output=False):
        content = b"".join(
            json.dumps(record, ensure_ascii=False).encode() + b"\n"
            for record in records
        )
        if gzip_output:
            with gzip.open(path, "wb") as stream:
                stream.write(content)
        else:
            path.write_bytes(content)
        return content

    def test_registry_is_valid(self):
        self.assertEqual([], ti.validate_registry(self.registry))

    def test_registry_rejects_empty_match(self):
        registry = json.loads(json.dumps(self.registry))
        registry["rules"][0]["match"] = {}
        self.assertTrue(
            any("empty match" in error for error in ti.validate_registry(registry))
        )

    def test_registry_rejects_person_matched_only_by_network(self):
        registry = json.loads(json.dumps(self.registry))
        registry["subjects"].append(
            {
                "id": "person:test",
                "type": "person",
                "label": "Test",
                "state": "ACTIVE",
            }
        )
        registry["rules"].append(
            {
                "id": "person-network-only",
                "subject_id": "person:test",
                "match": {"networks": ["8.8.8.8/32"]},
                "requires_confirmation": True,
                "evidence": "test",
                "state": "ACTIVE",
            }
        )
        errors = ti.validate_registry(registry)
        self.assertTrue(any("cannot match only a network" in error for error in errors))

    def test_registry_requires_until_for_historical_rules(self):
        registry = json.loads(json.dumps(self.registry))
        historical = next(
            rule for rule in registry["rules"] if rule["state"] == "HISTORICAL"
        )
        historical["until"] = None
        errors = ti.validate_registry(registry)
        self.assertTrue(
            any("historical rule requires until" in error for error in errors)
        )

    def test_registry_rejects_unknown_match_fields_and_reversed_window(self):
        registry = json.loads(json.dumps(self.registry))
        registry["rules"][0]["match"]["typo"] = "value"
        registry["rules"][0]["from"] = "2026-09-02T00:00:00Z"
        registry["rules"][0]["until"] = "2026-09-01T00:00:00Z"
        errors = ti.validate_registry(registry)
        self.assertTrue(any("unknown match fields" in error for error in errors))
        self.assertTrue(any("from is after until" in error for error in errors))

    def test_registry_requires_confirmation_for_every_person_rule(self):
        registry = json.loads(json.dumps(self.registry))
        registry["subjects"].append(
            {
                "id": "person:test",
                "type": "person",
                "label": "Test",
                "state": "ACTIVE",
            }
        )
        registry["rules"].append(
            {
                "id": "person-signature",
                "subject_id": "person:test",
                "match": {"ua": "other"},
                "evidence": "test",
                "state": "ACTIVE",
            }
        )
        errors = ti.validate_registry(registry)
        self.assertTrue(
            any("requires explicit confirmation" in error for error in errors)
        )

    def test_parse_time_rejects_naive_timestamp(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            ti.parse_time("2026-09-01T12:00:00")

    def test_live_and_archive_are_deduplicated(self):
        duplicate = event(1770000000, "37.187.180.135")
        self.write_lines(self.archives / "error_sources-1.jsonl.gz", [duplicate], True)
        self.write_lines(self.live, [duplicate, event(1770000001, "8.8.8.8")])
        observations, coverage = ti.scan(ti.discover_sources(self.live, self.archives))
        self.assertEqual(2, len(observations))
        self.assertEqual("COMPLETE", coverage["verdict"])
        self.assertEqual(2, coverage["unique_lines"])

    def test_archive_final_line_without_newline_is_not_lost(self):
        archived = event(1770000000, "8.8.8.8")
        path = self.archives / "error_sources-1.jsonl"
        path.write_bytes(json.dumps(archived).encode())
        observations, coverage = ti.scan([path])
        self.assertEqual(1, len(observations))
        self.assertEqual("COMPLETE", coverage["verdict"])

    def test_malformed_and_partial_lines_do_not_abort(self):
        good = json.dumps(event(1770000000, "8.8.8.8")).encode() + b"\n"
        self.live.write_bytes(good + b"not-json\n" + b'{"partial":')
        observations, coverage = ti.scan([self.live])
        self.assertEqual(1, len(observations))
        self.assertEqual(1, coverage["parse_errors"])
        self.assertEqual("INCOMPLETE", coverage["verdict"])

    def test_invalid_timestamp_marks_coverage_incomplete(self):
        missing = event(1770000000, "8.8.8.8")
        missing.pop("ts")
        non_finite = event(float("nan"), "8.8.4.4")
        self.write_lines(self.live, [missing, non_finite])
        observations, coverage = ti.scan([self.live])
        self.assertEqual([], observations)
        self.assertEqual(2, coverage["parse_errors"])
        self.assertEqual("INCOMPLETE", coverage["verdict"])

    def test_corrupt_archive_marks_coverage_incomplete(self):
        (self.archives / "error_sources-bad.jsonl.gz").write_bytes(b"not-gzip")
        _, coverage = ti.scan(ti.discover_sources(self.live, self.archives))
        self.assertEqual("INCOMPLETE", coverage["verdict"])
        self.assertEqual("BadGzipFile", coverage["source_errors"][0]["error"])

    def test_corrupt_gzip_payload_marks_coverage_incomplete(self):
        path = self.archives / "error_sources-corrupt.jsonl.gz"
        payload = bytearray(gzip.compress(b'{"ts":1770000000}\n'))
        for index in range(12, min(len(payload) - 8, 18)):
            payload[index] ^= 0xFF
        path.write_bytes(payload)
        _, coverage = ti.scan([path])
        self.assertEqual("INCOMPLETE", coverage["verdict"])
        self.assertIn(coverage["source_errors"][0]["error"], {"error", "BadGzipFile"})

    def test_address_parsing_handles_xff_ports_ipv6_and_real_ip(self):
        self.assertEqual(
            "203.0.113.7",
            ti.client_ip({"x_forwarded_for": "203.0.113.7:456, 10.0.0.1"}),
        )
        self.assertEqual(
            "2001:db8::1", ti.client_ip({"x_forwarded_for": "[2001:db8::1]:443"})
        )
        self.assertEqual("8.8.4.4", ti.client_ip({"x_real_ip": "8.8.4.4"}))
        self.assertEqual("global", ti.ip_scope("172.200.1.1"))
        self.assertEqual("private", ti.ip_scope("172.19.0.1"))

    def test_safari_business_is_not_browser_safari(self):
        business = event(
            1788220800,
            "92.184.113.1",
            ua="",
            text="SAFARI — réglementation des ascenseurs",
        )
        browser = event(
            1788220801,
            "43.207.125.128",
            ua="Mozilla Safari/605.1",
            text="SAFARI — réglementation des ascenseurs",
        )
        self.write_lines(self.live, [business, browser])
        observations, _ = ti.scan([self.live])
        groups = ti.group_observations(observations, self.registry)
        safari = [group for group in groups if group["signature"]["ua"] == "empty"][0]
        browser_group = [
            group for group in groups if group["signature"]["ua"] == "browser_safari"
        ][0]
        self.assertTrue(
            any(match["subject_id"] == "team:safari" for match in safari["matches"])
        )
        self.assertFalse(
            any(
                match["subject_id"] == "team:safari"
                for match in browser_group["matches"]
            )
        )
        self.assertFalse(
            any(match["subject_type"] == "person" for match in safari["matches"])
        )

    def test_safari_cohort_survives_disputed_network_match(self):
        timestamp = ti.parse_time("2026-09-01T12:00:00Z")
        self.write_lines(
            self.live,
            [event(timestamp, "90.65.170.144", ua="", text="SAFARI ascenseur")],
        )
        observations, _ = ti.scan([self.live])
        group = ti.group_observations(observations, self.registry)[0]
        subject_ids = {match["subject_id"] for match in group["matches"]}
        self.assertEqual("DISPUTED", group["verdict"])
        self.assertIn("team:safari", subject_ids)
        self.assertIn("network:disputed-egress", subject_ids)

    def test_safari_classification_uses_both_raw_fragments_when_json_is_truncated(self):
        record = event(1788220800, "92.184.113.1", ua="", text="ignored")
        record["body_head"] = '{"messages":[{"role":"user","content":"SAFARI'
        record["body_tail"] = 'réglementation des ascenseurs"}]}'
        clue = ti.conversation_clue(record)
        self.assertEqual("safari_business", ti.categorize_conversation(record, clue))

    def test_pending_and_conditional_subjects_never_auto_identify_people(self):
        records = [
            event(1789000000, "8.8.8.8", ua="AI Engine", text="Maison d'édition"),
            event(1789000000.5, "8.8.4.4", ua="AI Engine", text="", path="/v1/models"),
            event(1789000001, "77.83.247.145", ua="curl/8.4.0", text="liveness"),
            event(1789000002, "1.1.1.1", ua="Claude Desktop/1.0", text="hello"),
        ]
        self.write_lines(self.live, records)
        observations, _ = ti.scan([self.live])
        groups = ti.group_observations(observations, self.registry)
        livres = [group for group in groups if group["signature"]["ua"] == "ai_engine"]
        self.assertEqual(2, len(livres))
        self.assertTrue(
            all(
                group["matches"][0]["state"] == "PENDING_DEPLOYMENT" for group in livres
            )
        )
        self.assertTrue(
            all(group["verdict"] == "PENDING_DEPLOYMENT" for group in livres)
        )
        self.assertFalse(
            any(
                match["subject_type"] == "person"
                for group in groups
                for match in group["matches"]
            )
        )
        vanessa = next(
            group
            for group in groups
            if group["signature"]["ua"] == "claude_desktop_candidate"
        )
        self.assertEqual("UNKNOWN", vanessa["verdict"])

    def test_disputed_network_stays_disputed(self):
        self.write_lines(self.live, [event(1789000000, "90.65.170.144")])
        observations, _ = ti.scan([self.live])
        group = ti.group_observations(observations, self.registry)[0]
        self.assertEqual("DISPUTED", group["verdict"])

    def test_expired_rule_does_not_label_later_matching_traffic(self):
        old = event(1788220800, "92.184.113.1", ua="", text="SAFARI ascenseur")
        later = event(1790000000, "92.184.113.1", ua="", text="SAFARI ascenseur")
        self.write_lines(self.live, [old, later])
        observations, _ = ti.scan([self.live])
        groups = ti.group_observations(observations, self.registry)
        self.assertEqual(2, len(groups))
        self.assertEqual({"KNOWN", "UNKNOWN"}, {group["verdict"] for group in groups})

    def test_conditional_network_is_not_reported_as_known(self):
        self.write_lines(
            self.live,
            [event(1789000001, "77.83.247.145", ua="curl/8.4.0", text="liveness")],
        )
        observations, _ = ti.scan([self.live])
        group = ti.group_observations(observations, self.registry)[0]
        self.assertEqual("CONDITIONAL", group["verdict"])

    def test_shared_output_has_no_conversation_or_credentials(self):
        canary = "PRIVATE-CANARY-987"
        old = os.environ.get("TRAFFIC_IDENTITY_PRIVACY_CANARY")
        os.environ["TRAFFIC_IDENTITY_PRIVACY_CANARY"] = canary
        try:
            self.write_lines(
                self.live, [event(1789000000, "8.8.8.8", text=f"{canary} token=ABCDEF")]
            )
            observations, coverage = ti.scan([self.live])
            groups = ti.group_observations(observations, self.registry)
            shared = {
                "schema_version": 1,
                "generated_at": ti.now_iso(),
                "coverage": coverage,
                "pending_subjects": [],
                "groups": ti.shared_rows(groups),
            }
            rendered = json.dumps(shared)
            ti.assert_shared_safe(shared)
            self.assertNotIn(canary, rendered)
            self.assertNotIn("Bearer", rendered)
            self.assertNotIn("conversation_clues", rendered)
            self.assertNotIn("8.8.8", rendered)
        finally:
            if old is None:
                os.environ.pop("TRAFFIC_IDENTITY_PRIVACY_CANARY", None)
            else:
                os.environ["TRAFFIC_IDENTITY_PRIVACY_CANARY"] = old

    def test_unknown_groups_keep_redacted_clues_only_in_operator_report(self):
        clue = ti.conversation_clue(
            event(
                1789000000,
                "8.8.8.8",
                text="contact me at a@example.com token=secretvalue",
            )
        )
        self.assertIn("[REDACTED]", clue)
        self.assertNotIn("a@example.com", clue)
        self.assertNotIn("secretvalue", clue)
        json_clue = ti.redact('{"api_key":"json secret with spaces", "message":"safe"}')
        self.assertNotIn("json secret with spaces", json_clue)
        self.assertNotIn("with spaces", json_clue)
        bearer_clue = ti.redact("Authorization: Bearer short-secret")
        self.assertNotIn("short-secret", bearer_clue)

    def test_shared_report_suppresses_unattributed_internal_groups(self):
        self.write_lines(
            self.live,
            [
                event(1789000000, "172.19.0.1", text="internal"),
                event(1789000001, "8.8.8.8", text="public"),
                event(1789000002, "192.168.0.47", text="known internal"),
            ],
        )
        observations, _ = ti.scan([self.live])
        groups = ti.group_observations(observations, self.registry)
        shared = ti.shared_rows(groups)
        addresses = {group["ip"] for group in shared}
        self.assertNotIn("172.19.0.1", addresses)
        self.assertNotIn("8.8.8.8", addresses)
        self.assertIn("192.168.0.47", addresses)

    def test_inventory_reports_missing_corpus_as_non_success(self):
        operator = self.root / "operator.json"
        shared = self.root / "shared.json"
        markdown = self.root / "shared.md"
        args = type(
            "Args",
            (),
            {
                "registry": str(REGISTRY_PATH),
                "live": str(self.root / "missing.jsonl"),
                "archive_dir": str(self.root / "missing-archive"),
                "operator_output": str(operator),
                "shared_output": str(shared),
                "markdown_output": str(markdown),
            },
        )()
        self.assertEqual(4, ti.inventory(args))
        payload = json.loads(shared.read_text(encoding="utf-8"))
        self.assertEqual("NO_CORPUS", payload["coverage"]["verdict"])
        self.assertIsNone(payload["coverage"]["first_observed"])
        self.assertIsNone(payload["coverage"]["last_observed"])

    def test_inventory_summarizes_unknowns_without_listing_them(self):
        self.write_lines(
            self.live,
            [
                event(1789000000, "8.8.8.8", text="unknown private clue"),
                event(1789000001, "192.168.0.47", text="known internal"),
            ],
        )
        operator = self.root / "operator.json"
        shared = self.root / "shared.json"
        markdown = self.root / "shared.md"
        args = type(
            "Args",
            (),
            {
                "registry": str(REGISTRY_PATH),
                "live": str(self.live),
                "archive_dir": str(self.archives),
                "operator_output": str(operator),
                "shared_output": str(shared),
                "markdown_output": str(markdown),
            },
        )()
        self.assertEqual(0, ti.inventory(args))
        payload = json.loads(shared.read_text(encoding="utf-8"))
        self.assertEqual(1, payload["unknown_public"]["group_count"])
        self.assertEqual(1, payload["unknown_public"]["event_count"])
        self.assertEqual(1, payload["unknown_public"]["groups_with_local_clues"])
        self.assertEqual(1, len(payload["groups"]))
        self.assertFalse(
            any(item["id"] == "person:vanessa" for item in payload["pending_subjects"])
        )
        rendered = markdown.read_text(encoding="utf-8")
        self.assertIn("Public unknowns: 1 groups / 1 events", rendered)
        self.assertNotIn("8.8.8", rendered)
        self.assertNotIn("unknown private clue", rendered)

    def test_explain_omits_conversation_clues(self):
        report = self.root / "operator.json"
        report.write_text(
            json.dumps(
                {
                    "coverage": {"verdict": "COMPLETE"},
                    "groups": [
                        {
                            "group_id": "abc",
                            "ip": "8.8.8.8",
                            "conversation_clues": ["private clue"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        args = type(
            "Args", (), {"operator_output": str(report), "group": "abc", "ip": None}
        )()
        from contextlib import redirect_stdout
        from io import StringIO

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, ti.explain(args))
        rendered = output.getvalue()
        self.assertNotIn("private clue", rendered)
        self.assertNotIn("conversation_clues", rendered)
        self.assertIn('"group_id": "abc"', rendered)

    def test_review_command_filters_to_public_unknown_groups(self):
        self.write_lines(
            self.live,
            [
                event(1789000000, "172.19.0.1", text="internal"),
                event(1789000001, "8.8.8.8", text="public clue"),
            ],
        )
        observations, coverage = ti.scan([self.live])
        groups = ti.group_observations(observations, self.registry)
        operator = self.root / "operator.json"
        operator.write_text(
            json.dumps({"coverage": coverage, "groups": groups}), encoding="utf-8"
        )
        review_file = self.root / "review.md"
        args = type(
            "Args",
            (),
            {
                "operator_output": str(operator),
                "since": None,
                "include_known": False,
                "limit": 10,
                "output": str(review_file),
            },
        )()
        self.assertEqual(0, ti.review(args))
        rendered = review_file.read_text(encoding="utf-8")
        self.assertIn("8.8.8.8", rendered)
        self.assertIn("public clue", rendered)
        self.assertNotIn("172.19.0.1", rendered)


if __name__ == "__main__":
    unittest.main()
