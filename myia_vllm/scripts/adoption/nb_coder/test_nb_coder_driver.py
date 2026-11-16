"""Pins for the call-failure classifier (vllm#457, on top of #442's F5).

#442 shipped `call_failure()` with **no test at all** — one file touched, the driver. That
function carries two properties worth freezing: the verdict must name the right REPAIR
(a credential problem and a model-name problem are repaired in different places, by
different people), and a long error must not lose the sentence that explains it.

Every fixture below is a string measured on po-2028:claudish the 16/11 three-model sweep,
not an invented shape — a pin built on a made-up payload protects nothing.

Skipped when `mcp` is not importable (the driver imports the MCP client at load).
"""
import json
import subprocess
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
# The tag is read by TWO guards, and the second one was measured the hard way: the tier guard
# wants `Grain: <TIER>/<GENRE>`, and #10983's guard poses `variation-tag-prev-absent` on a tag
# that declares no predecessor. CoursIA#26943 carried both labels the moment it opened.

def test_grain_tag_is_the_line_the_parser_reads():
    assert d.grain_tag("MED", "myia-po-2028:claudish") == (
        "Grain: MED/notebook-python — lane myia-po-2028:claudish — "
        "prev: none (premier grain)")


def test_auto_is_refused_rather_than_written_silently():
    """The exact string that made every harness PR unmergeable: `auto` is not a tier."""
    with pytest.raises(ValueError):
        d.grain_tag("auto", "myia-po-2028:claudish")


def test_a_predecessor_is_cited_verbatim():
    assert d.grain_tag("LIGHT", "l", prev="MED/tooling #26943") == (
        "Grain: LIGHT/notebook-python — lane l — prev: MED/tooling #26943")


def test_a_prev_that_is_not_a_predecessor_is_refused():
    """`prev:` is read as a CITATION, so a value that is not one must not reach the body."""
    with pytest.raises(ValueError):
        d.grain_tag("MED", "l", prev="auto/notebook-python")
    with pytest.raises(ValueError):
        d.grain_tag("MED", "l", prev="see the previous one")


def test_an_unreadable_history_omits_the_field_rather_than_inventing_one():
    """No predecessor READ is not the same fact as no predecessor EXISTING.

    Writing the exemption here would assert a first grain nobody checked; the guard's label
    is then the true verdict, and the trace records why (see `lane_predecessor`).
    """
    tag = d.grain_tag("MED", "myia-po-2028:claudish", prev=None)
    assert "prev" not in tag
    assert tag == "Grain: MED/notebook-python — lane myia-po-2028:claudish"


def test_nothing_scannable_follows_the_prev_field():
    """The parser takes the first `#N` within 120 chars after `prev: <TIER>/<GENRE>`.

    A trailing `— issue #26804` (this harness's old tag shape) would be READ AS THE PR
    NUMBER: an adjacency verdict against an issue that is not a grain. `prev:` is last.
    """
    tag = d.grain_tag("MED", "l", prev="MED/notebook-python")
    assert tag.endswith("prev: MED/notebook-python")


def test_the_pr_body_is_built_from_the_flag_not_from_a_literal():
    """A pin on the CALL SITE: `grain_tag()` can be perfect and still never be used.

    Reverting the body to its old literal would leave every behavioural pin green — the
    regression lives in a string, so the pin reads the source (house pattern: grep the
    wiring, not the intent).
    """
    src = Path(d.__file__).read_text(encoding="utf-8")
    assert 'f"{grain_tag(args.grain_tier' in src, "the PR body no longer uses the flag"
    assert '"Grain: auto' not in src, "a literal `auto` tier is back in the source"
    # The predecessor reaches the tag from a real read, not from a constant.
    assert "lane_predecessor(repo_slug, args.lane, token)" in src
    assert "prev=prev" in src, "the read predecessor is no longer handed to the tag"


# ---- lane predecessor (vllm#459: `prev:` is lane history, not a value this run knows) ----

def _stub_gh(monkeypatch, prs, rc=0):
    """Replace the `gh` runner: the pins below are about READING, not about GitHub."""
    calls = []

    def fake(args, token=None, timeout=60):
        calls.append(args)
        if rc != 0:
            return rc, "HTTP 502"
        return 0, json.dumps(prs)
    monkeypatch.setattr(d, "gh", fake)
    return calls


def test_a_lane_with_no_earlier_grain_cites_the_documented_exemption(monkeypatch):
    _stub_gh(monkeypatch, [])
    assert d.lane_predecessor("o/r", "myia-po-2028:claudish", None) == d.GRAIN_PREV_FIRST


def test_the_newest_matching_grain_is_the_predecessor(monkeypatch):
    _stub_gh(monkeypatch, [
        {"number": 26950, "body": "Grain: LIGHT/docs — lane myia-po-2028:claudish — prev: none"},
        {"number": 26920, "body": "Grain: DEEP/tooling — lane myia-po-2028:claudish"},
    ])
    assert d.lane_predecessor("o/r", "myia-po-2028:claudish", None) == "LIGHT/docs #26950"


def test_the_predecessor_is_the_highest_number_not_the_first_row(monkeypatch):
    """GitHub's search ordering is not creation order — measured 16/11 on CoursIA, where
    `#26790` came back ABOVE `#26806`. Reading the first row would cite an older grain."""
    _stub_gh(monkeypatch, [
        {"number": 26790, "body": "Grain: MED/notebook-python — lane myia-po-2028:claudish"},
        {"number": 26821, "body": "Grain: MED/notebook-python — lane myia-po-2028:claudish"},
    ])
    assert d.lane_predecessor("o/r", "myia-po-2028:claudish", None) == "MED/notebook-python #26821"


def test_a_sibling_lane_is_not_cited(monkeypatch):
    """The search is a substring match: `lane myia-po-2028:claudish` also returns
    `…:claudish-2`. Citing a sibling's grain would make the adjacency verdict meaningless."""
    _stub_gh(monkeypatch, [
        {"number": 26951, "body": "Grain: DEEP/docs — lane myia-po-2028:claudish-2"},
        {"number": 26949, "body": "Grain: MED/notebook-python — lane myia-po-2028:claudish"},
    ])
    assert d.lane_predecessor("o/r", "myia-po-2028:claudish", None) == "MED/notebook-python #26949"


def test_an_unreadable_history_says_so_instead_of_citing_a_first_grain(monkeypatch):
    _stub_gh(monkeypatch, [], rc=1)
    assert d.lane_predecessor("o/r", "myia-po-2028:claudish", None) is None


def test_a_tag_without_grain_is_not_a_predecessor(monkeypatch):
    _stub_gh(monkeypatch, [
        {"number": 26952, "body": "Fix something. Closes #26804"},
        {"number": 26940, "body": "Grain: MED/notebook-python — lane myia-po-2028:claudish"},
    ])
    assert d.lane_predecessor("o/r", "myia-po-2028:claudish", None) == "MED/notebook-python #26940"


def test_the_cited_pr_number_is_the_pull_request_not_an_issue(monkeypatch):
    """The wrong-pointer pin. The harness's OWN old tag ends `— issue #26804`; reading that
    line must yield the PR it lives in, never the issue it cites."""
    _stub_gh(monkeypatch, [
        {"number": 26943, "body": "Grain: LIGHT/docs — lane myia-po-2028:claudish — issue #26804"},
    ])
    assert d.lane_predecessor("o/r", "myia-po-2028:claudish", None) == "LIGHT/docs #26943"


def test_grain_tag_round_trips_through_the_coursia_parser():
    """Read by the CONSUMER, not by a copy of its grammar. Skipped where CoursIA is absent."""
    coursia = Path(r"D:\dev\CoursIA\scripts")
    if not (coursia / "grain_tag.py").is_file():
        pytest.skip("CoursIA checkout absent on this seat")
    sys.path.insert(0, str(coursia))
    import grain_tag as g  # noqa: E402

    parsed = g.parse_grain_tag(d.grain_tag("LIGHT", "myia-po-2028:claudish"))
    assert parsed["tier"] == "LIGHT"
    assert parsed["genre"] == "notebook-python"
    assert parsed["lane"] == "myia-po-2028:claudish"


def test_the_prev_field_round_trips_through_the_coursia_parser():
    """Both shapes reach the guard as what they claim: an exemption, and a citation."""
    coursia = Path(r"D:\dev\CoursIA\scripts")
    if not (coursia / "grain_tag.py").is_file():
        pytest.skip("CoursIA checkout absent on this seat")
    sys.path.insert(0, str(coursia))
    import grain_tag as g  # noqa: E402

    first = g.parse_prev(d.grain_tag("MED", "myia-po-2028:claudish"))
    assert first["exempt"] is True, "the documented exemption must not be labelled"

    cited = g.parse_prev(d.grain_tag("MED", "myia-po-2028:claudish",
                                     prev="LIGHT/docs #26943"))
    assert cited["present"] is True
    assert (cited["tier"], cited["genre"], cited["pr_number"]) == ("LIGHT", "docs", 26943)


# ---- sticky shared worktree (vllm#460: the previous run's branch must not ride along) ----
# Measured 16/11 on po-2028:claudish -- run --issue 26983 after run --issue 26972 (PR #26974
# still open) was born with TWO files, because stage 5 does `checkout -b` off the WORKTREE
# HEAD and the reused worktree still sat on the previous run's unmerged branch. These pins
# run against real throwaway git stacks (repo + local origin), not mocks: the bug lived in
# subprocess plumbing, and a mocked `git` would pin the mock, not the contract.

def _g(cwd, *args):
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    assert p.returncode == 0, f"git {' '.join(args)}: {p.stderr}"
    return p.stdout.strip()


@pytest.fixture()
def stack(tmp_path):
    """A repo whose `origin` is a local bare -- `origin/main` resolves, fetch is real."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)],
                   capture_output=True, check=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    _g(repo, "init", "-b", "main")
    _g(repo, "config", "user.email", "t@example.com")
    _g(repo, "config", "user.name", "t")
    (repo / "f.txt").write_text("base\n", encoding="utf-8")
    _g(repo, "add", ".")
    _g(repo, "commit", "-m", "base")
    _g(repo, "remote", "add", "origin", str(origin))
    _g(repo, "push", "-q", "origin", "main")
    _g(repo, "fetch", "origin", "main")
    return repo


def test_a_clean_worktree_at_origin_main_is_reused(stack, tmp_path):
    dest = tmp_path / "wt"
    d.prepare_worktree(stack, dest, fresh=False)          # builds at origin/main
    r2 = d.prepare_worktree(stack, dest, fresh=False)
    assert r2["reused"] is True and r2["ok"] is True


def test_the_previous_runs_open_branch_is_not_reused(stack, tmp_path):
    """THE #460 case: the shared worktree left on run N-1's branch (PR still open)
    must be rebuilt at origin/main, never reused as the birth base of run N."""
    dest = tmp_path / "wt"
    d.prepare_worktree(stack, dest, fresh=False)
    # run N-1: branch born off HEAD (= origin/main), one grain commit, PR stays open
    _g(dest, "checkout", "-b", "nbcoder/auto-26972")
    (dest / "stowaway.txt").write_text("run N-1 grain\n", encoding="utf-8")
    _g(dest, "add", ".")
    _g(dest, "commit", "-m", "run N-1 grain")
    r = d.prepare_worktree(stack, dest, fresh=False)
    assert r["reused"] is False, "a worktree on another branch was reused as-is"
    assert r["ok"] is True
    assert _g(dest, "rev-parse", "HEAD") == _g(stack, "rev-parse", "origin/main")
    # the branch itself survives -- only the scratch checkout was discarded
    assert _g(stack, "rev-parse", "--verify", "nbcoder/auto-26972")
    assert not (dest / "stowaway.txt").exists(), "the stowaway rode into the rebuilt tree"


def test_a_dirty_worktree_is_refused_not_discarded(stack, tmp_path):
    """Uncommitted changes are the one state the guard must NOT repair by itself:
    rebuilding would discard work nobody archived. Refused loud, tree untouched."""
    dest = tmp_path / "wt"
    d.prepare_worktree(stack, dest, fresh=False)
    (dest / "uncommitted.txt").write_text("in-flight\n", encoding="utf-8")
    r = d.prepare_worktree(stack, dest, fresh=False)
    assert r["ok"] is False and r["refused"] == "dirty"
    assert (dest / "uncommitted.txt").exists(), "the guard destroyed uncommitted work"
    assert "--fresh-worktree" in r["err"], "the refusal must name the exits"


def test_fresh_rebuilds_even_when_the_worktree_is_reusable(stack, tmp_path):
    dest = tmp_path / "wt"
    d.prepare_worktree(stack, dest, fresh=False)
    r = d.prepare_worktree(stack, dest, fresh=True)
    assert r["reused"] is False and r["ok"] is True


def test_a_stale_origin_main_base_is_rebuilt(stack, tmp_path):
    """Second condition of the incident: the worktree HEAD is an OLD origin/main
    (the --repo fetched since). Same verdict -- rebuild, don't reuse."""
    dest = tmp_path / "wt"
    d.prepare_worktree(stack, dest, fresh=False)
    (stack / "f.txt").write_text("main moved\n", encoding="utf-8")
    _g(stack, "add", ".")
    _g(stack, "commit", "-m", "main moved")
    _g(stack, "push", "-q", "origin", "main")
    r = d.prepare_worktree(stack, dest, fresh=False)
    assert r["reused"] is False and r["ok"] is True
    assert _g(dest, "rev-parse", "HEAD") == _g(stack, "rev-parse", "origin/main")


def test_the_main_flow_stops_on_a_refused_worktree():
    """Call-site pin (house pattern): `prepare_worktree` can refuse perfectly and
    still never be obeyed. Before #460 the `ok` key was recorded and ignored."""
    src = Path(d.__file__).read_text(encoding="utf-8")
    assert 'worktree-refused:' in src, "a refused worktree no longer stops the run"
    assert 'wt.get("ok", True)' in src, "the guard's verdict is no longer read"