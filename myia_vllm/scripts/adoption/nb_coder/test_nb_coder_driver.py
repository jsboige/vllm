"""Pins for the call-failure classifier (vllm#457, on top of #442's F5).

#442 shipped `call_failure()` with **no test at all** — one file touched, the driver. That
function carries two properties worth freezing: the verdict must name the right REPAIR
(a credential problem and a model-name problem are repaired in different places, by
different people), and a long error must not lose the sentence that explains it.

Every fixture below is a string measured on po-2028:claudish the 16/11 three-model sweep,
not an invented shape — a pin built on a made-up payload protects nothing.

Skipped when `mcp` is not importable (the driver imports the MCP client at load).
"""
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nb_coder_driver as d  # noqa: E402


# The real 403 body, verbatim from the luna run's driver.log (em dashes included: they are
# what the proxy emits, and a pin that normalises them stops testing the real string).
_LUNA_403 = (
    'ServiceResponseException: ("<class \'…OpenAIChatCompletion\'> service failed to complete '
    "the prompt\", PermissionDeniedError(\"Error code: 403 - {'error': {'message': 'claudish: "
    "unknown model nb-luna — not found in any provider catalog or routing map (it was "
    "defaulted to the native lane, which this proxy cannot serve: no Anthropic credential) "
    "— use provider@model or a configured alias', 'type': 'permission_error', 'code': "
    'None}}"))'
)


def _verdict(err: str) -> str:
    return d.call_failure({"error": err})


def test_unknown_model_403_is_model_unresolved():
    v = _verdict(_LUNA_403)
    assert v.startswith("model-unresolved: "), v


def test_model_unresolved_wins_over_the_status_code():
    """Both markers are present (403 and 'unknown model'); the body must win.

    This is the whole point of #457: the code is ambiguous (`permission_error` rides 403 on
    the OpenAI wire), the wording is not. A future refactor that checks the code first turns
    this test red without moving the fixture.
    """
    v = _verdict(_LUNA_403)
    assert "auth-failed" not in v


def test_401_invalid_proxy_authentication_is_still_auth_failed():
    """The #441 case must not regress: an unset api_key_env IS a credential problem."""
    v = _verdict("Error code: 401 - invalid proxy authentication")
    assert v.startswith("auth-failed: "), v


def test_timeout_with_a_large_ms_count_is_not_auth():
    """Word boundaries, not substring search: '1401' must never match '401'."""
    v = _verdict("timeout after 1401 ms")
    assert v.startswith("call-failed: "), v


def test_a_port_number_is_not_auth():
    v = _verdict("listening on port 8403")
    assert v.startswith("call-failed: "), v


def test_a_model_unresolved_verdict_names_the_model():
    """The window is centred on the marker: the verdict must carry the word that justifies it.

    Head+tail alone put the model name at char ~185 — past the head slice, before the tail
    slice. The pin found that gap in the fix itself; this assertion is what keeps it closed.
    """
    v = _verdict(_LUNA_403)
    assert "nb-luna" in v, "the verdict lost the model name it is about"
    assert "unknown model" in v


def test_a_long_plain_error_keeps_both_ends():
    """Without a marker: the head names the exception, the tail names the cause."""
    v = _verdict("E" * 300 + " THE ACTUAL CAUSE")
    assert v.startswith("call-failed: EEE"), v
    assert v.endswith("THE ACTUAL CAUSE"), v


def test_the_abbreviated_payload_stays_bounded():
    payload = _verdict(_LUNA_403).removeprefix("model-unresolved: ")
    assert len(payload) <= 160, len(payload)
    assert not payload.startswith(" "), "the window opens mid-token"


def test_the_short_error_is_not_abbreviated():
    v = _verdict("boom")
    assert v == "call-failed: boom"


def test_an_answered_call_returns_no_verdict():
    assert d.call_failure({}) == ""
    assert d.call_failure({"response": "fine"}) == ""


# ---- grain tag (CoursIA's merge gate, 16/11) ----

def test_grain_tag_is_the_line_the_parser_reads():
    assert d.grain_tag("MED", "myia-po-2028:claudish", 26804) == (
        "Grain: MED/notebook-python — lane myia-po-2028:claudish — issue #26804")


def test_auto_is_refused_rather_than_written_silently():
    """The exact string that made every harness PR unmergeable: `auto` is not a tier."""
    with pytest.raises(ValueError):
        d.grain_tag("auto", "myia-po-2028:claudish", 26804)


def test_the_pr_body_is_built_from_the_flag_not_from_a_literal():
    """A pin on the CALL SITE: `grain_tag()` can be perfect and still never be used.

    Reverting the body to its old literal would leave every behavioural pin green — the
    regression lives in a string, so the pin reads the source (house pattern: grep the
    wiring, not the intent).
    """
    src = Path(d.__file__).read_text(encoding="utf-8")
    assert 'f"{grain_tag(args.grain_tier' in src, "the PR body no longer uses the flag"
    assert '"Grain: auto' not in src, "a literal `auto` tier is back in the source"


def test_grain_tag_round_trips_through_the_coursia_parser():
    """Read by the CONSUMER, not by a copy of its grammar. Skipped where CoursIA is absent."""
    coursia = Path(r"D:\dev\CoursIA\scripts")
    if not (coursia / "grain_tag.py").is_file():
        pytest.skip("CoursIA checkout absent on this seat")
    sys.path.insert(0, str(coursia))
    import grain_tag as g  # noqa: E402

    parsed = g.parse_grain_tag(d.grain_tag("LIGHT", "myia-po-2028:claudish", 26804))
    assert parsed["tier"] == "LIGHT"
    assert parsed["genre"] == "notebook-python"
    assert parsed["lane"] == "myia-po-2028:claudish"