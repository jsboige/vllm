"""Keep the suite hermetic: without a GitHub App the driver pins a gh account through real
`gh auth` calls (pinned_gh_token). No test may reach the machine's gh accounts."""
import pytest


@pytest.fixture(autouse=True)
def _no_real_gh_pin(monkeypatch):
    try:
        import nb_coder_driver as d
    except Exception:
        yield
        return
    d.GH_IDENTITY.clear()
    monkeypatch.setattr(d, "_gh_out", lambda argv, timeout=20, token=None: None)
    yield
    d.GH_IDENTITY.clear()
